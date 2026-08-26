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
import os as _os
import re as _re
import smtplib
import threading as _threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from urllib.parse import quote as _urlquote

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.proyecto import Proyecto
from app.services.email_service import _configured, _fecha_cl
from app.settings import settings

log = logging.getLogger(__name__)

# Zona horaria REAL de Chile con DST (UTC-4 invierno / UTC-3 verano ~sep-abr).
# TODAS las horas mostradas y las ventanas día-calendario usan esta constante.
# Antes se usaba timezone(timedelta(hours=-4)) fijo → en verano chileno todo
# quedaba 1 hora corrido (auditoría 2026-07-02). Fallback por si faltara tzdata.
try:
    from zoneinfo import ZoneInfo
    TZ_CL = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover
    TZ_CL = timezone(timedelta(hours=-4))


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
    # tipo con fallback a tipologia (algunas fuentes tipean ahí) + "parking"
    # (misma semántica que unidades.py: substring, cubre 'Parking'/'parking doble').
    t = ((u.tipo or getattr(u, "tipologia", None)) or "").lower()
    n = (u.numero or "")
    if n.startswith("E-") or "estac" in t or "parking" in t: return False
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
    if not p.direccion or not str(p.direccion).strip():
        warnings.append("Sin dirección")
    if not p.region or not str(p.region).strip():
        warnings.append("Sin región")
    # Foto de fachada: MISMA semántica que _foto_principal_fallback del API (que es
    # lo que decide el cover real del catálogo): vale foto_principal_url, O una imagen
    # marcada es_principal, O una imagen fachada-like (jb-foto*/foto/fachada/exterior/
    # sin categoría — nunca plantas jb-planta-*). Evita falsos "sin foto" en proyectos
    # importados de JB, donde el importador sube 'jb-foto'/'cover' sin setear la portada.
    def _img_fachada(im):
        c = (im.categoria or "").strip().lower()
        if c.startswith("jb-planta"):
            return False
        return im.es_principal or c in {"jb-foto", "foto", "fachada", "exterior", "cover", ""} or "foto" in c
    _tiene_fachada = bool(p.foto_principal_url) or any(_img_fachada(im) for im in (p.imagenes or []))
    if not _tiene_fachada:
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
    # (2026-07-06) quitado el lookup muerto a extra["fisicos"]["ano_entrega"] —
    # esa clave no existe en producción (ver nota más abajo); p.ano_entrega (columna
    # real) ya cubre el caso, así que esto no cambia el resultado, solo la claridad.
    if not p.fecha_entrega and not p.ano_entrega:
        warnings.append("Sin fecha de entrega")
    com = extra.get("comercial") or {}
    # (el pie % faltante se reporta SOLO en el crítico "Plan de pago incompleto";
    # antes salía además como warning "Sin pie %" — mismo dato dos veces)

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
               ("cuotas_pre_entrega", "cuotas_post_entrega",
                "cuoton_inicial_pct", "cuoton_final_pct",
                "cuoton_inicial_uf", "cuoton_final_uf")):  # cuotones en UF también valen
        falta_pp.append("cuotas del pie (pre/post o cuotones)")
    # Condiciones comerciales (2026-07-06, pedido Nicolás: la ficha debe estar
    # completa). Selects que muestra el editor bajo "Condiciones Comerciales".
    # (2026-08-01) Se SACA el chequeo de `precio_cotizacion`: el selector "Precio
    # en cotizador" se eliminó a propósito de la ficha (tarea #98) porque la regla
    # del proyecto es que el precio publicado es SIEMPRE precio_lista_uf. Al no
    # tener input, la alerta era imposible de resolver para el admin — quedaba
    # encendida de forma permanente en el panel "Pendientes" de la ficha. El mismo
    # chequeo ya se sacó del listado (stock-interno/index.js), así que dejarlo acá
    # solo generaba divergencia entre las dos pantallas.
    if com.get("tipo_pie") in (None, ""):
        falta_pp.append("tipo de pie")
    # (2026-08-25) `tipo_descuento` solo se exige cuando el proyecto TIENE descuentos.
    # El campo perdió su selector propio el 2026-07-24: hoy se deriva del "Alcance" de la
    # primera fila de Descuento principal, y esa sincronización solo corre cuando alguien
    # toca una fila. Sin ninguna fila cargada no había forma de resolverlo desde la ficha
    # — mismo caso que `precio_cotizacion` arriba: un pendiente permanente pidiendo un
    # campo sin UI. Eran 28 proyectos de 139, los 28 sin una sola fila de descuento.
    # Preguntar de qué tipo es un descuento que no existe no informa nada, y el cotizador
    # ya trata el vacío igual que "Todo".
    _descuentos = com.get("descuentos")
    _hay_descuentos = isinstance(_descuentos, list) and len(_descuentos) > 0
    if _hay_descuentos and com.get("tipo_descuento") in (None, ""):
        falta_pp.append("tipo de descuento")
    if com.get("tipo_bono_pie") in (None, ""):
        falta_pp.append("tipo de bono pie")
    if falta_pp:
        criticos.append("Plan de pago incompleto: falta " + ", ".join(falta_pp))

    # Forma de pago del pie (2026-07-06): CONDICIONAL a la estructura que el
    # proyecto realmente usa — si no hay cuotón inicial, no corresponde exigir
    # "cómo se paga el cuotón inicial" (sería falso positivo). uf_minima_cuota_pre
    # y nota_pago_pie quedan fuera a propósito: el propio editor dice "déjalo en
    # blanco si el proyecto no lo usa" — son opcionales, no ficha incompleta.
    falta_fp = []
    if (_pos(com.get("cuoton_inicial_pct")) or _pos(com.get("cuoton_inicial_uf"))) \
            and com.get("pago_cuoton_inicial") in (None, ""):
        falta_fp.append("pago del cuotón inicial")
    if _pos(com.get("cuotas_pre_entrega")) and com.get("pago_pre_entrega") in (None, ""):
        falta_fp.append("pago pre-entrega")
    if _pos(com.get("cuotas_post_entrega")) and com.get("pago_post_entrega") in (None, ""):
        falta_fp.append("pago post-entrega")
    # (2026-08-03) `valor_cuota_clp` deja de exigirse: es OPCIONAL — solo aplica
    # cuando la inmobiliaria fija un monto parejo por cuota. El cotizador nunca
    # llegó a leer este campo, y la exigencia era falso positivo en 107/138
    # proyectos (ej. proyectos con "Cuotas construcción = No aplica" igual
    # quedaban marcados como incompletos).
    if falta_fp:
        criticos.append("Forma de pago del pie incompleta: falta " + ", ".join(falta_fp))

    # Datos físicos (2026-07-06): pisos/unidades/estacionamientos/bodegas/
    # ascensores — mismos campos de la pestaña General del editor. 0 es un valor
    # VÁLIDO (ej. edificio bajo sin ascensor) → solo None/"" cuenta como faltante.
    #
    # BUG REAL (encontrado 2026-07-06 en mega-audit, confirmado contra 3 proyectos
    # reales vía API): NO existe extra["fisicos"] en producción — estos campos
    # viven PLANOS en extra, y "estacionamientos" se llama "estac_totales" (NO
    # "estacionamientos_totales"). fis=extra.get("fisicos") daba SIEMPRE {} →
    # marcaba "Datos físicos incompletos" en el 100% de los proyectos (114/114),
    # incluso los que tenían el dato completo (ej. Tocornal: pisos=9, ascensores=3,
    # estac_totales=95 — igual salía como "falta todo"). jb_importer.py sí escribe
    # con path "extra.fisicos.X" al importar, pero lo que queda GUARDADO y lo que
    # lee este archivo son cosas distintas — verificado en vivo, no es teoría.
    FISICOS_LABELS = [
        ("pisos", "pisos"),
        ("unidades_totales", "unidades totales"),
        ("unidades_por_piso", "unidades por piso"),
        ("estac_totales", "estacionamientos totales"),
        ("bodegas_totales", "bodegas totales"),
        ("ascensores", "ascensores"),
    ]
    falta_fis = [lbl for key, lbl in FISICOS_LABELS if extra.get(key) in (None, "")]
    if falta_fis:
        criticos.append("Datos físicos incompletos: falta " + ", ".join(falta_fis))

    # ─── GRANULARES (modelos / unidades)
    modelos = extra.get("modelos") or []
    imagenes = list(p.imagenes or [])
    norm = lambda s: (s or "").strip().lower()

    # Modelos sin planta (en uso = crítico; resto = warning).
    # Las plantas JB se guardan como imágenes categoría "jb-planta-<blueprintId>".
    # Un modelo TIENE planta si: su _blueprint (id, case-sensitive) está entre esas
    # imágenes, O trae planta_thumb_src/planta_url/plano_url, O (legacy) su nombre
    # coincide con un id de planta. Antes solo miraba el NOMBRE → falso "sin planta"
    # en proyectos JB (las plantas existen pero referenciadas por blueprintId).
    plantas_ids = set()       # blueprintIds tal cual (case-sensitive)
    plantas_norm = set()      # mismos, normalizados (fallback por nombre legacy)
    for im in imagenes:
        cat = (im.categoria or "").strip()
        if cat.lower().startswith("jb-planta-"):
            bid = cat[len("jb-planta-"):]
            plantas_ids.add(bid)
            plantas_norm.add(bid.lower())

    def _blueprint_id(m):
        b = m.get("_blueprint")
        if isinstance(b, str):
            return b
        if isinstance(b, dict):
            return b.get("id") or b.get("blueprintId")
        return None

    modelos_en_uso = set()
    for u in deptos_disp:
        if u.modelo:
            modelos_en_uso.add(norm(u.modelo))
    modelos_sin_planta = []
    for m in modelos:
        nombre = m.get("nombre") or m.get("name")
        k = norm(nombre)
        if not k: continue
        # planta_no_disponible: la INMOBILIARIA no publica la planta de este modelo
        # (lo marca el operador en el editor). No es un pendiente accionable → no
        # cuenta como "sin planta" (Cristofer no puede subir lo que la fuente no tiene).
        if m.get("planta_no_disponible"):
            continue
        bid = _blueprint_id(m)
        tiene_planta = (
            (bid is not None and bid in plantas_ids)
            or k in plantas_norm
            or bool(m.get("planta_thumb_src") or m.get("plano_url") or m.get("planta_url"))
        )
        if not tiene_planta:
            modelos_sin_planta.append(nombre)
    en_uso_sin_planta = [n for n in modelos_sin_planta if norm(n) in modelos_en_uso]
    if en_uso_sin_planta:
        criticos.append(f"{len(en_uso_sin_planta)} modelo(s) sin planta en uso: {', '.join(en_uso_sin_planta[:5])}")
    fuera_uso_sin_planta = [n for n in modelos_sin_planta if norm(n) not in modelos_en_uso]
    if fuera_uso_sin_planta:
        warnings.append(f"{len(fuera_uso_sin_planta)} modelo(s) sin planta (no en uso): {', '.join(fuera_uso_sin_planta[:5])}")

    # Unidades con modelo huérfano (modelo no existe en extra.modelos)
    modelos_by_name = {norm(m.get("nombre") or m.get("name")): m for m in modelos if (m.get("nombre") or m.get("name"))}
    huerfanos = []
    for u in deptos:  # TODAS las filas vivas: un modelo inexistente es bug de datos
        m = norm(u.modelo)  # aunque la unidad esté no-disponible (y el cruce no
        if m and m not in modelos_by_name:  # debe dar falso "Solucionado" al togglear)
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

    # ─── Del scraper: _deptos_con_warning (estado persistente). Se filtra contra el
    # catálogo VIGENTE (si el modelo ya se registró a mano, el aviso del scraper quedó
    # obsoleto) y NO se reporta si el mismo problema ya salió como "modelo que no
    # existe" arriba (era el mismo dato dos veces).
    dw = extra.get("_deptos_con_warning") or []
    if isinstance(dw, list) and dw and not huerfanos:
        dw_vigentes = sorted({d.get("modelo") for d in dw
                              if d.get("modelo") and norm(d.get("modelo")) not in modelos_by_name})
        if dw_vigentes:
            criticos.append(f"{len(dw_vigentes)} modelo(s) no registrado(s) (scraper): {', '.join(dw_vigentes[:5])}")

    return {"criticos": criticos, "warnings": warnings}


