"""Capacitaciones: video con calidad automática, como YouTube (21-oct-2026).

Cada video de Capacitaciones ya se comprime a un MP4 de hasta 720p. Aquí, a partir de ese MP4, se
generan 3 calidades en HLS (720p, 480p y 360p) para que el reproductor se ajuste solo a la conexión
de quien mira, igual que el video del edificio (`video_proyecto`). El MP4 sigue existiendo y es el
respaldo: si un video no tiene HLS, o falla, se reproduce como siempre.

Dónde queda: `{UPLOAD_DIR}/capacitaciones/video/<token24>/` (master.m3u8, 720p/, 480p/, 360p/, poster.jpg).
El token es al azar; `{UPLOAD_DIR}/capacitaciones/mapa/<file_id>` guarda a qué token pertenece cada
archivo de Capacitaciones. `GET /capacitaciones/hls/{file_id}` lo entrega (solo quien conoce el id).
El Worker de Cloudflare sirve esos archivos con caché (ruta /video/capacitaciones/<token>/…).
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app.settings import settings
from app.routes import video_proyecto as vp

log = logging.getLogger("bc.cap_hls")
router = APIRouter(prefix="/capacitaciones", tags=["capacitaciones-hls"])

ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
ESCALERA = (720, 480, 360)


def _raiz() -> Path:
    return Path(settings.upload_dir) / "capacitaciones"


def _mapa(file_id: str) -> Path:
    return _raiz() / "mapa" / file_id


def token_de(file_id: str) -> Optional[str]:
    try:
        t = _mapa(file_id).read_text().strip()
        return t if TOKEN_RE.match(t) and (_raiz() / "video" / t / "master.m3u8").exists() else None
    except Exception:
        return None


def alturas_para(info: Dict[str, Any]) -> List[int]:
    """Calidades que se generan: solo las que no superan el lado corto del original (nunca se amplía).
    Vertical (alto > ancho): no se genera (el reproductor usa el MP4)."""
    if info["alto"] > info["ancho"] > 0:
        return []
    corto = info["alto"]
    ok = [h for h in ESCALERA if h <= corto + 8]
    return ok or ([corto - corto % 2] if corto >= 240 else [])


def generar(file_id: str, mp4: Path) -> Optional[str]:
    """Genera el HLS de `mp4` y lo deja registrado para `file_id`. Devuelve el token, o None si no
    se pudo (nunca lanza: es un extra, el MP4 sigue sirviendo)."""
    if not ID_RE.match(file_id or ""):
        return None
    try:
        existente = token_de(file_id)
        if existente:
            return existente
        info = vp._sondear(mp4)
        alturas = alturas_para(info)
        if not alturas:
            return None
        token = secrets.token_hex(12)
        final = _raiz() / "video" / token
        tmp = _raiz() / "video" / (token + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        for h in alturas:
            (tmp / f"{h}p").mkdir(parents=True, exist_ok=True)
        subprocess.run(vp._prefijo() + ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
                                        "-ss", f"{min(info['duracion'] * 0.1, 30):.2f}", "-i", str(mp4), "-frames:v", "1",
                                        "-vf", "scale=-2:480", "-q:v", "3", str(tmp / "poster.jpg")],
                       capture_output=True, timeout=300)
        cmd = vp._prefijo() + vp._comando_hls(mp4, tmp, info, alturas)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3 * 3600)
        if r.returncode != 0 or not (tmp / "master.m3u8").exists():
            log.warning("HLS de %s falló: %s", file_id, (r.stderr or "")[-300:])
            shutil.rmtree(tmp, ignore_errors=True)
            return None
        tmp.rename(final)
        _mapa(file_id).parent.mkdir(parents=True, exist_ok=True)
        _mapa(file_id).write_text(token)
        log.info("HLS de %s listo (%s, %s)", file_id, token, alturas)
        return token
    except Exception as e:  # noqa: BLE001 — es un extra
        log.warning("HLS de %s: %s", file_id, e)
        return None


async def generar_async(file_id: str, mp4: Path) -> Optional[str]:
    return await asyncio.to_thread(generar, file_id, mp4)


@router.get("/hls/{file_id}")
def hls_de(file_id: str):
    if not ID_RE.match(file_id):
        raise HTTPException(404, "No encontrado")
    t = token_de(file_id)
    if not t:
        raise HTTPException(404, "Sin versión adaptativa")
    base = f"/uploads/capacitaciones/video/{t}"
    return {"token": t, "hls": f"{base}/master.m3u8", "poster": f"{base}/poster.jpg"}
