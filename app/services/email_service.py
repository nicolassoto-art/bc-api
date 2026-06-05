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


def _stock_cc() -> str:
    """CC ('en copia') de las notificaciones de STOCK: el equipo (Pamela, Álvaro).
    El destinatario principal (To) es notify_to. Coma-separado en NOTIFY_STOCK_CC.
    Excluye a notify_to para no duplicar. Los tickets/diagnóstico no llevan CC."""
    raw = (settings.notify_stock_cc or "")
    to = settings.notify_to.strip().lower()
    return ", ".join([e.strip() for e in raw.split(",") if e.strip() and e.strip().lower() != to])


def notify_change(titulo: str, proyecto: str, detalle: str, proyecto_id: str) -> None:
    """Notificación de cambio de stock: To = admin (notify_to), Cc = equipo (notify_stock_cc).

    NO-OP si SMTP no está configurado. Traga errores (corre como BackgroundTask).
    """
    if not _configured():
        log.info("SMTP no configurado — notificación '%s' (%s) NO enviada.", titulo, proyecto)
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"{titulo} · {proyecto}"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        msg["To"] = settings.notify_to
        _cc = _stock_cc()
        if _cc:
            msg["Cc"] = _cc
        msg["Reply-To"] = from_addr
        msg.set_content(f"{titulo}\n{proyecto}\n{detalle}\n{_fecha_cl()}")
        msg.add_alternative(_html(titulo, proyecto, detalle, proyecto_id), subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))  # Gmail App Password sin espacios
            s.send_message(msg)
        log.info("Notificación '%s' (%s) → To:%s Cc:%s", titulo, proyecto, settings.notify_to, _stock_cc())
    except Exception as e:
        log.warning("Error enviando notificación '%s' (%s): %s", titulo, proyecto, e)


def notify_ticket(autor: str, page_url: str, descripcion: str, tiene_captura: bool = False) -> None:
    """Email inmediato al admin por un nuevo ticket de reporte de falla (Fase 5).

    NO-OP si SMTP no está configurado. Traga errores (corre como BackgroundTask).
    """
    if not _configured():
        log.info("SMTP no configurado — ticket de %s NO notificado.", autor)
        return
    try:
        panel = "https://herramientas.bigcapital.cl/tickets.html"
        cap_txt = " · incluye captura" if tiene_captura else ""
        html = f"""<div style="font-family:Inter,Arial,sans-serif;background:#f4f6f9;padding:24px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e6e9ef">
    <div style="background:#0e1b2c;padding:18px 24px">
      <span style="color:#7DC242;font-weight:700;font-size:18px">BigCapital</span><span style="color:#9fb0c7;font-size:13px"> · Reporte de falla</span>
    </div>
    <div style="padding:24px">
      <h2 style="margin:0 0 8px;font-size:18px;color:#0e1b2c">🐞 Nuevo reporte de falla{_esc(cap_txt)}</h2>
      <p style="margin:0 0 4px;font-size:14px;color:#55657a">Reportó: <b style="color:#0e1b2c">{_esc(autor)}</b></p>
      <p style="margin:0 0 12px;font-size:13px;color:#9fb0c7;word-break:break-word">Página: {_esc(page_url or '—')}</p>
      <div style="background:#f4f6f9;border-radius:8px;padding:14px;font-size:14px;color:#0e1b2c;line-height:1.5;white-space:pre-wrap;word-break:break-word">{_esc(descripcion)}</div>
      <a href="{panel}" style="display:inline-block;margin-top:18px;background:#7DC242;color:#fff;text-decoration:none;padding:10px 22px;border-radius:8px;font-weight:600;font-size:14px">Ver tickets</a>
      <p style="margin:18px 0 0;font-size:12px;color:#9fb0c7">{_fecha_cl()} · Reporte automático · Herramientas BigCapital</p>
    </div>
  </div>
</div>"""
        msg = EmailMessage()
        msg["Subject"] = "🐞 Nuevo reporte de falla · Herramientas"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        msg["To"] = settings.notify_to
        msg["Reply-To"] = from_addr
        msg.set_content(
            f"Nuevo reporte de falla\nReportó: {autor}\nPágina: {page_url or '—'}\n\n{descripcion}\n\nPanel: {panel}\n{_fecha_cl()}"
        )
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        log.info("Ticket de %s notificado a %s", autor, settings.notify_to)
    except Exception as e:
        log.warning("Error notificando ticket de %s: %s", autor, e)


def status() -> dict:
    """Estado de la config SMTP (sin exponer la contraseña). Para diagnóstico."""
    return {
        "configured": _configured(),
        "host": settings.smtp_host or "(vacío)",
        "port": settings.smtp_port,
        "user": settings.smtp_user or "(vacío)",
        "pass_set": bool(settings.smtp_pass),
        "from": (settings.smtp_from or settings.smtp_user) or "(vacío)",
        "to": settings.notify_to,
    }


def test_send(to: str | None = None) -> dict:
    """Envía un correo de prueba SÍNCRONO y devuelve el resultado (diagnóstico)."""
    st = status()
    if not _configured():
        return {**st, "sent": False, "error": "SMTP no configurado: faltan SMTP_HOST/SMTP_USER/SMTP_PASS en el .env de bc-api."}
    dest = to or settings.notify_to
    from_addr = settings.smtp_from or settings.smtp_user
    try:
        msg = EmailMessage()
        msg["Subject"] = "Prueba de notificaciones · Stock BigCapital"
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        msg["To"] = dest
        msg["Reply-To"] = from_addr
        msg.set_content("Prueba de envío desde bc-api. Si recibes esto, las notificaciones de stock funcionan.")
        msg.add_alternative(_html("Prueba de notificaciones ✅", "Stock BigCapital",
                                  "Si recibes este correo, el envío automático de notificaciones quedó funcionando.", ""),
                            subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        return {**st, "sent": True, "error": None, "dest": dest}
    except Exception as e:
        return {**st, "sent": False, "error": f"{type(e).__name__}: {e}", "dest": dest}
