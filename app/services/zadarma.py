"""Zadarma: verificación de notificaciones, armado de llamadas y firma de la API.

Firmas (documentación de Zadarma, sección Webhook). El ejemplo oficial en PHP es
`base64_encode(hash_hmac('sha1', <campos>, API_SECRET))`: `hash_hmac` devuelve el
HEX, así que se codifica en base64 el texto hexadecimal, no los bytes crudos. Se
aceptan ambas variantes por si Zadarma cambia el cálculo.

`SPEECH_RECOGNITION` no trae fórmula documentada: para ese evento la barrera es el
token secreto de la URL (y la IP de origen).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models.llamada import Llamada, ZadarmaEvento
from ..settings import settings

log = logging.getLogger(__name__)

RED_ZADARMA = ipaddress.ip_network("185.45.152.40/30")

# Campos que entran en la firma de cada evento, en orden.
CAMPOS_FIRMA: dict[str, tuple[str, ...]] = {
    "NOTIFY_START": ("caller_id", "called_did", "call_start"),
    "NOTIFY_INTERNAL": ("caller_id", "called_did", "call_start"),
    "NOTIFY_END": ("caller_id", "called_did", "call_start"),
    "NOTIFY_ANSWER": ("caller_id", "destination", "call_start"),
    "NOTIFY_OUT_START": ("internal", "destination", "call_start"),
    "NOTIFY_OUT_END": ("internal", "destination", "call_start"),
    "NOTIFY_RECORD": ("pbx_call_id", "call_id_with_rec"),
}


# ── Firmas ───────────────────────────────────────────────────────────────────
def _hmac_b64_variantes(secret: str, mensaje: str) -> tuple[str, str]:
    mac = hmac.new(secret.encode(), mensaje.encode(), hashlib.sha1)
    return (
        base64.b64encode(mac.hexdigest().encode()).decode(),  # como el PHP oficial
        base64.b64encode(mac.digest()).decode(),               # bytes crudos
    )


def firma_evento(evento: str, datos: dict, secret: str) -> Optional[str]:
    """Firma esperada (variante PHP) o None si el evento no tiene fórmula."""
    campos = CAMPOS_FIRMA.get(evento)
    if campos is None:
        return None
    return _hmac_b64_variantes(secret, "".join(str(datos.get(c, "")) for c in campos))[0]


def verificar_firma(evento: str, datos: dict, firma: str, secret: str) -> Optional[bool]:
    """True/False según la firma; None si el evento no tiene fórmula documentada."""
    campos = CAMPOS_FIRMA.get(evento)
    if campos is None:
        return None
    if not firma:
        return False
    mensaje = "".join(str(datos.get(c, "")) for c in campos)
    return any(hmac.compare_digest(firma, v) for v in _hmac_b64_variantes(secret, mensaje))


def firma_api(metodo: str, params: dict, secret: str) -> str:
    """Firma de la API REST: base64(hex(HMAC-SHA1(metodo + query + md5(query))))."""
    query = urlencode(sorted((k, str(v)) for k, v in params.items()))
    mensaje = metodo + query + hashlib.md5(query.encode()).hexdigest()
    return _hmac_b64_variantes(secret, mensaje)[0]


API_ZADARMA = "https://api.zadarma.com"


def llamar_api(verbo: str, metodo: str, params: dict) -> dict:
    """Llamada firmada a la API REST de Zadarma. Lanza si falla."""
    import httpx
    cabecera = {"Authorization": f"{settings.zadarma_api_key}:{firma_api(metodo, params, settings.zadarma_api_secret)}"}
    if verbo == "GET":
        r = httpx.get(API_ZADARMA + metodo, params=params, headers=cabecera, timeout=20)
    elif verbo == "PUT":
        r = httpx.put(API_ZADARMA + metodo, data=params, headers=cabecera, timeout=20)
    else:
        r = httpx.post(API_ZADARMA + metodo, data=params, headers=cabecera, timeout=20)
    r.raise_for_status()
    return r.json()


def enlace_grabacion(call_id: Optional[str], pbx_call_id: Optional[str], segundos: int = 600) -> Optional[str]:
    """Enlace temporal para escuchar la grabación (no se guarda: vence)."""
    params = {"lifetime": max(180, segundos)}
    if call_id:
        params["call_id"] = call_id
    elif pbx_call_id:
        params["pbx_call_id"] = pbx_call_id
    else:
        return None
    r = llamar_api("GET", "/v1/pbx/record/request/", params)
    if r.get("link"):
        return r["link"]
    links = r.get("links") or []
    return links[0] if links else None


def ip_es_de_zadarma(ip: Optional[str]) -> bool:
    try:
        return ipaddress.ip_address((ip or "").strip()) in RED_ZADARMA
    except ValueError:
        return False


# ── Armado de llamadas ───────────────────────────────────────────────────────
def _fecha(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _entero(valor) -> Optional[int]:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _anexo(*candidatos: Optional[str]) -> Optional[str]:
    """Primer valor con forma de anexo (3 dígitos, p. ej. '102')."""
    for c in candidatos:
        c = (c or "").strip()
        if c.isdigit() and len(c) <= 4:
            return c
    return None


def _frases(resultado) -> list[dict]:
    """Normaliza `result` de SPEECH_RECOGNITION a [{"canal": n, "texto": "…"}]."""
    if isinstance(resultado, str):
        try:
            resultado = json.loads(resultado)
        except ValueError:
            return [{"canal": None, "texto": resultado}] if resultado.strip() else []
    if not isinstance(resultado, dict):
        return []
    out = []
    for f in resultado.get("phrases") or []:
        if isinstance(f, dict) and (f.get("result") or "").strip():
            out.append({"canal": f.get("channel"), "texto": f["result"].strip()})
    return out


def _upsert(db: Session, pbx_call_id: str, campos: dict, pasar_a_pendiente: bool = False) -> None:
    """Crea o completa la fila de la llamada sin pisar datos con vacíos."""
    ahora = datetime.utcnow()
    campos = {k: v for k, v in campos.items() if v is not None}
    stmt = insert(Llamada).values(
        pbx_call_id=pbx_call_id, created_at=ahora, updated_at=ahora,
        estado="pendiente" if pasar_a_pendiente else "nuevo", intentos=0, **campos,
    )
    actualizar = {**campos, "updated_at": ahora}
    if pasar_a_pendiente:
        tabla = Llamada.__table__
        actualizar["estado"] = case((tabla.c.estado == "nuevo", "pendiente"), else_=tabla.c.estado)
    db.execute(stmt.on_conflict_do_update(index_elements=["pbx_call_id"], set_=actualizar))


def aplicar_evento(db: Session, evento: str, d: dict) -> None:
    """Registra el evento crudo y actualiza la llamada. No hace commit."""
    pbx = (d.get("pbx_call_id") or "").strip() or None
    db.add(ZadarmaEvento(evento=evento, pbx_call_id=pbx, payload=d))
    if not pbx:
        return
    anexos = settings.zadarma_anexos_map

    def con_setter(campos: dict) -> dict:
        if campos.get("anexo"):
            campos["setter"] = anexos.get(campos["anexo"])
        return campos

    if evento in ("NOTIFY_START", "NOTIFY_INTERNAL"):
        _upsert(db, pbx, con_setter({
            "sentido": "entrante", "numero_cliente": d.get("caller_id"),
            "numero_linea": d.get("called_did"), "inicio": _fecha(d.get("call_start")),
            "anexo": _anexo(d.get("internal")),
        }))
    elif evento == "NOTIFY_ANSWER":
        _upsert(db, pbx, con_setter({"anexo": _anexo(d.get("internal"), d.get("destination"))}))
    elif evento == "NOTIFY_END":
        _upsert(db, pbx, con_setter({
            "sentido": "entrante", "numero_cliente": d.get("caller_id"),
            "numero_linea": d.get("called_did"), "inicio": _fecha(d.get("call_start")),
            "anexo": _anexo(d.get("internal"), d.get("last_internal")),
            "duracion_s": _entero(d.get("duration")), "resultado": d.get("disposition"),
            "call_id_con_grabacion": d.get("call_id_with_rec") or None,
        }))
    elif evento in ("NOTIFY_OUT_START", "NOTIFY_OUT_END"):
        campos = {
            "sentido": "saliente", "numero_cliente": d.get("destination"),
            "inicio": _fecha(d.get("call_start")), "anexo": _anexo(d.get("internal")),
        }
        if evento == "NOTIFY_OUT_END":
            campos.update({
                "numero_linea": d.get("caller_id"), "duracion_s": _entero(d.get("duration")),
                "resultado": d.get("disposition"),
                "call_id_con_grabacion": d.get("call_id_with_rec") or None,
            })
        _upsert(db, pbx, con_setter(campos))
    elif evento == "NOTIFY_RECORD":
        _upsert(db, pbx, {"call_id_con_grabacion": d.get("call_id_with_rec") or None})
    elif evento == "SPEECH_RECOGNITION":
        frases = _frases(d.get("result"))
        texto = "\n".join(f"Canal {f['canal']}: {f['texto']}" for f in frases)
        _upsert(db, pbx, {
            "transcripcion_frases": frases, "transcripcion_texto": texto or None,
            "transcripcion_idioma": d.get("lang"),
            "call_id_con_grabacion": d.get("call_id") or None,
        }, pasar_a_pendiente=bool(frases))


def purgar_eventos(db: Session, dias: int = 30) -> int:
    """Borra los eventos crudos más antiguos que `dias`. Devuelve cuántos borró."""
    limite = datetime.utcnow() - timedelta(days=dias)
    res = db.execute(delete(ZadarmaEvento).where(ZadarmaEvento.recibido_en < limite))
    db.commit()
    return res.rowcount or 0


# ── Sincronización con las estadísticas de Zadarma ───────────────────────────
# Respaldo del webhook: trae las llamadas de la centralita (GET /v1/statistics/pbx/)
# y las transcripciones que falten (GET /v1/speech_recognition/). Idempotente.
ECO = "4444"   # prueba de audio gratuita de Zadarma: no es un anexo ni un cliente


def _ext(valor) -> Optional[str]:
    """'102', 102 o '383974-102' → '102'; un número de teléfono → None."""
    s = str(valor or "").strip()
    if s == ECO:
        return None
    if "-" in s:
        s = s.rsplit("-", 1)[1]
    return s if s.isdigit() and len(s) <= 4 else None


def fila_estadistica_a_campos(f: dict) -> dict:
    """Convierte una fila de /v1/statistics/pbx/ (versión 2) en campos de Llamada."""
    anexo_origen = _ext(f.get("sip")) or _ext(f.get("clid"))
    anexo_destino = _ext(f.get("destination"))
    saliente = bool(anexo_origen) and not anexo_destino
    anexo = anexo_origen if saliente else (anexo_destino or anexo_origen)
    campos = {
        "sentido": "saliente" if saliente else "entrante",
        "anexo": anexo,
        "setter": settings.zadarma_anexos_map.get(anexo or ""),
        "numero_cliente": str(f.get("destination") if saliente else f.get("clid") or "") or None,
        "inicio": _fecha(f.get("callstart")),
        "duracion_s": _entero(f.get("seconds")),
        "resultado": f.get("disposition"),
    }
    if f.get("is_recorded") in (True, "true", 1, "1") and f.get("call_id"):
        campos["call_id_con_grabacion"] = str(f["call_id"])
    return campos


def sincronizar_estadisticas(db: Session, desde: datetime, hasta: datetime) -> int:
    """Upsert de las llamadas del período. Si un pbx_call_id trae varias filas (desvíos,
    menús), se queda con la de mayor duración. Devuelve cuántas llamadas tocó."""
    mejores: dict[str, dict] = {}
    skip = 0
    while True:
        r = llamar_api("GET", "/v1/statistics/pbx/", {
            "start": desde.strftime("%Y-%m-%d %H:%M:%S"), "end": hasta.strftime("%Y-%m-%d %H:%M:%S"),
            "version": 2, "skip": skip, "limit": 1000,
        })
        filas = r.get("stats") or []
        for f in filas:
            pbx = str(f.get("pbx_call_id") or "").strip()
            if not pbx:
                continue
            if pbx not in mejores or (_entero(f.get("seconds")) or 0) > (_entero(mejores[pbx].get("seconds")) or 0):
                mejores[pbx] = f
        if len(filas) < 1000:
            break
        skip += 1000
    for pbx, f in mejores.items():
        _upsert(db, pbx, fila_estadistica_a_campos(f))
    db.commit()
    return len(mejores)


def traer_transcripciones_faltantes(db: Session, limite: int = 20, estados: Optional[dict] = None) -> int:
    """Pide la transcripción de llamadas grabadas y contestadas (20 s o más) que aún no
    la tienen. Si Zadarma la tiene «lista para reconocer», le pide que la reconozca
    (PUT) y se trae en la siguiente pasada. `estados` acumula el estado de cada una."""
    corte = datetime.utcnow() - timedelta(minutes=15)
    pendientes = (
        db.query(Llamada)
        .filter(Llamada.call_id_con_grabacion.isnot(None), Llamada.transcripcion_texto.is_(None),
                Llamada.resultado == "answered", Llamada.duracion_s >= 20, Llamada.created_at < corte)
        .order_by(Llamada.id.desc()).limit(limite).all()
    )
    n = 0
    for ll in pendientes:
        try:
            r = llamar_api("GET", "/v1/speech_recognition/", {"call_id": ll.call_id_con_grabacion})
        except Exception as e:
            if estados is not None:
                estados[f"error {type(e).__name__}"] = estados.get(f"error {type(e).__name__}", 0) + 1
            continue
        st = r.get("recognitionStatus") or "sin estado"
        if estados is not None:
            estados[st] = estados.get(st, 0) + 1
        if st == "ready for recognize":
            try:
                llamar_api("PUT", "/v1/speech_recognition/", {"call_id": ll.call_id_con_grabacion,
                                                               "lang": ll.transcripcion_idioma or "es-MX"})
            except Exception:
                pass
            continue
        if st != "recognized":
            continue
        frases = _frases({"phrases": r.get("phrases") or []})
        if not frases:
            continue
        _upsert(db, ll.pbx_call_id, {
            "transcripcion_frases": frases,
            "transcripcion_texto": "\n".join(f"Canal {f['canal']}: {f['texto']}" for f in frases),
            "transcripcion_idioma": r.get("lang"),
        }, pasar_a_pendiente=True)
        n += 1
    db.commit()
    return n


def sincronizar_job() -> None:
    """Job del programador: últimas 48 h de llamadas + transcripciones faltantes."""
    if not (settings.zadarma_api_key and settings.zadarma_api_secret):
        return
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        ahora = datetime.now()
        n = sincronizar_estadisticas(db, ahora - timedelta(hours=48), ahora)
        t = traer_transcripciones_faltantes(db)
        log.info("zadarma: sincronización %s llamadas, %s transcripciones", n, t)
    except Exception as e:
        db.rollback()
        log.error("zadarma: falló la sincronización (%s)", e, exc_info=True)
    finally:
        db.close()