def _catalogo_vs_stock(proyectos) -> list[dict]:
    """Compara, por proyecto, lo que el CATÁLOGO público mostrará contra el STOCK
    INTERNO real (la fuente de verdad — proyecto-vista.html manda). El catálogo y
    la vista de "Modelos" agrupan las unidades por su campo `modelo`; si ese campo
    no calza con un modelo registrado, la unidad se cae de esa vista y el catálogo
    muestra MENOS de lo que hay en stock. Ese fue el bug de Carrera Capital (el
    scraper subía las unidades con modelo vacío → los 5 modelos salían en 0).

    Detecta tres divergencias (todo desde bc-api, sin depender del caché del worker):
      1. unidades disponibles con modelo VACÍO (el catálogo no las agrupa)
      2. unidades disponibles con modelo que NO existe entre los registrados
      3. modelos registrados SIN ninguna unidad disponible (tarjeta vacía en catálogo)
    Devuelve solo los proyectos con alguna divergencia, ordenados inmobiliaria→proyecto.
    """
    norm = lambda s: (s or "").strip().lower()
    out = []
    for p in proyectos:
        extra = p.extra or {}
        modelos = extra.get("modelos") or []
        modelos_nombres = [(m.get("nombre") or m.get("name")) for m in modelos
                           if (m.get("nombre") or m.get("name"))]
        modelos_norm = {norm(n) for n in modelos_nombres}
        deptos_disp = [u for u in (p.unidades or []) if _is_depto(u) and u.disponible]
        if not deptos_disp:
            continue  # sin stock disponible no hay nada que comparar en el catálogo
        sin_modelo = [u for u in deptos_disp if not norm(u.modelo)]
        inexistente = [u for u in deptos_disp
                       if norm(u.modelo) and norm(u.modelo) not in modelos_norm]
        modelos_en_uso = {norm(u.modelo) for u in deptos_disp if norm(u.modelo)}
        modelos_vacios = [n for n in modelos_nombres if norm(n) not in modelos_en_uso]
        # GATILLO = solo divergencia DURA: unidades disponibles que el catálogo NO
        # agrupa (modelo vacío o inexistente) → muestra MENOS stock del real (bug CCA).
        # Un modelo registrado sin unidades (modelos_vacios) NO gatilla por sí solo:
        # suele ser legítimo (tipo agotado, o un modelo "con jardín" que hoy no tiene
        # stock) y llenaría la sección de ruido (62 proyectos). Se muestra solo como
        # dato secundario en los proyectos que YA divergen por la señal dura.
        if not (sin_modelo or inexistente):
            continue
        disp_total = len(deptos_disp)
        # las que el catálogo SÍ agrupa bien = disponibles con modelo válido
        disp_catalogo = disp_total - len(sin_modelo) - len(inexistente)
        out.append({
            "id": p.id,
            "proyecto": p.nombre or p.id,
            "inmobiliaria": (p.inmobiliaria or "").strip() or "Sin inmobiliaria",
            "disp_total": disp_total,
            "disp_catalogo": disp_catalogo,
            "n_sin_modelo": len(sin_modelo),
            "n_inexistente": len(inexistente),
            "inexistente_ej": [f'{u.numero or "?"} ("{u.modelo}")' for u in inexistente[:5]],
            "modelos_vacios": modelos_vacios,
        })
    out.sort(key=lambda x: (x["inmobiliaria"].lower(), x["proyecto"].lower()))
    return out


