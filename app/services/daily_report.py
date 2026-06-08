"""Informe diario de stock — bc-api · 2026-06-08

Disparado por APScheduler L-V 10:00 AM America/Santiago (configurado en main.py).

REEMPLAZA los emails individuales por cada cambio de stock (notify_change quedó
silenciado vía settings.emails_per_change=False). El usuario recibe UN solo email
con:
- Conteos generales (proyectos activos, publicados, stock disponible)
- Cambios de stock de las últimas 24h
- Alertas activas (sin foto, sin GPS verificado y publicado, sin stock)
- Errores del scraper (eventos timeline tipo "Alerta" CRITICO en últimas 24h)

Adicionalmente expone `send_alert_email_if_critical(...)` para que el scraper
pueda emitir un email INMEDIATO cuando algo falla durante una importación.
"""
from __future__ import annotations
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.proyecto import Proyecto
from app.services.email_service import _configured, _fecha_cl
from app.settings import settings

log = logging.getLogger(__name__)

# UTC-3 para Chile (CLT). En invierno chileno es UTC-4 (CLST); el cálculo es solo
# para mostrar la fecha del día en el subject — el cron usa apscheduler con
# timezone='America/Santiago' que maneja el DST correctamente.


def _proyectos_activos(db: Session):
    return (
        db.query(Proyecto)
        .filter(Proyecto.activo == True, Proyecto.deleted_at.is_(None))  # noqa: E712
        .all()
    )


def _disp(unidades):
    return sum(1 for u in (unidades or []) if u.disponible)


def _eventos_24h(p):
    """Eventos del timeline en últimas 24h. Devuelve [{tipo,fecha,detalles}]."""
    tl = (p.extra or {}).get("timeline") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    out = []
    for ev in tl:
        try:
            f = ev.get("fecha", "")
            if not f:
                continue
            # bc-api: timestamps naive UTC. Si no trae Z/offset, asumir UTC.
            if not f.endswith("Z") and "+" not in f[-6:] and "-" not in f[-6:]:
                f = f + "Z"
            dt = datetime.fromisoformat(f.replace("Z", "+00:00"))
            if dt >= cutoff:
                out.append({"tipo": ev.get("tipo", ""), "fecha": dt, "detalles": ev.get("detalles", ""), "usuario": ev.get("usuario", "")})
        except Exception:
            continue
    return out


def build_daily_report(db: Session) -> dict:
    """Arma el resumen del estado del stock para enviar por email."""
    proyectos = _proyectos_activos(db)
    publicados = [p for p in proyectos if (p.extra or {}).get("publicar_en_catalogo")]

    # Conteos
    total_disp = sum(_disp(p.unidades) for p in proyectos)
    total_cargado = sum(len(p.unidades or []) for p in proyectos)

    # Cambios de stock en las últimas 24h (proyectos cuyo stock_updated_at es reciente)
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cambios_24h = [
        p for p in proyectos
        if p.stock_updated_at and p.stock_updated_at >= cutoff_24h
    ]
    cambios_24h.sort(key=lambda x: x.stock_updated_at or datetime.min, reverse=True)

    # Alertas activas (gating del catálogo)
    sin_foto = [p for p in proyectos if not p.foto_principal_url]
    sin_stock = [p for p in proyectos if not (p.unidades and len(p.unidades) > 0)]
    publicados_sin_gps = [p for p in publicados if not (p.extra or {}).get("gps_verificado")]
    publicados_sin_disp = [p for p in publicados if _disp(p.unidades) == 0]

    # Errores del scraper en últimas 24h (eventos tipo 'Alerta')
    errores_24h = []
    for p in proyectos:
        for ev in _eventos_24h(p):
            if ev["tipo"] == "Alerta":
                errores_24h.append({"proyecto": p.nombre, **ev})
    errores_24h.sort(key=lambda x: x["fecha"], reverse=True)

    return {
        "fecha_cl": _fecha_cl(),
        "n_activos": len(proyectos),
        "n_publicados": len(publicados),
        "n_disponibles_total": total_disp,
        "n_unidades_cargadas": total_cargado,
        "cambios_24h": [
            {"id": p.id, "nombre": p.nombre, "disp": _disp(p.unidades), "stock_updated_at": p.stock_updated_at}
            for p in cambios_24h[:15]
        ],
        "n_cambios_24h": len(cambios_24h),
        "alertas": {
            "sin_foto": [{"id": p.id, "nombre": p.nombre} for p in sin_foto[:10]],
            "n_sin_foto": len(sin_foto),
            "sin_stock": [{"id": p.id, "nombre": p.nombre} for p in sin_stock[:10]],
            "n_sin_stock": len(sin_stock),
            "publicados_sin_gps": [{"id": p.id, "nombre": p.nombre} for p in publicados_sin_gps[:10]],
            "n_publicados_sin_gps": len(publicados_sin_gps),
            "publicados_sin_disp": [{"id": p.id, "nombre": p.nombre} for p in publicados_sin_disp[:10]],
            "n_publicados_sin_disp": len(publicados_sin_disp),
        },
        "errores_24h": errores_24h[:15],
        "n_errores_24h": len(errores_24h),
    }


