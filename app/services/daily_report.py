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
import re as _re
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

    # Plan de pago completo (necesario para cotizar bien). "Completo" = pie % + valor
    # de reserva + alguna estructura de cuotas del pie (pre/post entrega o cuotones).
    # En datos reales los proyectos cargados traen los 3; el cuotón inicial suele ser 0
    # (válido), por eso NO se exige. Es CRÍTICO → entra al cruce de resolución.
    def _pos(v):
        try:
            return float(v) > 0
        except (TypeError, ValueError):
            return False
    falta_pp = []
    if com.get("pie_pct") in (None, ""):
        falta_pp.append("pie %")
    if com.get("valor_reserva_clp") in (None, ""):
        falta_pp.append("valor de reserva")
    if not any(_pos(com.get(k)) for k in
               ("cuotas_pre_entrega", "cuotas_post_entrega", "cuoton_inicial_pct", "cuoton_final_pct")):
        falta_pp.append("cuotas del pie (pre/post o cuotones)")
    if falta_pp:
        criticos.append("Plan de pago incompleto: falta " + ", ".join(falta_pp))

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


def _eventos_ventana(p, cutoff):
    """Eventos del timeline de un proyecto desde `cutoff` (datetime aware UTC).
    Devuelve [{tipo,fecha,detalles,usuario}]. Base de _eventos_24h y de la
    sección 'Actividad desde el informe anterior'."""
    tl = (p.extra or {}).get("timeline") or []
    out = []
    for ev in tl:
        try:
            f = ev.get("fecha", "")
            if not f:
                continue
            if not f.endswith("Z") and "+" not in f[-6:] and "-" not in f[-6:]:
                f = f + "Z"
            dt = datetime.fromisoformat(f.replace("Z", "+00:00"))
            if dt >= cutoff:
                out.append({"tipo": ev.get("tipo", ""), "fecha": dt, "detalles": ev.get("detalles", ""),
                            "usuario": ev.get("usuario", ""), "origen_auto": bool(ev.get("origen_auto"))})
        except Exception:
            continue
    return out


def _operador_email() -> str:
    """Email del operador humano (Cristofer) = destinatario To del informe diario."""
    return (settings.daily_report_to or "").strip().lower()


def _operador_nombre() -> str:
    """Nombre para mostrar del operador. Del setting explícito o derivado del email."""
    n = (settings.daily_report_operator_name or "").strip()
    if not n:
        e = _operador_email()
        if e:
            n = e.split("@")[0].split(".")[0].title()
    return n or "el operador"


def _operador_actividad(proyectos, cutoff, end=None):
    """Cambios MANUALES del operador humano (Cristofer) por proyecto en [cutoff, end).

    `end` (aware UTC) acota por arriba: el informe 09:00 usa día-CALENDARIO exacto
    [ayer 00:00, hoy 00:00) Chile, así "el día anterior" es realmente el día anterior
    (no una ventana móvil de 24h que se mete en hoy o pierde temprano de ayer). El
    informe 13:00 pasa end=None → hasta ahora ("hoy").

    Filtro doble anti-scraper: (1) usuario == email exacto del operador (el scraper
    entra como mnk-scraper@/jb-scraper, NUNCA con el email de Cristofer) Y (2) descarta
    cualquier evento con origen_auto=True (importación automática). Así el informe SOLO
    refleja lo que hizo la persona logueada con su usuario y contraseña.

    Devuelve (grupos_ordenados, n_total, n_proyectos). Cada grupo:
    {id, nombre, eventos:[{tipo,fecha,detalles,usuario,origen_auto}]} con eventos
    del más reciente al más antiguo.
    """
    op_email = _operador_email()
    grupos: dict[str, dict] = {}
    n = 0
    if op_email:
        for p in proyectos:
            for ev in _eventos_ventana(p, cutoff):
                if end is not None and ev["fecha"] >= end:
                    continue  # fuera del día-calendario (p.ej. acciones de hoy)
                if ev["tipo"] == "Alerta":
                    continue
                if ev.get("origen_auto"):  # scraper / importación automática
                    continue
                if (ev.get("usuario") or "").strip().lower() != op_email:
                    continue  # solo el usuario humano de Cristofer
                key = p.nombre or p.id
                g = grupos.setdefault(key, {"id": p.id, "nombre": key, "eventos": []})
                g["eventos"].append(ev)
                n += 1
    # Orden CRONOLÓGICO ascendente: eventos del más antiguo al más reciente dentro de
    # cada proyecto, y los proyectos ordenados por su primer cambio del día.
    for g in grupos.values():
        g["eventos"].sort(key=lambda e: e["fecha"])
    orden = sorted(grupos.values(), key=lambda g: g["eventos"][0]["fecha"])
    return orden, n, len(orden)


