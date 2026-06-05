"""Notificaciones por email de cambios de stock/proyectos (Fase 2).

Reusa las MISMAS credenciales SMTP del dashboard de brokers (mismos env:
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS). Si no están configuradas, el
envío es NO-OP silencioso (no rompe nada hasta que el .env las tenga).

Se invoca como FastAPI BackgroundTask → corre DESPUÉS de responder, no bloquea
la API, y traga cualquier error (una falla de correo nunca debe romper un guardado).
"""
from __future__ import annotations
import smtplib
import logging
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from ..settings import settings

log = logging.getLogger("bcapi.mail")

# Sello horario aprox. zona Chile (no crítico; evita depender de tzdata).
_CL_TZ = timezone(timedelta(hours=-4))


def _configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_pass)


def _fecha_cl() -> str:
    return datetime.now(_CL_TZ).strftime("%d/%m/%Y · %H:%M")


def _esc(s: str) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _html(titulo: str, proyecto: str, detalle: str, proyecto_id: str) -> str:
    ver_url = f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto.html?id={proyecto_id}"
    return f"""<div style="font-family:Inter,Arial,sans-serif;background:#f4f6f9;padding:24px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e6e9ef">
    <div style="background:#0e1b2c;padding:18px 24px">
      <span style="color:#7DC242;font-weight:700;font-size:18px">BigCapital</span><span style="color:#9fb0c7;font-size:13px"> · Stock</span>
    </div>
    <div style="padding:24px">
      <h2 style="margin:0 0 8px;font-size:18px;color:#0e1b2c">{_esc(titulo)}</h2>
      <p style="margin:0 0 4px;font-size:15px;color:#0e1b2c"><b>{_esc(proyecto)}</b></p>
      <p style="margin:0 0 18px;font-size:14px;color:#55657a;line-height:1.5">{_esc(detalle)}</p>
      <a href="{ver_url}" style="display:inline-block;background:#7DC242;color:#fff;text-decoration:none;padding:10px 22px;border-radius:8px;font-weight:600;font-size:14px">Ver proyecto</a>
      <p style="margin:18px 0 0;font-size:12px;color:#9fb0c7">{_fecha_cl()} · Notificación automática · Stock BigCapital</p>
    </div>
  </div>
</div>"""


def notify_change(titulo: str, proyecto: str, detalle: str, proyecto_id: str) -> None:
    """Envía una notificación de cambio al admin (settings.notify_to).

    NO-OP si SMTP no está configurado. Traga errores (corre como BackgroundTask).
    """
    if not _configured():
        log.info("SMTP no configurado — notificación '%s' (%s) NO enviada.", titulo, proyecto)
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"{titulo} · {proyecto}"
        msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
        msg["To"] = settings.notify_to
        msg["Reply-To"] = settings.smtp_from
        msg.set_content(f"{titulo}\n{proyecto}\n{detalle}\n{_fecha_cl()}")
        msg.add_alternative(_html(titulo, proyecto, detalle, proyecto_id), subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)
        log.info("Notificación '%s' (%s) enviada a %s", titulo, proyecto, settings.notify_to)
    except Exception as e:
        log.warning("Error enviando notificación '%s' (%s): %s", titulo, proyecto, e)
