"""Webhook de Zadarma (telefonía de las setters).

GET  /webhooks/zadarma?zd_echo=…  → saludo de validación que pide Zadarma al registrar la URL.
POST /webhooks/zadarma?k=<token>   → notificaciones de llamadas y transcripciones.

Barreras: token secreto en la URL, firma HMAC por evento y la IP de origen
(185.45.152.40/30) según `zadarma_ip_mode`. Responde rápido; la evaluación de las
llamadas la hace un job aparte. Nunca se registra el cuerpo (trae teléfonos).
"""
from __future__ import annotations

import logging
import secrets

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import current_user, lector_informes
from ..models.llamada import Llamada
from ..models import Usuario
from ..services import gestion_setters, zadarma
from ..settings import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
consulta = APIRouter(prefix="/llamadas", tags=["llamadas"], dependencies=[Depends(lector_informes)])
mias = APIRouter(prefix="/mis-llamadas", tags=["llamadas"])


def _resumen(ll: Llamada) -> dict:
    ev = ll.evaluacion or {}
    return {
        "id": ll.id, "setter": ll.setter, "anexo": ll.anexo, "sentido": ll.sentido,
        "numero_cliente": ll.numero_cliente, "numero_linea": ll.numero_linea,
        "inicio": ll.inicio.isoformat() if ll.inicio else None, "duracion_s": ll.duracion_s,
        "resultado": ll.resultado, "estado": ll.estado, "puntaje": ll.puntaje,
        "resultado_llamada": ev.get("resultado_llamada"), "tiene_grabacion": bool(ll.call_id_con_grabacion),
    }