_TIPO_LBL = {
    "Excel Stock": "Carga de stock", "Creación": "Proyecto nuevo",
    "Publicación": "Publicación", "Edición": "Edición", "Nota": "Nota",
    "Importación": "Importación", "Cambio": "Cambio", "Foto": "Foto",
    "Modelo": "Modelo", "Unidad": "Unidad", "Documento": "Documento",
}


def _operador_section_html(op_nombre, op_grupos, n_op, n_op_proj, periodo, titulo=None) -> str:
    """Bloque HTML "Los avances de X …" agrupado por proyecto, detallando cada acción
    (tipo · hora Chile · detalle). Reutilizado por el informe de las 09:00 y el de 13:00."""
    head = titulo or f"📋 Los avances de {escape(op_nombre)} {periodo}"
    if not n_op:
        return (f'<div style="margin:18px 0 0;padding:11px 14px;background:#f9fafb;border-radius:8px;'
                f'color:#6b7280;font-size:12.5px">📋 <b>{escape(head)}:</b> sin cambios registrados.</div>')
    bloques = []
    for g in op_grupos:
        link = _project_link({"id": g.get("id"), "nombre": g.get("nombre")})
        items = []
        for ev in g["eventos"]:
            rel = _hora_cl(ev["fecha"])
            tipo = _TIPO_LBL.get(ev.get("tipo", ""), ev.get("tipo") or "Cambio")
            det = escape((ev.get("detalles") or "")[:200])
            # Email-safe: <div> en vez de <ul><li> (Gmail/Outlook recortan listas
            # anidadas → por eso el detalle "desaparecía" en el correo). La hora chilena
            # de cada movimiento va SIEMPRE en la misma línea del tipo.
            det_html = (f'<br><span style="color:#6b7280;padding-left:14px">{det}</span>') if det else ''
            items.append(
                f'<div style="margin:0;padding:4px 0;font-size:12px;color:#374151">'
                f'<span style="color:#9ca3af">&bull;</span> '
                f'<b style="color:#0a0d12">{escape(tipo)}</b> '
                f'<span style="color:#9ca3af">· {escape(rel)}</span>'
                f'{det_html}</div>'
            )
        bloques.append(
            f'<div style="padding:9px 0;border-bottom:1px solid #eef2f7">'
            f'<div style="font-size:13px;font-weight:700;color:#0a0d12;margin-bottom:3px">{link} '
            f'<span style="color:#6b7280;font-weight:500">· {len(g["eventos"])} cambio(s)</span></div>'
            f'{"".join(items)}</div>'
        )
    return (
        f'<h3 style="margin:22px 0 6px;color:#0a0d12;font-size:15px">{escape(head)}</h3>'
        f'<div style="font-size:12px;color:#6b7280;margin-bottom:6px">{n_op} cambio(s) en {n_op_proj} proyecto(s)</div>'
        f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:4px 14px">{"".join(bloques)}</div>'
    )


def _disclaimer_html() -> str:
    """Aviso fijo: informe automático en desarrollo."""
    return ('<div style="margin:0 0 14px;padding:10px 12px;background:#fef9c3;border:1px solid #fde68a;'
            'border-radius:8px;color:#854d0e;font-size:11.5px;line-height:1.5">'
            '⚙️ <b>Informe automático en desarrollo.</b> Puede contener errores o datos incompletos. '
            'Si ves algo raro, avísanos para corregirlo.</div>')


# ── Cruce de pendientes (errores) entre informes ────────────────────────────
# Snapshot persistente en upload_path para comparar "qué se solucionó / qué sigue".
# Los "errores mencionados" = los CRÍTICOS por proyecto (mismo criterio que el editor:
# _alertas_de_proyecto). Cada uno se identifica por (id_proyecto :: texto del crítico).
import json as _json