def _catalogo_vs_stock_html(items: list[dict]) -> str:
    """Sección 'Catálogo vs Stock interno'. Lista los proyectos donde el catálogo
    NO refleja fielmente el stock (fuente de verdad = proyecto-vista.html). Numera
    cada caso. Vacía = todo alineado (mensaje verde)."""
    header = ('<h3 style="margin:22px 0 6px;color:#0a0d12;font-size:15px">🔄 Catálogo vs Stock interno</h3>'
              '<div style="font-size:11.5px;color:#6b7280;margin:-2px 0 8px">Manda el <b>stock interno</b> '
              '(proyecto-vista). El catálogo público agrupa por modelo: si una unidad no calza con un modelo '
              'registrado, se cae del catálogo y se muestra menos stock del real.</div>')
    if not items:
        return (header + '<div style="background:#dcfce7;border-left:4px solid #16a34a;border-radius:0 6px 6px 0;'
                'padding:10px 14px;color:#15803d;font-weight:700;font-size:12.5px">🟢 Catálogo y stock interno '
                'alineados — todas las unidades disponibles calzan con su modelo.</div>')
    filas = ""
    for i, it in enumerate(items, 1):
        url = _editor_url(it["id"], "modelos")
        proy = escape(it["proyecto"])
        inmob = escape(it["inmobiliaria"])
        partes = []
        if it["disp_catalogo"] < it["disp_total"]:
            partes.append(f'<b style="color:#dc2626">el catálogo muestra {it["disp_catalogo"]} de '
                          f'{it["disp_total"]}</b> disponibles')
        if it["n_sin_modelo"]:
            partes.append(f'{it["n_sin_modelo"]} unidad(es) sin modelo asignado')
        if it["n_inexistente"]:
            ej = escape(", ".join(it["inexistente_ej"]))
            partes.append(f'{it["n_inexistente"]} con modelo inexistente: {ej}')
        if it["modelos_vacios"]:
            mv = escape(", ".join(it["modelos_vacios"][:5]))
            partes.append(f'{len(it["modelos_vacios"])} modelo(s) sin stock: {mv}')
        detalle = " · ".join(partes)
        filas += (f'<div style="margin:2px 0;font-size:12px;color:#374151">'
                  f'<span style="color:#9ca3af">{i}.</span> '
                  f'<a href="{url}" style="color:#9a3412;text-decoration:underline"><b>{proy}</b> '
                  f'<span style="font-size:11px">({inmob})</span></a> — {detalle} '
                  f'<span style="color:#9ca3af;font-size:11px">→ revisar</span></div>')
    return (header + f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;'
            f'padding:10px 14px">{filas}</div>')


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
    """Email del operador humano (Cristofer) = destinatario To del informe diario.
    Si DAILY_REPORT_TO trae varios emails coma-separados, el operador es el PRIMERO
    (antes el match exacto fallaba y los informes decían "sin cambios" para siempre)."""
    return (settings.daily_report_to or "").split(",")[0].strip().lower()


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
                g = grupos.setdefault(key, {
                    "id": p.id, "nombre": key,
                    "inmobiliaria": (p.inmobiliaria or "").strip() or "Sin inmobiliaria",
                    "eventos": [],
                })
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
    """Bloque HTML "Mejoras …" como LÍNEA DE TIEMPO: una fila por movimiento ordenada
    por hora (todas mezcladas, NO agrupadas por proyecto). Cada fila:
    HH:MM · Proyecto — detalle. Reutilizado por el informe de las 09:00 y el de 13:00."""
    # op_nombre SIN escape acá: head pasa por escape() al renderizar (evitaba doble
    # entidad "&amp;amp;" si algún llamador omitía titulo).
    head = titulo or f"📋 Los avances de {op_nombre} {periodo}"
    if not n_op:
        return (f'<div style="margin:18px 0 0;padding:11px 14px;background:#f9fafb;border-radius:8px;'
                f'color:#6b7280;font-size:12.5px">📋 <b>{escape(head)}:</b> sin cambios registrados.</div>')
    # Aplanar todos los eventos de todos los proyectos en una sola línea de tiempo
    flat = []
    for g in op_grupos:
        for ev in g["eventos"]:
            flat.append((ev, g.get("nombre") or g.get("id"), g.get("inmobiliaria") or "Sin inmobiliaria"))
    flat.sort(key=lambda x: x[0]["fecha"])  # cronológico ascendente
    filas = []
    for ev, proy, inmob in flat:
        # solo la hora HH:MM (Chile), sin "hoy/ayer" — la fecha ya está en la cabecera
        hhmm = _hora_cl(ev["fecha"]).split(" ")[-1]
        tipo = _TIPO_LBL.get(ev.get("tipo", ""), ev.get("tipo") or "Cambio")
        det = escape((ev.get("detalles") or "").strip()[:200]) or escape(tipo)
        # (2026-07-06) SIEMPRE mostrar proyecto Y inmobiliaria — antes solo salía el
        # proyecto y era ambiguo de qué inmobiliaria era sin abrir el editor.
        filas.append(
            f'<div style="margin:0;padding:5px 0;border-bottom:1px solid #f3f4f6;font-size:12.5px;color:#374151">'
            f'<b style="color:#0a0d12">{escape(hhmm)}</b> '
            f'<span style="color:#9ca3af">·</span> '
            f'<b style="color:#1f7a3d">{escape(proy)}</b> '
            f'<span style="color:#9ca3af;font-size:11px">({escape(inmob)})</span> '
            f'<span style="color:#9ca3af">—</span> {det}</div>'
        )
    # Los build_* truncan op_grupos ([:20]/[:40]) pero pasan los TOTALES: si se
    # muestran menos movimientos que n_op, avisar en vez de truncar en silencio.
    _extra_op = (f'<div style="font-size:11px;color:#9ca3af;margin-top:6px">… y {n_op - len(flat)} '
                 f'movimiento(s) más (proyectos con menos cambios; detalle en el listado web)</div>'
                 if n_op > len(flat) else '')
    return (
        f'<h3 style="margin:22px 0 6px;color:#0a0d12;font-size:15px">{escape(head)}</h3>'
        f'<div style="font-size:12px;color:#6b7280;margin-bottom:6px">{n_op} cambio(s) en {n_op_proj} proyecto(s) · en orden cronológico</div>'
        f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:4px 14px">{"".join(filas)}</div>'
        f'{_extra_op}'
    )


