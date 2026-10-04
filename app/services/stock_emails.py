"""Correos "Stock interno" al equipo de stock — bc-api · 2026-10-05

Pedido de Nicolás (30/09/2026), L-V a las 09:02 y 09:04, a los cuatro del equipo
(settings.equipo_stock_to). Solo salen si hay algo que hacer: silencio = todo bien.

1. "Stock interno · N proyectos sin revisar": proyectos publicados con más de 3 días
   corridos sin que un robot o una persona haya revisado el stock (8 en Vellatrix y
   Las Palmas). Tres secciones: robot detenido, robot sin actualizar, sin revisar (a
   mano). Se repite cada día mientras siga pendiente. Cálculo: estado_stock.py.
2. "Stock interno · fallas en N fichas": lo que falta o no cuadra en cada ficha de
   stock propio (publicadas, en preparación y desactivadas). Lista completa cada día,
   con "abierta hace N días" y NUEVA. Reglas: fallas.py.

El estado (desde cuándo está abierta cada falla, qué salió en el último correo, el
resultado de cada envío) vive en settings.state_dir, FUERA de uploads/ (que se sirve
público). Solo lo escribe el envío programado; las vistas previas nunca lo tocan.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models.proyecto import Proyecto
from app.services.email_service import _fecha_cl, destinatarios_equipo, enviar_html
from app.services.estado_stock import TZ_CL, estado_stock, grupo_publicacion
from app.services.fallas import AVISO, CRITICA, fallas_seguras
from app.settings import settings

log = logging.getLogger(__name__)

ARCHIVO_ESTADO = "stock_emails_state.json"
DIAS_RECUERDO_AUSENTE = 7   # una falla que desaparece y vuelve antes de esto no es NUEVA
MAX_FILAS_FALLAS = 80       # cuerpo del correo; la lista completa va en el PDF
MAX_BYTES = 90_000          # Gmail recorta sobre ~102 KB
_LOCK = threading.Lock()

SECCIONES_STOCK = [
    ("robot_detenido", "⛔ Robot detenido",
     "El robot revisa, pero frenó la subida. Revisa el motivo; si hace falta, actualiza el stock a mano."),
    ("robot_sin_actualizar", "🤖 Robot sin actualizar",
     "Nicolás: revisa el robot. Equipo: mientras tanto, actualiza el stock a mano."),
    ("sin_revisar", "✋ Sin revisar (a mano)",
     "Revisa el stock y súbelo, o marca «Revisé el stock: sin cambios» en el editor."),
]
SECCIONES_FALLAS = [
    ("publicados", "Publicadas"),
    ("en_preparacion", "En preparación (no publicadas)"),
    ("desactivados", "Desactivadas"),
]


# ── Estado ──────────────────────────────────────────────────────────────────

def _ruta():
    return settings.state_path / ARCHIVO_ESTADO


def hoy_cl(now: Optional[datetime] = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TZ_CL).date()


def cargar_estado() -> dict:
    """Lee el estado. Si el archivo está dañado lo aparta (.corrupto-<fecha>) y parte
    de cero (la próxima corrida de fallas vuelve a sembrar, sin marcar nada NUEVA)."""
    ruta = _ruta()
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        try:
            os.replace(ruta, ruta.with_name(f"{ruta.name}.corrupto-{datetime.now(TZ_CL):%Y%m%d-%H%M%S}"))
        except Exception:  # noqa: BLE001
            pass
        log.warning("stock_emails: estado dañado (%s), se parte de cero", e)
        return {}


def guardar_estado(estado: dict) -> None:
    """Escritura atómica (tmp + os.replace) bajo candado."""
    ruta = _ruta()
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, ruta)


def _marcar_job(estado: dict, job: str, resultado: str, now: Optional[datetime] = None) -> None:
    estado.setdefault("jobs", {})[job] = {"fecha_chile": hoy_cl(now).isoformat(), "resultado": resultado}


def registrar_resultado(job: str, resultado: str) -> None:
    """Anota el resultado de un envío (para la línea «resultado de ayer» del informe)."""
    try:
        with _LOCK:
            est = cargar_estado()
            _marcar_job(est, job, resultado)
            guardar_estado(est)
    except Exception as e:  # noqa: BLE001
        log.warning("stock_emails: no se pudo anotar el resultado de %s: %s", job, e)


def resultados_jobs() -> dict:
    return (cargar_estado().get("jobs") or {})


# ── Utilidades HTML ─────────────────────────────────────────────────────────

def _editor_url(pid: str, tab: str = "") -> str:
    from app.services.daily_report import _editor_url as _u
    return _u(pid, tab)


def _marco(titulo: str, subtitulo: str, cuerpo: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;padding:0;font-family:-apple-system,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:720px;margin:0 auto;padding:24px 16px">
    <div style="background:#7DC242;color:#0a0d12;padding:16px 20px;border-radius:12px 12px 0 0">
      <div style="font-weight:800;font-size:18px">{escape(titulo)}</div>
      <div style="font-size:12.5px;opacity:.78;margin-top:3px">{escape(subtitulo)}</div>
    </div>
    <div style="background:#fff;padding:18px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none">
      {cuerpo}
      <div style="margin:22px 0 0;padding:12px 14px;background:#f9fafb;border-radius:8px;text-align:center;font-size:12px;color:#6b7280">
        Correo automático · L-V 09:00 Chile · solo llega si hay algo pendiente<br>
        <a href="https://herramientas.bigcapital.cl/src/stock-interno/" style="color:#1f7a3d;font-weight:700;text-decoration:none">→ Abrir el listado de stock propio</a>
      </div>
    </div>
  </div></body></html>"""


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


