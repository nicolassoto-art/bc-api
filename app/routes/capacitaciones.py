"""Compresión de videos de Capacitaciones.

El hosting donde vive Capacitaciones (Banahosting) no permite ejecutar programas, así que
comprimir ahí es imposible. Este VPS sí tiene ffmpeg. Pero el VPS es TALLER, no bodega:
recibe el video por pedazos, lo comprime hasta quedar bajo el tope, lo manda al hosting con
la subida por pedazos que ya existe en api.php, y BORRA todo — original y comprimido.
Nada de video se queda acá (decisión de Nicolás, 4-sep-2026: el disco iba en 87%).

Permisos: el mismo token de sesión de Herramientas. Se valida contra api.php (check-session,
isAdmin) y ese mismo token se usa después para subir el resultado al hosting: la compresión
tiene exactamente los permisos del administrador que la pidió, sin secretos nuevos.

Barandillas, que son lo importante:
- Un solo trabajo a la vez. Dos compresiones de archivos grandes llenan un disco al 87%.
- Espacio libre comprobado antes de aceptar (original + comprimido + margen).
- Si algo falla a mitad, se borra igual. Los restos de más de 6 h se barren solos.
- Pedazos chicos (900 KB): por debajo del tope por defecto de nginx (1 MB) sin depender
  de la configuración del servidor, que desde acá no se puede comprobar.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..settings import settings

router = APIRouter(prefix="/capacitaciones", tags=["capacitaciones"])

DIR_TRABAJOS = Path(os.environ.get("BC_COMPRIMIR_DIR", "/var/tmp/bc-comprimir"))
TOPE_MB = 200                      # lo que pidió el dueño
OBJETIVO_MB = 185                  # apuntar un poco abajo: el tamaño final nunca es exacto
PEDAZO_KB = 900
MARGEN_DISCO = 3 * 1024 ** 3       # 3 GB libres como piso, siempre
VIDA_MAX_SEG = 6 * 3600

# Estado en memoria del único trabajo permitido a la vez. Se respalda en disco (estado.json)
# para poder consultarlo aunque se reinicie el proceso: el corredor ve "error" y no un limbo.
_trabajos: Dict[str, Dict[str, Any]] = {}
_candado = asyncio.Lock()


# ── Permiso: administrador de Herramientas ───────────────────────────────────
# api.php tiene una copia vieja en /backend/ con OTRO almacén de sesiones, y la dirección
# configurada en el VPS puede apuntar ahí (le pasó al login de bc-api: rechazaba tokens
# válidos). Se prueba primero la raíz —la del login del sitio— y después la configurada.
# La que valide es la que se usa también para subir el resultado.
_API_CANDIDATAS = ["https://herramientas.bigcapital.cl/api.php", settings.legacy_api_url]
_api_valida: Dict[str, str] = {}   # token → url que lo reconoció


def _api_url_para(token: str) -> str:
    return _api_valida.get(token) or _API_CANDIDATAS[0]


async def admin_herramientas(authorization: Optional[str] = Header(None)) -> str:
    """Devuelve el token si corresponde a un administrador de Herramientas."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Falta la sesión")
    token = authorization.split(" ", 1)[1].strip()
    ultimo: Dict[str, Any] = {}
    for url in dict.fromkeys(u for u in _API_CANDIDATAS if u):
        try:
            async with httpx.AsyncClient(timeout=15) as cli:
                r = await cli.post(url, json={"action": "check-session"},
                                   headers={"Authorization": f"Bearer {token}"})
            datos = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except Exception:
            continue
        ultimo = datos or {}
        if ultimo.get("ok"):
            usuario = ultimo.get("user") or {}
            if not usuario.get("isAdmin"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Solo administradores")
            _api_valida[token] = url
            return token
    if not ultimo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo verificar la sesión con Herramientas")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")


# ── Utilidades ───────────────────────────────────────────────────────────────
def _dir(trabajo_id: str) -> Path:
    return DIR_TRABAJOS / trabajo_id


