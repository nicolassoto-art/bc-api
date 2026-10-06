"""Compresión de videos de Capacitaciones.

El VPS es TALLER, no bodega: recibe el video por pedazos, lo comprime, lo entrega a la subida
por pedazos de api.php (Herramientas) y BORRA el original y el comprimido. Nada de video se
queda acá (decisión de Nicolás, 4-sep-2026).

Permisos: el mismo token de sesión de Herramientas. Se valida contra api.php (check-session,
isAdmin) y ese mismo token se usa después para entregar el resultado: la compresión tiene
exactamente los permisos del administrador que la pidió, sin secretos nuevos.

05-oct-2026 · archivos de hasta 2 GB (pedido de Nicolás). Lo que cambió y por qué:
- Topes: entrada y salida de hasta 2 GB. Antes el resultado tenía que quedar bajo 200 MB, así
  que todo video de más de ~75 minutos fallaba y uno largo quedaba borroso. Ahora apunta al
  menor entre 1,9 GB y el 85 % del original, en 720p con video de hasta 2.000 kbps.
- Si el video ya viene liviano (H.264/AAC, 1080p o menos, bajo el tope de kbps) solo se
  reacomoda para que empiece a verse al tiro (-c copy +faststart): segundos, sin pérdida.
- Estado EN DISCO (estado.json por trabajo, candados fcntl). bc-api corre con 2 procesos
  (uvicorn --workers 2) y antes el trabajo vivía en la memoria de uno: un pedazo que caía en
  el otro respondía "no existe". Además cada despliegue reinicia el servicio: antes mataba la
  compresión y borraba el original; ahora un vigía (cada minuto, en cada proceso) retoma solo
  los trabajos que quedaron a medias, y un apagado no borra nada.
- Cola: uno comprimiendo y uno esperando (el disco se comparte). Un tercero recibe 409 y la
  página reintenta sola. ffmpeg corre con prioridad baja (nice/ionice) y la mitad de los núcleos,
  para no frenar el resto del servidor.
- Pedazos "crudos" de 8 MB con ?desde=N (se agregan con candado solo si calzan: repetir uno no
  daña nada). Sigue aceptando el multipart de 900 KB de antes, para páginas en caché.
- El resultado se entrega a api.php por la red local (127.0.0.1:8080, sin salir a Cloudflare),
  en modo crudo si api.php lo anuncia, y retoma donde quedó si se cortó.
- Si un trabajo falla del todo, se avisa por correo a quien lo subió (con copia a Nicolás).
  Si sale bien, silencio.

05-oct-2026 · lo que encontró la revisión de código (antes de publicar):
- Un despliegue a mitad de una compresión: systemd manda SIGTERM a todo el servicio (ffmpeg
  incluido) y ffmpeg sale con 255 antes de que bc-api alcance a apagarse. Eso se tomaba como
  "ffmpeg falló": se borraba el original y se mandaba un correo de falla falso. Ahora una
  salida por señal es un corte (se conserva todo y se retoma solo), con un tope de cortes
  seguidos para que un video que siempre mata a ffmpeg (falta de memoria) termine avisando.
- ffmpeg se podía colgar para siempre: nadie leía sus mensajes de error hasta que terminaba y,
  con un video dañado, el tubo se llenaba y ffmpeg quedaba esperando. Ahora se leen mientras
  corre, y si pasan 15 minutos sin avanzar se corta y se avisa.
- Entregar al sitio: un 502 o una respuesta perdida (recarga de php-fpm, despliegue del sitio)
  mataba el trabajo, y retomar podía duplicar el video. Ahora cada llamada se reintenta, si el
  sitio sigue sin responder se guarda todo y se reintenta en unos minutos, y solo se abre una
  subida nueva cuando el sitio confirma que la anterior no existe.
- Calidad pareja (CRF) con techo de kbps: un video simple pesa menos y uno complejo no pasa del
  techo, en un solo pase. Si el original ya se ve en cualquier navegador y comprimirlo no lo
  achica, se entrega el original reacomodado.
- Videos de ancho impar o verticales: medidas pares y 720p en el lado corto.
- Videos grabados en el navegador (WebM sin duración en la cabecera) ya no fallan como
  "no es un video".
- El correo de falla sale sin bloquear al resto (en un hilo) y con el certificado verificado.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import re
import secrets
import shutil
import signal
import smtplib
import ssl
import subprocess
import time
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from ..settings import settings

log = logging.getLogger("bc-api.capacitaciones")
router = APIRouter(prefix="/capacitaciones", tags=["capacitaciones"])

DIR_TRABAJOS = Path(os.environ.get("BC_COMPRIMIR_DIR", "/var/tmp/bc-comprimir"))
TOPE_BYTES = 2 * 1024 ** 3                    # entrada y salida (Nicolás, 05-oct-2026)
OBJETIVO_BYTES = int(1.9 * 1024 ** 3)         # un poco abajo del tope: el tamaño final nunca es exacto
VIDEO_KBPS_MAX = 2000                         # 720p: de sobra para una capacitación
VIDEO_KBPS_MIN = 250
AUDIO_KBPS = 96
CRF = "23"                                    # calidad pareja; el techo de kbps la limita
PEDAZO_VIEJO_KB = 900                         # multipart de antes (páginas en caché)
PEDAZO_CRUDO = 8 * 1024 * 1024                # crudo: ?desde=N
MARGEN_DISCO = 3 * 1024 ** 3                  # 3 GB libres como piso, siempre
VIDA_MAX_SEG = 6 * 3600                       # recibiendo sin pedazos por 6 h: se barre
QUIETO_SEG = 30 * 60                          # recibiendo sin pedazos por 30 min: no ocupa lugar en la cola
VIDA_TERMINADO_SEG = 6 * 3600                 # listo o error: el estado se puede leer 6 h
MAX_ACTIVOS = 2                               # uno comprimiendo y uno esperando
PROCESO = ("en_cola", "comprimiendo", "subiendo")
ID_RE = re.compile(r"cx_[a-f0-9]{20}")
SIN_AVANCE_SEG = 15 * 60                      # ffmpeg 15 min sin avanzar: está colgado
CORTES_MAX = 8                                # reinicios del servicio que aguanta un trabajo antes de rendirse
MATADOS_MAX = 2                               # el sistema mató a ffmpeg (casi siempre falta de memoria)
ENTREGAS_MAX = 6                              # vueltas del vigía para entregar al sitio, si no responde
# Se pueden acortar por variable de entorno (las pruebas locales no esperan minutos).
VIGIA_SEG = int(os.environ.get("BC_COMPRIMIR_VIGIA_SEG", "60"))
ESPERA_RETOMAR_SEG = int(os.environ.get("BC_COMPRIMIR_ESPERA_RETOMAR", "90"))     # tras un corte
ESPERA_ENTREGA_SEG = int(os.environ.get("BC_COMPRIMIR_ESPERA_ENTREGA", "300"))    # tras un sitio que no responde
PAUSA_REINTENTO = float(os.environ.get("BC_COMPRIMIR_PAUSA_REINTENTO", "1"))      # escala de las esperas entre reintentos
# 720p sin agrandar: cabe en 1280×720 (720×1280 si es vertical), sin deformar y con medidas pares
# (libx264 rechaza un ancho impar: un WebM de 853×479 fallaba con "Nothing was written").
ESCALA = ("scale=w='if(gte(iw,ih),min(1280,iw),min(720,iw))':h='if(gte(iw,ih),min(720,ih),min(1280,ih))'"
          ":force_original_aspect_ratio=decrease:force_divisible_by=2")

# api.php tiene una copia vieja en /backend/ con OTRO almacén de sesiones: se prueba primero la
# raíz —la del ingreso al sitio— y después la configurada. La que valide es la que se usa.
_API_CANDIDATAS = [os.environ.get("BC_HERRAMIENTAS_API", "https://herramientas.bigcapital.cl/api.php"),
                   settings.legacy_api_url]
# Para entregar el resultado: la misma máquina, sin pasar por Cloudflare.
_API_LOCAL = os.environ.get("BC_HERRAMIENTAS_LOCAL", "http://127.0.0.1:8080/api.php")
_api_valida: Dict[str, str] = {}   # token → url que lo reconoció
_correo_de: Dict[str, str] = {}    # token → correo del administrador
_valido_hasta: Dict[str, float] = {}  # token → hasta cuándo no hace falta volver a preguntarle a api.php
VALIDEZ_SEG = 60                   # un video de 2 GB son ~256 pedazos: no preguntar 256 veces
_tareas: set = set()               # referencias a las tareas en curso (si no, se las puede llevar el recolector)


class Interrumpido(Exception):
    """ffmpeg o ffprobe terminaron por una señal: un reinicio del servicio (SIGTERM) o el sistema
    (SIGKILL, casi siempre falta de memoria). No es culpa del video: se conserva todo."""

    def __init__(self, tipo: str, codigo: int):
        super().__init__(f"interrumpido ({tipo}, código {codigo})")
        self.tipo = tipo


class EntregaPendiente(Exception):
    """El sitio no respondió bien al entregar (caído, recargando, red): se conserva el comprimido
    y el vigía vuelve a intentarlo en unos minutos."""


class FallaFfmpeg(RuntimeError):
    """ffmpeg terminó con error por el video en sí (dañado o en un formato que no reconoce)."""


def _por_senal(codigo: Optional[int]) -> Optional[str]:
    """255: ffmpeg recibió SIGTERM/SIGINT y salió ordenado. Negativo: lo mató esa señal."""
    if codigo is None:
        return None
    if codigo == 255 or codigo in (-signal.SIGTERM, -signal.SIGINT, -signal.SIGHUP):
        return "corte"
    if codigo < 0:
        return "matado"
    return None


def _api_url_para(token: str) -> str:
    return _api_valida.get(token) or _API_CANDIDATAS[0]


async def admin_herramientas(authorization: Optional[str] = Header(None)) -> str:
    """Devuelve el token si corresponde a un administrador de Herramientas."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Falta la sesión")
    token = authorization.split(" ", 1)[1].strip()
    if _valido_hasta.get(token, 0) > time.time() and token in _correo_de:
        return token
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
            _correo_de[token] = str(usuario.get("email") or "").strip().lower()
            _valido_hasta[token] = time.time() + VALIDEZ_SEG
            return token
    if not ultimo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo verificar la sesión con Herramientas")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")