# ── 1. Stock sin revisar ────────────────────────────────────────────────────

def build_sin_revisar(db: Session, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    proyectos = db.query(Proyecto).filter(Proyecto.deleted_at.is_(None)).all()
    filas = []
    for p in proyectos:
        try:
            e = estado_stock(p, now)
        except Exception:  # noqa: BLE001
            log.warning("estado_stock falló para %s", p.id, exc_info=True)
            continue
        if not e["aplica"] or e["estado"] == "al_dia":
            continue
        filas.append({"id": p.id, "nombre": p.nombre or p.id,
                      "inmobiliaria": (p.inmobiliaria or "").strip() or "Sin inmobiliaria", **e})

    def _orden_dias(f):
        return -(f["dias"] if f["dias"] is not None else 10_000)

    secciones = []
    for clave, titulo, instruccion in SECCIONES_STOCK:
        del_tipo = [f for f in filas if f["estado"] == clave]
        if not del_tipo:
            continue
        por_inmob: dict = {}
        for f in del_tipo:
            por_inmob.setdefault(f["inmobiliaria"], []).append(f)
        grupos = []
        for inmob, fs in por_inmob.items():
            fs.sort(key=lambda f: (_orden_dias(f), f["nombre"].lower()))
            grupos.append({"inmobiliaria": inmob, "filas": fs, "urgente": any(f["urgente"] for f in fs)})
        grupos.sort(key=lambda g: (not g["urgente"], _orden_dias(g["filas"][0]), g["inmobiliaria"].lower()))
        secciones.append({"clave": clave, "titulo": titulo, "instruccion": instruccion,
                          "n": len(del_tipo), "grupos": grupos})
    cuenta = {c: sum(1 for f in filas if f["estado"] == c) for c, _, _ in SECCIONES_STOCK}
    return {"fecha_cl": _fecha_cl(), "n": len(filas), "n_urgentes": sum(1 for f in filas if f["urgente"]),
            "cuenta": cuenta, "secciones": secciones}


def asunto_sin_revisar(data: dict) -> str:
    c = data["cuenta"]
    partes = []
    if c.get("robot_detenido"):
        partes.append(_plural(c["robot_detenido"], "robot detenido", "robots detenidos"))
    if c.get("robot_sin_actualizar"):
        partes.append(_plural(c["robot_sin_actualizar"], "robot sin actualizar", "robots sin actualizar"))
    if c.get("sin_revisar"):
        partes.append(f"{c['sin_revisar']} a mano")
    return (f"Stock interno · {_plural(data['n'], 'proyecto sin revisar', 'proyectos sin revisar')}"
            + (f" ({', '.join(partes)})" if partes else ""))


def html_sin_revisar(data: dict) -> str:
    if not data["n"]:
        cuerpo = ('<div style="padding:12px 14px;background:#dcfce7;border-radius:8px;color:#15803d;font-weight:700">'
                  'Todo el stock publicado tiene una revisión de los últimos 3 días (8 en Vellatrix y Las Palmas). '
                  'Hoy no se enviaría correo.</div>')
        return _marco("Stock interno · proyectos sin revisar", data["fecha_cl"], cuerpo)
    intro = ('<div style="font-size:12.5px;color:#374151;margin-bottom:10px;line-height:1.5">'
             'Proyectos <b>publicados</b> con más de <b>3 días corridos</b> sin revisión del stock '
             '(8 en Vellatrix y Las Palmas, que mandan archivo semanal). Cuenta como revisión que un robot '
             'corrió o que alguien revisó, aunque no haya cambios. En <b style="color:#dc2626">rojo</b>: '
             '7 días o más.</div>')
    bloques = []
    for sec in data["secciones"]:
        filas_html = []
        for g in sec["grupos"]:
            filas_html.append(f'<div style="margin:10px 0 2px;font-size:13px;font-weight:800;color:#0b1628">'
                              f'{escape(g["inmobiliaria"])}</div>')
            for f in g["filas"]:
                rojo = f["urgente"]
                color = "#dc2626" if rojo else "#9a3412"
                dias = ("nunca revisado" if f["dias"] is None
                        else _plural(f["dias"], "día sin revisión", "días sin revisión"))
                quien = (f"por {f['por']}" if f.get("por") and f["por"] != "sin registro"
                         else "sin registro de quién la hizo")
                ultima = (f"Última revisión: {escape(f['ok_at_txt'])} · {escape(quien)}"
                          if f["ok_at_txt"] else "Sin revisiones registradas")
                motivo = (f'<div style="font-size:11.5px;color:#7f1d1d;margin-top:1px">{escape(f["motivo"])}</div>'
                          if f.get("motivo") else "")
                filas_html.append(
                    f'<div style="padding:5px 0;border-bottom:1px solid #f3f4f6;font-size:12.5px">'
                    f'<a href="{_editor_url(f["id"], "stock")}" style="color:#1f7a3d;font-weight:700;'
                    f'text-decoration:underline">{escape(f["nombre"])}</a> '
                    f'<b style="color:{color}">· {escape(dias)}</b>'
                    f'<div style="font-size:11.5px;color:#6b7280">{ultima}</div>{motivo}</div>')
        bloques.append(
            f'<h3 style="margin:20px 0 4px;color:#0a0d12;font-size:15px">{escape(sec["titulo"])} · {sec["n"]}</h3>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px">{escape(sec["instruccion"])}</div>'
            f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:2px 14px 8px">'
            f'{"".join(filas_html)}</div>')
    return _marco("Stock interno · proyectos sin revisar", data["fecha_cl"], intro + "".join(bloques))


def _texto_plano_sin_revisar(data: dict) -> str:
    lineas = [asunto_sin_revisar(data), data["fecha_cl"], ""]
    for sec in data["secciones"]:
        lineas.append(f"{sec['titulo']} · {sec['n']}")
        for g in sec["grupos"]:
            for f in g["filas"]:
                d = "nunca revisado" if f["dias"] is None else f"{f['dias']} días"
                lineas.append(f"- {f['nombre']} ({g['inmobiliaria']}): {d}")
        lineas.append("")
    return "\n".join(lineas)


def send_sin_revisar() -> str:
    """Disparado por el programador L-V 09:02. Silencio si no hay nada que avisar."""
    if not settings.stock_sin_revisar_enabled:
        return "deshabilitado"
    try:
        with SessionLocal() as db:
            data = build_sin_revisar(db)
    except Exception as e:  # noqa: BLE001
        log.error("stock sin revisar: falló al armar: %s", e, exc_info=True)
        _avisar_error("Correo «proyectos sin revisar» no se pudo armar", str(e))
        return f"error: {e}"
    if not data["n"]:
        registrar_resultado("stock", "sin novedad")
        return "sin_novedad"
    estado = enviar_html(asunto_sin_revisar(data), html_sin_revisar(data), _texto_plano_sin_revisar(data),
                         destinatarios_equipo())
    if estado == "enviado":
        registrar_resultado("stock", f"enviado ({data['n']})")
    else:
        _avisar_error("Correo «proyectos sin revisar» no salió", estado)
    log.info("stock sin revisar → %s · %d proyectos", estado, data["n"])
    return estado


# ── 2. Fallas en fichas ─────────────────────────────────────────────────────

def build_fallas(db: Session, now: Optional[datetime] = None, estado: Optional[dict] = None) -> dict:
    """Arma el correo de fallas y el estado que quedaría si se envía (no lo guarda)."""
    now = now or datetime.now(timezone.utc)
    hoy = hoy_cl(now)
    hoy_iso = hoy.isoformat()
    estado = dict(estado if estado is not None else cargar_estado())
    previas = dict(estado.get("fallas") or {})
    sembrando = not estado.get("fallas_sembrada")
    fecha_siembra = estado.get("fallas_sembrada") or hoy_iso

    proyectos = (db.query(Proyecto)
                 .options(selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes),
                          selectinload(Proyecto.documentos))
                 .filter(Proyecto.deleted_at.is_(None)).all())
    actuales: dict = {}
    por_seccion = {clave: [] for clave, _ in SECCIONES_FALLAS}
    resumen = {"textos.sin_info_relevante": 0, "textos.sin_porque_si": 0}
    pdf_items = []
    for p in proyectos:
        grupo = grupo_publicacion(p)
        inmob = (p.inmobiliaria or "").strip() or "Sin inmobiliaria"
        filas = []
        for it in fallas_seguras(p, now.replace(tzinfo=None)):
            if it.get("resumen"):
                if grupo == "publicados" and it["codigo"] in resumen:
                    resumen[it["codigo"]] += 1
                continue
            clave = f"{p.id}::{it['codigo']}"
            prev = previas.get(clave)
            if prev and prev.get("last_seen") and \
                    (hoy - date.fromisoformat(prev["last_seen"])).days <= DIAS_RECUERDO_AUSENTE:
                first_seen, sembrada = prev.get("first_seen") or hoy_iso, bool(prev.get("sembrada"))
            else:
                first_seen, sembrada = hoy_iso, sembrando
            actuales[clave] = {"first_seen": first_seen, "last_seen": hoy_iso, "sembrada": sembrada,
                               "proyecto": p.nombre or p.id, "inmobiliaria": inmob, "texto": it["texto"]}
            dias = (hoy - date.fromisoformat(first_seen)).days
            fila = {**it, "clave": clave, "nueva": first_seen == hoy_iso and not sembrada,
                    "sembrada": sembrada, "dias": dias}
            filas.append(fila)
            pdf_items.append({"id": p.id, "proyecto": p.nombre or p.id, "inmobiliaria": inmob,
                              "texto": it["texto"], "tab": it["tab"]})
        if filas:
            filas.sort(key=lambda f: (f["severidad"] != CRITICA, not f["nueva"], f["texto"]))
            por_seccion[grupo].append({"id": p.id, "nombre": p.nombre or p.id, "inmobiliaria": inmob,
                                       "filas": filas,
                                       "n_crit": sum(1 for f in filas if f["severidad"] == CRITICA)})

    secciones = []
    for clave, titulo in SECCIONES_FALLAS:
        proys = por_seccion[clave]
        proys.sort(key=lambda x: (x["inmobiliaria"].lower(), -x["n_crit"], x["nombre"].lower()))
        if proys:
            secciones.append({"clave": clave, "titulo": titulo, "proyectos": proys,
                              "n_fallas": sum(len(x["filas"]) for x in proys)})

    ult = estado.get("ultimo_envio_fallas") or {}
    resueltas = [previas[k] for k in (ult.get("claves") or []) if k not in actuales and k in previas]
    # Ausentes: se recuerdan 7 días para no marcar NUEVA lo que vuelve enseguida.
    nuevas_previas = {k: v for k, v in previas.items()
                      if k not in actuales and v.get("last_seen")
                      and (hoy - date.fromisoformat(v["last_seen"])).days <= DIAS_RECUERDO_AUSENTE}
    nuevo = {**estado, "fallas": {**nuevas_previas, **actuales}, "fallas_sembrada": fecha_siembra,
             "ultimo_envio_fallas": {"fecha": hoy_iso, "claves": sorted(actuales)}}
    todas = [f for s in secciones for x in s["proyectos"] for f in x["filas"]]
    n_fichas = sum(len(s["proyectos"]) for s in secciones)
    return {
        "fecha_cl": _fecha_cl(), "secciones": secciones, "n_fichas": n_fichas,
        "n_criticas": sum(1 for f in todas if f["severidad"] == CRITICA),
        "n_nuevas": sum(1 for f in todas if f["nueva"]),
        "resumen_textos": resumen, "resueltas": resueltas, "sembrando": sembrando,
        "fecha_siembra": fecha_siembra, "pdf_items": pdf_items, "estado_nuevo": nuevo,
        "conteo_por_regla": _conteo_por_regla(todas, n_total=len(proyectos)),
    }


