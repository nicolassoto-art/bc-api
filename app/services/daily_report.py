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


def _tiempo_relativo(dt):
    """'Hace 3h', 'Hace 2d 5h', 'Hace 14d', '—' si None. dt es naive UTC de bc-api."""
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff_min = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() / 60))
    if diff_min < 1:
        return "ahora"
    if diff_min < 60:
        return f"hace {diff_min}m"
    h = diff_min // 60
    m = diff_min % 60
    if h < 24:
        return f"hace {h}h" if m == 0 else f"hace {h}h {m}m"
    d = h // 24
    hr = h % 24
    return f"hace {d}d" if hr == 0 else f"hace {d}d {hr}h"


def _antiguedad_color(dt):
    """Color del 'estado de salud' del stock según cuándo fue la última actualización."""
    if not dt:
        return ("#6b7280", "#f3f4f6", "sin datos")  # gris
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    horas = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    if horas < 24:
        return ("#16a34a", "#dcfce7", "al día")        # verde
    if horas < 72:
        return ("#ca8a04", "#fef9c3", "atención")      # amarillo
    if horas < 168:  # 7 días
        return ("#ea580c", "#ffedd5", "demorado")      # naranja
    return ("#dc2626", "#fee2e2", "desactualizado")    # rojo


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

    # Estado por proyecto (ordenado por más reciente actualización primero)
    proyectos_estado = []
    for p in proyectos:
        proyectos_estado.append({
            "id": p.id,
            "nombre": p.nombre or p.id,
            "inmobiliaria": p.inmobiliaria or "",
            "disp": _disp(p.unidades),
            "cargadas": len(p.unidades or []),
            "stock_updated_at": p.stock_updated_at,
            "publicado": bool((p.extra or {}).get("publicar_en_catalogo")),
        })
    # Orden: nunca actualizados al final, resto por antigüedad ASC (más reciente arriba)
    proyectos_estado.sort(key=lambda x: (x["stock_updated_at"] is None, -(x["stock_updated_at"].timestamp() if x["stock_updated_at"] else 0)))

    # Distribución de salud del stock
    salud = {"al_dia": 0, "atencion": 0, "demorado": 0, "desactualizado": 0, "sin_datos": 0}
    for pe in proyectos_estado:
        _, _, label = _antiguedad_color(pe["stock_updated_at"])
        key = label.replace(" ", "_")
        salud[key] = salud.get(key, 0) + 1

    return {
        "fecha_cl": _fecha_cl(),
        "n_activos": len(proyectos),
        "n_publicados": len(publicados),
        "n_disponibles_total": total_disp,
        "n_unidades_cargadas": total_cargado,
        "salud": salud,
        "proyectos_estado": proyectos_estado,
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
        "errores_24h": errores_24h[:20],
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
    """HTML ejecutivo del informe diario · diseño visual con KPIs + tabla por proyecto."""
    al = data["alertas"]

    # ─── KPIs grandes (cuadrícula 2x2 + extras) ───────────────────────────
    def kpi(label, value, color="#0a0d12", subtitle=""):
        sub_html = f'<div style="font-size:11px;color:#6b7280;margin-top:2px">{escape(subtitle)}</div>' if subtitle else ''
        return f'''
        <td style="padding:14px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;text-align:center;width:50%">
          <div style="font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;letter-spacing:.5px">{escape(label)}</div>
          <div style="font-size:28px;color:{color};font-weight:800;margin-top:4px;line-height:1">{value}</div>
          {sub_html}
        </td>'''
    kpis = f'''
    <table style="width:100%;border-collapse:separate;border-spacing:8px"><tr>
      {kpi("Proyectos activos", data["n_activos"], subtitle=f'{data["n_publicados"]} publicados')}
      {kpi("Stock disponible", data["n_disponibles_total"], color="#16a34a", subtitle=f'de {data["n_unidades_cargadas"]} cargadas')}
    </tr><tr>
      {kpi("Cambios 24h", data["n_cambios_24h"], color="#16a34a" if data["n_cambios_24h"] else "#9ca3af", subtitle="actualizaciones de stock")}
      {kpi("Errores 24h", data["n_errores_24h"], color="#dc2626" if data["n_errores_24h"] else "#16a34a", subtitle="del scraper")}
    </tr></table>'''

    # ─── Distribución de salud del stock (barras horizontales) ─────────────
    s = data["salud"]
    total = sum(s.values()) or 1
    def bar(label, n, color):
        pct = round(100 * n / total)
        return f'''<tr>
          <td style="padding:2px 0;width:130px;font-size:12px;color:#374151">{escape(label)}</td>
          <td style="padding:2px 6px;width:36px;font-size:12px;color:#0a0d12;font-weight:700;text-align:right">{n}</td>
          <td style="padding:2px 0"><div style="background:#f3f4f6;border-radius:4px;height:10px;overflow:hidden"><div style="background:{color};width:{pct}%;height:100%"></div></div></td>
        </tr>'''
    salud_html = f'''
    <h3 style="margin:24px 0 8px;color:#0a0d12;font-size:15px">💚 Salud del stock</h3>
    <table style="width:100%;border-collapse:collapse">
      {bar("Al día (< 24h)",     s.get("al_dia",0),         "#16a34a")}
      {bar("Atención (1-3d)",    s.get("atencion",0),       "#ca8a04")}
      {bar("Demorado (3-7d)",    s.get("demorado",0),       "#ea580c")}
      {bar("Desactualizado (>7d)",s.get("desactualizado",0),"#dc2626")}
      {bar("Sin datos",          s.get("sin_datos",0),      "#9ca3af")}
    </table>'''

    # ─── Tabla por proyecto: nombre · disp · hace tanto · estado ───────────
    pe = data.get("proyectos_estado", [])
    if pe:
        rows = []
        for p in pe[:50]:
            color, bg, label = _antiguedad_color(p["stock_updated_at"])
            rel = _tiempo_relativo(p["stock_updated_at"])
            disp = p["disp"]
            disp_color = "#16a34a" if disp > 0 else "#dc2626"
            pub_icon = "🌐" if p["publicado"] else ""
            inmob = f'<div style="color:#9ca3af;font-size:11px">{escape(p["inmobiliaria"])}</div>' if p["inmobiliaria"] else ""
            rows.append(f'''<tr>
              <td style="padding:8px 10px;border-bottom:1px solid #f3f4f6">
                <div style="font-weight:700;color:#0a0d12;font-size:13px">{_project_link(p)} {pub_icon}</div>
                {inmob}
              </td>
              <td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;text-align:right;color:{disp_color};font-weight:800;font-size:14px">{disp}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;text-align:right;color:#6b7280;font-size:12px;white-space:nowrap">{rel}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #f3f4f6;text-align:center"><span style="background:{bg};color:{color};font-size:10.5px;font-weight:700;padding:3px 8px;border-radius:10px;text-transform:uppercase;letter-spacing:.3px">{escape(label)}</span></td>
            </tr>''')
        extra = ""
        if len(pe) > 50:
            extra = f'<p style="font-size:11px;color:#9ca3af;margin:6px 0 0;text-align:center">… y {len(pe)-50} proyectos más en el listado</p>'
        proyectos_html = f'''
        <h3 style="margin:28px 0 8px;color:#0a0d12;font-size:15px">🏢 Estado por proyecto</h3>
        <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
          <thead><tr style="background:#f9fafb">
            <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Proyecto</th>
            <th style="padding:8px 10px;text-align:right;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Disp.</th>
            <th style="padding:8px 10px;text-align:right;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Última act.</th>
            <th style="padding:8px 10px;text-align:center;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Estado</th>
          </tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
        {extra}'''
    else:
        proyectos_html = ""

    # ─── Alertas (categorizadas, tipo banner) ──────────────────────────────
    def alert_box(title, items, total, color, bg):
        if not items: return ""
        lis = "".join(f'<li style="margin:2px 0;font-size:12.5px">{_project_link(p)}</li>' for p in items[:8])
        extra = f' <span style="color:#6b7280;font-weight:500">+{total-8} más</span>' if total > 8 else ""
        return f'''<div style="background:{bg};border-left:3px solid {color};padding:10px 14px;border-radius:6px;margin-bottom:8px">
          <div style="color:{color};font-weight:800;font-size:13px;margin-bottom:4px">{escape(title)} · {total}{extra}</div>
          <ul style="margin:0;padding-left:18px;color:#374151">{lis}</ul>
        </div>'''
    alertas_items = [
        ("🔴 Publicados sin stock disponible", al["publicados_sin_disp"], al["n_publicados_sin_disp"], "#dc2626", "#fee2e2"),
        ("🔴 Publicados sin GPS verificado",   al["publicados_sin_gps"],  al["n_publicados_sin_gps"],  "#dc2626", "#fee2e2"),
        ("⚠ Sin foto de fachada",              al["sin_foto"],            al["n_sin_foto"],            "#ea580c", "#ffedd5"),
        ("⚠ Sin stock cargado",                al["sin_stock"],           al["n_sin_stock"],           "#ea580c", "#ffedd5"),
    ]
    alertas_html = "".join(alert_box(*x) for x in alertas_items)
    if alertas_html:
        alertas_html = f'<h3 style="margin:28px 0 8px;color:#0a0d12;font-size:15px">⚠️ Alertas que requieren acción</h3>{alertas_html}'
    else:
        alertas_html = '<div style="margin:24px 0 0;padding:12px 14px;background:#dcfce7;border-left:3px solid #16a34a;border-radius:6px;color:#15803d;font-weight:700;font-size:13px">✅ Sin alertas críticas activas.</div>'

    # ─── Errores del scraper (con resumen + detalles) ──────────────────────
    errores_html = ""
    if data["errores_24h"]:
        rows_err = []
        for e in data["errores_24h"]:
            hora = e["fecha"].astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m %H:%M") if e.get("fecha") else "—"
            rows_err.append(f'''<tr>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;font-size:12px;color:#6b7280;white-space:nowrap;width:90px">{escape(hora)}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;font-weight:700;color:#0a0d12;font-size:12.5px">{escape(e["proyecto"])}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;color:#7f1d1d;font-size:12px">{escape((e.get("detalles","") or "")[:160])}</td>
            </tr>''')
        extra_err = ""
        if data["n_errores_24h"] > len(data["errores_24h"]):
            extra_err = f'<p style="font-size:11px;color:#9ca3af;margin:6px 0 0">… y {data["n_errores_24h"]-len(data["errores_24h"])} errores más</p>'
        errores_html = f'''
        <h3 style="margin:28px 0 8px;color:#dc2626;font-size:15px">🚨 Errores del scraper · {data["n_errores_24h"]} en últimas 24h</h3>
        <table style="width:100%;border-collapse:collapse;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;overflow:hidden">
          <thead><tr style="background:#fee2e2">
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Hora</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Proyecto</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Detalle</th>
          </tr></thead>
          <tbody>{"".join(rows_err)}</tbody>
        </table>
        {extra_err}'''

    return f"""
    <!doctype html><html><body style="margin:0;background:#f3f4f6;padding:0;font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
      <div style="max-width:720px;margin:0 auto;padding:24px 16px">
        <div style="background:linear-gradient(135deg,#7DC242,#5fa832);color:#0a0d12;padding:18px 22px;border-radius:12px 12px 0 0;font-weight:800;font-size:18px">
          📊 Informe diario de stock
          <div style="font-weight:400;font-size:12.5px;color:#0a0d12;opacity:.75;margin-top:3px">{escape(data["fecha_cl"])} · BigCapital</div>
        </div>
        <div style="background:#fff;padding:18px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none">
          {kpis}
          {salud_html}
          {alertas_html}
          {errores_html}
          {proyectos_html}
          <div style="margin:28px 0 0;padding:12px 14px;background:#f9fafb;border-radius:8px;text-align:center;font-size:12px;color:#6b7280">
            Sistema automático · L-V 10:00 AM Chile<br>
            <a href="https://herramientas.bigcapital.cl/src/stock-interno/" style="color:#1f7a3d;font-weight:700;text-decoration:none">→ Abrir listado completo</a>
          </div>
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
        # Cc del informe diario: Pamela y Álvaro (configurable por DAILY_REPORT_CC).
        # Distinto de notify_stock_cc (que es de notify_change, ahora silenciado).
        cc_raw = (settings.daily_report_cc or "")
        to_lower = settings.notify_to.strip().lower()
        cc_list = [e.strip() for e in cc_raw.split(",") if e.strip() and e.strip().lower() != to_lower]
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Reply-To"] = from_addr
        msg.set_content(f"Informe diario de stock · {data['fecha_cl']}\nActivos: {data['n_activos']} · Disp: {data['n_disponibles_total']} · Cambios 24h: {data['n_cambios_24h']}")
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        log.info(
            "daily_report enviado → To:%s Cc:%s · activos:%d disp:%d cambios24h:%d errores24h:%d alertas:%d",
            settings.notify_to, ", ".join(cc_list) or "—",
            data["n_activos"], data["n_disponibles_total"],
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
