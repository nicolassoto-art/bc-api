"""Video del edificio (19-oct-2026).

Se sube desde la ficha del proyecto (stock propio), pesa hasta 2 GB y se ve en el catálogo sobre el
mapa. El servidor lo convierte a HLS adaptativo (las 2 calidades más altas que traiga el video) para
que el navegador cambie solo de calidad según la conexión.

Flujo (mismo protocolo que el compresor de Capacitaciones, así el cliente `BCSubidaGrande` lo reutiliza):
  POST   /proyectos/{id}/video/iniciar          {nombre, tamano, mime}  → {ok, trabajo_id, crudo, pedazo_bytes}
  POST   /proyectos/{id}/video/pedazo-crudo     ?trabajo_id&desde  (cuerpo binario) → {ok, recibido}
  GET    /proyectos/{id}/video/estado-subida/{trabajo_id}
  POST   /proyectos/{id}/video/terminar         {trabajo_id}  → empieza a procesar
  POST   /proyectos/{id}/video/cancelar         {trabajo_id}
  GET    /proyectos/{id}/video                   estado del video del proyecto (+ progreso)
  DELETE /proyectos/{id}/video                   quitar el video

El resultado queda en `extra.video_ubicacion` (clave que SOLO escribe este módulo: el PUT del proyecto
la conserva del servidor) y los archivos en {UPLOAD_DIR}/<proyecto>/video/<token>/.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps.auth import stock_access
from ..models import Proyecto, Usuario
from ..settings import settings

log = logging.getLogger("bc.video")
router = APIRouter(prefix="/proyectos/{proyecto_id}/video", tags=["video"])

MAX_BYTES = 2 * 1024 ** 3
PEDAZO = 6 * 1024 * 1024
MIN_LIBRE = 5 * 1024 ** 3                 # debe quedar libre después de guardar el original
EXTENSIONES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
DIR = Path(os.environ.get("BC_VIDEO_DIR", "/var/tmp/bc-video"))
VIDA_SUBIDA_SEG = 24 * 3600               # una subida sin pedazos por 24 h se descarta
SIN_AVANCE_SEG = 20 * 60                  # ffmpeg 20 min sin avanzar = colgado
ID_RE = re.compile(r"^[0-9a-f]{24}$")

# Escalera de calidades: (alto, bitrate máximo del video). Se usan las 2 más altas que no superen al original.
ESCALERA = [(2160, 14000), (1080, 5500), (720, 2800), (480, 1200)]


# ── Estado en disco ─────────────────────────────────────────────────────────────────
def _dir_trabajo(jid: str) -> Path:
    return DIR / jid


def _leer(jid: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((_dir_trabajo(jid) / "estado.json").read_text("utf-8"))
    except Exception:
        return None


def _guardar(jid: str, est: Dict[str, Any]) -> None:
    d = _dir_trabajo(jid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "estado.json.tmp"
    tmp.write_text(json.dumps(est, ensure_ascii=False), "utf-8")
    os.replace(tmp, d / "estado.json")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _proyecto_ok(db: Session, pid: str) -> Proyecto:
    p = db.get(Proyecto, pid)
    if not p or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


def _set_video(pid: str, valor: Optional[Dict[str, Any]]) -> None:
    """Escribe (o quita) extra.video_ubicacion con una sesión propia (sirve desde hilos)."""
    db = SessionLocal()
    try:
        p = db.get(Proyecto, pid)
        if not p:
            return
        extra = dict(p.extra or {})
        if valor is None:
            extra.pop("video_ubicacion", None)
        else:
            extra["video_ubicacion"] = valor
        p.extra = extra
        db.commit()
    finally:
        db.close()


def _video_actual(p: Proyecto) -> Optional[Dict[str, Any]]:
    v = (p.extra or {}).get("video_ubicacion")
    return v if isinstance(v, dict) else None


def _libre() -> int:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(DIR).free
    except Exception:
        return 0


# ── Subida por pedazos ──────────────────────────────────────────────────────────────
class IniciarIn(BaseModel):
    nombre: str
    tamano: int
    mime: str = ""


class TrabajoIn(BaseModel):
    trabajo_id: str


@router.post("/iniciar")
def iniciar(proyecto_id: str, body: IniciarIn, db: Session = Depends(get_db), user: Usuario = Depends(stock_access)):
    _proyecto_ok(db, proyecto_id)
    ext = Path(body.nombre or "").suffix.lower()
    if ext not in EXTENSIONES and not (body.mime or "").startswith("video/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ese archivo no parece un video (mp4, mov, mkv, webm…).")
    if ext not in EXTENSIONES:
        ext = ".mp4"
    if body.tamano <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío.")
    if body.tamano > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="El video pasa del máximo de 2 GB.")
    # Lo que ya está reservado por otras subidas cuenta contra el espacio libre.
    reservado = 0
    if DIR.exists():
        for d in DIR.iterdir():
            e = _leer(d.name) if ID_RE.match(d.name) else None
            if e and e.get("estado") == "recibiendo":
                reservado += max(0, int(e.get("tamano", 0)) - int(e.get("recibido", 0)))
    if _libre() - reservado - body.tamano < MIN_LIBRE:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, detail="No queda espacio en el servidor para ese video. Avísale a Nicolás.")
    jid = secrets.token_hex(12)
    (_dir_trabajo(jid)).mkdir(parents=True, exist_ok=True)
    (_dir_trabajo(jid) / f"origen{ext}.part").write_bytes(b"")
    _guardar(jid, {"id": jid, "pid": proyecto_id, "nombre": body.nombre[:200], "tamano": body.tamano, "ext": ext,
                   "estado": "recibiendo", "recibido": 0, "usuario": user.email, "creado": _ahora(), "ultimo": time.time()})
    return {"ok": True, "trabajo_id": jid, "crudo": True, "pedazo_bytes": PEDAZO}


def _estado_de(jid: str, pid: str) -> Dict[str, Any]:
    if not ID_RE.match(jid or ""):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La subida expiró. Vuelve a elegir el archivo.")
    e = _leer(jid)
    if not e or e.get("pid") != pid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La subida expiró. Vuelve a elegir el archivo.")
    return e


def _escribir_pedazo(ruta: Path, desde: int, datos: bytes) -> int:
    """Agrega solo si `desde` es justo lo que ya llegó. Devuelve el tamaño final."""
    with open(ruta, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0, os.SEEK_END)
        actual = f.tell()
        if actual == desde:
            f.write(datos)
            f.flush()
            actual += len(datos)
        return actual


@router.post("/pedazo-crudo")
async def pedazo_crudo(proyecto_id: str, request: Request, trabajo_id: str, desde: int,
                       _: Usuario = Depends(stock_access)):
    e = _estado_de(trabajo_id, proyecto_id)
    if e.get("estado") != "recibiendo":
        return {"ok": True, "recibido": e.get("tamano", 0), "terminado": True}
    datos = await request.body()
    if len(datos) > PEDAZO or desde < 0 or desde + len(datos) > int(e["tamano"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Pedazo fuera de rango.")
    ruta = _dir_trabajo(trabajo_id) / f"origen{e['ext']}.part"
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La subida expiró. Vuelve a elegir el archivo.")
    nuevo = await run_in_threadpool(_escribir_pedazo, ruta, desde, datos)
    e["recibido"], e["ultimo"] = nuevo, time.time()
    _guardar(trabajo_id, e)
    # Si el pedazo llegó repetido o adelantado, el cliente se corrige con `recibido`.
    return {"ok": nuevo == desde + len(datos), "recibido": nuevo}


@router.get("/estado-subida/{trabajo_id}")
def estado_subida(proyecto_id: str, trabajo_id: str, _: Usuario = Depends(stock_access)):
    e = _estado_de(trabajo_id, proyecto_id)
    return {"estado": e.get("estado"), "recibido": e.get("recibido", 0), "tamano": e.get("tamano", 0)}


@router.post("/cancelar")
def cancelar(proyecto_id: str, body: TrabajoIn, _: Usuario = Depends(stock_access)):
    if ID_RE.match(body.trabajo_id or ""):
        e = _leer(body.trabajo_id)
        if e and e.get("pid") == proyecto_id and e.get("estado") == "recibiendo":
            shutil.rmtree(_dir_trabajo(body.trabajo_id), ignore_errors=True)
    return {"ok": True}


@router.post("/terminar")
def terminar(proyecto_id: str, body: TrabajoIn, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = _proyecto_ok(db, proyecto_id)
    e = _estado_de(body.trabajo_id, proyecto_id)
    if e.get("estado") != "recibiendo":
        return {"ok": True, "estado": e.get("estado")}
    ruta = _dir_trabajo(body.trabajo_id) / f"origen{e['ext']}.part"
    if not ruta.exists() or ruta.stat().st_size != int(e["tamano"]):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Faltan pedazos: el video no llegó completo.")
    os.replace(ruta, _dir_trabajo(body.trabajo_id) / f"origen{e['ext']}")
    token = secrets.token_hex(12)
    e.update({"estado": "en_cola", "token": token, "progreso": 0, "ultimo": time.time()})
    _guardar(body.trabajo_id, e)
    previo = _video_actual(p)
    _set_video(proyecto_id, {"estado": "procesando", "trabajo": body.trabajo_id, "token": token, "nombre": e["nombre"],
                             "progreso": 0, "actualizado": _ahora(),
                             **({"anterior": previo.get("token")} if previo and previo.get("token") else {})})
    _lanzar(body.trabajo_id)
    return {"ok": True, "estado": "procesando"}


# ── Estado del video del proyecto ───────────────────────────────────────────────────
@router.get("")
def ver(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = _proyecto_ok(db, proyecto_id)
    v = _video_actual(p)
    if not v:
        return {"video": None}
    v = dict(v)
    if v.get("estado") == "procesando" and v.get("trabajo"):
        e = _leer(v["trabajo"])
        if e:
            v["progreso"] = e.get("progreso", v.get("progreso", 0))
            v["fase"] = e.get("estado")
    return {"video": v}


def _borrar_archivos(pid: str, conservar: Optional[str] = None) -> None:
    base = settings.upload_path / pid / "video"
    if not base.exists():
        return
    for d in base.iterdir():
        if conservar and d.name == conservar:
            continue
        shutil.rmtree(d, ignore_errors=True)


@router.delete("")
def quitar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = _proyecto_ok(db, proyecto_id)
    v = _video_actual(p)
    if v and v.get("trabajo"):
        # Si está procesando, se avisa al hilo que pare y se borra su carpeta de trabajo.
        with contextlib.suppress(Exception):
            (_dir_trabajo(v["trabajo"])).mkdir(parents=True, exist_ok=True)
            (_dir_trabajo(v["trabajo"]) / "cancelar").write_text("1")
    _set_video(proyecto_id, None)
    _borrar_archivos(proyecto_id)
    return {"ok": True}


# ── Procesamiento (HLS) ─────────────────────────────────────────────────────────────
_prefijo_cache: Optional[List[str]] = None


def _prefijo() -> List[str]:
    global _prefijo_cache
    if _prefijo_cache is None:
        pre: List[str] = []
        if shutil.which("setpriv"):
            with contextlib.suppress(Exception):
                if subprocess.run(["setpriv", "--pdeathsig", "KILL", "--", "true"], capture_output=True, timeout=5).returncode == 0:
                    pre += ["setpriv", "--pdeathsig", "KILL", "--"]
        if shutil.which("nice"):
            pre += ["nice", "-n", "19"]
        if shutil.which("ionice"):
            pre += ["ionice", "-c", "3"]
        _prefijo_cache = pre
    return list(_prefijo_cache)


def elegir_calidades(alto: int) -> List[int]:
    """Las 2 calidades más altas de la escalera que no superen el alto del original (nunca se amplía)."""
    ok = [h for h, _ in ESCALERA if h <= alto + 8]   # 1080 con 1088 de relleno entra
    if not ok:
        return [max(2, alto - alto % 2)]
    return ok[:2]


def _bitrate(alto: int) -> int:
    for h, b in ESCALERA:
        if h == alto:
            return b
    return 1200


def _sondear(ruta: Path) -> Dict[str, Any]:
    r = subprocess.run(_prefijo() + ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(ruta)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("El archivo no se pudo leer como video.")
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise RuntimeError("El archivo no trae imagen de video.")
    tiene_audio = any(s.get("codec_type") == "audio" for s in j.get("streams", []))
    alto = int(v.get("height") or 0)
    ancho = int(v.get("width") or 0)
    # Rotación (celulares): el alto real es el ancho
    try:
        rot = abs(int(float((v.get("tags") or {}).get("rotate", 0))))
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = abs(int(float(sd["rotation"])))
        if rot in (90, 270):
            alto, ancho = ancho, alto
    except Exception:
        pass
    dur = float((j.get("format") or {}).get("duration") or v.get("duration") or 0)
    if alto <= 0 or dur <= 0:
        raise RuntimeError("No se pudo leer el tamaño ni la duración del video.")
    return {"alto": alto, "ancho": ancho, "duracion": dur, "audio": tiene_audio}


def _comando_hls(origen: Path, salida: Path, info: Dict[str, Any], alturas: List[int]) -> List[str]:
    n = len(alturas)
    etiquetas = "".join(f"[s{i}]" for i in range(n))
    filtros = [f"[0:v:0]split={n}{etiquetas}"] if n > 1 else []
    for i, h in enumerate(alturas):
        entrada = f"[s{i}]" if n > 1 else "[0:v:0]"
        filtros.append(f"{entrada}scale=-2:{h}:flags=lanczos,format=yuv420p[v{i}]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-i", str(origen), "-filter_complex", ";".join(filtros)]
    for i, h in enumerate(alturas):
        cmd += ["-map", f"[v{i}]"]
        if info["audio"]:
            cmd += ["-map", "0:a:0"]
    mapa = []
    audio_i = 0
    for i, h in enumerate(alturas):
        br = _bitrate(h)
        cmd += [f"-c:v:{i}", "libx264", f"-preset:v:{i}", "veryfast", f"-crf:v:{i}", "22", f"-profile:v:{i}", "high",
                f"-maxrate:v:{i}", f"{br}k", f"-bufsize:v:{i}", f"{br * 2}k"]
        if info["audio"]:
            cmd += [f"-c:a:{i}", "aac", f"-b:a:{i}", "128k", f"-ac:a:{i}", "2"]
            mapa.append(f"v:{i},a:{i},name:{h}p")
        else:
            mapa.append(f"v:{i},name:{h}p")
    cmd += ["-force_key_frames", "expr:gte(t,n_forced*4)", "-sc_threshold", "0",
            "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "vod", "-hls_flags", "independent_segments",
            "-master_pl_name", "master.m3u8", "-var_stream_map", " ".join(mapa),
            "-hls_segment_filename", str(salida / "%v" / "seg%05d.ts"), str(salida / "%v" / "index.m3u8")]
    return cmd


def _tam_dir(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def _fallo(jid: str, pid: str, mensaje: str) -> None:
    log.warning("video %s: %s", jid, mensaje)
    e = _leer(jid) or {}
    _set_video_si_es_este(pid, jid, {"estado": "error", "mensaje": mensaje, "nombre": e.get("nombre", ""), "actualizado": _ahora()})
    shutil.rmtree(_dir_trabajo(jid), ignore_errors=True)


def _set_video_si_es_este(pid: str, jid: str, valor: Optional[Dict[str, Any]]) -> bool:
    """Solo escribe si el video del proyecto sigue siendo el de este trabajo (si lo quitaron o
    reemplazaron mientras se procesaba, no se pisa)."""
    db = SessionLocal()
    try:
        p = db.get(Proyecto, pid)
        v = _video_actual(p) if p else None
        if not p or not v or v.get("trabajo") != jid:
            return False
        extra = dict(p.extra or {})
        if valor is None:
            extra.pop("video_ubicacion", None)
        else:
            extra["video_ubicacion"] = valor
        p.extra = extra
        db.commit()
        return True
    finally:
        db.close()


def _procesar(jid: str) -> None:
    e = _leer(jid)
    if not e or e.get("estado") not in ("en_cola", "procesando"):
        return
    pid = e["pid"]
    carpeta = _dir_trabajo(jid)
    lock_job = open(carpeta / ".job.lock", "w")
    try:
        fcntl.flock(lock_job, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_job.close()
        return        # otro proceso ya lo está haciendo
    try:
        # Un video a la vez en todo el servidor (los 2 procesos de uvicorn comparten este candado).
        with open(DIR / ".ffmpeg.lock", "w") as glock:
            fcntl.flock(glock, fcntl.LOCK_EX)
            if (carpeta / "cancelar").exists():
                shutil.rmtree(carpeta, ignore_errors=True)
                return
            e = _leer(jid) or e
            e["estado"] = "procesando"
            _guardar(jid, e)
            origen = next(carpeta.glob("origen.*"), None) or next(carpeta.glob("origen*"), None)
            try:
                if not origen or origen.name.endswith(".part"):
                    raise RuntimeError("Falta el archivo original.")
                info = _sondear(origen)
                alturas = elegir_calidades(info["alto"])
                tmp = carpeta / "salida"
                shutil.rmtree(tmp, ignore_errors=True)
                for h in alturas:
                    (tmp / f"{h}p").mkdir(parents=True, exist_ok=True)
                # Póster: un cuadro al 10 % del video
                subprocess.run(_prefijo() + ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
                                             "-ss", f"{info['duracion'] * 0.1:.2f}", "-i", str(origen), "-frames:v", "1",
                                             "-vf", "scale=-2:720", "-q:v", "3", str(tmp / "poster.jpg")],
                               capture_output=True, timeout=300)
                cmd = _prefijo() + _comando_hls(origen, tmp, info, alturas)
                err = open(carpeta / "ffmpeg.err", "w")
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
                ultimo_avance = time.time()
                ultimo_guardado = 0.0
                try:
                    for linea in proc.stdout:   # type: ignore[union-attr]
                        if linea.startswith("out_time_us=") or linea.startswith("out_time_ms="):
                            try:
                                t = int(linea.split("=", 1)[1]) / 1_000_000
                            except ValueError:
                                continue
                            pct = max(0, min(99, int(t * 100 / info["duracion"])))
                            ultimo_avance = time.time()
                            if pct != e.get("progreso") and time.time() - ultimo_guardado > 3:
                                e["progreso"], ultimo_guardado = pct, time.time()
                                _guardar(jid, e)
                        if (carpeta / "cancelar").exists():
                            proc.kill()
                            break
                        if time.time() - ultimo_avance > SIN_AVANCE_SEG:
                            proc.kill()
                            raise RuntimeError("El procesamiento se quedó detenido.")
                finally:
                    proc.wait()
                    err.close()
                if (carpeta / "cancelar").exists():
                    shutil.rmtree(carpeta, ignore_errors=True)
                    return
                if proc.returncode != 0:
                    cola = (carpeta / "ffmpeg.err").read_text("utf-8", "ignore")[-300:].strip().splitlines()
                    raise RuntimeError("No se pudo convertir el video" + (": " + cola[-1] if cola else "."))
                final = settings.upload_path / pid / "video" / e["token"]
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.rmtree(final, ignore_errors=True)
                shutil.move(str(tmp), str(final))
                valor = {"estado": "listo", "trabajo": jid, "token": e["token"], "nombre": e["nombre"],
                         "hls": f"/uploads/{pid}/video/{e['token']}/master.m3u8",
                         "poster": f"/uploads/{pid}/video/{e['token']}/poster.jpg" if (final / "poster.jpg").exists() else "",
                         "duracion": round(info["duracion"]), "calidades": alturas, "ancho": info["ancho"], "alto": info["alto"],
                         "bytes": _tam_dir(final), "actualizado": _ahora()}
                if _set_video_si_es_este(pid, jid, valor):
                    _borrar_archivos(pid, conservar=e["token"])      # el video anterior (si lo había)
                else:
                    shutil.rmtree(final, ignore_errors=True)         # lo quitaron mientras se procesaba
                shutil.rmtree(carpeta, ignore_errors=True)
            except Exception as ex:   # noqa: BLE001
                _fallo(jid, pid, str(ex)[:300] or "No se pudo procesar el video.")
    finally:
        with contextlib.suppress(Exception):
            lock_job.close()


_hilos: Dict[str, threading.Thread] = {}


def _lanzar(jid: str) -> None:
    t = _hilos.get(jid)
    if t and t.is_alive():
        return
    t = threading.Thread(target=_procesar, args=(jid,), name=f"video-{jid[:6]}", daemon=True)
    _hilos[jid] = t
    t.start()


def reanudar() -> None:
    """Al arrancar bc-api: retoma lo que quedó procesando (un reinicio mata a ffmpeg) y descarta
    subidas abandonadas. Se llama desde el evento startup (cada proceso; el candado evita duplicar)."""
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        for d in DIR.iterdir():
            if not ID_RE.match(d.name):
                continue
            e = _leer(d.name)
            if not e:
                shutil.rmtree(d, ignore_errors=True)
            elif e.get("estado") == "recibiendo" and time.time() - float(e.get("ultimo", 0)) > VIDA_SUBIDA_SEG:
                shutil.rmtree(d, ignore_errors=True)
            elif e.get("estado") in ("en_cola", "procesando"):
                _lanzar(d.name)
    except Exception:   # noqa: BLE001
        log.exception("reanudar video")