def _snap_path():
    return settings.upload_path / "report_snapshots.json"


def _snap_load() -> dict:
    try:
        p = _snap_path()
        if p.exists():
            return _json.loads(p.read_text("utf-8"))
    except Exception as e:
        log.warning("report_snapshots load falló: %s", e)
    return {}


def _snap_set(slot: str, items: dict, ts: str) -> None:
    """Guarda el set de pendientes actuales en el slot ('morning'|'afternoon')."""
    try:
        snap = _snap_load()
        snap[slot] = {"ts": ts, "items": items}
        _snap_path().write_text(_json.dumps(snap, ensure_ascii=False), "utf-8")
    except Exception as e:
        log.warning("report_snapshots save falló: %s", e)


def _critico_key(texto: str) -> str:
    """Clave ESTABLE de un crítico, ignorando conteos/listados variables. Así
    '3 modelo(s) sin planta en uso: A, B' y '2 modelo(s) sin planta en uso: A'
    son el MISMO pendiente (no 'resuelto' + 'nuevo' al bajar el conteo)."""
    base = (texto or "").split(":")[0]                # corta el listado tras ':'
    base = _re.sub(r"^\s*\d+\s+", "", base)           # quita el conteo inicial "3 "
    return base.strip().lower()


def _pendientes_actuales(proyectos) -> dict:
    """Errores/pendientes CRÍTICOS vigentes ahora. key = 'pid::clave_estable'.
    Guarda el texto vigente (con conteo actual) para mostrar."""
    out = {}
    for p in proyectos:
        a = _alertas_de_proyecto(p)
        for c in a.get("criticos", []):
            out[f"{p.id}::{_critico_key(c)}"] = {"proyecto": p.nombre or p.id, "id": p.id, "texto": c}
    return out


def _resolucion_cruce(slot: str, pend_actual: dict) -> dict:
    """Compara los pendientes de AHORA contra el snapshot guardado en `slot` (el informe
    previo). Devuelve resueltos (estaban antes y ya no), persisten (siguen) y nuevos."""
    snap = _snap_load()
    prev_entry = snap.get(slot) or {}
    prev = prev_entry.get("items") or {}
    cur_k, prev_k = set(pend_actual), set(prev)
    return {
        "resueltos": [prev[k] for k in sorted(prev_k - cur_k)],
        "persisten": [pend_actual[k] for k in sorted(cur_k & prev_k)],
        "nuevos": [pend_actual[k] for k in sorted(cur_k - prev_k)],
        "prev_ts": prev_entry.get("ts"),
        "tiene_previo": slot in snap,
    }


def _resolucion_html(cruce: dict, ref_label: str) -> str:
    """Bloque 'Resolución de pendientes' comparando contra el informe previo."""
    if not cruce.get("tiene_previo"):
        return ('<div style="margin:18px 0 0;padding:11px 14px;background:#f9fafb;border-radius:8px;'
                'color:#6b7280;font-size:12.5px">🔁 <b>Resolución de pendientes:</b> es la primera '
                f'corrida — todavía no hay un informe previo ({escape(ref_label)}) con qué comparar.</div>')
    res, per, nue = cruce["resueltos"], cruce["persisten"], cruce["nuevos"]

    def _lista(items, color):
        # Email-safe: <div> con bullet (no <ul><li>, que Gmail/Outlook recortan).
        filas = "".join(
            f'<div style="margin:2px 0;font-size:12px;color:{color}">'
            f'<span style="color:#9ca3af">&bull;</span> <b style="color:#0a0d12">'
            f'{escape(it["proyecto"])}</b> — {escape(it["texto"])}</div>' for it in items[:25]
        )
        extra = f'<div style="font-size:11px;color:#9ca3af;margin:2px 0">… y {len(items)-25} más</div>' if len(items) > 25 else ''
        return f'<div style="margin:3px 0 8px">{filas}{extra}</div>' if items else ''

    cuerpo = ""
    cuerpo += f'<div style="font-size:12.5px;color:#16a34a;font-weight:700;margin-top:6px">✅ Solucionados {escape(ref_label)} · {len(res)}</div>'
    cuerpo += _lista(res, "#15803d") if res else '<div style="font-size:11.5px;color:#9ca3af;margin-bottom:6px">— ninguno —</div>'
    cuerpo += f'<div style="font-size:12.5px;color:#ea580c;font-weight:700">⏳ Siguen pendientes · {len(per)}</div>'
    cuerpo += _lista(per, "#9a3412") if per else '<div style="font-size:11.5px;color:#9ca3af;margin-bottom:6px">— ninguno —</div>'
    if nue:
        cuerpo += f'<div style="font-size:12.5px;color:#dc2626;font-weight:700">🆕 Nuevos · {len(nue)}</div>'
        cuerpo += _lista(nue, "#991b1b")
    return (
        f'<h3 style="margin:22px 0 6px;color:#0a0d12;font-size:15px">🔁 Resolución de pendientes ({escape(ref_label)})</h3>'
        f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px">{cuerpo}</div>'
    )


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