def _guardar_estado(trabajo_id: str) -> None:
    t = _trabajos.get(trabajo_id)
    if not t:
        return
    try:
        _dir(trabajo_id).mkdir(parents=True, exist_ok=True)
        (_dir(trabajo_id) / "estado.json").write_text(json.dumps(
            {k: v for k, v in t.items() if k != "token"}, ensure_ascii=False))
    except Exception:
        pass


def _leer_estado_disco(trabajo_id: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((_dir(trabajo_id) / "estado.json").read_text())
    except Exception:
        return None


def _barrer_viejos() -> None:
    """Restos de trabajos abandonados: nunca deben quedar ocupando disco."""
    try:
        DIR_TRABAJOS.mkdir(parents=True, exist_ok=True)
        ahora = time.time()
        for d in DIR_TRABAJOS.iterdir():
            if d.is_dir() and ahora - d.stat().st_mtime > VIDA_MAX_SEG:
                shutil.rmtree(d, ignore_errors=True)
                _trabajos.pop(d.name, None)
    except Exception:
        pass


def _limpiar(trabajo_id: str) -> None:
    shutil.rmtree(_dir(trabajo_id), ignore_errors=True)


def _hay_trabajo_activo() -> bool:
    return any(t.get("estado") in ("recibiendo", "comprimiendo", "subiendo") for t in _trabajos.values())


def _libre() -> int:
    try:
        return shutil.disk_usage(DIR_TRABAJOS if DIR_TRABAJOS.exists() else "/").free
    except Exception:
        return 0


# ── 1. Iniciar ───────────────────────────────────────────────────────────────
class Iniciar(BaseModel):
    nombre: str
    tamano: int
    mime: str = ""
    seccion_id: str
    carpeta_id: str = ""
    title: str = ""
    descripcion: str = ""


@router.post("/comprimir/iniciar")
async def iniciar(cuerpo: Iniciar, token: str = Depends(admin_herramientas)):
    _barrer_viejos()
    if cuerpo.tamano <= 0:
        raise HTTPException(400, "Tamaño inválido")
    if cuerpo.tamano > 6 * 1024 ** 3:
        raise HTTPException(413, "Más de 6 GB no se puede procesar acá")
    async with _candado:
        if _hay_trabajo_activo():
            raise HTTPException(409, "Ya hay un video comprimiéndose. Espera a que termine.")
        # Original + comprimido (≤ tope) + margen. Este disco es compartido con otros servicios.
        necesario = cuerpo.tamano + TOPE_MB * 1024 ** 2 + MARGEN_DISCO
        if _libre() < necesario:
            raise HTTPException(507, "No queda espacio en el servidor para comprimir ese video. Avísale a Nicolás.")
        trabajo_id = "cx_" + secrets.token_hex(10)
        _trabajos[trabajo_id] = {
            "id": trabajo_id, "estado": "recibiendo", "progreso": 0, "detalle": "",
            "nombre": cuerpo.nombre, "tamano": cuerpo.tamano, "mime": cuerpo.mime,
            "seccion_id": cuerpo.seccion_id, "carpeta_id": cuerpo.carpeta_id,
            "title": cuerpo.title, "descripcion": cuerpo.descripcion,
            "recibido": 0, "proximo": 0, "creado": int(time.time()), "token": token,
        }
        _dir(trabajo_id).mkdir(parents=True, exist_ok=True)
        (_dir(trabajo_id) / "original").touch()
        _guardar_estado(trabajo_id)
    return {"ok": True, "trabajo_id": trabajo_id, "pedazo_kb": PEDAZO_KB}


# ── 2. Pedazo ────────────────────────────────────────────────────────────────
@router.post("/comprimir/pedazo")
async def pedazo(
    trabajo_id: str = Form(...),
    indice: int = Form(...),
    pedazo: UploadFile = File(...),
    token: str = Depends(admin_herramientas),
):
    t = _trabajos.get(trabajo_id)
    if not t or not re.fullmatch(r"cx_[a-f0-9]{20}", trabajo_id):
        raise HTTPException(404, "El trabajo expiró o no existe")
    if t["estado"] != "recibiendo":
        raise HTTPException(409, "Ese trabajo ya no recibe pedazos")
    if indice != t["proximo"]:
        # Fuera de orden se rechaza: aceptarlo dejaría el archivo mezclado.
        return {"ok": False, "error": "Pedazo fuera de orden", "espera": t["proximo"]}
    datos = await pedazo.read()
    with open(_dir(trabajo_id) / "original", "ab") as fh:
        fh.write(datos)
    t["recibido"] += len(datos)
    t["proximo"] = indice + 1
    t["progreso"] = min(99, int(t["recibido"] * 100 / max(1, t["tamano"])))
    return {"ok": True, "recibido": t["recibido"], "proximo": t["proximo"]}


# ── 3. Terminar → comprimir en segundo plano ─────────────────────────────────
class Terminar(BaseModel):
    trabajo_id: str


@router.post("/comprimir/terminar")
async def terminar(cuerpo: Terminar, token: str = Depends(admin_herramientas)):
    t = _trabajos.get(cuerpo.trabajo_id)
    if not t:
        raise HTTPException(404, "El trabajo expiró o no existe")
    real = (_dir(t["id"]) / "original").stat().st_size
    if real != t["tamano"]:
        _limpiar(t["id"]); _trabajos.pop(t["id"], None)
        raise HTTPException(422, f"El archivo llegó incompleto ({real} de {t['tamano']} bytes). Vuelve a intentarlo.")
    t["estado"] = "comprimiendo"; t["progreso"] = 0; t["detalle"] = "Leyendo el video"
    _guardar_estado(t["id"])
    asyncio.create_task(_procesar(t["id"]))
    return {"ok": True, "estado": "comprimiendo"}


@router.get("/comprimir/estado/{trabajo_id}")
async def estado(trabajo_id: str):
    t = _trabajos.get(trabajo_id) or _leer_estado_disco(trabajo_id)
    if not t:
        raise HTTPException(404, "El trabajo expiró o no existe")
    return {k: v for k, v in t.items() if k != "token"}


# ── El trabajo de verdad ─────────────────────────────────────────────────────
async def _duracion(ruta: Path) -> float:
    p = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(ruta),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    salida, _ = await p.communicate()
    try:
        return max(0.0, float(salida.decode().strip()))
    except Exception:
        return 0.0


async def _comprimir(trabajo_id: str, origen: Path, destino: Path, duracion: float, factor: float) -> None:
    """Un pase de ffmpeg apuntando a OBJETIVO_MB · factor. Avanza el progreso leyendo out_time."""
    t = _trabajos[trabajo_id]
    # El objetivo NUNCA supera al original: comprimir es achicar. En la primera prueba
    # real, apuntar siempre a 185 MB convirtió un video de 5,4 MB en uno de 124,7 MB.
    # Se apunta al menor entre el tope y el 85% del original, y además se topa la calidad
    # (4.000 kbps a 720p ya es más de lo que cualquier capacitación necesita).
    tam_original = max(1, origen.stat().st_size)
    objetivo_bytes = min(OBJETIVO_MB * 1024 ** 2, int(tam_original * 0.85)) * factor
    objetivo_bits = objetivo_bytes * 8
    audio_k = 96
    video_k = int(objetivo_bits / max(1.0, duracion) / 1000) - audio_k
    video_k = max(250, min(4000, video_k))
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(origen),
        "-vf", "scale='min(1280,iw)':-2",          # 720p es más que suficiente para capacitación
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{video_k}k",
        "-maxrate", f"{int(video_k * 1.3)}k", "-bufsize", f"{video_k * 2}k",
        "-c:a", "aac", "-b:a", f"{audio_k}k", "-ac", "2",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(destino),
    ]
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    assert p.stdout
    while True:
        linea = await p.stdout.readline()
        if not linea:
            break
        s = linea.decode(errors="ignore").strip()
        if s.startswith("out_time_ms=") and duracion > 0:
            try:
                seg = int(s.split("=", 1)[1]) / 1_000_000
                t["progreso"] = min(99, int(seg * 100 / duracion))
                t["detalle"] = f"Comprimiendo · {t['progreso']}%"
            except Exception:
                pass
    _, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError((err or b"").decode(errors="ignore")[-300:] or "ffmpeg falló")