_DIAS_FULL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MES_FULL = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]


def _operador_eventos_planos(proyectos, cutoff, end):
    """Todos los movimientos MANUALES del operador en [cutoff, end), aplanados con su
    proyecto y ordenados por hora ascendente (sin agrupar por proyecto)."""
    op_email = _operador_email()
    out = []
    if op_email:
        for p in proyectos:
            for ev in _eventos_ventana(p, cutoff):
                if end is not None and ev["fecha"] >= end:
                    continue
                if ev["tipo"] == "Alerta" or ev.get("origen_auto"):
                    continue
                if (ev.get("usuario") or "").strip().lower() != op_email:
                    continue
                out.append({**ev, "proyecto": p.nombre or p.id,
                            "inmobiliaria": (p.inmobiliaria or "").strip() or "Sin inmobiliaria"})
    out.sort(key=lambda e: e["fecha"])
    return out


def _resumen_semana_html(eventos) -> str:
    """Resumen día a día de la semana anterior (informe del lunes): por cada día con
    actividad, sus movimientos en orden de horario (HH:MM · Proyecto — detalle)."""
    titulo = '<h3 style="margin:24px 0 6px;color:#0a0d12;font-size:15px">📅 Resumen de la semana anterior</h3>'
    if not eventos:
        return (titulo + '<div style="padding:11px 14px;background:#f9fafb;border-radius:8px;'
                'color:#6b7280;font-size:12.5px">Sin actividad manual registrada la semana anterior.</div>')
    tz_cl = TZ_CL
    dias = {}  # iso -> [(cl_dt, ev)]
    for ev in eventos:
        cl = ev["fecha"].astimezone(tz_cl)
        dias.setdefault(cl.date().isoformat(), []).append((cl, ev))
    bloques = []
    # Cap por día (2026-07-07, anti-recorte de Gmail ~102KB): un solo día con
    # muchos cambios podía inflar todo el correo. El TOTAL real de la semana no
    # se esconde: sigue en el título del bloque siguiente y en el PDF adjunto
    # (Resolución de pendientes) para lo que sea un pendiente vigente.
    DIA_CAP = 15
    for iso in sorted(dias):
        lst = sorted(dias[iso], key=lambda x: x[0])  # orden horario ascendente
        d0 = lst[0][0]
        cab = f'{_DIAS_FULL[d0.weekday()]} {d0.day} {_MES_FULL[d0.month - 1]}'
        filas = []
        for cl, ev in lst[:DIA_CAP]:
            tipo = _TIPO_LBL.get(ev.get("tipo", ""), ev.get("tipo") or "Cambio")
            det = escape((ev.get("detalles") or "").strip()[:200]) or escape(tipo)
            filas.append(
                f'<div style="margin:0;padding:4px 0;border-bottom:1px solid #f3f4f6;font-size:12.5px;color:#374151">'
                f'<b style="color:#0a0d12">{cl.strftime("%H:%M")}</b> '
                f'<span style="color:#9ca3af">·</span> '
                f'<b style="color:#1f7a3d">{escape(ev["proyecto"])}</b> '
                f'<span style="color:#9ca3af;font-size:11px">({escape(ev.get("inmobiliaria") or "Sin inmobiliaria")})</span> '
                f'<span style="color:#9ca3af">—</span> {det}</div>'
            )
        if len(lst) > DIA_CAP:
            filas.append(
                f'<div style="margin:0;padding:4px 0;font-size:11px;color:#9ca3af">… y {len(lst) - DIA_CAP} '
                f'movimiento(s) más ese día — detalle en el listado web</div>'
            )
        bloques.append(
            f'<div style="margin-top:10px"><div style="font-size:13px;font-weight:700;color:#0a0d12;'
            f'background:#f3f4f6;padding:6px 10px;border-radius:6px">{escape(cab)} '
            f'<span style="color:#6b7280;font-weight:500">· {len(lst)} cambio(s)</span></div>'
            f'<div style="background:#fff;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;padding:2px 12px">{"".join(filas)}</div></div>'
        )
    return titulo + "".join(bloques)


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