def _calidad_score(n_crit: int, n_warn: int, cargadas: int, age_h) -> int:
    """Índice de calidad del listado de UN proyecto (0-100): qué tan completo y fresco
    está el dato para publicar/cotizar. Componentes transparentes (se muestran en el mail):
      · Sin críticas   50 pts  (cada crítica −15 · bloquean publicar/cotizar)
      · Sin warnings   20 pts  (cada warning −5)
      · Stock fresco   20 pts  (≤24h=20 · ≤72h=15 · ≤7d=10 · +7d o sin fecha=0)
      · Stock cargado  10 pts  (tiene unidades)
    """
    s = max(0, 50 - 15 * n_crit) + max(0, 20 - 5 * n_warn)
    if cargadas > 0:
        s += 10
        if age_h is not None:
            if age_h < 24:
                s += 20
            elif age_h < 72:
                s += 15
            elif age_h < 168:
                s += 10
    return int(round(min(100, s)))


def _calidad_band(score: int):
    """(color_texto, color_fondo, etiqueta) según el índice de calidad."""
    if score >= 85:
        return ("#16a34a", "#dcfce7", "excelente")
    if score >= 70:
        return ("#ca8a04", "#fef9c3", "buena")
    if score >= 50:
        return ("#ea580c", "#ffedd5", "regular")
    return ("#dc2626", "#fee2e2", "deficiente")


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

    # ─── Actividad desde el informe anterior (avances del día previo) ──────
    # El informe corre L-V 09:00. Ventana: 24h normalmente; 72h los lunes (cubre
    # el fin de semana para no perder lo del viernes). Resume TODO lo que se movió
    # en el stock (carga de stock, ediciones, publicaciones, notas…) leído del
    # timeline, con quién y cuándo. Los errores ('Alerta') van en su sección, se excluyen.
    _now_cl = datetime.now(timezone(timedelta(hours=-4)))  # Chile (≈UTC-4) solo para el weekday
    _vent_h = 72 if _now_cl.weekday() == 0 else 24         # lunes mira hasta el viernes
    _cut_act = datetime.now(timezone.utc) - timedelta(hours=_vent_h)
    actividad = []
    for p in proyectos:
        for ev in _eventos_ventana(p, _cut_act):
            if ev["tipo"] == "Alerta":
                continue
            actividad.append({"proyecto": p.nombre or p.id, "id": p.id, **ev})
    actividad.sort(key=lambda x: x["fecha"], reverse=True)
    actividad_resumen = dict(collections.Counter(a["tipo"] or "Cambio" for a in actividad))

    # ─── Cambios del operador HUMANO (Cristofer) — detalle por proyecto ─────
    # SOLO acciones del usuario logueado de Cristofer (email exacto) y NUNCA del
    # scraper: _operador_actividad filtra por email + descarta origen_auto. Misma
    # ventana que la actividad general (24h, o 72h los lunes).
    _op_nombre = _operador_nombre()
    # Ventana día-CALENDARIO Chile: [ayer 00:00, hoy 00:00). Lunes = vie+sáb+dom.
    _tz_cl = timezone(timedelta(hours=-4))
    _hoy_cl_00 = datetime.now(_tz_cl).replace(hour=0, minute=0, second=0, microsecond=0)
    _dias_atras = 3 if _now_cl.weekday() == 0 else 1
    _op_cutoff = _hoy_cl_00 - timedelta(days=_dias_atras)
    operador_grupos, n_operador, _ = _operador_actividad(proyectos, _op_cutoff, end=_hoy_cl_00)

    # ─── Cruce de pendientes vs el informe de la MAÑANA anterior ────────────
    # Compara los críticos de hoy contra el último snapshot 'morning' (informe de
    # ayer) → qué se solucionó / qué sigue. El snapshot se guarda al ENVIAR (no en
    # el preview), así la comparación no se corrompe al previsualizar.
    pend_actual = _pendientes_actuales(proyectos)
    cruce = _resolucion_cruce("morning", pend_actual)

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
        pe["calidad"] = _calidad_score(pe["n_crit"], pe["n_warn"], cargadas, age_h)
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
        cal = round(sum(x["calidad"] for x in ps) / len(ps)) if ps else 0
        inmobiliarias.append({
            "nombre": _display(norm),
            "proyectos": ps,
            "n_proj": len(ps),
            "n_crit": c,
            "n_warn": w,
            "n_crit_proj": sum(1 for x in ps if x["n_crit"] > 0),
            "calidad": cal,
        })
    inmobiliarias.sort(key=lambda g: (-g["n_crit"], -g["n_warn"], g["nombre"].lower()))

    # Índice de calidad general = promedio ponderado por proyecto (mean de todos los pe).
    all_cal = [x["calidad"] for ps in grupos.values() for x in ps]
    calidad_general = round(sum(all_cal) / len(all_cal)) if all_cal else 0

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
        "calidad_general": calidad_general,
        "salud": salud,
        "inmobiliarias": inmobiliarias,
        "sin_cargar": sin_cargar,
        "sin_actualizar": sin_actualizar,
        "stale_days": STALE_DAYS,
        "errores_24h": errores_24h[:20],
        "n_errores_24h": len(errores_24h),
        "actividad": actividad[:30],
        "n_actividad": len(actividad),
        "actividad_resumen": actividad_resumen,
        "actividad_horas": _vent_h,
        "operador_nombre": _op_nombre,
        "operador_grupos": operador_grupos[:20],
        "n_operador": n_operador,
        "n_operador_proyectos": len(operador_grupos),
        "cruce": cruce,
        "pend_actual": pend_actual,
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


