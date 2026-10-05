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
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, List, Optional

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
PEDAZO_VIEJO_KB = 900                         # multipart de antes (páginas en caché)
PEDAZO_CRUDO = 8 * 1024 * 1024                # crudo: ?desde=N
MARGEN_DISCO = 3 * 1024 ** 3                  # 3 GB libres como piso, siempre
VIDA_MAX_SEG = 6 * 3600                       # recibiendo sin pedazos por 6 h: se barre
QUIETO_SEG = 30 * 60                          # recibiendo sin pedazos por 30 min: no ocupa lugar en la cola
VIDA_TERMINADO_SEG = 6 * 3600                 # listo o error: el estado se puede leer 6 h
MAX_ACTIVOS = 2                               # uno comprimiendo y uno esperando
PROCESO = ("en_cola", "comprimiendo", "subiendo")
ID_RE = re.compile(r"cx_[a-f0-9]{20}")

# api.php tiene una copia vieja en /backend/ con OTRO almacén de sesiones: se prueba primero la
# raíz —la del ingreso al sitio— y después la configurada. La que valide es la que se usa.
_API_CANDIDATAS = [os.environ.get("BC_HERRAMIENTAS_API", "https://herramientas.bigcapital.cl/api.php"),
                   settings.legacy_api_url]
# Para entregar el resultado: la misma máquina, sin pasar por Cloudflare.
_API_LOCAL = os.environ.get("BC_HERRAMIENTAS_LOCAL", "http://127.0.0.1:8080/api.php")
_api_valida: Dict[str, str] = {}   # token → url que lo reconoció
_correo_de: Dict[str, str] = {}    # token → correo del administrador
_tareas: set = set()               # referencias a las tareas en curso (si no, se las puede llevar el recolector)


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
            _correo_de[token] = str(usuario.get("email") or "").strip().lower()
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
    with _candado(d / ".candado"):
        t = _leer(tid)
        if t is None:
            return None
        t.update(cambios)
        t["actualizado"] = int(time.time())
        _escribir(tid, t)
        return t


def _token(tid: str) -> str:
    try:
        return (_dir(tid) / "token").read_text().strip()
    except Exception:
        return ""


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
    for f in ("original", "comprimido.mp4", "token"):
        with contextlib.suppress(Exception):
            (_dir(tid) / f).unlink()


def _barrer_viejos() -> None:
    """Restos de trabajos abandonados o terminados: nunca deben quedar ocupando disco."""
    ahora = time.time()
    for t in _todos():
        quieto = ahora - _ultimo_movimiento(t)
        if (t.get("estado") == "recibiendo" and quieto > VIDA_MAX_SEG) or \
           (t.get("estado") in ("listo", "error") and quieto > VIDA_TERMINADO_SEG):
            shutil.rmtree(_dir(t["id"]), ignore_errors=True)


def _libre() -> int:
    try:
        return shutil.disk_usage(DIR_TRABAJOS if DIR_TRABAJOS.exists() else "/").free
    except Exception:
        return 0


def _duena(t: Dict[str, Any], token: str) -> bool:
    por = (t.get("por") or "").lower()
    return not por or por == _correo_de.get(token, "")