_SNAP_LOCK = _threading.Lock()


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
    """Guarda el set de pendientes en el slot ('morning'). Escritura ATÓMICA
    (tmp + os.replace) bajo lock: una muerte del proceso a mitad de escritura ya no
    puede dejar el JSON truncado (y _snap_load devolviendo {} = línea base perdida)."""
    try:
        with _SNAP_LOCK:
            snap = _snap_load()
            snap[slot] = {"ts": ts, "items": items}
            path = _snap_path()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(_json.dumps(snap, ensure_ascii=False), "utf-8")
            _os.replace(tmp, path)
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
        # (2026-08-25) Marcar los pendientes de fichas que aún no están publicadas. Medido
        # ese día: de 28 proyectos con "Plan de pago incompleto", 24 no estaban a la venta —
        # son fichas a medio cargar, no urgencias, y mezcladas con las de proyectos
        # publicados hacían difícil ver cuál importa. El stock-interno ya las distingue en
        # pantalla; acá se anota el texto para que el informe se lea igual de claro.
        # Es SOLO texto: no cambia qué se reporta, ni el conteo, ni la clasificación.
        _pub = bool((p.extra or {}).get("publicar_en_catalogo"))
        for c in a.get("criticos", []):
            # OJO: la clave se calcula con el texto ORIGINAL, sin la anotación. Si la
            # anotación entrara en la clave, el informe siguiente vería TODOS los pendientes
            # como "resueltos" (los viejos) y "nuevos" (los mismos, anotados) de una vez.
            out[f"{p.id}::{_critico_key(c)}"] = {
                "proyecto": p.nombre or p.id, "id": p.id,
                "texto": c if _pub else c + " · ficha sin publicar",
                "inmobiliaria": (p.inmobiliaria or "").strip() or "Sin inmobiliaria",
            }
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


def _enriquecer_resueltos(cruce: dict, proyectos) -> None:
    """Agrega a cada pendiente 'resuelto' la HORA en que se solucionó: el último cambio
    en ese proyecto desde el informe previo (prev_ts del snapshot)."""
    prev_ts = cruce.get("prev_ts")
    since = None
    if prev_ts:
        try:
            since = datetime.fromisoformat(prev_ts)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except Exception:
            since = None
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=48)
    by_id = {p.id: p for p in proyectos}
    for it in cruce.get("resueltos", []):
        p = by_id.get(it.get("id"))
        if not p:
            continue
        evs = _eventos_ventana(p, since)
        # Solo eventos MANUALES cuentan como "cuándo se solucionó": una Alerta o un
        # import del scraper (origen_auto) no es un arreglo de la persona. Si no hay
        # eventos manuales, mejor SIN hora que una hora engañosa.
        evs = [e for e in evs if e.get("tipo") != "Alerta" and not e.get("origen_auto")]
        if evs:
            ult = max(evs, key=lambda e: e["fecha"])
            it["hora"] = _hora_cl(ult["fecha"]).split(" ")[-1]  # solo HH:MM


def _resolucion_html(cruce: dict, ref_label: str) -> str:
    """Bloque 'Resolución de pendientes' comparando contra el informe previo."""
    if not cruce.get("tiene_previo"):
        return ('<div style="margin:18px 0 0;padding:11px 14px;background:#f9fafb;border-radius:8px;'
                'color:#6b7280;font-size:12.5px">🔁 <b>Resolución de pendientes:</b> es la primera '
                f'corrida — todavía no hay un informe previo ({escape(ref_label)}) con qué comparar.</div>')
    res, per, nue = cruce["resueltos"], cruce["persisten"], cruce["nuevos"]

    def _lista(items, color, con_link=False):
        # Email-safe: <div> con bullet (no <ul><li>, que Gmail/Outlook recortan).
        # con_link=True: el error es un LINK al editor en la pestaña donde se arregla.
        # Orden inmobiliaria → proyecto (mismo criterio que el PDF adjunto, pedido
        # Nicolás 2026-07-07) + número de caso por fila (antes solo bullet, sin
        # forma de referenciar "el pendiente #12" al hablar con el equipo).
        def _fila(it, n):
            hora = it.get("hora")
            hora_html = f' <b style="color:#0a0d12">{escape(hora)}</b>' if hora else ''
            proy = escape(it["proyecto"])
            # .get() con fallback: snapshots viejos (previos a este cambio) no tienen
            # "inmobiliaria" — nunca debe faltar en pantalla, aunque venga de un snapshot antiguo.
            inmob = escape(it.get("inmobiliaria") or "Sin inmobiliaria")
            txt = escape(it["texto"])
            if con_link and it.get("id"):
                url = _editor_url(it["id"], _tab_for(it["texto"]))
                cuerpo = (f'<a href="{url}" style="color:{color};text-decoration:underline">'
                          f'<b>{proy}</b> <span style="font-size:11px">({inmob})</span> — {txt}</a> '
                          f'<span style="color:#9ca3af;font-size:11px">→ arreglar</span>')
            else:
                cuerpo = f'<b style="color:#0a0d12">{proy}</b> <span style="font-size:11px;color:#6b7280">({inmob})</span> — {txt}'
            return (f'<div style="margin:2px 0;font-size:12px;color:{color}">'
                    f'<span style="color:#9ca3af">{n}.</span>{hora_html} {cuerpo}</div>')
        items_sorted = sorted(items, key=lambda it: (
            (it.get("inmobiliaria") or "").lower(), (it.get("proyecto") or "").lower(),
        ))
        # (2026-07-06) El PDF adjunto SIEMPRE trae el listado COMPLETO (sin cortar,
        # inmune al límite ~102KB de Gmail que recortaba el cuerpo del email si se
        # listaban todos acá). El cuerpo muestra una vista previa acotada; bajado
        # de 25→15 el 2026-07-07 (junto con compactar "Resumen por inmobiliaria")
        # porque el correo real llegó a pesar 169KB y Gmail lo recortaba entero.
        CAP = 15
        filas = "".join(_fila(it, i + 1) for i, it in enumerate(items_sorted[:CAP]))
        extra = (f'<div style="font-size:11px;color:#9ca3af;margin:2px 0">… y {len(items_sorted)-CAP} más '
                 f'→ ver el listado completo en el PDF adjunto</div>') if len(items_sorted) > CAP else ''
        return f'<div style="margin:3px 0 8px">{filas}{extra}</div>' if items_sorted else ''

    cuerpo = ""
    cuerpo += f'<div style="font-size:12.5px;color:#16a34a;font-weight:700;margin-top:6px">✅ Solucionados {escape(ref_label)} · {len(res)}</div>'
    cuerpo += _lista(res, "#15803d") if res else '<div style="font-size:11.5px;color:#9ca3af;margin-bottom:6px">— ninguno —</div>'
    cuerpo += f'<div style="font-size:12.5px;color:#ea580c;font-weight:700">⏳ Siguen pendientes · {len(per)}</div>'
    cuerpo += _lista(per, "#9a3412", con_link=True) if per else '<div style="font-size:11.5px;color:#9ca3af;margin-bottom:6px">— ninguno —</div>'
    if nue:
        cuerpo += f'<div style="font-size:12.5px;color:#dc2626;font-weight:700">🆕 Nuevos · {len(nue)}</div>'
        cuerpo += _lista(nue, "#991b1b", con_link=True)
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