async def _subir_al_hosting(trabajo_id: str, ruta: Path) -> Dict[str, Any]:
    """Manda el comprimido a api.php con su propia subida por pedazos, con el token del usuario."""
    t = _trabajos[trabajo_id]
    cab = {"Authorization": f"Bearer {t['token']}"}
    nombre = re.sub(r"\.[^.]+$", "", t["nombre"]) + ".mp4"
    tam = ruta.stat().st_size
    async with httpx.AsyncClient(timeout=60) as cli:
        api_url = _api_url_para(t["token"])
        r = await cli.post(api_url, headers=cab, json={
            "action": "capacitaciones-subida-iniciar", "seccion_id": t["seccion_id"],
            "carpeta_id": t["carpeta_id"], "nombre": nombre, "tamano": tam, "mime": "video/mp4"})
        ini = r.json()
        if not ini.get("ok"):
            raise RuntimeError(ini.get("error") or "El hosting no aceptó la subida")
        ped = int(ini.get("pedazo_kb") or 1024) * 1024
        idx, enviado = 0, 0
        with open(ruta, "rb") as fh:
            while True:
                trozo = fh.read(ped)
                if not trozo:
                    break
                for intento in range(3):
                    r = await cli.post(api_url, headers=cab,
                                       data={"action": "capacitaciones-subida-pedazo",
                                             "subida_id": ini["subida_id"], "indice": str(idx)},
                                       files={"pedazo": ("p", trozo)})
                    if r.status_code == 200:
                        break
                    await asyncio.sleep(0.8 * (intento + 1))
                else:
                    raise RuntimeError(f"El hosting rechazó el pedazo {idx} ({r.status_code})")
                idx += 1; enviado += len(trozo)
                t["progreso"] = min(99, int(enviado * 100 / max(1, tam)))
                t["detalle"] = f"Subiendo al sitio · {t['progreso']}%"
                # Pausa corta: el hosting bloquea la IP entera si ve muchos pedidos seguidos.
                await asyncio.sleep(0.12)
        r = await cli.post(api_url, headers=cab, json={
            "action": "capacitaciones-subida-terminar", "subida_id": ini["subida_id"],
            "title": t["title"], "descripcion": t["descripcion"]})
        fin = r.json()
        if not fin.get("ok"):
            raise RuntimeError(fin.get("error") or "El hosting no pudo guardar el archivo")
        return fin.get("file") or {}