# ── Estado en disco ──────────────────────────────────────────────────────────────────
def _dir(tid: str) -> Path:
    return DIR_TRABAJOS / tid


@contextlib.contextmanager
def _candado(ruta: Path):
    fd = os.open(ruta, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _leer(tid: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((_dir(tid) / "estado.json").read_text())
    except Exception:
        return None


def _escribir(tid: str, t: Dict[str, Any]) -> None:
    d = _dir(tid)
    tmp = d / f"estado.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps({k: v for k, v in t.items() if k != "token"}, ensure_ascii=False))
    os.replace(tmp, d / "estado.json")


def _actualizar(tid: str, **cambios: Any) -> Optional[Dict[str, Any]]:
    d = _dir(tid)
    if not d.is_dir():
        return None
    try:
        with _candado(d / ".candado"):
            t = _leer(tid)
            if t is None:
                return None
            t.update(cambios)
            t["actualizado"] = int(time.time())
            _escribir(tid, t)
            return t
    except FileNotFoundError:        # se canceló o se barrió mientras tanto
        return None


def _token(tid: str) -> str:
    try:
        return (_dir(tid) / "token").read_text().strip()
    except Exception:
        return ""


def _guardar_token(tid: str, token: str) -> None:
    fd = os.open(_dir(tid) / "token", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode())
    finally:
        os.close(fd)


def _recibido(tid: str) -> int:
    try:
        return (_dir(tid) / "original").stat().st_size
    except Exception:
        return 0


def _todos() -> List[Dict[str, Any]]:
    out = []
    try:
        for d in DIR_TRABAJOS.iterdir():
            if d.is_dir() and ID_RE.fullmatch(d.name):
                t = _leer(d.name)
                if t:
                    out.append(t)
    except FileNotFoundError:
        pass
    return out


def _ultimo_movimiento(t: Dict[str, Any]) -> float:
    d = _dir(t["id"])
    marcas = [t.get("actualizado") or 0, t.get("creado") or 0]
    for f in ("original", "estado.json"):
        try:
            marcas.append((d / f).stat().st_mtime)
        except Exception:
            pass
    return max(marcas)


def _borrar_archivos(tid: str) -> None:
    d = _dir(tid)
    for f in ["original", "comprimido.mp4", "token", *[p.name for p in d.glob("comprimido.*.mp4")]]:
        with contextlib.suppress(Exception):
            (d / f).unlink()


def _barrer_viejos() -> None:
    """Restos de trabajos abandonados o terminados: nunca deben quedar ocupando disco."""
    ahora = time.time()
    for t in _todos():
        quieto = ahora - _ultimo_movimiento(t)
        if (t.get("estado") == "recibiendo" and quieto > VIDA_MAX_SEG) or \
           (t.get("estado") in ("listo", "error") and quieto > VIDA_TERMINADO_SEG):
            shutil.rmtree(_dir(t["id"]), ignore_errors=True)
    # Una carpeta sin estado legible (se cortó justo al crearla) tampoco se queda para siempre.
    with contextlib.suppress(FileNotFoundError):
        for d in DIR_TRABAJOS.iterdir():
            if d.is_dir() and ID_RE.fullmatch(d.name) and _leer(d.name) is None:
                with contextlib.suppress(Exception):
                    if ahora - d.stat().st_mtime > VIDA_MAX_SEG:
                        shutil.rmtree(d, ignore_errors=True)


def _mantener_vivos() -> None:
    """/var/tmp se limpia sola: lo que no se toca en 30 días se borra (systemd-tmpfiles). Los
    candados nunca cambian, así que se tocan cada minuto para que no desaparezcan en uso."""
    for p in (DIR_TRABAJOS, DIR_TRABAJOS / ".ffmpeg.lock", DIR_TRABAJOS / ".candado"):
        with contextlib.suppress(Exception):
            os.utime(p)


def _libre() -> int:
    try:
        return shutil.disk_usage(DIR_TRABAJOS if DIR_TRABAJOS.exists() else "/").free
    except Exception:
        return 0


def _duena(t: Dict[str, Any], token: str) -> bool:
    por = (t.get("por") or "").lower()
    return not por or por == _correo_de.get(token, "")


_PRIVADO = {"token", "por", "subida_api", "subida_pedazo", "cortes", "matados", "entregas", "retomar_desde"}


def _publico(t: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que ve la página (sin sesión): ni el correo de quien subió ni datos internos."""
    out = {k: v for k, v in t.items() if k not in _PRIVADO}
    if isinstance(out.get("file"), dict):
        out["file"] = {k: v for k, v in out["file"].items() if k != "subido_por"}
    if t.get("estado") == "recibiendo":
        out["recibido"] = _recibido(t["id"])
        out["progreso"] = min(99, int(out["recibido"] * 100 / max(1, int(t.get("tamano") or 1))))
    return out


# ── 1. Iniciar ───────────────────────────────────────────────────────────────────────
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
    if cuerpo.tamano <= 0:
        raise HTTPException(400, "Tamaño inválido")
    if cuerpo.tamano > TOPE_BYTES:
        raise HTTPException(413, "El video pasa del máximo de 2 GB.")
    DIR_TRABAJOS.mkdir(parents=True, exist_ok=True)
    _barrer_viejos()
    with _candado(DIR_TRABAJOS / ".candado"):
        ahora = time.time()
        vivos = [t for t in _todos() if t.get("estado") in PROCESO or t.get("estado") == "recibiendo"]
        ocupan = [t for t in vivos if t.get("estado") in PROCESO or ahora - _ultimo_movimiento(t) < QUIETO_SEG]
        if len(ocupan) >= MAX_ACTIVOS:
            raise HTTPException(409, "Ya hay videos comprimiéndose. Este empieza solo apenas haya lugar.")
        # Lo que todavía puede ocupar disco cada trabajo en curso: lo que falta por llegar + su
        # comprimido. Una subida abandonada (30 min sin pedazos) no reserva nada: lo que ya llegó
        # está en el disco y se descuenta solo del espacio libre (lo mismo hace api.php).
        reservado = sum(max(0, int(t["tamano"]) - _recibido(t["id"])) + min(int(t["tamano"]), TOPE_BYTES) for t in ocupan)
        necesario = cuerpo.tamano + min(cuerpo.tamano, TOPE_BYTES) + MARGEN_DISCO + reservado
        if _libre() < necesario:
            raise HTTPException(507, "No queda espacio en el servidor para comprimir ese video. Avísale a Nicolás.")
        tid = "cx_" + secrets.token_hex(10)
        d = _dir(tid)
        d.mkdir(parents=True)
        (d / "original").touch()
        _guardar_token(tid, token)
        _escribir(tid, {
            "id": tid, "estado": "recibiendo", "progreso": 0, "detalle": "",
            "nombre": cuerpo.nombre, "tamano": cuerpo.tamano, "mime": cuerpo.mime,
            "seccion_id": cuerpo.seccion_id, "carpeta_id": cuerpo.carpeta_id,
            "title": cuerpo.title, "descripcion": cuerpo.descripcion,
            "por": _correo_de.get(token, ""), "creado": int(ahora), "actualizado": int(ahora),
        })
    return {"ok": True, "trabajo_id": tid, "pedazo_kb": PEDAZO_VIEJO_KB,
            "crudo": True, "pedazo_bytes": PEDAZO_CRUDO, "max_bytes": TOPE_BYTES}


# ── 2. Pedazos ───────────────────────────────────────────────────────────────────────
def _trabajo_que_recibe(tid: str, token: str) -> Dict[str, Any]:
    if not ID_RE.fullmatch(tid or ""):
        raise HTTPException(404, "El trabajo expiró o no existe")
    t = _leer(tid)
    if not t:
        raise HTTPException(404, "El trabajo expiró o no existe")
    if not _duena(t, token):
        raise HTTPException(403, "Este trabajo es de otra persona")
    return t


# 422 y no 409: la página nueva reintenta un 409 (cola llena) y este error es definitivo.
_YA_FALLO = "Este video ya terminó con error. Vuelve a subirlo."


def _agregar(tid: str, desde: int, datos: bytes) -> Dict[str, Any]:
    """Agrega el pedazo solo si calza con lo que ya llegó (con candado): repetirlo no daña nada."""
    with open(_dir(tid) / "original", "r+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            actual = os.fstat(fh.fileno()).st_size
            if desde > actual:
                return {"ok": False, "recibido": actual, "motivo": "hueco"}
            saltar = actual - desde
            if saltar >= len(datos):
                return {"ok": True, "recibido": actual, "repetido": True}
            fh.seek(0, os.SEEK_END)
            fh.write(datos[saltar:])
            fh.flush()
            return {"ok": True, "recibido": os.fstat(fh.fileno()).st_size}
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@router.post("/comprimir/pedazo")
async def pedazo(
    trabajo_id: str = Form(...),
    indice: int = Form(...),
    pedazo: UploadFile = File(...),
    token: str = Depends(admin_herramientas),
):
    """El de antes: multipart de 900 KB con su número de pedazo (páginas en caché)."""
    t = _trabajo_que_recibe(trabajo_id, token)
    ped = PEDAZO_VIEJO_KB * 1024
    if t["estado"] != "recibiendo":
        if t["estado"] in PROCESO or t["estado"] == "listo":
            return {"ok": True, "recibido": int(t["tamano"]), "proximo": (int(t["tamano"]) + ped - 1) // ped}
        raise HTTPException(422, _YA_FALLO)
    datos = await pedazo.read()
    if indice < 0 or indice * ped + len(datos) > int(t["tamano"]):
        raise HTTPException(400, "El pedazo no calza con el tamaño del video")
    r = _agregar(trabajo_id, indice * ped, datos)
    if not r["ok"]:
        return {"ok": False, "error": "Pedazo fuera de orden", "espera": r["recibido"] // ped}
    return {"ok": True, "recibido": r["recibido"], "proximo": (r["recibido"] + ped - 1) // ped}


@router.post("/comprimir/pedazo-crudo")
async def pedazo_crudo(request: Request, trabajo_id: str, desde: int, token: str = Depends(admin_herramientas)):
    """El nuevo: el cuerpo es el pedazo (hasta 8 MB) y ?desde=N dice dónde va."""
    t = _trabajo_que_recibe(trabajo_id, token)
    if t["estado"] != "recibiendo":
        if t["estado"] in PROCESO or t["estado"] == "listo":
            return {"ok": True, "recibido": int(t["tamano"]), "terminado": True}
        raise HTTPException(422, _YA_FALLO)
    datos = await request.body()
    if not datos or len(datos) > PEDAZO_CRUDO:
        raise HTTPException(400, f"Pedazo inválido ({len(datos)} bytes)")
    if desde < 0 or desde + len(datos) > int(t["tamano"]):
        raise HTTPException(400, "El pedazo no calza con el tamaño del video")
    return _agregar(trabajo_id, desde, datos)


# ── 3. Terminar → a la cola ──────────────────────────────────────────────────────────
class Terminar(BaseModel):
    trabajo_id: str


@router.post("/comprimir/terminar")
async def terminar(cuerpo: Terminar, token: str = Depends(admin_herramientas)):
    tid = cuerpo.trabajo_id
    t = _trabajo_que_recibe(tid, token)
    if t["estado"] in PROCESO or t["estado"] == "listo":
        return {"ok": True, "estado": t["estado"]}            # repetido: ya está en camino
    if t["estado"] != "recibiendo":
        raise HTTPException(422, _YA_FALLO)
    real = _recibido(tid)
    if real > int(t["tamano"]):
        shutil.rmtree(_dir(tid), ignore_errors=True)
        raise HTTPException(422, f"El video llegó con bytes de más ({real} de {t['tamano']}). Vuelve a subirlo.")
    if real < int(t["tamano"]):
        # No se borra: se puede seguir desde donde quedó.
        raise HTTPException(422, f"El video llegó incompleto ({real} de {t['tamano']} bytes). Vuelve a intentarlo.")
    if not _token(tid):
        # Trabajo empezado por la versión anterior, que guardaba la sesión solo en memoria: sin
        # esto se comprimía entero y fallaba al entregar ("se perdió la sesión").
        _guardar_token(tid, token)
    _actualizar(tid, estado="en_cola", progreso=0, detalle="En cola para comprimir")
    _lanzar(tid)
    return {"ok": True, "estado": "en_cola"}


class Cancelar(BaseModel):
    trabajo_id: str


@router.post("/comprimir/cancelar")
async def cancelar(cuerpo: Cancelar, token: str = Depends(admin_herramientas)):
    """Quien sube canceló: se borra lo que llegó. Si ya terminó de llegar, sigue su camino."""
    tid = cuerpo.trabajo_id
    _trabajo_que_recibe(tid, token)
    # Con el candado del trabajo y volviendo a leer: un "terminar" que llegó al otro proceso en
    # el mismo instante no puede quedar con su carpeta borrada a medio camino.
    try:
        with _candado(_dir(tid) / ".candado"):
            t = _leer(tid) or {}
            if t.get("estado") != "recibiendo":
                return {"ok": True, "estado": t.get("estado")}
            shutil.rmtree(_dir(tid), ignore_errors=True)
    except FileNotFoundError:
        pass
    return {"ok": True}


@router.get("/comprimir/estado/{trabajo_id}")
async def estado(trabajo_id: str):
    t = _leer(trabajo_id) if ID_RE.fullmatch(trabajo_id or "") else None
    if not t:
        raise HTTPException(404, "El trabajo expiró o no existe")
    return _publico(t)


# ── El trabajo de verdad ─────────────────────────────────────────────────────────────
def _lanzar(tid: str) -> None:
    tarea = asyncio.create_task(_procesar(tid))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)


_MUERE_CON_PADRE: Optional[bool] = None


def _prefijo(baja_prioridad: bool = True) -> List[str]:
    """setpriv --pdeathsig: si el proceso de bc-api muere de golpe, su ffmpeg muere con él (si no,
    quedaba huérfano y el vigía del proceso nuevo lanzaba un segundo ffmpeg sobre el mismo
    trabajo). nice/ionice: prioridad baja, para no frenar el resto del servidor."""
    global _MUERE_CON_PADRE
    if _MUERE_CON_PADRE is None:
        _MUERE_CON_PADRE = False
        if shutil.which("setpriv"):
            with contextlib.suppress(Exception):
                _MUERE_CON_PADRE = subprocess.run(["setpriv", "--pdeathsig", "KILL", "--", "true"],
                                                  capture_output=True, timeout=5).returncode == 0
    pre = ["setpriv", "--pdeathsig", "KILL", "--"] if _MUERE_CON_PADRE else []
    if baja_prioridad:
        if shutil.which("nice"):
            pre += ["nice", "-n", "19"]
        if shutil.which("ionice"):
            pre += ["ionice", "-c", "3"]
    return pre


async def _sondear(ruta: Path) -> Dict[str, Any]:
    p = await asyncio.create_subprocess_exec(
        *_prefijo(), "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(ruta),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        salida, _ = await p.communicate()
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            p.kill()
        raise
    tipo = _por_senal(p.returncode)
    if tipo:                          # un reinicio, no un video dañado
        raise Interrumpido(tipo, p.returncode)
    try:
        return json.loads(salida.decode() or "{}")
    except Exception:
        return {}


def _videos(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pistas de video de verdad (una carátula o miniatura incrustada no cuenta)."""
    return [s for s in info.get("streams", []) if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")]


def _audios(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]


def _duracion(info: Dict[str, Any]) -> float:
    """La del archivo; si no la trae (un WebM grabado en el navegador), la de sus pistas; 0 si nada."""
    candidatas = [(info.get("format") or {}).get("duration")] + \
                 [s.get("duration") for s in _videos(info) + _audios(info)]
    for c in candidatas:
        try:
            v = float(c)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return 0.0


def _reproducible(info: Dict[str, Any]) -> bool:
    """¿Se ve tal cual en cualquier navegador? H.264 de 8 bits y audio AAC/MP3 (o sin audio)."""
    videos, audios = _videos(info), _audios(info)
    if not videos:
        return False
    v = videos[0]
    if v.get("codec_name") != "h264" or v.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        return False
    return not audios or audios[0].get("codec_name") in ("aac", "mp3")


def _sirve_tal_cual(info: Dict[str, Any], tam: int) -> bool:
    """¿Se puede entregar sin recomprimir? Reproducible, ≤1080p (horizontal o vertical) y bajo el
    tope de kbps. Entonces basta reacomodarlo (+faststart) para que empiece al tiro."""
    dur = _duracion(info)
    if tam > TOPE_BYTES or dur <= 0 or not _reproducible(info):
        return False
    v = _videos(info)[0]
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if max(w, h) > 1920 or min(w, h) > 1080:
        return False
    kbps = tam * 8 / dur / 1000
    return kbps <= VIDEO_KBPS_MAX + AUDIO_KBPS + 200


async def _ffmpeg(tid: str, args: List[str], duracion: float, etiqueta: str) -> None:
    cmd = _prefijo() + ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin"] + args
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    assert p.stdout and p.stderr
    errores = bytearray()

    async def _vaciar_errores() -> None:
        # Se leen MIENTRAS corre: si nadie lee, el tubo se llena (~64 KB; un video dañado escribe
        # cientos de KB de avisos) y ffmpeg queda esperando para siempre. Se guarda solo la cola.
        while True:
            b = await p.stderr.read(65536)
            if not b:
                return
            errores.extend(b)
            if len(errores) > 16384:
                del errores[:-8192]

    lector = asyncio.create_task(_vaciar_errores())
    resto, mayor, ultimo_aviso, ultimo_avance = b"", -1, 0.0, time.monotonic()
    try:
        while True:
            try:
                b = await asyncio.wait_for(p.stdout.read(65536), timeout=30)
            except asyncio.TimeoutError:
                b = None
            if b == b"":
                break
            if b:
                resto += b
                *lineas, resto = resto.split(b"\n")
                for linea in lineas:
                    s = linea.decode(errors="ignore").strip()
                    if s.startswith("out_time_us=") or s.startswith("out_time_ms="):   # ambos en µs
                        with contextlib.suppress(ValueError):
                            us = int(s.split("=", 1)[1])
                            if us > mayor:
                                mayor, ultimo_avance = us, time.monotonic()
                if mayor >= 0 and time.time() - ultimo_aviso > 2:
                    seg = mayor / 1_000_000
                    if duracion > 0:
                        pct = min(99, int(seg * 100 / duracion))
                        _actualizar(tid, progreso=pct, detalle=f"{etiqueta} · {pct}%")
                    else:
                        _actualizar(tid, detalle=f"{etiqueta} · {int(seg // 60)} min de video listos")
                    ultimo_aviso = time.time()
            if time.monotonic() - ultimo_avance > SIN_AVANCE_SEG:
                with contextlib.suppress(Exception):
                    p.kill()
                await p.wait()
                raise FallaFfmpeg(f"{etiqueta}: pasaron {SIN_AVANCE_SEG // 60} minutos sin avanzar "
                                  "(el video puede estar dañado)")
        codigo = await p.wait()
        await lector
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            p.kill()
        raise
    finally:
        if not lector.done():
            lector.cancel()
    tipo = _por_senal(codigo)
    if tipo:
        raise Interrumpido(tipo, codigo)
    if codigo != 0:
        cola = bytes(errores).decode(errors="ignore").strip().splitlines()[-3:]
        log.warning("ffmpeg %s (%s) salió con %s: %s", tid, etiqueta, codigo, " | ".join(cola))
        raise FallaFfmpeg("No se pudo convertir el video (puede estar dañado o en un formato que el servidor no reconoce)")


async def _preparar(tid: str, origen: Path, destino: Path) -> None:
    info = await _sondear(origen)
    if not _videos(info):
        raise RuntimeError("No se pudo leer el video (¿archivo dañado o no es un video?)")
    dur = _duracion(info)                    # 0 = no se sabe (se comprime igual, sin %)
    tam = origen.stat().st_size
    d = destino.parent
    for viejo in d.glob("comprimido.*.mp4"):  # restos de un intento cortado
        with contextlib.suppress(Exception):
            viejo.unlink()

    def temporal() -> Path:
        # Cada intento escribe en su propio archivo y se renombra al final: nada a medias llega a
        # entregarse aunque un intento anterior siga escribiendo.
        return d / f"comprimido.{os.getpid()}.{secrets.token_hex(3)}.mp4"

    mapa = ["-map", "0:V:0", "-map", "0:a:0?"]   # V mayúscula: sin la carátula

    async def reacomodar() -> Optional[Path]:
        salida = temporal()
        try:
            await _ffmpeg(tid, ["-i", str(origen), *mapa, "-c", "copy", "-movflags", "+faststart",
                                "-progress", "pipe:1", "-f", "mp4", str(salida)], dur, "Preparando el video")
        except FallaFfmpeg:
            salida.unlink(missing_ok=True)
            return None                         # no se pudo copiar tal cual: se comprime
        if salida.stat().st_size > TOPE_BYTES:
            salida.unlink(missing_ok=True)
            return None
        return salida

    if _sirve_tal_cual(info, tam):
        _actualizar(tid, estado="comprimiendo", progreso=0, detalle="Preparando el video")
        listo = await reacomodar()
        if listo:
            os.replace(listo, destino)
            return

    hilos = str(max(1, (os.cpu_count() or 2) // 2))
    audio_k = AUDIO_KBPS
    with contextlib.suppress(Exception):          # no subir el audio por sobre el del original
        audio_k = max(64, min(AUDIO_KBPS, int(int(_audios(info)[0]["bit_rate"]) / 1000)))
    objetivo = min(OBJETIVO_BYTES, int(tam * 0.85))
    techo = VIDEO_KBPS_MAX
    if dur > 0:
        techo = max(VIDEO_KBPS_MIN, min(VIDEO_KBPS_MAX, int(objetivo * 8 / dur / 1000) - audio_k))
    for pase in range(2):
        _actualizar(tid, estado="comprimiendo", progreso=0, detalle="Comprimiendo")
        salida = temporal()
        # Calidad pareja (CRF) con techo de kbps: lo simple pesa menos y lo complejo no pasa del
        # techo, en un solo pase (antes, apuntar a un tamaño fijo podía agrandar un video liviano).
        await _ffmpeg(tid, [
            "-i", str(origen), *mapa,
            "-vf", ESCALA, "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-threads", hilos,
            "-crf", CRF, "-maxrate", f"{techo}k", "-bufsize", f"{techo * 2}k",
            "-c:a", "aac", "-b:a", f"{audio_k}k", "-ac", "2",
            "-movflags", "+faststart", "-progress", "pipe:1", "-f", "mp4", str(salida),
        ], dur, "Comprimiendo")
        final = salida.stat().st_size
        if final <= TOPE_BYTES:
            if final >= tam and _reproducible(info):
                # Comprimir no lo achicó y el original ya se ve en cualquier navegador: se entrega
                # el original reacomodado (nunca más pesado que lo que se subió).
                _actualizar(tid, detalle="Preparando el video")
                copia = await reacomodar()
                if copia:
                    salida.unlink(missing_ok=True)
                    os.replace(copia, destino)
                    return
            os.replace(salida, destino)
            return
        # Se pasó del tope (el techo es un promedio, o no se sabía la duración): otro pase con el
        # techo ajustado según lo que de verdad salió.
        if dur <= 0:
            dur = _duracion(await _sondear(salida))
        salida.unlink(missing_ok=True)
        if dur > 0:
            techo = min(techo, int(OBJETIVO_BYTES * 8 / dur / 1000) - audio_k)
        techo = int(techo * 0.9)
        if pase or techo < VIDEO_KBPS_MIN:
            break
    raise RuntimeError("No se logró dejarlo bajo los 2 GB")


async def _llamar(cli: httpx.AsyncClient, url: str, token: str, **kw: Any) -> Tuple[int, Dict[str, Any]]:
    """POST al sitio con reintentos. Red caída, 5xx, 429 o una página que no es JSON (Cloudflare,
    php-fpm recargando) se reintentan ~2 min con espera creciente; si sigue así, EntregaPendiente:
    se conserva todo y el vigía vuelve a intentarlo más tarde. Un 4xx con JSON es la respuesta."""
    cab = {"Authorization": f"Bearer {token}", **kw.pop("headers", {})}
    ultimo = ""
    for intento in range(7):
        try:
            r = await cli.post(url, headers=cab, **kw)
            try:
                j = r.json()
            except ValueError:
                j = None
            if r.status_code < 500 and r.status_code != 429 and isinstance(j, dict):
                return r.status_code, j
            ultimo = f"respuesta {r.status_code}"
        except httpx.TransportError as e:
            ultimo = type(e).__name__
        await asyncio.sleep(min(30, 2 ** (intento + 1)) * PAUSA_REINTENTO)
    raise EntregaPendiente(f"el sitio no respondió bien ({ultimo})")


async def _url_del_sitio(cli: httpx.AsyncClient, token: str) -> str:
    """La misma máquina (sin pasar por Cloudflare) si responde; si no, la dirección pública."""
    vencida = False
    for url in dict.fromkeys([_API_LOCAL, _api_url_para(token)]):
        try:
            r = await cli.post(url, json={"action": "check-session"}, headers={"Authorization": f"Bearer {token}"}, timeout=20)
            j = r.json()
        except (httpx.TransportError, ValueError):
            continue
        if isinstance(j, dict) and j.get("ok"):
            return url
        if r.status_code in (401, 403):
            vencida = True
    if vencida:
        raise RuntimeError("Se venció la sesión de quien subió el video")
    raise EntregaPendiente("el sitio no responde")


async def _entregar(tid: str, ruta: Path) -> Dict[str, Any]:
    """Entrega el resultado a api.php (subida por pedazos), con el token del administrador.
    Retoma si ya había empezado: pregunta por la subida anterior antes de abrir otra, y solo
    abre otra si el sitio confirma que la anterior no existe (así nunca queda el video dos veces)."""
    t = _leer(tid) or {}
    token = _token(tid)
    if not token:
        raise RuntimeError("Se perdió la sesión de quien subió el video")
    nombre = re.sub(r"\.[^.]+$", "", t.get("nombre") or "video") + ".mp4"
    tam = ruta.stat().st_size
    async with httpx.AsyncClient(timeout=120) as cli:
        url = await _url_del_sitio(cli, token)
        sid, desde, crudo, ped = t.get("subida_api"), 0, False, 0
        if sid:
            st, e = await _llamar(cli, url, token, json={"action": "subida-estado", "subida_id": sid})
            if e.get("terminada") and e.get("file"):
                return e["file"]
            if e.get("ok") and e.get("existe") is False:
                sid = None                                     # ya no está en el sitio: se abre otra
            elif e.get("ok") and e.get("existe") and int(e.get("tamano") or 0) == tam:
                desde, crudo, ped = int(e.get("recibido") or 0), True, int(t.get("subida_pedazo") or 0)
            elif e.get("ok") and e.get("existe"):
                # Era de otro comprimido (se volvió a comprimir): se descarta y se abre otra.
                await _llamar(cli, url, token, json={"action": "subida-cancelar", "subida_id": sid})
                sid = None
            elif st in (401, 403):
                raise RuntimeError(e.get("error") or "Se venció la sesión de quien subió el video")
            else:
                raise EntregaPendiente(f"no se pudo saber cómo quedó la subida anterior ({st})")
        if not sid:
            st, ini = await _llamar(cli, url, token, json={
                "action": "capacitaciones-subida-iniciar", "seccion_id": t.get("seccion_id"),
                "carpeta_id": t.get("carpeta_id", ""), "nombre": nombre, "tamano": tam,
                "mime": "video/mp4", "crudo": True})
            if not ini.get("ok") or not ini.get("subida_id"):
                raise RuntimeError(ini.get("error") or "El sitio no aceptó la subida")
            sid = ini["subida_id"]
            crudo = ini.get("crudo") is True
            ped = int(ini.get("pedazo_bytes") or 0) if crudo else int(ini.get("pedazo_kb") or 1536) * 1024
            _actualizar(tid, subida_api=sid, subida_pedazo=ped if crudo else 0)
        if crudo and ped <= 0:
            ped = 6 * 1024 * 1024
        ultimo_pct, sin_avance = -1, 0
        with open(ruta, "rb") as fh:
            while desde < tam:
                antes = desde
                fh.seek(desde)
                trozo = fh.read(ped)
                if crudo:
                    st, j = await _llamar(cli, url, token, content=trozo,
                                          params={"action": "capacitaciones-subida-pedazo", "subida_id": sid, "desde": desde},
                                          headers={"Content-Type": "application/octet-stream"})
                    if st == 200 and j.get("terminada"):
                        desde = tam
                    elif st == 200 and "recibido" in j:
                        desde = int(j["recibido"])                 # ok, repetido o hueco: sigue desde lo que llegó
                else:
                    st, j = await _llamar(cli, url, token, files={"pedazo": ("p", trozo)},
                                          data={"action": "capacitaciones-subida-pedazo", "subida_id": sid, "indice": str(desde // ped)})
                    if st == 200 and j.get("ok"):
                        desde = min(tam, desde + len(trozo))
                    elif st == 409 and "espera" in j:
                        desde = int(j["espera"]) * ped
                if desde == antes and st != 200 and not (st == 409 and "espera" in j):
                    if st == 404:                                  # la subida del sitio expiró: se empieza otra
                        _actualizar(tid, subida_api=None)
                        raise EntregaPendiente("la subida en el sitio expiró")
                    raise RuntimeError(j.get("error") or f"El sitio rechazó el video ({st})")
                sin_avance = sin_avance + 1 if desde <= antes else 0
                if sin_avance > 5:
                    raise RuntimeError(f"La entrega al sitio no avanza desde el byte {desde}")
                pct = min(99, int(desde * 100 / max(1, tam)))
                if pct != ultimo_pct and pct % 5 == 0:
                    _actualizar(tid, progreso=pct, detalle=f"Subiendo al sitio · {pct}%")
                    ultimo_pct = pct
        st, fin = await _llamar(cli, url, token, json={
            "action": "capacitaciones-subida-terminar", "subida_id": sid,
            "title": t.get("title", ""), "descripcion": t.get("descripcion", "")})
        if fin.get("ok"):
            return fin.get("file") or {}
        # ¿Se guardó igual y solo se perdió la respuesta? Se pregunta antes de rendirse.
        _, e = await _llamar(cli, url, token, json={"action": "subida-estado", "subida_id": sid})
        if e.get("terminada") and e.get("file"):
            return e["file"]
        if st == 422 and "recibido" in fin:
            raise EntregaPendiente("al sitio le faltaron bytes: se completa en la próxima vuelta")
        raise RuntimeError(fin.get("error") or "El sitio no pudo guardar el video")


def _avisar_falla(t: Dict[str, Any], motivo: str) -> None:
    """Correo a quien subió el video (con copia a Nicolás), solo si falló del todo. Corre en un
    hilo aparte: el envío puede tardar y no debe frenar los pedazos ni las consultas de estado."""
    para = (t.get("por") or "").strip()
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_pass) or not para:
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"No se pudo publicar el video «{t.get('nombre') or 'sin nombre'}» en Capacitaciones"
        de = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr(("BigCapital · Capacitaciones", de))
        msg["To"] = para
        if settings.notify_to and settings.notify_to.lower() != para.lower():
            msg["Cc"] = settings.notify_to
        msg.set_content(
            f"Hola.\n\nEl video «{t.get('nombre')}» que subiste a Capacitaciones no se pudo preparar y no quedó publicado.\n\n"
            f"Motivo: {motivo}\n\n"
            "Puedes volver a subirlo. Si vuelve a fallar, avísale a Nicolás.\n\n— Herramientas BigCapital\n")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo avisar la falla de %s: %s", t.get("id"), e)


@contextlib.asynccontextmanager
async def _turno_ffmpeg():
    """Un ffmpeg a la vez en todo el servidor. Se espera sin bloquear (un hilo colgado en un
    candado impediría apagar el servicio a tiempo)."""
    g = os.open(DIR_TRABAJOS / ".ffmpeg.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        while True:
            try:
                fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(3)
        yield
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(g, fcntl.LOCK_UN)
        os.close(g)


async def _procesar(tid: str) -> None:
    d = _dir(tid)
    try:
        fd = os.open(d / "proceso.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except FileNotFoundError:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)     # otro proceso ya lo tiene: nada que hacer
    except BlockingIOError:
        os.close(fd)
        return
    fallo: Optional[str] = None
    t_err: Dict[str, Any] = {}
    try:
        try:
            t = _leer(tid)
            if not t or t.get("estado") not in PROCESO:
                return
            origen, destino = d / "original", d / "comprimido.mp4"
            if t.get("estado") != "subiendo" or not destino.exists():
                if not origen.exists():
                    raise RuntimeError("Se perdió el video original")
                async with _turno_ffmpeg():
                    await _preparar(tid, origen, destino)
                _actualizar(tid, estado="subiendo", progreso=0, detalle="Subiendo al sitio",
                            resultado_bytes=destino.stat().st_size)
            archivo = await _entregar(tid, destino)
            _actualizar(tid, estado="listo", progreso=100, detalle="Listo", file=archivo,
                        resultado_bytes=destino.stat().st_size)
            _borrar_archivos(tid)
        except asyncio.CancelledError:
            # Apagado o despliegue: no se borra nada. El vigía lo retoma al volver.
            raise
        except Interrumpido as e:
            # Un reinicio del servicio (o el sistema matando a ffmpeg): se conserva todo y se
            # retoma solo, un poco después (si este proceso se está apagando, que lo tome el nuevo).
            t = _leer(tid) or {}
            clave, tope = ("cortes", CORTES_MAX) if e.tipo == "corte" else ("matados", MATADOS_MAX)
            n = int(t.get(clave) or 0) + 1
            log.warning("Compresión %s interrumpida (%s, %d de %d)", tid, e, n, tope)
            if n < tope:
                _actualizar(tid, **{clave: n}, retomar_desde=time.time() + ESPERA_RETOMAR_SEG,
                            detalle=("Se interrumpió por un reinicio del servidor: sigue sola en unos minutos" if e.tipo == "corte"
                                     else "Se interrumpió: se vuelve a intentar sola en unos minutos"))
            elif e.tipo == "matado":
                fallo = "El servidor se quedó sin memoria al comprimir este video"
            else:
                fallo = "La compresión se interrumpió demasiadas veces"
        except EntregaPendiente as e:
            t = _leer(tid) or {}
            n = int(t.get("entregas") or 0) + 1
            log.warning("Entrega de %s pendiente (%s, %d de %d)", tid, e, n, ENTREGAS_MAX)
            if n < ENTREGAS_MAX:
                _actualizar(tid, entregas=n, retomar_desde=time.time() + ESPERA_ENTREGA_SEG,
                            detalle="El sitio no respondió: se vuelve a intentar sola en unos minutos")
            else:
                fallo = f"No se pudo entregar el video al sitio ({e})"
        except Exception as e:  # noqa: BLE001
            fallo = (str(e) or type(e).__name__)[:300]
        if fallo:
            # Con el candado tomado todavía: ningún otro proceso alcanza a retomarlo entre medio.
            log.warning("Compresión %s falló: %s", tid, fallo)
            t_err = _actualizar(tid, estado="error", detalle=fallo) or {}
            _borrar_archivos(tid)
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    if fallo:
        await asyncio.to_thread(_avisar_falla, t_err, fallo)


async def _vigia() -> None:
    """En cada proceso, cada minuto: barre restos y retoma los trabajos que quedaron a medias
    (un despliegue, un proceso que murió). Si otro proceso ya lo tiene, _procesar no hace nada."""
    await asyncio.sleep(5)
    while True:
        try:
            _mantener_vivos()
            _barrer_viejos()
            ahora = time.time()
            for t in _todos():
                if t.get("estado") in PROCESO and ahora >= float(t.get("retomar_desde") or 0):
                    _lanzar(t["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("Vigía de compresión: %s", e)
        await asyncio.sleep(VIGIA_SEG)


@router.on_event("startup")
async def _arrancar_vigia() -> None:
    tarea = asyncio.create_task(_vigia())
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