def build_daily_report(db: Session, forzar_semana: bool = False) -> dict:
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
    _now_cl = datetime.now(TZ_CL)  # hora real de Chile (DST-aware)
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
    _tz_cl = TZ_CL
    _hoy_cl_00 = datetime.now(_tz_cl).replace(hour=0, minute=0, second=0, microsecond=0)
    _dias_atras = 3 if _now_cl.weekday() == 0 else 1
    _op_cutoff = _hoy_cl_00 - timedelta(days=_dias_atras)
    operador_grupos, n_operador, _ = _operador_actividad(proyectos, _op_cutoff, end=_hoy_cl_00)

    # Los LUNES: resumen día a día de la SEMANA CALENDARIO anterior (lunes→domingo),
    # SIEMPRE empezando en lunes (aunque se fuerce otro día con ?semana=true).
    semana_anterior = None
    if _now_cl.weekday() == 0 or forzar_semana:
        _este_lunes = _hoy_cl_00 - timedelta(days=_now_cl.weekday())  # lunes de ESTA semana 00:00
        _sem_ini = _este_lunes - timedelta(days=7)                    # lunes pasado 00:00
        semana_anterior = _operador_eventos_planos(proyectos, _sem_ini, _este_lunes)

    # ─── Cruce de pendientes vs el informe de la MAÑANA anterior ────────────
    # Compara los críticos de hoy contra el último snapshot 'morning' (informe de
    # ayer) → qué se solucionó / qué sigue. El snapshot se guarda al ENVIAR (no en
    # el preview), así la comparación no se corrompe al previsualizar.
    pend_actual = _pendientes_actuales(proyectos)
    cruce = _resolucion_cruce("morning", pend_actual)
    _enriquecer_resueltos(cruce, proyectos)

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
        "semana_anterior": semana_anterior,
        "catalogo_vs_stock": _catalogo_vs_stock(proyectos),
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
    u = f"{_BASE}/src/stock-interno/proyecto.html?id={_urlquote(pid or '', safe='')}"
    return u + (f"#tab={tab}" if tab else "")


