"""Informe diario de stock — bc-api · 2026-06-08

Disparado por APScheduler L-V 09:00 AM America/Santiago (configurado en main.py).

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
import collections
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


def _is_depto(u):
    """¿La unidad es un departamento (no estac/bodega/pack)?"""
    t = (u.tipo or "").lower() if u.tipo else ""
    n = (u.numero or "")
    if n.startswith("E-") or "estac" in t: return False
    if n.startswith("B-") or "bodeg" in t or t == "storage": return False
    if "pack" in t: return False
    return True


def _alertas_de_proyecto(p) -> dict:
    """Genera TODAS las alertas (críticos + warnings) para un proyecto, con la MISMA
    lógica que el frontend (_alertasProyecto + _alertasGranulares + _alertasDeProyecto).
    Devuelve {criticos: [str], warnings: [str]}.
    """
    criticos = []
    warnings = []
    extra = p.extra or {}
    pub = bool(extra.get("publicar_en_catalogo"))
    unidades = list(p.unidades or [])
    deptos = [u for u in unidades if _is_depto(u)]
    deptos_disp = [u for u in deptos if u.disponible]

    # ─── CRÍTICAS (datos básicos faltantes que bloquean publicar/cotizar)
    if not p.nombre or not p.nombre.strip():
        criticos.append("Sin nombre")
    if not p.inmobiliaria or not str(p.inmobiliaria).strip():
        criticos.append("Sin inmobiliaria")
    if not p.comuna or not str(p.comuna).strip():
        criticos.append("Sin comuna")
    if not p.foto_principal_url:
        criticos.append("Sin foto de fachada")
    no_tiene_stock = (len(unidades) == 0)
    if no_tiene_stock:
        criticos.append("Sin stock cargado")

    # GPS: crítico solo si está publicado (igual que frontend tras fix de jun 8)
    if extra.get("gps_verificado") is not True:
        if pub:
            criticos.append("Sin ubicación verificada (publicado)")
        else:
            warnings.append("Sin ubicación verificada")
    # Publicado sin stock disponible (si tiene unidades pero 0 disp)
    if pub and len(deptos_disp) == 0 and not no_tiene_stock:
        criticos.append("Publicado sin stock disponible")

    # ─── WARNINGS (revisar pero no bloquean)
    if not p.fase:
        warnings.append("Sin fase definida")
    if not p.fecha_entrega and not (extra.get("fisicos") or {}).get("ano_entrega") and not p.ano_entrega:
        warnings.append("Sin fecha de entrega")
    com = extra.get("comercial") or {}
    if com.get("pie_pct") in (None, ""):
        warnings.append("Sin pie %")

    # ─── GRANULARES (modelos / unidades)
    modelos = extra.get("modelos") or []
    imagenes = list(p.imagenes or [])
    norm = lambda s: (s or "").strip().lower()

    # Modelos sin planta (en uso = crítico; resto = warning)
    plantas_por_modelo = set()
    for im in imagenes:
        cat = norm(im.categoria)
        if cat.startswith("jb-planta-"):
            plantas_por_modelo.add(cat[len("jb-planta-"):])
    modelos_en_uso = set()
    for u in deptos_disp:
        if u.modelo:
            modelos_en_uso.add(norm(u.modelo))
    modelos_sin_planta = []
    for m in modelos:
        k = norm(m.get("nombre") or m.get("name"))
        if not k: continue
        tiene_planta = k in plantas_por_modelo or bool(m.get("plano_url") or m.get("planta_url"))
        if not tiene_planta:
            modelos_sin_planta.append(m.get("nombre") or m.get("name"))
    en_uso_sin_planta = [n for n in modelos_sin_planta if norm(n) in modelos_en_uso]
    if en_uso_sin_planta:
        criticos.append(f"{len(en_uso_sin_planta)} modelo(s) sin planta en uso: {', '.join(en_uso_sin_planta[:5])}")
    fuera_uso_sin_planta = [n for n in modelos_sin_planta if norm(n) not in modelos_en_uso]
    if fuera_uso_sin_planta:
        warnings.append(f"{len(fuera_uso_sin_planta)} modelo(s) sin planta (no en uso): {', '.join(fuera_uso_sin_planta[:5])}")

    # Unidades con modelo huérfano (modelo no existe en extra.modelos)
    modelos_by_name = {norm(m.get("nombre") or m.get("name")): m for m in modelos if (m.get("nombre") or m.get("name"))}
    huerfanos = []
    for u in deptos_disp:
        m = norm(u.modelo)
        if m and m not in modelos_by_name:
            huerfanos.append(f"{u.numero or '?'} (modelo \"{u.modelo}\")")
    if huerfanos:
        criticos.append(f"{len(huerfanos)} unidad(es) con modelo que no existe: {', '.join(huerfanos[:5])}")

    # Deptos sin precio
    deptos_sin_precio = [u.numero or "?" for u in deptos_disp if not (u.precio_final_uf or u.precio_lista_uf)]
    if deptos_sin_precio:
        warnings.append(f"{len(deptos_sin_precio)} depto(s) sin precio: {', '.join(deptos_sin_precio[:8])}")

    # Deptos sin tipología
    deptos_sin_tipo = [u.numero or "?" for u in deptos_disp if not u.tipologia]
    if deptos_sin_tipo:
        warnings.append(f"{len(deptos_sin_tipo)} depto(s) sin tipología: {', '.join(deptos_sin_tipo[:8])}")

    # ─── Del scraper: _deptos_con_warning (estado persistente)
    dw = extra.get("_deptos_con_warning") or []
    if isinstance(dw, list) and dw:
        modelos_dw = sorted(set(d.get("modelo") for d in dw if d.get("modelo")))
        criticos.append(f"{len(dw)} depto(s) con modelo no registrado (scraper): {', '.join(modelos_dw[:5])}")

    return {"criticos": criticos, "warnings": warnings}


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


STALE_DAYS = 7  # umbral "mucho tiempo sin actualizar stock" (pedido del usuario 2026-06-17)


def _age_hours(dt):
    """Horas desde dt (naive UTC de bc-api) hasta ahora; None si dt es None."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def build_daily_report(db: Session) -> dict:
    """Arma el resumen del estado del stock AGRUPADO POR INMOBILIARIA.

    Solo proyectos SBC activos (tabla Proyecto de bc-api). Cada proyecto trae el
    detalle exacto de sus pendientes (mismos críticos/warnings que el editor).
    Además: lista de proyectos disponibles pero SIN cargar (0 unidades) y lista
    de proyectos con mucho tiempo sin actualizar stock (> STALE_DAYS días).
    """
    proyectos = _proyectos_activos(db)
    publicados = [p for p in proyectos if (p.extra or {}).get("publicar_en_catalogo")]

    total_disp = sum(_disp(p.unidades) for p in proyectos)
    total_cargado = sum(len(p.unidades or []) for p in proyectos)

    # Cambios de stock en las últimas 24h
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cambios_24h = [p for p in proyectos if p.stock_updated_at and p.stock_updated_at >= cutoff_24h]

    # Errores del scraper en últimas 24h (eventos tipo 'Alerta')
    errores_24h = []
    for p in proyectos:
        for ev in _eventos_24h(p):
            if ev["tipo"] == "Alerta":
                errores_24h.append({"proyecto": p.nombre, **ev})
    errores_24h.sort(key=lambda x: x["fecha"], reverse=True)

    # ─── Estado + alertas por proyecto, agrupado por inmobiliaria.
    # El nombre se NORMALIZA (trim + casefold) para que variantes de tipeo
    # ("AJ URBANA" / "AJ Urbana", espacios de más) caigan en UN solo grupo.
    # El display de cada grupo usa la forma original más frecuente.
    grupos: dict[str, list] = {}                          # norm_key -> [pe]
    display_votes: dict[str, "collections.Counter"] = {}  # norm_key -> Counter(original)
    sin_cargar = []      # activos con 0 unidades (disponibles pero NO cargados)
    sin_actualizar = []  # con stock pero > STALE_DAYS sin tocar (o sin fecha)
    n_con_critico = n_con_warning = n_sin_alertas = 0

    for p in proyectos:
        a = _alertas_de_proyecto(p)
        cargadas = len(p.unidades or [])
        age_h = _age_hours(p.stock_updated_at)
        if a["criticos"]:
            n_con_critico += 1
        elif a["warnings"]:
            n_con_warning += 1
        else:
            n_sin_alertas += 1
        raw_inmob = (p.inmobiliaria or "").strip()
        norm = raw_inmob.casefold()  # "" = sin inmobiliaria
        if raw_inmob:
            display_votes.setdefault(norm, collections.Counter())[raw_inmob] += 1
        pe = {
            "id": p.id,
            "nombre": p.nombre or p.id,
            "inmobiliaria": raw_inmob or "Sin inmobiliaria",
            "_norm": norm,
            "disp": _disp(p.unidades),
            "cargadas": cargadas,
            "stock_updated_at": p.stock_updated_at,
            "publicado": bool((p.extra or {}).get("publicar_en_catalogo")),
            "criticos": a["criticos"],
            "warnings": a["warnings"],
            "n_crit": len(a["criticos"]),
            "n_warn": len(a["warnings"]),
        }
        grupos.setdefault(norm, []).append(pe)
        if cargadas == 0:
            sin_cargar.append(pe)
        elif age_h is None or age_h > STALE_DAYS * 24:
            sin_actualizar.append(pe)

    def _display(norm: str) -> str:
        if not norm:
            return "Sin inmobiliaria"
        votes = display_votes.get(norm)
        return votes.most_common(1)[0][0] if votes else "Sin inmobiliaria"

    # Reasignar a cada proyecto el display canónico del grupo (consistencia en
    # las listas de "sin cargar" / "sin actualizar").
    for norm, ps in grupos.items():
        disp = _display(norm)
        for pe in ps:
            pe["inmobiliaria"] = disp

    # Orden dentro de cada inmobiliaria: críticos → warnings → ok; reciente arriba.
    def _psort(x):
        return (
            -1 * (x["n_crit"] * 1000 + x["n_warn"]),
            x["stock_updated_at"] is None,
            -(x["stock_updated_at"].timestamp() if x["stock_updated_at"] else 0),
        )
    for ps in grupos.values():
        ps.sort(key=_psort)

    # Lista de inmobiliarias ordenada: más críticas primero, luego warnings, luego nombre.
    inmobiliarias = []
    for norm, ps in grupos.items():
        c = sum(x["n_crit"] for x in ps)
        w = sum(x["n_warn"] for x in ps)
        inmobiliarias.append({
            "nombre": _display(norm),
            "proyectos": ps,
            "n_proj": len(ps),
            "n_crit": c,
            "n_warn": w,
            "n_crit_proj": sum(1 for x in ps if x["n_crit"] > 0),
        })
    inmobiliarias.sort(key=lambda g: (-g["n_crit"], -g["n_warn"], g["nombre"].lower()))

    # Distribución de salud del stock
    salud = {"al_dia": 0, "atencion": 0, "demorado": 0, "desactualizado": 0, "sin_datos": 0}
    for p in proyectos:
        _, _, label = _antiguedad_color(p.stock_updated_at)
        key = label.replace(" ", "_")
        salud[key] = salud.get(key, 0) + 1

    sin_cargar.sort(key=lambda x: x["nombre"].lower())
    # sin_actualizar: el más viejo (o sin fecha) primero
    sin_actualizar.sort(key=lambda x: (
        x["stock_updated_at"] is not None,
        x["stock_updated_at"].timestamp() if x["stock_updated_at"] else 0,
    ))

    return {
        "fecha_cl": _fecha_cl(),
        "n_activos": len(proyectos),
        "n_publicados": len(publicados),
        "n_disponibles_total": total_disp,
        "n_unidades_cargadas": total_cargado,
        "n_cambios_24h": len(cambios_24h),
        "n_con_critico": n_con_critico,
        "n_con_warning": n_con_warning,
        "n_sin_alertas": n_sin_alertas,
        "salud": salud,
        "inmobiliarias": inmobiliarias,
        "sin_cargar": sin_cargar,
        "sin_actualizar": sin_actualizar,
        "stale_days": STALE_DAYS,
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


_BASE = "https://herramientas.bigcapital.cl"


def _editor_url(pid: str, tab: str = "") -> str:
    """Link al EDITOR del proyecto (donde se corrige), opcionalmente en una pestaña.
    El editor acepta deep-link por hash: proyecto.html?id=X#tab=fotos."""
    u = f"{_BASE}/src/stock-interno/proyecto.html?id={escape(pid or '')}"
    return u + (f"#tab={tab}" if tab else "")


# Mapa pendiente → pestaña del editor donde se arregla (orden importa: el primer
# keyword que aparezca gana). "modelo sin planta" → modelos; "depto sin precio" → unidades.
_TAB_KEYWORDS = [
    ("foto", "fotos"),
    ("planta", "modelos"),
    ("ubicaci", "local"),
    ("modelo", "modelos"),
    ("precio", "unidades"),
    ("tipolog", "unidades"),
    ("stock", "unidades"),
    ("unidad", "unidades"),
    ("pie", "general"),
    ("fase", "general"),
    ("entrega", "general"),
    ("comuna", "general"),
    ("inmobiliaria", "general"),
    ("nombre", "general"),
]


def _tab_for(msg: str) -> str:
    m = (msg or "").lower()
    for kw, tab in _TAB_KEYWORDS:
        if kw in m:
            return tab
    return "general"


def _project_link(p: dict, tab: str = "") -> str:
    """Nombre del proyecto como link al editor (pestaña opcional)."""
    nombre = escape(p.get("nombre") or p.get("id") or "")
    return f"<a href='{_editor_url(p.get('id') or '', tab)}' style='color:#1f7a3d;text-decoration:none;font-weight:700'>{nombre}</a>"


def _kpi_cell(label, value, color, sub, bg="#f9fafb", lblcolor="#6b7280"):
    return f'''<td style="background:{bg};border-radius:8px;padding:12px;text-align:center;width:25%">
      <div style="font-size:11px;color:{lblcolor};font-weight:700;text-transform:uppercase;letter-spacing:.3px">{escape(label)}</div>
      <div style="font-size:26px;color:{color};font-weight:800;margin-top:2px;line-height:1">{value}</div>
      <div style="font-size:11px;color:{lblcolor};margin-top:2px">{escape(sub)}</div></td>'''


def _proj_inline(p, tab: str = "unidades") -> str:
    """Link al proyecto (→ editor, pestaña Unidades por defecto) + inmobiliaria."""
    return f'{_project_link(p, tab)} <span style="color:#9ca3af">({escape(p["inmobiliaria"])})</span>'


def _build_html(data: dict) -> str:
    """HTML del informe diario · KPIs + bloques de pendientes + secciones por inmobiliaria."""

    # ─── KPIs (4): proyectos · stock disp · con críticas · sin actualizar +Nd
    n_stale = len(data["sin_actualizar"])
    n_crit = data["n_con_critico"]
    kpis = f'''<table style="width:100%;border-collapse:separate;border-spacing:8px"><tr>
      {_kpi_cell("Proyectos", data["n_activos"], "#0a0d12", f'{len(data["inmobiliarias"])} inmobiliaria(s)')}
      {_kpi_cell("Stock disp.", data["n_disponibles_total"], "#16a34a", f'de {data["n_unidades_cargadas"]} cargadas')}
      {_kpi_cell("Con críticas", n_crit, "#dc2626" if n_crit else "#16a34a", "requieren acción", bg="#fee2e2" if n_crit else "#dcfce7", lblcolor="#7f1d1d" if n_crit else "#14532d")}
      {_kpi_cell(f'Sin act. +{data["stale_days"]}d', n_stale, "#ea580c" if n_stale else "#16a34a", "stock viejo", bg="#ffedd5" if n_stale else "#dcfce7", lblcolor="#7c2d12" if n_stale else "#14532d")}
    </tr></table>'''

    # ─── Bloque: disponibles pero SIN cargar (0 unidades)
    sc = data["sin_cargar"]
    sin_cargar_html = ""
    if sc:
        items = " &nbsp;·&nbsp; ".join(_proj_inline(p) for p in sc[:25])
        sin_cargar_html = f'''<div style="background:#fef2f2;border-left:4px solid #dc2626;border-radius:0 6px 6px 0;padding:10px 14px;margin:14px 0 6px">
          <div style="color:#dc2626;font-weight:800;font-size:13px;margin-bottom:4px">▲ Disponibles pero SIN cargar (0 unidades) · {len(sc)}</div>
          <div style="font-size:12.5px;color:#374151;line-height:1.6">{items}</div></div>'''

    # ─── Bloque: mucho tiempo sin actualizar stock (> stale_days)
    sa = data["sin_actualizar"]
    sin_act_html = ""
    if sa:
        def _sa_item(p):
            rel = _tiempo_relativo(p["stock_updated_at"]) if p["stock_updated_at"] else "sin fecha"
            return f'{_proj_inline(p)} — {escape(rel)}'
        items = " &nbsp;·&nbsp; ".join(_sa_item(p) for p in sa[:25])
        sin_act_html = f'''<div style="background:#fff7ed;border-left:4px solid #ea580c;border-radius:0 6px 6px 0;padding:10px 14px;margin:6px 0 4px">
          <div style="color:#c2410c;font-weight:800;font-size:13px;margin-bottom:4px">⧗ Mucho tiempo sin actualizar stock (+{data["stale_days"]}d) · {len(sa)}</div>
          <div style="font-size:12.5px;color:#374151;line-height:1.6">{items}</div></div>'''

    # ─── Secciones por inmobiliaria, con detalle de pendientes por proyecto
    inmob_html = ""
    for g in data["inmobiliarias"]:
        if g["n_crit"]:
            chip_bg, chip_col = "#fee2e2", "#7f1d1d"
            chip_txt = f'{g["n_proj"]} proyecto(s) · {g["n_crit_proj"]} con críticas'
        elif g["n_warn"]:
            chip_bg, chip_col = "#fef3c7", "#854d0e"
            chip_txt = f'{g["n_proj"]} proyecto(s) · {g["n_warn"]} warning(s)'
        else:
            chip_bg, chip_col = "#dcfce7", "#14532d"
            chip_txt = f'{g["n_proj"]} proyecto(s) · al día'
        rows = ""
        ps = g["proyectos"]
        for i, p in enumerate(ps):
            color, _bg, label = _antiguedad_color(p["stock_updated_at"])
            rel = _tiempo_relativo(p["stock_updated_at"]) if p["cargadas"] else "sin datos de stock"
            border = "" if i == len(ps) - 1 else "border-bottom:1px solid #f3f4f6;"
            pub = ' 🌐' if p["publicado"] else ''
            if p["n_crit"]:
                badge = f'<span style="background:#fee2e2;color:#dc2626;font-size:11px;font-weight:800;padding:3px 9px;border-radius:11px">● {p["n_crit"]} crit</span>'
            elif p["n_warn"]:
                badge = f'<span style="background:#fef3c7;color:#ca8a04;font-size:11px;font-weight:800;padding:3px 9px;border-radius:11px">● {p["n_warn"]} warn</span>'
            else:
                badge = '<span style="background:#dcfce7;color:#16a34a;font-size:11px;font-weight:800;padding:3px 9px;border-radius:11px">● OK</span>'
            # Cada pendiente es un LINK al editor en la pestaña donde se corrige.
            def _li(items, color):
                return "".join(
                    f'<li><a href="{_editor_url(p["id"], _tab_for(t))}" style="color:{color};text-decoration:underline">{escape(t)}</a></li>'
                    for t in items
                )
            detail = ""
            if p["criticos"]:
                detail += f'<ul style="margin:4px 0 0;padding-left:16px;color:#dc2626;font-size:12px;line-height:1.5">{_li(p["criticos"], "#dc2626")}</ul>'
            if p["warnings"]:
                detail += f'<ul style="margin:2px 0 0;padding-left:16px;color:#ca8a04;font-size:12px;line-height:1.5">{_li(p["warnings"], "#ca8a04")}</ul>'
            if not detail:
                detail = '<div style="font-size:12px;color:#16a34a;margin-top:3px">Sin pendientes — publicable.</div>'
            rows += f'''<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:10px 0;{border}">
              <div style="padding-right:10px">
                <div style="font-weight:700;font-size:13.5px;color:#0a0d12">{_project_link(p)}{pub}</div>
                <div style="font-size:11.5px;color:#6b7280;margin-top:2px">{p["disp"]} disp · {p["cargadas"]} cargadas · {escape(rel)}</div>
                {detail}
              </div>
              <div style="text-align:right;white-space:nowrap">
                {badge}
                <div style="font-size:10.5px;color:{color};margin-top:4px;font-weight:700;text-transform:uppercase">{escape(label)}</div>
              </div></div>'''
        inmob_html += f'''<div style="margin-top:14px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
          <div style="background:#0b1628;color:#fff;padding:10px 14px;display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:800;font-size:15px">{escape(g["nombre"])}</span>
            <span style="font-size:11.5px;background:{chip_bg};color:{chip_col};padding:3px 9px;border-radius:11px;font-weight:700">{escape(chip_txt)}</span>
          </div>
          <div style="padding:6px 14px 12px">{rows}</div></div>'''

    # ─── Errores del scraper (si hay)
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
        errores_html = f'''
        <h3 style="margin:24px 0 8px;color:#dc2626;font-size:15px">🚨 Errores del scraper · {data["n_errores_24h"]} en últimas 24h</h3>
        <table style="width:100%;border-collapse:collapse;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;overflow:hidden">
          <thead><tr style="background:#fee2e2">
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Hora</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Proyecto</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Detalle</th>
          </tr></thead>
          <tbody>{"".join(rows_err)}</tbody>
        </table>'''

    # Mensaje cuando NO hay nada que hacer
    todo_ok_html = ""
    if not sc and not sa and data["n_con_critico"] == 0:
        todo_ok_html = '<div style="margin:14px 0 0;padding:12px 14px;background:#dcfce7;border-left:4px solid #16a34a;border-radius:0 6px 6px 0;color:#15803d;font-weight:700;font-size:13px">🟢 Sin pendientes críticos — todo el stock al día.</div>'

    return f"""
    <!doctype html><html><body style="margin:0;background:#f3f4f6;padding:0;font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
      <div style="max-width:720px;margin:0 auto;padding:24px 16px">
        <div style="background:#7DC242;color:#0a0d12;padding:16px 20px;border-radius:12px 12px 0 0">
          <div style="font-weight:800;font-size:18px">📊 Informe diario de stock · SBC</div>
          <div style="font-weight:400;font-size:12.5px;color:#0a0d12;opacity:.78;margin-top:3px">{escape(data["fecha_cl"])} · BigCapital</div>
        </div>
        <div style="background:#fff;padding:18px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none">
          {kpis}
          {sin_cargar_html}
          {sin_act_html}
          {todo_ok_html}
          {inmob_html}
          {errores_html}
          <div style="margin:24px 0 0;padding:12px 14px;background:#f9fafb;border-radius:8px;text-align:center;font-size:12px;color:#6b7280">
            Sistema automático · L-V 09:00 Chile · solo stock propio (SBC)<br>
            <a href="https://herramientas.bigcapital.cl/src/stock-interno/" style="color:#1f7a3d;font-weight:700;text-decoration:none">→ Abrir listado completo</a>
          </div>
        </div>
      </div>
    </body></html>
    """


def send_daily_report() -> None:
    """Disparado por APScheduler L-V 09am. No-op si SMTP no configurado."""
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
        # Subject con highlights de la jornada (semáforo)
        n_crit = data.get("n_con_critico", 0)
        n_warn = data.get("n_con_warning", 0)
        warn = ""
        if data["n_errores_24h"] > 0:
            warn = f" · 🚨 {data['n_errores_24h']} error(es)"
        elif n_crit > 0 and n_warn > 0:
            warn = f" · 🔴 {n_crit} crit · 🟡 {n_warn} warn"
        elif n_crit > 0:
            warn = f" · 🔴 {n_crit} crit"
        elif n_warn > 0:
            warn = f" · 🟡 {n_warn} warn"
        else:
            warn = " · 🟢 todo OK"
        msg["Subject"] = f"📊 Stock · {data['n_disponibles_total']} disp · {data['n_cambios_24h']} cambios 24h{warn}"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        # Destinatarios (2026-06-17): To = Cristopher (responsable de carga),
        # Cc = Nicolás. Fallback a notify_to si daily_report_to queda vacío.
        to_addr = (settings.daily_report_to or settings.notify_to).strip()
        msg["To"] = to_addr
        cc_raw = (settings.daily_report_cc or "")
        to_lower = to_addr.lower()
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
            "daily_report enviado → To:%s Cc:%s · activos:%d disp:%d inmob:%d crit:%d warn:%d sinCargar:%d staleStock:%d",
            to_addr, ", ".join(cc_list) or "—",
            data["n_activos"], data["n_disponibles_total"], len(data["inmobiliarias"]),
            data["n_con_critico"], data["n_con_warning"],
            len(data["sin_cargar"]), len(data["sin_actualizar"]),
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