def _publico(t: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in t.items() if k not in ("token", "por", "subida_api")}
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
        # Lo que todavía puede ocupar disco cada trabajo vivo: lo que falta por llegar + su comprimido.
        reservado = sum(max(0, int(t["tamano"]) - _recibido(t["id"])) + min(int(t["tamano"]), TOPE_BYTES) for t in vivos)
        necesario = cuerpo.tamano + min(cuerpo.tamano, TOPE_BYTES) + MARGEN_DISCO + reservado
        if _libre() < necesario:
            raise HTTPException(507, "No queda espacio en el servidor para comprimir ese video. Avísale a Nicolás.")
        tid = "cx_" + secrets.token_hex(10)
        d = _dir(tid)
        d.mkdir(parents=True)
        (d / "original").touch()
        fd = os.open(d / "token", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.write(fd, token.encode())
        os.close(fd)
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
    if t["estado"] != "recibiendo":
        raise HTTPException(409, "Ese trabajo ya no recibe pedazos")
    datos = await pedazo.read()
    ped = PEDAZO_VIEJO_KB * 1024
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
        raise HTTPException(409, "Ese trabajo ya no recibe pedazos")
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
        raise HTTPException(409, "Ese trabajo ya terminó con error")
    real = _recibido(tid)
    if real > int(t["tamano"]):
        shutil.rmtree(_dir(tid), ignore_errors=True)
        raise HTTPException(422, f"El video llegó con bytes de más ({real} de {t['tamano']}). Vuelve a subirlo.")
    if real < int(t["tamano"]):
        # No se borra: se puede seguir desde donde quedó.
        raise HTTPException(422, f"El video llegó incompleto ({real} de {t['tamano']} bytes). Vuelve a intentarlo.")
    _actualizar(tid, estado="en_cola", progreso=0, detalle="En cola para comprimir")
    _lanzar(tid)
    return {"ok": True, "estado": "en_cola"}


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


async def _sondear(ruta: Path) -> Dict[str, Any]:
    p = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(ruta),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    salida, _ = await p.communicate()
    try:
        return json.loads(salida.decode() or "{}")
    except Exception:
        return {}


def _duracion(info: Dict[str, Any]) -> float:
    try:
        return max(0.0, float((info.get("format") or {}).get("duration") or 0))
    except Exception:
        return 0.0


def _sirve_tal_cual(info: Dict[str, Any], tam: int) -> bool:
    """¿Se puede entregar sin recomprimir? H.264 8 bits, ≤1080p, audio AAC/MP3 (o sin audio),
    bajo el tope de kbps. Entonces basta reacomodarlo (+faststart) para que empiece al tiro."""
    dur = _duracion(info)
    if tam > TOPE_BYTES or dur <= 0:
        return False
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not videos:
        return False
    v = videos[0]
    if v.get("codec_name") != "h264" or v.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        return False
    if int(v.get("height") or 0) > 1080 or int(v.get("width") or 0) > 1920:
        return False
    if audios and audios[0].get("codec_name") not in ("aac", "mp3"):
        return False
    kbps = tam * 8 / dur / 1000
    return kbps <= VIDEO_KBPS_MAX + AUDIO_KBPS + 200


def _prefijo_baja_prioridad() -> List[str]:
    pre = ["nice", "-n", "19"] if shutil.which("nice") else []
    if shutil.which("ionice"):
        pre += ["ionice", "-c", "3"]
    return pre


async def _ffmpeg(tid: str, args: List[str], duracion: float, etiqueta: str) -> None:
    cmd = _prefijo_baja_prioridad() + ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin"] + args
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    assert p.stdout
    ultimo = 0.0
    try:
        while True:
            linea = await p.stdout.readline()
            if not linea:
                break
            s = linea.decode(errors="ignore").strip()
            if s.startswith("out_time_ms=") and duracion > 0 and time.time() - ultimo > 2:
                with contextlib.suppress(Exception):
                    pct = min(99, int(int(s.split("=", 1)[1]) / 1_000_000 * 100 / duracion))
                    _actualizar(tid, progreso=pct, detalle=f"{etiqueta} · {pct}%")
                    ultimo = time.time()
        _, err = await p.communicate()
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            p.kill()
        raise
    if p.returncode != 0:
        raise RuntimeError((err or b"").decode(errors="ignore")[-300:] or "ffmpeg falló")


async def _preparar(tid: str, origen: Path, destino: Path) -> None:
    info = await _sondear(origen)
    dur = _duracion(info)
    if dur <= 0:
        raise RuntimeError("No se pudo leer el video (¿archivo dañado o no es un video?)")
    tam = origen.stat().st_size
    mapa = ["-map", "0:v:0", "-map", "0:a:0?"]
    if _sirve_tal_cual(info, tam):
        _actualizar(tid, estado="comprimiendo", progreso=0, detalle="Preparando el video")
        await _ffmpeg(tid, ["-i", str(origen)] + mapa + ["-c", "copy", "-movflags", "+faststart",
                      "-progress", "pipe:1", "-f", "mp4", str(destino)], dur, "Preparando el video")
        if destino.stat().st_size <= TOPE_BYTES:
            return
    hilos = str(max(1, (os.cpu_count() or 2) // 2))
    factor = 1.0
    for _ in range(3):                       # si se pasa del tope, otro pase más apretado
        # El objetivo NUNCA supera al original: comprimir es achicar (un video de 5,4 MB salió en
        # 124,7 MB la primera vez que se apuntó a un tamaño fijo).
        objetivo = min(OBJETIVO_BYTES, int(tam * 0.85)) * factor
        video_k = int(objetivo * 8 / max(1.0, dur) / 1000) - AUDIO_KBPS
        video_k = max(VIDEO_KBPS_MIN, min(VIDEO_KBPS_MAX, video_k))
        _actualizar(tid, estado="comprimiendo", progreso=0, detalle="Comprimiendo")
        await _ffmpeg(tid, [
            "-i", str(origen), *mapa,
            "-vf", "scale='min(1280,iw)':-2", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-threads", hilos, "-b:v", f"{video_k}k",
            "-maxrate", f"{int(video_k * 1.3)}k", "-bufsize", f"{video_k * 2}k",
            "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ac", "2",
            "-movflags", "+faststart", "-progress", "pipe:1", "-f", "mp4", str(destino),
        ], dur, "Comprimiendo")
        if destino.stat().st_size <= TOPE_BYTES:
            return
        factor *= 0.8
    raise RuntimeError("No se logró dejarlo bajo los 2 GB")


async def _post(cli: httpx.AsyncClient, url: str, token: str, **kw) -> Dict[str, Any]:
    r = await cli.post(url, headers={"Authorization": f"Bearer {token}", **kw.pop("headers", {})}, **kw)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "error": f"respuesta {r.status_code}"}


async def _entregar(tid: str, ruta: Path) -> Dict[str, Any]:
    """Entrega el resultado a api.php (subida por pedazos), con el token del administrador.
    Retoma si ya había empezado: pregunta por la subida anterior antes de abrir otra."""
    t = _leer(tid) or {}
    token = _token(tid)
    if not token:
        raise RuntimeError("Se perdió la sesión del administrador")
    nombre = re.sub(r"\.[^.]+$", "", t.get("nombre") or "video") + ".mp4"
    tam = ruta.stat().st_size
    ultimo_error = None
    for url in dict.fromkeys([_API_LOCAL, _api_url_para(token)]):
        try:
            async with httpx.AsyncClient(timeout=120) as cli:
                sid, desde, crudo, ped = t.get("subida_api"), 0, False, 0
                if sid:
                    e = await _post(cli, url, token, json={"action": "subida-estado", "subida_id": sid})
                    if e.get("terminada") and e.get("file"):
                        return e["file"]
                    if e.get("existe") and int(e.get("tamano") or 0) == tam:
                        desde, crudo, ped = int(e.get("recibido") or 0), True, int(t.get("subida_pedazo") or 0)
                    else:
                        sid = None
                if not sid:
                    ini = await _post(cli, url, token, json={
                        "action": "capacitaciones-subida-iniciar", "seccion_id": t.get("seccion_id"),
                        "carpeta_id": t.get("carpeta_id", ""), "nombre": nombre, "tamano": tam,
                        "mime": "video/mp4", "crudo": True})
                    if not ini.get("ok"):
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
                        for intento in range(5):
                            try:
                                if crudo:
                                    r = await cli.post(url, params={"action": "capacitaciones-subida-pedazo", "subida_id": sid, "desde": desde},
                                                       content=trozo, headers={"Authorization": f"Bearer {token}",
                                                                               "Content-Type": "application/octet-stream"})
                                    if r.status_code == 200:
                                        desde = int(r.json().get("recibido", desde))   # ok, repetido o hueco: sigue desde lo que llegó
                                        break
                                else:
                                    r = await cli.post(url, headers={"Authorization": f"Bearer {token}"},
                                                       data={"action": "capacitaciones-subida-pedazo", "subida_id": sid, "indice": str(desde // ped)},
                                                       files={"pedazo": ("p", trozo)})
                                    if r.status_code == 200 and r.json().get("ok"):
                                        desde = min(tam, desde + len(trozo))
                                        break
                                    if r.status_code == 409 and "espera" in r.json():
                                        desde = int(r.json()["espera"]) * ped
                                        break
                            except (httpx.TransportError, ValueError):
                                pass
                            await asyncio.sleep(1.5 * (intento + 1))
                        else:
                            raise RuntimeError(f"El sitio no recibió el pedazo desde el byte {desde}")
                        sin_avance = sin_avance + 1 if desde <= antes else 0
                        if sin_avance > 5:
                            raise RuntimeError(f"La entrega no avanza desde el byte {desde}")
                        pct = min(99, int(desde * 100 / max(1, tam)))
                        if pct != ultimo_pct and pct % 5 == 0:
                            _actualizar(tid, progreso=pct, detalle=f"Subiendo al sitio · {pct}%")
                            ultimo_pct = pct
                fin = await _post(cli, url, token, json={
                    "action": "capacitaciones-subida-terminar", "subida_id": sid,
                    "title": t.get("title", ""), "descripcion": t.get("descripcion", "")})
                if not fin.get("ok"):
                    raise RuntimeError(fin.get("error") or "El sitio no pudo guardar el video")
                return fin.get("file") or {}
        except httpx.ConnectError as e:      # la red local no responde: se prueba la dirección pública
            ultimo_error = e
            continue
    raise RuntimeError(f"No se pudo entregar el video al sitio ({ultimo_error})")


def _avisar_falla(t: Dict[str, Any], motivo: str) -> None:
    """Correo a quien subió el video (con copia a Nicolás), solo si falló del todo."""
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
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo avisar la falla de %s: %s", t.get("id"), e)


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
    g = None
    try:
        t = _leer(tid)
        if not t or t.get("estado") not in PROCESO:
            return
        # Un ffmpeg a la vez en todo el servidor. Se espera sin bloquear (un hilo colgado en un
        # candado impediría apagar el servicio a tiempo).
        g = os.open(DIR_TRABAJOS / ".ffmpeg.lock", os.O_CREAT | os.O_RDWR, 0o600)
        while True:
            try:
                fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(3)
        t = _leer(tid) or t
        origen, destino = d / "original", d / "comprimido.mp4"
        if t.get("estado") != "subiendo" or not destino.exists():
            if not origen.exists():
                raise RuntimeError("Se perdió el video original")
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
    except Exception as e:  # noqa: BLE001
        motivo = str(e)[:300]
        log.warning("Compresión %s falló: %s", tid, motivo)
        t = _actualizar(tid, estado="error", detalle=motivo) or {}
        _borrar_archivos(tid)
        _avisar_falla(t, motivo)
    finally:
        if g is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(g, fcntl.LOCK_UN)
                os.close(g)
        with contextlib.suppress(Exception):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


async def _vigia() -> None:
    """En cada proceso, cada minuto: barre restos y retoma los trabajos que quedaron a medias
    (un despliegue, un proceso que murió). Si otro proceso ya lo tiene, _procesar no hace nada."""
    await asyncio.sleep(5)
    while True:
        try:
            _barrer_viejos()
            for t in _todos():
                if t.get("estado") in PROCESO:
                    _lanzar(t["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("Vigía de compresión: %s", e)
        await asyncio.sleep(60)


@router.on_event("startup")
async def _arrancar_vigia() -> None:
    tarea = asyncio.create_task(_vigia())
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