def _row(label: str, value, total: int = 0, color: str = "#0a0d12") -> str:
    """Una fila tipo tarjeta para el resumen."""
    sub = f" <span style='color:#6b7280;font-weight:500'>de {total}</span>" if total else ""
    return f"""
    <tr><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#374151">{escape(label)}</td>
        <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right;color:{color};font-weight:700">{value}{sub}</td></tr>
    """


def _project_link(p: dict, base: str = "https://herramientas.bigcapital.cl") -> str:
    nombre = escape(p.get("nombre") or p.get("id") or "")
    pid = escape(p.get("id") or "")
    return f"<a href='{base}/src/stock-interno/proyecto-vista.html?id={pid}' style='color:#1f7a3d;text-decoration:none'>{nombre}</a>"


def _build_html(data: dict) -> str:
    """HTML del informe diario."""
    al = data["alertas"]

    cambios_html = ""
    if data["cambios_24h"]:
        rows = "".join(
            f"<tr><td style='padding:4px 8px'>{_project_link(p)}</td>"
            f"<td style='padding:4px 8px;text-align:right;color:#1f7a3d;font-weight:700'>{p['disp']} disp.</td></tr>"
            for p in data["cambios_24h"]
        )
        extra = ""
        if data["n_cambios_24h"] > len(data["cambios_24h"]):
            extra = f"<p style='font-size:12px;color:#6b7280;margin:4px 0 0'>… y {data['n_cambios_24h'] - len(data['cambios_24h'])} más</p>"
        cambios_html = f"""
        <h3 style="margin:24px 0 8px;color:#0a0d12">📦 Cambios de stock (últimas 24h)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;background:#f9fafb;border-radius:8px">{rows}</table>
        {extra}
        """
    else:
        cambios_html = "<p style='color:#6b7280;font-size:13px;margin:24px 0 0'>📦 Sin cambios de stock en las últimas 24h.</p>"

    def list_block(title: str, icon: str, items: list, total: int) -> str:
        if not items:
            return ""
        lis = "".join(f"<li style='margin:3px 0'>{_project_link(p)}</li>" for p in items)
        extra = ""
        if total > len(items):
            extra = f"<p style='font-size:12px;color:#6b7280;margin:4px 0 0'>… y {total - len(items)} más</p>"
        return f"""
        <h4 style="margin:14px 0 4px;color:#0a0d12;font-size:14px">{icon} {escape(title)} <span style='color:#dc2626;font-weight:700'>({total})</span></h4>
        <ul style="margin:0;padding-left:20px;color:#374151;font-size:13px">{lis}</ul>
        {extra}
        """

    alertas_html = ""
    has_alertas = any([al["n_sin_foto"], al["n_sin_stock"], al["n_publicados_sin_gps"], al["n_publicados_sin_disp"]])
    if has_alertas:
        alertas_html = "<h3 style='margin:24px 0 8px;color:#0a0d12'>⚠️ Alertas activas</h3>"
        alertas_html += list_block("Publicados sin stock disponible", "🔴", al["publicados_sin_disp"], al["n_publicados_sin_disp"])
        alertas_html += list_block("Publicados sin GPS verificado", "🔴", al["publicados_sin_gps"], al["n_publicados_sin_gps"])
        alertas_html += list_block("Sin foto de fachada", "⚠", al["sin_foto"], al["n_sin_foto"])
        alertas_html += list_block("Sin stock cargado", "⚠", al["sin_stock"], al["n_sin_stock"])
    else:
        alertas_html = "<p style='color:#1f7a3d;font-size:13px;margin:24px 0 0;font-weight:700'>✅ Sin alertas críticas activas.</p>"

    errores_html = ""
    if data["errores_24h"]:
        rows = "".join(
            f"<tr><td style='padding:4px 8px'>{escape(e['proyecto'])}</td>"
            f"<td style='padding:4px 8px;color:#dc2626;font-size:12px'>{escape(e['detalles'][:120])}</td></tr>"
            for e in data["errores_24h"]
        )
        errores_html = f"""
        <h3 style="margin:24px 0 8px;color:#dc2626">🚨 Errores del scraper (últimas 24h)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;background:#fef2f2;border-radius:8px">{rows}</table>
        """

    resumen = f"""
    <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
      {_row("Proyectos activos", data["n_activos"])}
      {_row("Publicados en catálogo", data["n_publicados"])}
      {_row("Stock disponible total", data["n_disponibles_total"], total=data["n_unidades_cargadas"], color="#1f7a3d")}
      {_row("Cambios de stock (24h)", data["n_cambios_24h"], color="#1f7a3d" if data["n_cambios_24h"] else "#6b7280")}
      {_row("Errores en últimas 24h", data["n_errores_24h"], color="#dc2626" if data["n_errores_24h"] else "#1f7a3d")}
    </table>
    """

    return f"""
    <!doctype html><html><body style="margin:0;background:#f3f4f6;padding:0;font-family:-apple-system,Segoe UI,sans-serif">
      <div style="max-width:640px;margin:0 auto;padding:24px 16px">
        <div style="background:#7DC242;color:#0a0d12;padding:16px 20px;border-radius:10px 10px 0 0;font-weight:800;font-size:16px">
          📊 Informe diario de stock · BigCapital
          <div style="font-weight:400;font-size:12px;color:#0a0d12;opacity:.8;margin-top:2px">{escape(data["fecha_cl"])}</div>
        </div>
        <div style="background:#fff;padding:20px;border-radius:0 0 10px 10px;border:1px solid #e5e7eb;border-top:none">
          {resumen}
          {cambios_html}
          {alertas_html}
          {errores_html}
          <p style="margin:24px 0 0;font-size:11px;color:#9ca3af;text-align:center">
            Sistema automático · L-V 10:00 AM Chile · <a href="https://herramientas.bigcapital.cl/src/stock-interno/" style="color:#1f7a3d">Abrir listado</a>
          </p>
        </div>
      </div>
    </body></html>
    """