def _filtrar(q, setter: Optional[str], desde: Optional[date], hasta: Optional[date]):
    if setter:
        q = q.filter(Llamada.setter == setter)
    if desde:
        q = q.filter(Llamada.inicio >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        q = q.filter(Llamada.inicio < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
    return q


@consulta.get("")
def listar_llamadas(setter: Optional[str] = None, desde: Optional[date] = None, hasta: Optional[date] = None,
                    limite: int = 300, db: Session = Depends(get_db)):
    q = _filtrar(db.query(Llamada), setter, desde, hasta)
    filas = q.order_by(Llamada.inicio.desc().nullslast(), Llamada.id.desc()).limit(max(1, min(limite, 1000))).all()
    return [_resumen(ll) for ll in filas]


@consulta.get("/resumen")
def resumen_por_setter(desde: Optional[date] = None, hasta: Optional[date] = None, db: Session = Depends(get_db)):
    q = _filtrar(db.query(Llamada), None, desde, hasta)
    por = {}
    for ll in q.all():
        s = por.setdefault(ll.setter or "Sin identificar", {"setter": ll.setter or "Sin identificar", "llamadas": 0,
                                                           "contestadas": 0, "evaluadas": 0, "agendadas": 0, "_suma": 0.0})
        s["llamadas"] += 1
        s["contestadas"] += 1 if ll.resultado == "answered" else 0
        if ll.estado == "ok" and ll.puntaje is not None:
            s["evaluadas"] += 1
            s["_suma"] += ll.puntaje
        if (ll.evaluacion or {}).get("resultado_llamada") == "agendo":
            s["agendadas"] += 1
    out = []
    for s in por.values():
        s["puntaje_promedio"] = round(s.pop("_suma") / s["evaluadas"], 1) if s["evaluadas"] else None
        out.append(s)
    return sorted(out, key=lambda s: s["setter"])


@consulta.get("/gestion")
def gestion(fecha: Optional[date] = None, db: Session = Depends(get_db)):
    return gestion_setters.gestion_dia(db, fecha or date.today())


@consulta.get("/gestion/rango")
def gestion_rango(desde: date, hasta: date, db: Session = Depends(get_db)):
    return gestion_setters.gestion_rango(db, desde, hasta)


@consulta.get("/horarios")
def horarios(desde: date, hasta: date, db: Session = Depends(get_db)):
    return gestion_setters.mejor_horario(db, desde, hasta)


@consulta.get("/{llamada_id}")
def detalle_llamada(llamada_id: int, db: Session = Depends(get_db)):
    ll = db.get(Llamada, llamada_id)
    if not ll:
        raise HTTPException(404, "Llamada no encontrada")
    return {**_resumen(ll), "transcripcion_frases": ll.transcripcion_frases or [],
            "evaluacion": ll.evaluacion, "version_pauta": ll.version_pauta,
            "evaluada_en": ll.evaluada_en.isoformat() if ll.evaluada_en else None}


@consulta.get("/{llamada_id}/grabacion")
def grabacion_llamada(llamada_id: int, db: Session = Depends(get_db)):
    ll = db.get(Llamada, llamada_id)
    if not ll:
        raise HTTPException(404, "Llamada no encontrada")
    if not (settings.zadarma_api_key and settings.zadarma_api_secret):
        raise HTTPException(503, "Zadarma no configurado")
    try:
        link = zadarma.enlace_grabacion(ll.call_id_con_grabacion, ll.pbx_call_id)
    except Exception as e:
        log.warning("zadarma: no se pudo pedir la grabación id=%s (%s)", llamada_id, type(e).__name__)
        raise HTTPException(502, "Zadarma no entregó la grabación")
    if not link:
        raise HTTPException(404, "La llamada no tiene grabación")
    return {"link": link}


@router.get("/zadarma", response_class=PlainTextResponse)
def zadarma_echo(zd_echo: str = ""):
    return zd_echo[:200] if zd_echo else "ok"


@router.post("/zadarma", response_class=PlainTextResponse)
async def zadarma_webhook(request: Request, k: str = "", db: Session = Depends(get_db)):
    if not settings.zadarma_webhook_token or not settings.zadarma_api_secret:
        raise HTTPException(503, "Webhook de Zadarma no configurado")
    if not secrets.compare_digest(k, settings.zadarma_webhook_token):
        raise HTTPException(403, "Token inválido")

    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    if settings.zadarma_ip_mode != "off" and not zadarma.ip_es_de_zadarma(ip):
        if settings.zadarma_ip_mode == "enforce":
            raise HTTPException(403, "Origen no permitido")
        log.warning("zadarma: notificación desde IP fuera del rango esperado")

    datos = {k_: str(v) for k_, v in (await request.form()).items()}
    evento = (datos.get("event") or "").strip().upper()
    pbx = datos.get("pbx_call_id", "")

    firma_ok = zadarma.verificar_firma(evento, datos, request.headers.get("signature", ""), settings.zadarma_api_secret)
    if firma_ok is False:
        log.warning("zadarma: firma inválida evento=%s pbx_call_id=%s", evento, pbx)
        raise HTTPException(403, "Firma inválida")

    zadarma.aplicar_evento(db, evento or "DESCONOCIDO", datos)
    db.commit()
    log.info("zadarma: evento=%s pbx_call_id=%s", evento, pbx)
    return "ok"


# ── Vista de cada setter: solo sus propias llamadas ──────────────────────────
def _anexo_propio(anexo: Optional[str] = None, user: Usuario = Depends(current_user)) -> str:
    # Vista previa: un super admin puede ver la página de una setter con ?anexo=102.
    email = user.email.lower()
    if anexo and (user.is_admin or email in settings.super_admins_list):
        if anexo not in settings.zadarma_anexos_map:
            raise HTTPException(404, "Anexo no configurado")
        return anexo
    anexo = settings.zadarma_correos_map.get(email)
    if not anexo:
        raise HTTPException(403, "Esta vista es solo para las setters")
    return anexo


def _propia(db: Session, llamada_id: int, anexo: str) -> Llamada:
    ll = db.get(Llamada, llamada_id)
    if not ll or ll.anexo != anexo:
        raise HTTPException(404, "Llamada no encontrada")
    return ll


@mias.get("/gestion")
def mi_gestion(fecha: Optional[date] = None, anexo: str = Depends(_anexo_propio), db: Session = Depends(get_db)):
    return gestion_setters.gestion_dia(db, fecha or date.today(), [anexo])[0]


@mias.get("/gestion/rango")
def mi_gestion_rango(desde: date, hasta: date, anexo: str = Depends(_anexo_propio), db: Session = Depends(get_db)):
    return gestion_setters.gestion_rango(db, desde, hasta, [anexo])


@mias.get("")
def mis_llamadas(desde: Optional[date] = None, hasta: Optional[date] = None,
                 anexo: str = Depends(_anexo_propio), db: Session = Depends(get_db)):
    q = _filtrar(db.query(Llamada).filter(Llamada.anexo == anexo), None, desde, hasta)
    return [_resumen(ll) for ll in q.order_by(Llamada.inicio.desc().nullslast()).limit(300).all()]


@mias.get("/{llamada_id}")
def mi_llamada(llamada_id: int, anexo: str = Depends(_anexo_propio), db: Session = Depends(get_db)):
    return detalle_llamada(_propia(db, llamada_id, anexo).id, db)


@mias.get("/{llamada_id}/grabacion")
def mi_grabacion(llamada_id: int, anexo: str = Depends(_anexo_propio), db: Session = Depends(get_db)):
    return grabacion_llamada(_propia(db, llamada_id, anexo).id, db)