_DIAS_ABR = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _hora_cl(dt) -> str:
    """Hora exacta del evento en Chile (≈UTC-4) con 'hoy/ayer'. Ej: 'ayer 14:32',
    'hoy 08:10', 'lun 16 · 11:05' para más atrás."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cl = dt.astimezone(timezone(timedelta(hours=-4)))
    now = datetime.now(timezone(timedelta(hours=-4)))
    hm = cl.strftime("%H:%M")
    dias = (now.date() - cl.date()).days
    if dias <= 0:
        return f"hoy {hm}"
    if dias == 1:
        return f"ayer {hm}"
    return f"{_DIAS_ABR[cl.weekday()]} {cl.day} · {hm}"


# ── Faltantes: proyectos que la inmobiliaria publica en SU plataforma
# (PlanOk · MobySuite · inverapp · Drive) y que AÚN NO tenemos creados en stock-interno.
# v1: lista mantenida a mano (cruce 2026-06-19). Actualizar cuando cambie el catálogo de
# la inmobiliaria. Fuente del cruce: mappings de los scrapers (ingevec/euro) + inverapp (Ecasa)
# + Excel del Drive (AJ Urbana). JetBrokers NO cuenta como fuente.
FALTANTES_INMOB = {
    "Ecasa":     ("inverapp", [
        "Núcleo Costanera 2", "Terratoltén 3", "Lamara", "Ferroparque 2", "Espacio Victoria",
        "Lomas de Puyai 3", "Enlace Mackenna", "Alto San Joaquín 3", "Alto San Joaquín 2",
        "Núcleo Costanera", "Lomas de Puyai", "Wayra", "Alto San Joaquín", "Evaristo Lillo",
        "Conecta Huechuraba", "Urban Santiago", "Endémico", "Aires La Florida (etapa 1)",
        "Lomas de Puyai 2"]),
    "Ingevec":   ("cotizador ecore", [
        "Abdón Cifuentes", "Bellavista", "Cromo", "PRAT", "Santa Isabel 360", "Santos Ossa", "Terrazo"]),
    "AJ Urbana": ("Drive (Excel)", [
        "Morandé 776", "Lía Aguirre", "Vive Santa Isabel"]),
}


def _faltantes_html() -> str:
    grupos = [(k, v[0], v[1]) for k, v in FALTANTES_INMOB.items() if v[1]]
    if not grupos:
        return ""
    total = sum(len(p) for _, _, p in grupos)
    filas = ""
    for nombre, fuente, proyectos in grupos:
        items = " &nbsp;·&nbsp; ".join(escape(p) for p in proyectos)
        filas += (
            f'<div style="margin-top:8px"><span style="font-weight:800;color:#1e3a8a">{escape(nombre)}</span>'
            f'<span style="color:#6b7280;font-size:11.5px"> · {escape(fuente)} · {len(proyectos)}</span>'
            f'<div style="font-size:12.5px;color:#374151;line-height:1.6;margin-top:2px">{items}</div></div>')
    return (
        '<div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:0 6px 6px 0;padding:10px 14px;margin:14px 0 6px">'
        f'<div style="color:#1d4ed8;font-weight:800;font-size:13px;margin-bottom:2px">📥 Disponibles en la inmobiliaria y NO creados en stock-interno · {total}</div>'
        '<div style="color:#6b7280;font-size:11.5px;margin-bottom:2px">Proyectos que la inmobiliaria publica en su plataforma (PlanOk · MobySuite · inverapp · Drive) y que aún no cargamos en stock propio.</div>'
        f'{filas}</div>')


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

    # ─── Índice de calidad GENERAL (completitud + frescura del listado · 0-100)
    cg = data.get("calidad_general", 0)
    cg_col, cg_bg, cg_lbl = _calidad_band(cg)
    calidad_html = f'''<table style="width:100%;border-collapse:collapse;margin:8px 0 0"><tr>
      <td style="background:{cg_bg};border-radius:8px;padding:12px 14px;vertical-align:middle">
        <table style="width:100%;border-collapse:collapse"><tr>
          <td style="vertical-align:middle">
            <div style="font-size:12px;color:{cg_col};font-weight:800;text-transform:uppercase;letter-spacing:.3px">Índice de calidad general</div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px">Completitud + frescura del listado · sin críticas (50) + sin warnings (20) + stock fresco (20) + cargado (10)</div>
          </td>
          <td style="vertical-align:middle;text-align:right;white-space:nowrap">
            <span style="font-size:30px;font-weight:800;color:{cg_col}">{cg}<span style="font-size:14px;font-weight:700">/100</span></span>
            <div style="font-size:11px;color:{cg_col};font-weight:700;text-transform:uppercase">{escape(cg_lbl)}</div>
          </td>
        </tr></table>
      </td></tr></table>'''

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
        cal = g.get("calidad", 0)
        cal_col, cal_bg, _cal_lbl = _calidad_band(cal)
        inmob_html += f'''<div style="margin-top:14px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
          <div style="background:#0b1628;color:#fff;padding:10px 14px;display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:800;font-size:15px">{escape(g["nombre"])}</span>
            <span style="white-space:nowrap">
              <span style="font-size:11.5px;background:{cal_bg};color:{cal_col};padding:3px 9px;border-radius:11px;font-weight:800">calidad {cal}/100</span>
              <span style="font-size:11.5px;background:{chip_bg};color:{chip_col};padding:3px 9px;border-radius:11px;font-weight:700">{escape(chip_txt)}</span>
            </span>
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

    # ─── Actividad desde el informe anterior (avances del día previo) ──────
    act = data.get("actividad", [])
    n_act = data.get("n_actividad", 0)
    if n_act:
        res = data.get("actividad_resumen", {})
        chips = " · ".join(
            f'{_TIPO_LBL.get(k, k)}: {v}' for k, v in sorted(res.items(), key=lambda kv: -kv[1])
        )
        rows_act = []
        for a in act:
            rel = _hora_cl(a["fecha"])  # hora exacta Chile (ayer/hoy), elegido por el usuario
            usr = escape((a.get("usuario") or "—").split("@")[0])
            det = escape((a.get("detalles") or a.get("tipo") or "")[:170])
            link = _project_link({"id": a.get("id"), "nombre": a.get("proyecto")})
            rows_act.append(
                f'<div style="padding:7px 0;border-bottom:1px solid #f3f4f6">'
                f'<div style="font-size:12.5px"><b>{link}</b> <span style="color:#6b7280">· {usr} · {escape(rel)}</span></div>'
                f'<div style="font-size:12px;color:#374151;margin-top:1px">{det}</div></div>'
            )
        _extra_act = f'<div style="font-size:11px;color:#9ca3af;margin-top:6px">… y {n_act - len(act)} movimiento(s) más</div>' if n_act > len(act) else ''
        actividad_html = (
            f'<h3 style="margin:22px 0 6px;color:#0a0d12;font-size:15px">🗓 Actividad desde el informe anterior · {n_act}</h3>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:6px">{escape(chips)}</div>'
            f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:4px 14px">{"".join(rows_act)}</div>'
            f'{_extra_act}'
        )
    else:
        actividad_html = '<div style="margin:20px 0 0;padding:11px 14px;background:#f9fafb;border-radius:8px;color:#6b7280;font-size:12.5px">🗓 <b>Actividad:</b> sin movimientos registrados desde el informe anterior.</div>'

    # ─── Mejoras (cambios manuales del operador humano) — sin nombres ───────
    _vent = data.get("actividad_horas", 24)
    _periodo = "el fin de semana" if _vent > 24 else "el día anterior"
    _periodo_titulo = "del fin de semana" if _vent > 24 else "del día anterior"
    operador_html = _operador_section_html(
        data.get("operador_nombre") or "el operador",
        data.get("operador_grupos", []),
        data.get("n_operador", 0),
        data.get("n_operador_proyectos", 0),
        _periodo,
        titulo=f"📋 Mejoras {_periodo_titulo}",
    )
    # Cruce de pendientes vs informe anterior (qué se solucionó / qué sigue)
    resolucion_html = _resolucion_html(data.get("cruce", {}), "desde el informe anterior")
    disclaimer_html = _disclaimer_html()

    # Mensaje cuando NO hay nada que hacer
    faltantes_html = _faltantes_html()

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
          {disclaimer_html}
          {kpis}
          {calidad_html}
          {sin_cargar_html}
          {sin_act_html}
          {todo_ok_html}
          {operador_html}
          {resolucion_html}
          {actividad_html}
          {inmob_html}
          {faltantes_html}
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
        # Guardar el set de pendientes de HOY como snapshot 'morning' → el informe
        # de mañana compara contra esto para saber qué se solucionó.
        _snap_set("morning", data.get("pend_actual", {}), datetime.utcnow().isoformat())
        log.info(
            "daily_report enviado → To:%s Cc:%s · activos:%d disp:%d inmob:%d crit:%d warn:%d sinCargar:%d staleStock:%d",
            to_addr, ", ".join(cc_list) or "—",
            data["n_activos"], data["n_disponibles_total"], len(data["inmobiliarias"]),
            data["n_con_critico"], data["n_con_warning"],
            len(data["sin_cargar"]), len(data["sin_actualizar"]),
        )
    except Exception as e:
        log.error("daily_report falló: %s", e, exc_info=True)


# ════════════════════════════════════════════════════════════════════════════
# Informe de las 13:00 · SOLO los avances de Cristofer HOY (acciones manuales)
# ════════════════════════════════════════════════════════════════════════════

def build_operador_today(db: Session) -> dict:
    """Cambios MANUALES del operador humano (Cristofer) HOY: desde la medianoche de
    Chile hasta el momento de correr. SOLO su usuario (email exacto), sin scraper
    (mismo filtro doble que _operador_actividad: email + descarta origen_auto)."""
    proyectos = _proyectos_activos(db)
    tz_cl = timezone(timedelta(hours=-4))  # Chile ≈ UTC-4
    medianoche_cl = datetime.now(tz_cl).replace(hour=0, minute=0, second=0, microsecond=0)
    grupos, n, n_proj = _operador_actividad(proyectos, medianoche_cl)
    # Cruce: qué de los pendientes de la MAÑANA (informe 09:00 de hoy) se solucionó.
    pend_actual = _pendientes_actuales(proyectos)
    cruce = _resolucion_cruce("morning", pend_actual)
    return {
        "fecha_cl": _fecha_cl(),
        "operador_nombre": _operador_nombre(),
        "operador_grupos": grupos[:40],
        "n_operador": n,
        "n_operador_proyectos": n_proj,
        "cruce": cruce,
        "pend_actual": pend_actual,
    }


def _build_operador_html(data: dict) -> str:
    """Email compacto: cabecera + mejoras de HOY + resolución de pendientes (sin nombres)."""
    seccion = _operador_section_html(
        data.get("operador_nombre") or "el operador",
        data.get("operador_grupos", []),
        data.get("n_operador", 0), data.get("n_operador_proyectos", 0),
        "hoy", titulo="📋 Mejoras de hoy",
    )
    resolucion = _resolucion_html(data.get("cruce", {}), "desde el informe de la mañana")
    return f"""
    <!doctype html><html><body style="margin:0;background:#f3f4f6;padding:0;font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
      <div style="max-width:720px;margin:0 auto;padding:24px 16px">
        <div style="background:#7DC242;color:#0a0d12;padding:16px 20px;border-radius:12px 12px 0 0">
          <div style="font-weight:800;font-size:18px">📋 Mejoras de hoy · stock SBC</div>
          <div style="font-weight:400;font-size:12.5px;color:#0a0d12;opacity:.78;margin-top:3px">{escape(data["fecha_cl"])} · BigCapital · corte 13:00</div>
        </div>
        <div style="background:#fff;padding:18px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none">
          {_disclaimer_html()}
          {seccion}
          {resolucion}
          <div style="margin:24px 0 0;padding:12px 14px;background:#f9fafb;border-radius:8px;text-align:center;font-size:12px;color:#6b7280">
            Solo cambios manuales de hoy (sin scraper) · L-V 13:00 Chile<br>
            <a href="https://herramientas.bigcapital.cl/src/stock-interno/" style="color:#1f7a3d;font-weight:700;text-decoration:none">→ Abrir listado completo</a>
          </div>
        </div>
      </div>
    </body></html>
    """


def send_operador_today_report() -> None:
    """Disparado por APScheduler L-V 13:00 Chile. Envía SOLO los avances de hoy de
    Cristofer a operador_report_to. No-op si SMTP no configurado o si está deshabilitado."""
    if not _configured():
        log.info("operador_today: SMTP no configurado — informe NO enviado.")
        return
    if not settings.operador_report_enabled:
        log.info("operador_today: deshabilitado (OPERADOR_REPORT_ENABLED=false).")
        return
    try:
        with SessionLocal() as db:
            data = build_operador_today(db)
        html = _build_operador_html(data)
        msg = EmailMessage()
        msg["Subject"] = f"📋 Mejoras de hoy · {data['n_operador']} cambio(s) en {data['n_operador_proyectos']} proyecto(s)"
        from_addr = settings.smtp_from or settings.smtp_user
        msg["From"] = formataddr((settings.smtp_from_name, from_addr))
        # Destinatarios del informe de las 13:00 (pedido 2026-06-24): los 3 (Cristofer,
        # Nicolás, Álvaro). Coma-separados.
        dests = [e.strip() for e in (settings.operador_report_to or "").split(",") if e.strip()]
        if not dests:
            log.warning("operador_today: sin destinatarios (operador_report_to vacío).")
            return
        msg["To"] = ", ".join(dests)
        msg["Reply-To"] = from_addr
        msg.set_content(
            f"Mejoras de hoy · {data['fecha_cl']}\n"
            f"{data['n_operador']} cambio(s) en {data['n_operador_proyectos']} proyecto(s)."
        )
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        _snap_set("afternoon", data.get("pend_actual", {}), datetime.utcnow().isoformat())
        log.info("operador_today enviado → %s · %d cambios / %d proyectos",
                 ", ".join(dests), data["n_operador"], data["n_operador_proyectos"])
    except Exception as e:
        log.error("operador_today falló: %s", e, exc_info=True)


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