async def _procesar(trabajo_id: str) -> None:
    t = _trabajos[trabajo_id]
    origen = _dir(trabajo_id) / "original"
    destino = _dir(trabajo_id) / "comprimido.mp4"
    try:
        dur = await _duracion(origen)
        if dur <= 0:
            raise RuntimeError("No se pudo leer el video (¿archivo dañado o no es un video?)")
        factor = 1.0
        for _ in range(3):                       # si se pasa del tope, un segundo pase más apretado
            await _comprimir(trabajo_id, origen, destino, dur, factor)
            if destino.stat().st_size <= TOPE_MB * 1024 ** 2:
                break
            factor *= 0.8
        else:
            raise RuntimeError("No se logró dejarlo bajo los 200 MB")
        t["estado"] = "subiendo"; t["progreso"] = 0; t["detalle"] = "Subiendo al sitio"
        _guardar_estado(trabajo_id)
        archivo = await _subir_al_hosting(trabajo_id, destino)
        t.update({"estado": "listo", "progreso": 100, "detalle": "Listo",
                  "resultado_bytes": destino.stat().st_size, "file": archivo})
    except Exception as e:  # noqa: BLE001
        t.update({"estado": "error", "detalle": str(e)[:300]})
    finally:
        # Pase lo que pase, el video no se queda acá. Solo se conserva estado.json un rato
        # para que el corredor pueda leer el resultado.
        _guardar_estado(trabajo_id)
        for f in ("original", "comprimido.mp4"):
            try:
                (_dir(trabajo_id) / f).unlink()
            except Exception:
                pass
        t.pop("token", None)
