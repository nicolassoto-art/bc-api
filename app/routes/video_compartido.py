"""Video del edificio · link para enviar al cliente (31-oct-2026).

El video vigente de un proyecto cambia de carpeta (token) cada vez que se reemplaza, pero el link que el asesor
manda al cliente NO debe cambiar. Por eso el link lleva un «código de compartir» que se DERIVA del id del proyecto
con una clave del servidor (HMAC): es estable para siempre, no se guarda en ninguna parte (sin base de datos nueva,
sin relleno, sin carreras entre procesos) y no se puede adivinar. Cambiar la clave los invalida todos de golpe.

  GET /video-compartido/{codigo}   anónimo, solo lectura: devuelve el nombre del proyecto y el video vigente
                                   (solo si ya terminó de procesarse). Cualquier código inválido o desconocido da el
                                   mismo 404, sin pistas.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Proyecto
from ..settings import settings

router = APIRouter(tags=["video-compartido"])

_SAL = b"bc-video-compartir-v1:"
CODIGO_RE = re.compile(r"^[0-9a-f]{16}$")
_TTL_MAPA_SEG = 300          # el mapa código → proyecto se rehace cada 5 min…
_MIN_REINTENTO_SEG = 30      # …o, ante un código desconocido, como mucho cada 30 s (un proyecto nuevo)
_lock = threading.Lock()
_mapa: Dict[str, str] = {}
_mapa_ts = 0.0


def _clave() -> bytes:
    return (getattr(settings, "video_compartir_secret", "") or settings.jwt_secret).encode("utf-8")


def codigo_compartir(pid: str) -> str:
    """Código estable de 16 hex para el link del video de un proyecto."""
    return hmac.new(_clave(), _SAL + str(pid).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def video_listo(p: Any) -> Optional[Dict[str, Any]]:
    """El video vigente del proyecto, solo si ya terminó de procesarse (estado «listo» y con token)."""
    v = (getattr(p, "extra", None) or {}).get("video_ubicacion")
    if not isinstance(v, dict) or v.get("estado") != "listo":
        return None
    if not re.fullmatch(r"[0-9a-f]{24}", str(v.get("token") or "")):
        return None
    return v


def _reconstruir_mapa() -> None:
    global _mapa, _mapa_ts
    db = SessionLocal()
    try:
        ids = [r[0] for r in db.execute(select(Proyecto.id)).all()]
    finally:
        db.close()
    _mapa = {codigo_compartir(i): i for i in ids}
    _mapa_ts = time.time()


def _proyecto_de(codigo: str) -> Optional[str]:
    with _lock:
        ahora = time.time()
        if not _mapa or ahora - _mapa_ts > _TTL_MAPA_SEG:
            _reconstruir_mapa()
        pid = _mapa.get(codigo)
        if pid is None and ahora - _mapa_ts > _MIN_REINTENTO_SEG:
            _reconstruir_mapa()               # quizá es un proyecto creado hace poco
            pid = _mapa.get(codigo)
        return pid


@router.get("/video-compartido/{codigo}")
def ver(codigo: str, response: Response):
    response.headers["Cache-Control"] = "public, max-age=30"
    if not CODIGO_RE.match(codigo):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No encontrado")
    pid = _proyecto_de(codigo)
    if not pid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No encontrado")
    db = SessionLocal()
    try:
        p = db.get(Proyecto, pid)
        if not p:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No encontrado")
        v = video_listo(p)
        base = {"proyecto": p.nombre or "", "proyecto_id": pid}
        if not v:
            return {**base, "estado": "sin_video"}
        return {**base, "estado": "listo", "token": v["token"], "poster": bool(v.get("poster")),
                "duracion": v.get("duracion"), "calidades": v.get("calidades")}
    finally:
        db.close()