def send_daily_report() -> None:
    """Disparado por APScheduler L-V 10am. No-op si SMTP no configurado."""
    if not _configured():
        log.info("daily_report: SMTP no configurado — informe NO enviado.")
        return
    if not settings.daily_report_enabled:
        log.info("daily_report: deshabilitado (DAILY_REPORT_ENABLED=false).")
        return
    try:
        with SessionLocal() as db:
            data = build_daily_report(db)
        html = _build_html(data)
        msg = EmailMessage()
        # Subject con highlights de la jornada
        n_alertas = (
            data["alertas"]["n_publicados_sin_disp"]
            + data["alertas"]["n_publicados_sin_gps"]
            + data["alertas"]["n_sin_foto"]
            + data["alertas"]["n_sin_stock"]
        )
        warn = ""
        if data["n_errores_24h"] > 0:
            warn = f" · 🚨 {data['n_errores_24h']} error(es)"
        elif n_alertas > 0:
            warn = f" · ⚠ {n_alertas} alertas"
        msg["Subject"] = f"📊 Stock · {data['n_disponibles_total']} disp · {data['n_cambios_24h']} cambios 24h{warn}"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        msg["To"] = settings.notify_to
        msg["Reply-To"] = from_addr
        msg.set_content(f"Informe diario de stock · {data['fecha_cl']}\nActivos: {data['n_activos']} · Disp: {data['n_disponibles_total']} · Cambios 24h: {data['n_cambios_24h']}")
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        log.info(
            "daily_report enviado → %s · activos:%d disp:%d cambios24h:%d errores24h:%d alertas:%d",
            settings.notify_to, data["n_activos"], data["n_disponibles_total"],
            data["n_cambios_24h"], data["n_errores_24h"], n_alertas,
        )
    except Exception as e:
        log.error("daily_report falló: %s", e, exc_info=True)


def send_error_alert(titulo: str, detalle: str, proyecto: str = "") -> None:
    """Email INMEDIATO cuando algo falla (scraper, importación, etc.).

    Lo emiten los handlers de error para que el usuario se entere sin esperar
    al informe diario. NO-OP si SMTP no configurado.
    """
    if not _configured():
        log.warning("send_error_alert: SMTP no configurado — '%s' no enviado.", titulo)
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"🚨 BigCapital · {titulo}"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        msg["To"] = settings.notify_to
        msg["Reply-To"] = from_addr
        body = f"{titulo}\n{proyecto}\n\n{detalle}\n\n{_fecha_cl()}"
        msg.set_content(body)
        html = f"""<!doctype html><html><body style="font-family:-apple-system,sans-serif;background:#fef2f2;padding:24px">
          <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #fca5a5;border-radius:10px;padding:20px">
            <div style="color:#dc2626;font-weight:800;font-size:15px;margin-bottom:8px">🚨 {escape(titulo)}</div>
            {f'<div style="font-weight:700;color:#0a0d12;margin-bottom:8px">{escape(proyecto)}</div>' if proyecto else ''}
            <div style="color:#374151;font-size:13px;white-space:pre-wrap">{escape(detalle)}</div>
            <div style="margin-top:12px;font-size:11px;color:#9ca3af">{escape(_fecha_cl())}</div>
          </div></body></html>"""
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        log.info("send_error_alert enviado → '%s' (%s)", titulo, proyecto or "—")
    except Exception as e:
        log.warning("send_error_alert falló para '%s': %s", titulo, e)
