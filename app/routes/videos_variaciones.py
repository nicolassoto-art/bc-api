"""Variaciones de video: hook + desarrollo + CTA (página bigcapital.cl/videos).

Francisco (editor) sube clips en tres partes. El servidor arma TODAS las combinaciones
hook × desarrollo × CTA, siempre en el orden hook → desarrollo → CTA, y las entrega en un ZIP.

Decisiones (Nicolás, 25-oct-2026):
- Acceso por clave al correo: solo las personas de la lista (BC_VIDEOS_EMAILS) reciben el código.
- Calidad máxima: si los clips son compatibles se unen sin recodificar (copia exacta); si no, se
  ajustan al tamaño y los fps del HOOK y se codifican con x264 crf 12, audio AAC 320 kbps.
- Cada clip tiene un nombre claro (el que le pone Francisco) y cada video sale con ese nombre:
  «H1 nombre + D1 nombre + C1 nombre.mp4».
- Se descarga todo junto en un ZIP.
- Excepción acotada a «el VPS es taller, no bodega» (capacitaciones.py): los originales y los
  resultados se guardan 3 días y se borran solos.

Todo el estado vive en disco (lote.json por lote, con candado), como capacitaciones.py: bc-api corre
con 2 procesos y cada despliegue lo reinicia. Un vigía retoma los lotes que quedaron generando.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import fcntl
import hashlib
import hmac
import itertools
import json
import logging
import os
import re
import secrets
import shutil
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services import bc_email, email_service
from ..settings import settings
from . import capacitaciones as cap

log = logging.getLogger("bcapi.videos")
router = APIRouter(prefix="/videos", tags=["videos"])

DIR = Path(os.environ.get("BC_VIDEOS_DIR", "/var/tmp/bc-videos"))
EMAILS = [e.strip().lower() for e in os.environ.get(
    "BC_VIDEOS_EMAILS", "nicolas.soto@bigcapital.cl,francisco.ceballos@bigcapital.cl").split(",") if e.strip()]
VIDA_SEG = 3 * 24 * 3600                    # lotes: se borran a los 3 días
VIDA_SUBIENDO_SEG = 24 * 3600               # subiendo sin movimiento por un día: se barre
MARGEN_DISCO = 10 * 1024 ** 3               # piso de disco libre, siempre
PEDAZO_MAX = 64 * 1024 * 1024               # máximo por petición de subida
TOPE_ARCHIVO = 10 * 1024 ** 3               # tope técnico por clip
TOPE_COMBOS = 60
PARTES = ("hook", "desarrollo", "cta")
LETRA = {"hook": "H", "desarrollo": "D", "cta": "C"}
CODIGO_VALIDEZ_SEG = 10 * 60
CODIGO_INTENTOS = 5
CODIGO_PAUSA_SEG = 60
SESION_SEG = 30 * 24 * 3600
SIN_AVANCE_SEG = 20 * 60
VIGIA_SEG = int(os.environ.get("BC_VIDEOS_VIGIA_SEG", "60"))
BARRIDO_SEG = 10 * 60
ID_LOTE = re.compile(r"vl_[a-f0-9]{20}")
ID_CLIP = re.compile(r"[a-f0-9]{8,32}")
ARCHIVO_OK = re.compile(r"[^\w\-+ ().]", re.UNICODE)

_tareas: set = set()
_en_curso: set = set()                       # lotes que ESTE proceso está generando


# ─────────────────────────── acceso por código al correo ───────────────────────────

def _clave() -> bytes:
    return (settings.jwt_secret + "|videos").encode()


def _hmac(texto: str) -> str:
    return hmac.new(_clave(), texto.encode(), hashlib.sha256).hexdigest()


def _crear_token(email: str) -> str:
    cuerpo = base64.urlsafe_b64encode(json.dumps({"e": email, "x": int(time.time()) + SESION_SEG}).encode()).decode().rstrip("=")
    return f"{cuerpo}.{_hmac(cuerpo)}"


def _email_de_token(token: str) -> Optional[str]:
    try:
        cuerpo, firma = token.split(".", 1)
        if not hmac.compare_digest(firma, _hmac(cuerpo)):
            return None
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
        if datos["x"] < time.time() or datos["e"] not in EMAILS:
            return None
        return datos["e"]
    except Exception:
        return None


async def sesion(authorization: Optional[str] = Header(None), t: Optional[str] = Query(None)) -> str:
    """Bearer en el encabezado; ?t= para las descargas directas desde un enlace."""
    token = (authorization or "").removeprefix("Bearer ").strip() or (t or "")
    email = _email_de_token(token)
    if not email:
        raise HTTPException(401, "Tu sesión venció. Ingresa de nuevo con tu correo.")
    return email


def _archivo_codigo(email: str) -> Path:
    return DIR / "auth" / (hashlib.sha256(email.encode()).hexdigest()[:32] + ".json")


def _html_codigo(codigo: str) -> str:
    cuerpo = (bc_email.p("Hola.")
              + bc_email.p("Este es tu código para entrar a la página de videos de BigCapital:")
              + bc_email.codigo(codigo)
              + bc_email.p("Vale por 10 minutos. Si no lo pediste tú, ignora este correo.", suave=True))
    return bc_email.email_html("Tu código de acceso", cuerpo, preheader=f"Tu código es {codigo}")


def _enviar_codigo(email: str, codigo: str) -> None:
    estado = email_service.enviar_html(
        "Tu código de acceso a Videos BigCapital", _html_codigo(codigo),
        f"Tu código de acceso es {codigo}. Vale por 10 minutos.", [email])
    if estado != "enviado":
        log.warning("videos: no se envió el código a %s: %s", email, estado)


class Solicitud(BaseModel):
    email: str


class Verificacion(BaseModel):
    email: str
    codigo: str


@router.post("/auth/solicitar")
async def solicitar(c: Solicitud, fondo: BackgroundTasks):
    """Misma respuesta exista o no el correo: no se revela quién está en la lista."""
    email = c.email.strip().lower()
    if email in EMAILS:
        f = _archivo_codigo(email)
        f.parent.mkdir(parents=True, exist_ok=True)
        try:
            previo = json.loads(f.read_text())
        except Exception:
            previo = {}
        if time.time() - previo.get("pedido", 0) >= CODIGO_PAUSA_SEG:
            codigo = f"{secrets.randbelow(10 ** 6):06d}"
            f.write_text(json.dumps({"hash": _hmac(email + codigo), "exp": time.time() + CODIGO_VALIDEZ_SEG,
                                     "intentos": 0, "pedido": time.time()}))
            fondo.add_task(_enviar_codigo, email, codigo)
    return {"ok": True, "mensaje": "Si tu correo está autorizado, te enviamos un código. Revisa tu bandeja."}


@router.post("/auth/verificar")
async def verificar(c: Verificacion):
    email, codigo = c.email.strip().lower(), re.sub(r"\D", "", c.codigo)
    malo = HTTPException(400, "Código incorrecto o vencido. Pide uno nuevo.")
    if email not in EMAILS:
        raise malo
    f = _archivo_codigo(email)
    try:
        with cap._candado(f.parent / ".candado"):
            d = json.loads(f.read_text())
            if d["exp"] < time.time() or d["intentos"] >= CODIGO_INTENTOS:
                raise malo
            d["intentos"] += 1
            ok = hmac.compare_digest(d["hash"], _hmac(email + codigo))
            if ok:
                f.unlink(missing_ok=True)
            else:
                f.write_text(json.dumps(d))
    except HTTPException:
        raise
    except Exception:
        raise malo
    if not ok:
        raise malo
    return {"token": _crear_token(email), "email": email}


# ─────────────────────────── estado del lote en disco ───────────────────────────

def _lote_dir(lid: str) -> Path:
    if not ID_LOTE.fullmatch(lid or ""):
        raise HTTPException(404, "Lote no encontrado.")
    return DIR / "lotes" / lid


def _leer(lid: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((_lote_dir(lid) / "lote.json").read_text())
    except HTTPException:
        raise
    except Exception:
        return None


def _actualizar(lid: str, fn) -> Optional[Dict[str, Any]]:
    """Lee, aplica fn(lote) y guarda, todo bajo candado."""
    d = _lote_dir(lid)
    if not d.is_dir():
        return None
    try:
        with cap._candado(d / ".candado"):
            t = _leer(lid)
            if t is None:
                return None
            fn(t)
            t["actualizado"] = int(time.time())
            tmp = d / f"lote.json.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(t, ensure_ascii=False))
            os.replace(tmp, d / "lote.json")
            return t
    except FileNotFoundError:
        return None


def _del_usuario(lid: str, email: str) -> Dict[str, Any]:
    t = _leer(lid)
    if t is None or t.get("por") != email:
        raise HTTPException(404, "Lote no encontrado.")
    return t


def _nombre_limpio(texto: str, tope: int = 40) -> str:
    s = unicodedata.normalize("NFC", texto or "").strip()
    s = ARCHIVO_OK.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:tope].strip(" .") or "sin nombre"


def _nombre_de_archivo(archivo: str) -> str:
    return _nombre_limpio(Path(archivo or "").stem)


def _libre() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(DIR).free


def _publico(t: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in t.items() if k not in ("por",)}


# ─────────────────────────── subida por pedazos ───────────────────────────

@router.post("/lote")
async def nuevo_lote(email: str = Depends(sesion)):
    lid = "vl_" + secrets.token_hex(10)
    d = _lote_dir(lid)
    (d / "partes").mkdir(parents=True)
    ahora = int(time.time())
    (d / "lote.json").write_text(json.dumps({
        "id": lid, "por": email, "creado": ahora, "actualizado": ahora, "estado": "subiendo",
        "clips": {}, "combos": [], "progreso": 0, "zip": None}, ensure_ascii=False))
    return {"id": lid}


@router.post("/subir")
async def subir(request: Request, lote: str, clip: str, parte: str, desde: int, nombre: str = "",
                archivo: str = "", email: str = Depends(sesion)):
    """Pedazo crudo (hasta 64 MB). `desde` debe ser el tamaño ya recibido; si no, 409 con
    `recibido` y el cliente retoma desde ahí. Repetir un pedazo no daña nada."""
    t = _del_usuario(lote, email)
    if parte not in PARTES or not ID_CLIP.fullmatch(clip):
        raise HTTPException(400, "Parte o clip inválido.")
    if t["estado"] != "subiendo":
        raise HTTPException(409, "Este lote ya se está generando. Empieza uno nuevo.")
    ruta = _lote_dir(lote) / "partes" / f"{clip}.src"
    actual = ruta.stat().st_size if ruta.exists() else 0
    if desde != actual:
        return _json_409(actual)
    if _libre() < MARGEN_DISCO:
        raise HTTPException(507, "El servidor no tiene espacio libre ahora. Avísale a Nicolás.")
    recibido = 0
    with open(ruta, "ab") as f:
        async for trozo in request.stream():
            recibido += len(trozo)
            if recibido > PEDAZO_MAX or actual + recibido > TOPE_ARCHIVO:
                f.truncate(actual)
                raise HTTPException(413, "Pedazo o archivo demasiado grande.")
            f.write(trozo)
    total = actual + recibido

    def poner(x: Dict[str, Any]) -> None:
        c = x["clips"].setdefault(clip, {"id": clip})
        c.update(parte=parte, archivo=_nombre_limpio(archivo, 120) if archivo else c.get("archivo", ""),
                 tam=total, estado="subiendo")
        c.setdefault("nombre", _nombre_limpio(nombre) if nombre else _nombre_de_archivo(archivo))

    _actualizar(lote, poner)
    return {"recibido": total}


def _json_409(recibido: int):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"detail": "Pedazo fuera de lugar.", "recibido": recibido})


class Terminar(BaseModel):
    lote: str
    clip: str


@router.post("/subir/terminar")
async def terminar(c: Terminar, email: str = Depends(sesion)):
    _del_usuario(c.lote, email)
    ruta = _lote_dir(c.lote) / "partes" / f"{c.clip}.src"
    if not ID_CLIP.fullmatch(c.clip) or not ruta.exists():
        raise HTTPException(404, "Clip no encontrado.")
    info = await cap._sondear(ruta)
    vs = cap._videos(info)
    if not vs:
        ruta.unlink(missing_ok=True)
        _actualizar(c.lote, lambda x: x["clips"].pop(c.clip, None))
        raise HTTPException(422, "Ese archivo no es un video que el servidor pueda leer.")
    v = vs[0]
    ancho, alto = _dimensiones(v)

    def poner(x: Dict[str, Any]) -> None:
        x["clips"][c.clip].update(estado="listo", duracion=round(cap._duracion(info), 2), ancho=ancho, alto=alto,
                                  tam=ruta.stat().st_size)

    t = _actualizar(c.lote, poner)
    return {"clip": (t or {}).get("clips", {}).get(c.clip)}


class Renombrar(BaseModel):
    lote: str
    clip: str
    nombre: str


@router.post("/clip/nombre")
async def renombrar(c: Renombrar, email: str = Depends(sesion)):
    _del_usuario(c.lote, email)
    nombre = _nombre_limpio(c.nombre)
    _actualizar(c.lote, lambda x: x["clips"].get(c.clip, {}).update(nombre=nombre))
    return {"nombre": nombre}


@router.delete("/clip")
async def borrar_clip(lote: str, clip: str, email: str = Depends(sesion)):
    t = _del_usuario(lote, email)
    if t["estado"] != "subiendo":
        raise HTTPException(409, "Este lote ya se está generando.")
    if ID_CLIP.fullmatch(clip):
        (_lote_dir(lote) / "partes" / f"{clip}.src").unlink(missing_ok=True)
        _actualizar(lote, lambda x: x["clips"].pop(clip, None))
    return {"ok": True}


@router.get("/lote/{lid}")
async def estado(lid: str, email: str = Depends(sesion)):
    return _publico(_del_usuario(lid, email))


# ─────────────────────────── combinaciones ───────────────────────────

class Orden(BaseModel):
    hook: List[str]
    desarrollo: List[str]
    cta: List[str]


class Generar(BaseModel):
    lote: str
    orden: Orden


def _armar_combos(t: Dict[str, Any], orden: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """hook → desarrollo → CTA, en orden estable: H1-D1-C1, H1-D1-C2, … (el último varía más rápido)."""
    clips = t["clips"]
    numerados = {p: [(i + 1, clips[c]) for i, c in enumerate(orden[p])] for p in PARTES}
    out = []
    for (ih, h), (idd, d), (ic, c) in itertools.product(numerados["hook"], numerados["desarrollo"], numerados["cta"]):
        etiqueta = f"H{ih}-D{idd}-C{ic}"
        nombre = f"H{ih} {h['nombre']} + D{idd} {d['nombre']} + C{ic} {c['nombre']}"
        out.append({"id": etiqueta, "archivo": _nombre_limpio(nombre, 150) + ".mp4",
                    "hook": h["id"], "desarrollo": d["id"], "cta": c["id"],
                    "estado": "pendiente", "progreso": 0, "detalle": ""})
    return out


@router.post("/generar")
async def generar(c: Generar, email: str = Depends(sesion)):
    t = _del_usuario(c.lote, email)
    if t["estado"] != "subiendo":
        raise HTTPException(409, "Este lote ya se generó o se está generando.")
    orden = c.orden.model_dump()
    for p in PARTES:
        ids = orden[p]
        if not ids:
            raise HTTPException(400, f"Falta al menos un clip en {p}.")
        if len(set(ids)) != len(ids):
            raise HTTPException(400, f"Hay un clip repetido en {p}.")
        for i in ids:
            cl = t["clips"].get(i)
            if not cl or cl.get("parte") != p or cl.get("estado") != "listo":
                raise HTTPException(400, f"Un clip de {p} no terminó de subir.")
    combos = _armar_combos(t, orden)
    if len(combos) > TOPE_COMBOS:
        raise HTTPException(400, f"Son {len(combos)} videos; el máximo es {TOPE_COMBOS}. Quita alguno.")
    # espacio: cada combinación pesa a lo más lo de sus tres clips; más el zip final
    necesario = sum(t["clips"][x["hook"]]["tam"] + t["clips"][x["desarrollo"]]["tam"] + t["clips"][x["cta"]]["tam"]
                    for x in combos) * 2
    if _libre() < necesario + MARGEN_DISCO:
        raise HTTPException(507, f"No hay espacio para generar {len(combos)} videos ahora. Avísale a Nicolás.")

    def poner(x: Dict[str, Any]) -> None:
        x.update(estado="generando", combos=combos, progreso=0, orden=orden)

    _actualizar(c.lote, poner)
    _lanzar(c.lote)
    return {"ok": True, "combos": combos}


# ─────────────────────────── ffmpeg ───────────────────────────

def _dimensiones(v: Dict[str, Any]) -> tuple:
    """Ancho y alto como se VEN (una rotación de 90/270 de un celular los invierte)."""
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    giro = 0
    for s in v.get("side_data_list") or []:
        if "rotation" in s:
            giro = abs(int(float(s["rotation"])))
    with contextlib.suppress(Exception):
        giro = giro or abs(int(float((v.get("tags") or {}).get("rotate", 0))))
    return (h, w) if giro % 180 == 90 else (w, h)


def _fps(v: Dict[str, Any]) -> float:
    for k in ("avg_frame_rate", "r_frame_rate"):
        try:
            a, b = str(v.get(k) or "0/1").split("/")
            f = float(a) / float(b)
        except Exception:
            continue
        if 1 <= f <= 120:
            return round(f, 3)
    return 30.0


def _rutas(lid: str, combo: Dict[str, Any]) -> List[Path]:
    return [_lote_dir(lid) / "partes" / f"{combo[p]}.src" for p in PARTES]


async def _correr(args: List[str], duracion: float, cb) -> None:
    cmd = cap._prefijo() + ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1",
                            "-nostats"] + args
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    errores = bytearray()

    async def vaciar() -> None:
        while True:
            b = await p.stderr.read(65536)
            if not b:
                return
            errores.extend(b)
            if len(errores) > 16384:
                del errores[:-8192]

    lector = asyncio.create_task(vaciar())
    resto, mayor, ultimo = b"", -1, time.monotonic()
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
                for ln in lineas:
                    s = ln.decode(errors="ignore").strip()
                    if s.startswith(("out_time_us=", "out_time_ms=")):
                        with contextlib.suppress(ValueError):
                            us = int(s.split("=", 1)[1])
                            if us > mayor:
                                mayor, ultimo = us, time.monotonic()
                                if duracion > 0:
                                    cb(min(99, int(us / 1_000_000 * 100 / duracion)))
            if time.monotonic() - ultimo > SIN_AVANCE_SEG:
                with contextlib.suppress(Exception):
                    p.kill()
                await p.wait()
                raise cap.FallaFfmpeg("ffmpeg pasó 20 minutos sin avanzar (un clip puede estar dañado)")
        codigo = await p.wait()
        await lector
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            p.kill()
        raise
    finally:
        if not lector.done():
            lector.cancel()
    tipo = cap._por_senal(codigo)
    if tipo:
        raise cap.Interrumpido(tipo, codigo)
    if codigo != 0:
        cola = bytes(errores).decode(errors="ignore").strip().splitlines()[-3:]
        log.warning("videos: ffmpeg salió con %s: %s", codigo, " | ".join(cola))
        raise cap.FallaFfmpeg("No se pudieron unir los clips (alguno puede estar dañado o en un formato no soportado)")


def _escapar_lista(ruta: Path) -> str:
    return "file '" + str(ruta).replace("'", "'\\''") + "'"


async def _unir(lid: str, combo: Dict[str, Any], destino: Path, cb) -> str:
    rutas = _rutas(lid, combo)
    infos = [await cap._sondear(r) for r in rutas]
    if any(not cap._videos(i) for i in infos):
        raise cap.FallaFfmpeg("Un clip no se puede leer.")
    duracion = sum(cap._duracion(i) for i in infos)
    tmp = destino.with_name(f".{destino.stem}.{os.getpid()}.tmp.mp4")
    with contextlib.suppress(Exception):
        tmp.unlink()
    # Siempre se recodifica en UNA pasada (nunca copia): así la unión no se nota. Una copia exacta
    # deja saltos en las uniones: silencio o un clic al inicio del audio AAC, imagen y sonido
    # corridos, y cambios de color si un clip viene en otra matriz o rango.
    hook = cap._videos(infos[0])[0]
    W, H = _dimensiones(hook)
    W, H, F = W - W % 2, H - H % 2, _fps(hook)
    args, partes_f = [], []
    for i, (r, info) in enumerate(zip(rutas, infos)):
        args += ["-i", str(r)]
        v = cap._videos(info)[0]
        try:
            dur = float(v.get("duration") or 0) or cap._duracion(info)
        except (TypeError, ValueError):
            dur = cap._duracion(info)
        dur = max(dur, 0.1)
        partes_f.append(f"[{i}:v:0]scale={W}:{H}:force_original_aspect_ratio=decrease:out_color_matrix=bt709:"
                        f"out_range=tv,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={F},format=yuv420p,"
                        f"trim=0:{dur:.3f},setpts=PTS-STARTPTS[v{i}]")
        # El audio de cada clip dura EXACTAMENTE lo que su imagen (se rellena con silencio o se corta) y
        # lleva un fundido de 10 ms en cada borde: sin desfase acumulado y sin clics en las uniones.
        if cap._audios(info):
            origen = f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo"
        else:
            origen = "anullsrc=r=48000:cl=stereo"
        partes_f.append(f"{origen},apad=whole_dur={dur:.3f},atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                        f"afade=t=in:d=0.01,afade=t=out:st={max(dur - 0.01, 0):.3f}:d=0.01[a{i}]")
    enlace = "".join(f"[v{i}][a{i}]" for i in range(len(rutas)))
    partes_f.append(f"{enlace}concat=n={len(rutas)}:v=1:a=1[v][a]")
    await _correr(args + ["-filter_complex", ";".join(partes_f), "-map", "[v]", "-map", "[a]",
                          "-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p",
                          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                          "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(tmp)], duracion, cb)
    modo = f"{W}×{H} · {F:g} fps (como el hook), unión sin cortes visibles"
    os.replace(tmp, destino)
    return modo


def _armar_zip(lid: str, t: Dict[str, Any]) -> Optional[str]:
    """Un solo ZIP con todo lo que salió bien. Sin compresión: un mp4 ya viene comprimido y
    comprimirlo otra vez solo gasta tiempo."""
    d = _lote_dir(lid)
    listos = [c for c in t["combos"] if c["estado"] == "listo"]
    if not listos:
        return None
    tmp = d / f"zip.{os.getpid()}.tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for c in listos:
            z.write(d / "salida" / c["archivo"], arcname=c["archivo"])
    os.replace(tmp, d / "videos.zip")
    return "videos.zip"


async def _procesar(lid: str) -> None:
    d = _lote_dir(lid)
    (d / "salida").mkdir(exist_ok=True)
    t = _leer(lid)
    if not t:
        return
    for combo in t["combos"]:
        if combo["estado"] == "listo" and (d / "salida" / combo["archivo"]).exists():
            continue
        cid = combo["id"]

        def marcar(**kw: Any) -> None:
            _actualizar(lid, lambda x: next(c for c in x["combos"] if c["id"] == cid).update(**kw))

        marcar(estado="generando", progreso=0, detalle="esperando turno")
        try:
            cap.DIR_TRABAJOS.mkdir(parents=True, exist_ok=True)
            async with cap._turno_ffmpeg():
                marcar(detalle="uniendo")
                ultimo = [0.0]

                def avance(pct: int) -> None:
                    if time.time() - ultimo[0] > 2:
                        ultimo[0] = time.time()
                        marcar(progreso=pct, detalle=f"{pct} %")

                modo = await _unir(lid, combo, d / "salida" / combo["archivo"], avance)
            marcar(estado="listo", progreso=100, detalle=modo)
        except cap.Interrumpido:
            log.warning("videos: %s interrumpido (reinicio); el vigía lo retoma", lid)
            marcar(estado="pendiente", detalle="se retoma solo")
            return
        except Exception as e:  # noqa: BLE001
            log.warning("videos: falló %s/%s: %s", lid, cid, e)
            marcar(estado="error", detalle=str(e)[:200] or "falló")
    t = _leer(lid) or t
    nombre_zip = await asyncio.to_thread(_armar_zip, lid, t)
    ok = nombre_zip is not None

    def cerrar(x: Dict[str, Any]) -> None:
        x.update(estado="listo" if ok else "error", zip=nombre_zip, progreso=100)

    _actualizar(lid, cerrar)


def _lanzar(lid: str) -> None:
    if lid in _en_curso:
        return
    _en_curso.add(lid)

    async def correr() -> None:
        # bc-api corre con 2 procesos y los dos tienen vigía: un candado por lote asegura que
        # solo uno lo genere (si el proceso muere, el sistema suelta el candado solo).
        fd = None
        try:
            fd = os.open(_lote_dir(lid) / ".generando", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            await _procesar(lid)
        except Exception:  # noqa: BLE001
            log.exception("videos: falló el lote %s", lid)
            _actualizar(lid, lambda x: x.update(estado="error"))
        finally:
            if fd is not None:
                os.close(fd)
            _en_curso.discard(lid)

    tarea = asyncio.create_task(correr())
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)


# ─────────────────────────── descarga ───────────────────────────

@router.get("/descargar/{lid}/zip")
async def descargar_zip(lid: str, email: str = Depends(sesion)):
    t = _del_usuario(lid, email)
    ruta = _lote_dir(lid) / "videos.zip"
    if t.get("estado") != "listo" or not ruta.exists():
        raise HTTPException(409, "Los videos todavía no están listos.")
    return FileResponse(ruta, media_type="application/zip", filename="videos-bigcapital.zip")


@router.get("/descargar/{lid}/video")
async def descargar_video(lid: str, combo: str, email: str = Depends(sesion)):
    t = _del_usuario(lid, email)
    c = next((x for x in t["combos"] if x["id"] == combo and x["estado"] == "listo"), None)
    ruta = _lote_dir(lid) / "salida" / (c or {}).get("archivo", "")
    if not c or not ruta.exists():
        raise HTTPException(404, "Ese video no está listo.")
    return FileResponse(ruta, media_type="video/mp4", filename=c["archivo"])


# ─────────────────────────── vigía y limpieza ───────────────────────────

def _barrer() -> None:
    base = DIR / "lotes"
    if not base.is_dir():
        return
    ahora = time.time()
    for d in base.iterdir():
        try:
            t = json.loads((d / "lote.json").read_text())
            edad = ahora - t.get("actualizado", 0)
            if edad > VIDA_SEG or (t.get("estado") == "subiendo" and edad > VIDA_SUBIENDO_SEG):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            if ahora - d.stat().st_mtime > VIDA_SEG:
                shutil.rmtree(d, ignore_errors=True)


async def _vigia() -> None:
    ultimo_barrido = 0.0
    while True:
        try:
            if time.time() - ultimo_barrido > BARRIDO_SEG:
                await asyncio.to_thread(_barrer)
                ultimo_barrido = time.time()
            base = DIR / "lotes"
            if base.is_dir():
                for d in base.iterdir():
                    t = _leer(d.name) if ID_LOTE.fullmatch(d.name) else None
                    if t and t.get("estado") == "generando" and d.name not in _en_curso:
                        _lanzar(d.name)
        except Exception:  # noqa: BLE001
            log.exception("videos: falló el vigía")
        await asyncio.sleep(VIGIA_SEG)


@router.on_event("startup")
async def _arrancar_vigia() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tarea = asyncio.create_task(_vigia())
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