def _conteo_por_regla(filas: list, n_total: int) -> list:
    """Cuántas fichas toca cada regla (para medir antes de encender el correo)."""
    cuenta: dict = {}
    for f in filas:
        cuenta.setdefault(f["codigo"], set()).add(f["clave"].split("::")[0])
    return sorted(({"codigo": c, "fichas": len(ids), "pct": round(100 * len(ids) / max(1, n_total))}
                   for c, ids in cuenta.items()), key=lambda x: -x["fichas"])


def asunto_fallas(data: dict) -> str:
    extra = [_plural(data["n_criticas"], "crítica", "críticas")]
    if data["n_nuevas"]:
        extra.append(_plural(data["n_nuevas"], "nueva", "nuevas"))
    return (f"Stock interno · fallas en {_plural(data['n_fichas'], 'ficha', 'fichas')} "
            f"({', '.join(extra)})")


def html_fallas(data: dict, max_filas: int = MAX_FILAS_FALLAS) -> str:
    if not data["n_fichas"]:
        cuerpo = ('<div style="padding:12px 14px;background:#dcfce7;border-radius:8px;color:#15803d;font-weight:700">'
                  'No hay fallas en las fichas. Hoy no se enviaría correo.</div>')
        return _marco("Stock interno · fallas en fichas", data["fecha_cl"], cuerpo)
    intro = ('<div style="font-size:12.5px;color:#374151;margin-bottom:6px;line-height:1.5">'
             'Lo que falta o no cuadra en cada ficha de stock propio. Cada falla lleva el enlace a la pestaña '
             'del editor donde se arregla. <b style="color:#dc2626">●</b> crítica · '
             '<b style="color:#ca8a04">●</b> aviso. La lista completa va en el PDF adjunto.</div>')
    if data["sembrando"]:
        intro += ('<div style="font-size:12px;color:#6b7280;margin-bottom:6px">Primer correo: lo que ya estaba '
                  'abierto sale como «abierta desde antes del ' +
                  escape(date.fromisoformat(data["fecha_siembra"]).strftime("%d/%m/%Y")) +
                  '». Desde mañana, lo nuevo se marca NUEVA.</div>')
    filas_puestas = 0
    omitidas = 0
    bloques = []
    for sec in data["secciones"]:
        partes = []
        inmob_actual = None
        for x in sec["proyectos"]:
            visibles = [f for f in x["filas"] if f["nueva"] or filas_puestas < max_filas]
            omitidas += len(x["filas"]) - len(visibles)
            if not visibles:
                continue
            if x["inmobiliaria"] != inmob_actual:
                inmob_actual = x["inmobiliaria"]
                partes.append(f'<div style="margin:10px 0 2px;font-size:13px;font-weight:800;color:#0b1628">'
                              f'{escape(inmob_actual)}</div>')
            lis = []
            for f in visibles:
                filas_puestas += 1
                color = "#dc2626" if f["severidad"] == CRITICA else "#ca8a04"
                # Lo sembrado el primer día no repite la fecha en cada línea (ya la dice la
                # introducción); lo nuevo lleva NUEVA; lo demás, cuántos días lleva abierto.
                if f["nueva"]:
                    abierta = ('<span style="background:#dc2626;color:#fff;font-size:10px;font-weight:800;'
                               'padding:1px 6px;border-radius:8px">NUEVA</span>')
                elif f["sembrada"] or f["dias"] <= 0:
                    abierta = ""
                else:
                    abierta = (f'<span style="color:#9ca3af">— abierta hace '
                               f'{escape(_plural(f["dias"], "día", "días"))}</span>')
                lis.append(f'<div style="margin:2px 0 2px 8px;font-size:12px;color:#374151">'
                           f'<b style="color:{color}">●</b> {escape(f["texto"])} {abierta} '
                           f'<a href="{_editor_url(x["id"], f["tab"])}" style="color:#1d4ed8">→ arreglar</a></div>')
            partes.append(f'<div style="padding:4px 0;border-bottom:1px solid #f3f4f6">'
                          f'<a href="{_editor_url(x["id"])}" style="color:#1f7a3d;font-weight:700;'
                          f'text-decoration:none;font-size:12.5px">{escape(x["nombre"])}</a>{"".join(lis)}</div>')
        if partes:
            bloques.append(f'<h3 style="margin:20px 0 4px;color:#0a0d12;font-size:15px">{escape(sec["titulo"])} · '
                           f'{sec["n_fallas"]} falla(s)</h3><div style="background:#fff;border:1px solid #e5e7eb;'
                           f'border-radius:10px;padding:2px 14px 8px">{"".join(partes)}</div>')
    if omitidas:
        bloques.append(f'<div style="font-size:11.5px;color:#6b7280;margin-top:8px">… y {omitidas} falla(s) más: '
                       f'están todas en el PDF adjunto.</div>')
    rt = data["resumen_textos"]
    if rt.get("textos.sin_info_relevante") or rt.get("textos.sin_porque_si"):
        bloques.append(f'<div style="margin-top:14px;padding:9px 12px;background:#f9fafb;border-radius:8px;'
                       f'font-size:12px;color:#374151">✍️ <b>Textos de venta</b> (fichas publicadas): '
                       f'{rt.get("textos.sin_info_relevante", 0)} sin «Información relevante» y '
                       f'{rt.get("textos.sin_porque_si", 0)} sin «Por qué Sí».</div>')
    if data["resueltas"]:
        lis = "".join(f'<div style="font-size:12px;color:#15803d;margin:2px 0">✓ <b>{escape(r["proyecto"])}</b> '
                      f'<span style="color:#6b7280">({escape(r["inmobiliaria"])})</span> — {escape(r["texto"])}</div>'
                      for r in data["resueltas"][:15])
        mas = (f'<div style="font-size:11px;color:#9ca3af">… y {len(data["resueltas"]) - 15} más</div>'
               if len(data["resueltas"]) > 15 else "")
        bloques.append(f'<h3 style="margin:20px 0 4px;color:#15803d;font-size:15px">Resueltas desde el último correo · '
                       f'{len(data["resueltas"])}</h3>{lis}{mas}')
    return _marco("Stock interno · fallas en fichas", data["fecha_cl"], intro + "".join(bloques))


