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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import zadarma
from ..settings import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


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
