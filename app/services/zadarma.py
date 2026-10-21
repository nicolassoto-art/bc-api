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