def html_fallas_acotado(data: dict) -> str:
    """Baja el tope de filas hasta que el correo pese menos de MAX_BYTES."""
    tope = MAX_FILAS_FALLAS
    html = html_fallas(data, tope)
    while len(html.encode("utf-8")) > MAX_BYTES and tope > 10:
        tope = int(tope * 0.7)
        html = html_fallas(data, tope)
    return html


def pdf_fallas(data: dict) -> bytes:
    from app.services.daily_report import _pendientes_pdf_bytes
    return _pendientes_pdf_bytes(data["pdf_items"], data["fecha_cl"], titulo="Fallas en fichas · Stock BigCapital")


def send_fallas() -> str:
    """Disparado por el programador L-V 09:04. Silencio si no hay fallas."""
    if not settings.fallas_fichas_enabled:
        return "deshabilitado"
    with _LOCK:
        try:
            estado = cargar_estado()
            with SessionLocal() as db:
                data = build_fallas(db, estado=estado)
        except Exception as e:  # noqa: BLE001
            log.error("fallas en fichas: falló al armar: %s", e, exc_info=True)
            _avisar_error("Correo «fallas en fichas» no se pudo armar", str(e))
            return f"error: {e}"
        if not data["n_fichas"]:
            # Solo resueltas o nada: no se envía (las resueltas salen en el próximo correo).
            nuevo = dict(estado)
            nuevo["fallas"] = data["estado_nuevo"]["fallas"]
            nuevo["fallas_sembrada"] = data["estado_nuevo"]["fallas_sembrada"]
            _marcar_job(nuevo, "fallas", "sin novedad")
            guardar_estado(nuevo)
            return "sin_novedad"
        adjuntos = []
        try:
            adjuntos.append((pdf_fallas(data), "application", "pdf",
                             f"fallas_fichas_{datetime.now(TZ_CL):%Y-%m-%d}.pdf"))
        except Exception as e:  # noqa: BLE001
            log.warning("fallas en fichas: no se pudo armar el PDF: %s", e, exc_info=True)
        texto = f"{asunto_fallas(data)}\n{data['fecha_cl']}\nLa lista completa va en el PDF adjunto."
        resultado = enviar_html(asunto_fallas(data), html_fallas_acotado(data), texto, destinatarios_equipo(),
                                tuple(adjuntos))
        if resultado == "enviado":
            nuevo = data["estado_nuevo"]
            _marcar_job(nuevo, "fallas", f"enviado ({data['n_fichas']} fichas)")
            guardar_estado(nuevo)
        else:
            _avisar_error("Correo «fallas en fichas» no salió", resultado)
        log.info("fallas en fichas → %s · %d fichas, %d críticas, %d nuevas", resultado, data["n_fichas"],
                 data["n_criticas"], data["n_nuevas"])
        return resultado


def _avisar_error(titulo: str, detalle: str) -> None:
    """Solo a Nicolás y solo si falla (silencio = todo bien)."""
    try:
        from app.services.daily_report import send_error_alert
        send_error_alert(titulo, detalle)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo avisar el error '%s'", titulo, exc_info=True)