# Mapa pendiente → pestaña del editor donde se arregla (orden importa: el primer
# keyword que aparezca gana). "modelo sin planta" → modelos; "depto sin precio" → unidades.
_TAB_KEYWORDS = [
    # Estos 3 van PRIMERO: sus mensajes contienen "unidad"/"precio" (ej. "unidades
    # totales", "precio en cotizador") que de otro modo matchearían esos keywords
    # más abajo y mandarían a la pestaña equivocada (unidades) en vez de "general".
    ("físic", "general"),                # "Datos físicos incompletos: ..."
    ("plan de pago", "general"),          # "Plan de pago incompleto: ..."
    ("forma de pago del pie", "general"),  # "Forma de pago del pie incompleta: ..."
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


def _pendientes_pdf_bytes(items: list[dict], fecha_cl: str) -> bytes:
    """PDF con TODOS los pendientes vigentes, uno por fila, CADA FILA es un link
    clickeable directo a la pestaña del editor donde se arregla (pedido Nicolás
    2026-07-06). A diferencia del cuerpo del email (limitado a ~102KB antes de que
    Gmail lo recorte), el PDF nunca corta nada — es la lista completa garantizada.
    """
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=1.3 * cm, rightMargin=1.3 * cm, topMargin=1.3 * cm, bottomMargin=1.3 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PendTitulo", parent=styles["Heading1"], fontSize=15, spaceAfter=3)
    sub_style = ParagraphStyle("PendSub", parent=styles["Normal"], fontSize=9,
                               textColor=colors.HexColor("#6b7280"), spaceAfter=4)
    inmob_style = ParagraphStyle("PendInmob", parent=styles["Normal"], fontSize=10,
                                 textColor=colors.white, leading=13)
    row_style = ParagraphStyle("PendFila", parent=styles["Normal"], fontSize=9, leading=12,
                               textColor=colors.HexColor("#111827"))

    # Orden VISUAL por inmobiliaria → proyecto (no oculta ni resume nada: la
    # cantidad de filas es exactamente len(items), igual que si fuera una sola lista).
    items_sorted = sorted(items, key=lambda it: (
        (it.get("inmobiliaria") or "").lower(), (it.get("proyecto") or "").lower(),
    ))

    elems = [
        Paragraph("Pendientes de ficha · Stock BigCapital", title_style),
        Paragraph(
            f"{escape(fecha_cl)} &middot; {len(items_sorted)} pendiente(s) en total &middot; "
            f"clic en cualquier fila para arreglarlo directo en el editor",
            sub_style,
        ),
        Spacer(1, 6),
    ]

    LINK_COLOR = "#1d4ed8"
    rows = [[Paragraph("<b>#</b>", row_style), Paragraph("<b>Pendiente</b>", row_style)]]
    row_bg_idx = []  # índices de fila (dentro de `rows`, con header) que son cabecera de inmobiliaria
    last_inmob = None
    n = 0
    for it in items_sorted:
        inmob = it.get("inmobiliaria") or "Sin inmobiliaria"
        if inmob != last_inmob:
            rows.append([Paragraph("", inmob_style), Paragraph(escape(inmob), inmob_style)])
            row_bg_idx.append(len(rows) - 1)
            last_inmob = inmob
        n += 1
        pid = it.get("id") or ""
        url = _editor_url(pid, _tab_for(it.get("texto") or ""))
        proy = escape(it.get("proyecto") or pid)
        texto = escape(it.get("texto") or "")
        # Inmobiliaria SIEMPRE en la fila (no solo en el encabezado de grupo): si la
        # tabla corta entre páginas, el encabezado de arriba puede no quedar visible
        # en la página siguiente y la fila queda sin contexto de a quién pertenece.
        celda = (f'<link href="{escape(url)}" color="{LINK_COLOR}"><b>{proy}</b> '
                 f'<font size="8" color="#6b7280">({escape(inmob)})</font> &mdash; {texto}</link>')
        rows.append([Paragraph(str(n), row_style), Paragraph(celda, row_style)])

    tbl = Table(rows, colWidths=[1.2 * cm, 17.0 * cm], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for idx in row_bg_idx:
        style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#374151")))
        style_cmds.append(("SPAN", (0, idx), (-1, idx)))
    tbl.setStyle(TableStyle(style_cmds))
    elems.append(tbl)
    doc.build(elems)
    return buf.getvalue()


def _attach_pendientes_pdf(msg: EmailMessage, cruce: dict, fecha_cl: str) -> None:
    """Adjunta el PDF con TODOS los pendientes vigentes (persisten + nuevos). Si no
    hay ninguno, o si reportlab falla por cualquier motivo, no adjunta nada — nunca
    debe romper el envío del email por esto."""
    try:
        items = (cruce.get("persisten") or []) + (cruce.get("nuevos") or [])
        if not items:
            return
        pdf_bytes = _pendientes_pdf_bytes(items, fecha_cl)
        fname = f"pendientes_stock_{datetime.now(TZ_CL):%Y-%m-%d}.pdf"
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=fname)
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo generar/adjuntar el PDF de pendientes: %s", e, exc_info=True)


def _project_link(p: dict, tab: str = "") -> str:
    """Nombre del proyecto como link al editor (pestaña opcional)."""
    nombre = escape(p.get("nombre") or p.get("id") or "")
    return f"<a href='{_editor_url(p.get('id') or '', tab)}' style='color:#1f7a3d;text-decoration:none;font-weight:700'>{nombre}</a>"


def _kpi_cell(label, value, color, sub, bg="#f9fafb", lblcolor="#6b7280"):
    # Compacto para móvil: padding 8 + fuente 22 (con spacing 5 la fila de 4 KPIs
    # cabe en 375px; antes padding 12 + spacing 8 = 384px → scroll lateral).
    return f'''<td style="background:{bg};border-radius:8px;padding:8px 4px;text-align:center;width:25%">
      <div style="font-size:10.5px;color:{lblcolor};font-weight:700;text-transform:uppercase;letter-spacing:.2px">{escape(label)}</div>
      <div style="font-size:22px;color:{color};font-weight:800;margin-top:2px;line-height:1">{value}</div>
      <div style="font-size:10.5px;color:{lblcolor};margin-top:2px">{escape(sub)}</div></td>'''


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
    cl = dt.astimezone(TZ_CL)
    now = datetime.now(TZ_CL)
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
    kpis = f'''<table style="width:100%;border-collapse:separate;border-spacing:5px"><tr>
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
          <td style="vertical-align:middle;text-align:right">
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
        # Anti-recorte de Gmail (~102KB): el email pesaba 235KB porque cada proyecto
        # listaba TODOS sus pendientes con link (~1.9KB c/u × 113). En el EMAIL esta
        # sección va COMPACTA: 1 línea por proyecto, SOLO nombre + conteos (sin link
        # ni indicador de antigüedad — ver comentario más abajo, 2026-07-07). El
        # detalle accionable con links "→ arreglar" vive en Resolución de pendientes
        # (arriba), el PDF adjunto (completo) y el listado web (dashboard clicable).
        con_pend = [p for p in ps if p["n_crit"] or p["n_warn"]]
        ok_list = [p for p in ps if not (p["n_crit"] or p["n_warn"])]
        for p in con_pend:
            pub = ' 🌐' if p["publicado"] else ''
            if p["n_crit"]:
                cnt = f'<b style="color:#dc2626">●{p["n_crit"]}c</b>'
                if p["n_warn"]:
                    cnt += f'·{p["n_warn"]}w'
            else:
                cnt = f'<b style="color:#ca8a04">●{p["n_warn"]}w</b>'
            # (2026-07-07) SIN link ni indicador de antigüedad por fila — esta sección
            # es un TABLERO de un vistazo (114 proyectos), no la lista accionable.
            # Antes cada fila llevaba <a href=...editor> (~170 bytes) × 113 proyectos
            # con pendiente → 54KB solo esta sección, con "Resumen semana anterior"
            # empujaba el correo a 169KB (Gmail recorta sobre ~102KB, se perdía TODO
            # lo que viene después: errores del scraper incluido). Los links de
            # verdad viven en "Resolución de pendientes" (arriba) y en el PDF adjunto
            # (completo, sin límite de tamaño) — acá solo el nombre, en texto plano.
            rows += (f'<div style="padding:3px 0;font-size:12px;color:#374151">'
                     f'<b style="color:#0a0d12">{escape(p["nombre"])}</b>{pub} {cnt}</div>')
        if ok_list:
            nombres_ok = " &nbsp;·&nbsp; ".join(escape(p["nombre"]) for p in ok_list)
            rows += (f'<div style="padding:9px 0;font-size:12px;color:#15803d;line-height:1.7">'
                     f'<b>✓ Al día ({len(ok_list)}):</b> <span style="color:#374151">{nombres_ok}</span></div>')
        cal = g.get("calidad", 0)
        cal_col, cal_bg, _cal_lbl = _calidad_band(cal)
        # Header SIN flex ni nowrap: nombre y chips en líneas propias → apila
        # natural en teléfonos (los chips desbordaban 80px en 375px) y renderiza
        # bien en Outlook escritorio (que ignora flexbox).
        inmob_html += f'''<div style="margin-top:14px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
          <div style="background:#0b1628;color:#fff;padding:10px 14px">
            <div style="font-weight:800;font-size:15px">{escape(g["nombre"])}</div>
            <div style="margin-top:5px;line-height:2">
              <span style="font-size:11.5px;background:{cal_bg};color:{cal_col};padding:3px 9px;border-radius:11px;font-weight:800">calidad {cal}/100</span>
              <span style="font-size:11.5px;background:{chip_bg};color:{chip_col};padding:3px 9px;border-radius:11px;font-weight:700">{escape(chip_txt)}</span>
            </div>
          </div>
          <div style="padding:6px 14px 12px">{rows}</div></div>'''

    # ─── Errores del scraper (si hay)
    errores_html = ""
    if data["errores_24h"]:
        rows_err = []
        # Cap 10 filas en el EMAIL (anti-recorte Gmail); el conteo total va en el título.
        _errs = data["errores_24h"][:10]
        for e in _errs:
            hora = e["fecha"].astimezone(TZ_CL).strftime("%d/%m %H:%M") if e.get("fecha") else "—"
            rows_err.append(f'''<tr>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;font-size:12px;color:#6b7280;white-space:nowrap;width:90px">{escape(hora)}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;font-weight:700;color:#0a0d12;font-size:12.5px">{escape(e["proyecto"])}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #fecaca;color:#7f1d1d;font-size:12px">{escape((e.get("detalles","") or "")[:160])}</td>
            </tr>''')
        _extra_err = (f'<div style="font-size:11px;color:#9ca3af;margin-top:4px">… y {data["n_errores_24h"] - len(_errs)} error(es) más</div>'
                      if data["n_errores_24h"] > len(_errs) else '')
        errores_html = f'''
        <h3 style="margin:24px 0 8px;color:#dc2626;font-size:15px">🚨 Errores del scraper · {data["n_errores_24h"]} en últimas 24h</h3>
        <table style="width:100%;border-collapse:collapse;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;overflow:hidden">
          <thead><tr style="background:#fee2e2">
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Hora</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Proyecto</th>
            <th style="padding:6px 10px;text-align:left;font-size:11px;color:#7f1d1d;font-weight:700">Detalle</th>
          </tr></thead>
          <tbody>{"".join(rows_err)}</tbody>
        </table>{_extra_err}'''

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
    # LUNES (o ?semana=true): el "día anterior" es domingo (sin trabajo) → NO va la
    # sección diaria; en su lugar va el "Resumen de la semana anterior". Otros días: al revés.
    es_lunes = data.get("semana_anterior") is not None
    _vent = data.get("actividad_horas", 24)
    _periodo = "el fin de semana" if _vent > 24 else "el día anterior"
    _periodo_titulo = "del fin de semana" if _vent > 24 else "del día anterior"
    operador_html = "" if es_lunes else _operador_section_html(
        data.get("operador_nombre") or "el operador",
        data.get("operador_grupos", []),
        data.get("n_operador", 0),
        data.get("n_operador_proyectos", 0),
        _periodo,
        titulo=f"📋 Mejoras {_periodo_titulo}",
    )
    # Cruce de pendientes vs informe anterior (qué se solucionó / qué sigue)
    resolucion_html = _resolucion_html(data.get("cruce", {}), "desde el informe anterior")
    # Catálogo vs Stock interno (monitoreo diario de desincronización de modelos)
    catalogo_stock_html = _catalogo_vs_stock_html(data.get("catalogo_vs_stock", []))
    disclaimer_html = _disclaimer_html()
    # Lunes: resumen día a día de la semana anterior (None los demás días).
    semana_html = _resumen_semana_html(data["semana_anterior"]) if es_lunes else ""

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
          {semana_html}
          {resolucion_html}
          {catalogo_stock_html}
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


def send_daily_report(forzar_semana: bool = False, guardar_snapshot: bool = True) -> str:
    """Disparado por APScheduler L-V 09am. Retorna el estado real del envío
    ('enviado' | 'smtp_no_configurado' | 'deshabilitado' | 'error: …') para que
    los endpoints /test no digan ok:true cuando en realidad no salió nada."""
    if not _configured():
        log.info("daily_report: SMTP no configurado — informe NO enviado.")
        return "smtp_no_configurado"
    if not settings.daily_report_enabled:
        log.info("daily_report: deshabilitado (DAILY_REPORT_ENABLED=false).")
        return "deshabilitado"
    try:
        with SessionLocal() as db:
            data = build_daily_report(db, forzar_semana=forzar_semana)
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
        _attach_pendientes_pdf(msg, data.get("cruce", {}), data["fecha_cl"])
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        # Guardar el set de pendientes de HOY como snapshot 'morning' → el informe
        # de mañana compara contra esto para saber qué se solucionó. Los disparos
        # de PRUEBA (/admin/daily-report/test) pasan guardar_snapshot=False para NO
        # corromper la línea base del cruce (un test a las 18:00 borraría la foto
        # de las 09:00 y los "Solucionados" del día desaparecerían del informe).
        if guardar_snapshot:
            _snap_set("morning", data.get("pend_actual", {}), datetime.utcnow().isoformat())
        log.info(
            "daily_report enviado → To:%s Cc:%s · activos:%d disp:%d inmob:%d crit:%d warn:%d sinCargar:%d staleStock:%d",
            to_addr, ", ".join(cc_list) or "—",
            data["n_activos"], data["n_disponibles_total"], len(data["inmobiliarias"]),
            data["n_con_critico"], data["n_con_warning"],
            len(data["sin_cargar"]), len(data["sin_actualizar"]),
        )
        return "enviado"
    except Exception as e:
        log.error("daily_report falló: %s", e, exc_info=True)
        return f"error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# Informe de las 13:00 · SOLO los avances de Cristofer HOY (acciones manuales)
# ════════════════════════════════════════════════════════════════════════════

def build_operador_today(db: Session) -> dict:
    """Cambios MANUALES del operador humano (Cristofer) HOY: desde la medianoche de
    Chile hasta el momento de correr. SOLO su usuario (email exacto), sin scraper
    (mismo filtro doble que _operador_actividad: email + descarta origen_auto)."""
    proyectos = _proyectos_activos(db)
    tz_cl = TZ_CL  # Chile con DST real
    medianoche_cl = datetime.now(tz_cl).replace(hour=0, minute=0, second=0, microsecond=0)
    grupos, n, n_proj = _operador_actividad(proyectos, medianoche_cl)
    # Cruce: qué de los pendientes de la MAÑANA (informe 09:00 de hoy) se solucionó.
    pend_actual = _pendientes_actuales(proyectos)
    cruce = _resolucion_cruce("morning", pend_actual)
    _enriquecer_resueltos(cruce, proyectos)
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
        </div>
      </div>
    </body></html>
    """


def send_operador_today_report() -> str:
    """Disparado por APScheduler L-V 13:00 Chile. Envía SOLO los avances de hoy de
    Cristofer a operador_report_to. Retorna el estado real del envío."""
    if not _configured():
        log.info("operador_today: SMTP no configurado — informe NO enviado.")
        return "smtp_no_configurado"
    if not settings.operador_report_enabled:
        log.info("operador_today: deshabilitado (OPERADOR_REPORT_ENABLED=false).")
        return "deshabilitado"
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
            return "sin_destinatarios"
        msg["To"] = ", ".join(dests)
        msg["Reply-To"] = from_addr
        msg.set_content(
            f"Mejoras de hoy · {data['fecha_cl']}\n"
            f"{data['n_operador']} cambio(s) en {data['n_operador_proyectos']} proyecto(s)."
        )
        msg.add_alternative(html, subtype="html")
        _attach_pendientes_pdf(msg, data.get("cruce", {}), data["fecha_cl"])
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass.replace(" ", ""))
            s.send_message(msg)
        # (el slot 'afternoon' se eliminó: se escribía en cada envío de las 13:00
        # pero ningún cruce lo leía — solo 'morning' es línea base.)
        log.info("operador_today enviado → %s · %d cambios / %d proyectos",
                 ", ".join(dests), data["n_operador"], data["n_operador_proyectos"])
        return "enviado"
    except Exception as e:
        log.error("operador_today falló: %s", e, exc_info=True)
        return f"error: {e}"


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
