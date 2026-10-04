"""Estado del stock de un proyecto — bc-api · 2026-10-05

Un solo cálculo para el correo "Stock interno · proyectos sin revisar", el KPI del
informe de las 09:00 y el listado del editor.

Regla de Nicolás (30/09/2026): "actualizado" = REVISADO, con o sin cambios. Cuenta
que un robot corrió y confirmó el stock aunque no cambiara nada, y que una persona
revisó y no encontró nada nuevo (botón «Revisé el stock: sin cambios», o subir el
Excel de la inmobiliaria). Un proyecto publicado con más de 3 días corridos sin
revisión sale en el correo (8 días en Vellatrix y Las Palmas, que mandan archivo
semanal).

De dónde sale cada revisión:
- Persona: último evento "Stock revisado" o "Excel Stock" de una persona en la
  historia. Ninguna alerta posterior lo anula.
- Robot: `stock_ok_at` (lo ponen /verificado, /excel/upload, /timeline/evento y los
  cambios de unidades; no la reserva de la intranet ni una alerta), los eventos
  automáticos que no son alerta y las alertas "Stock actualizado (…)" de Ingevec
  (proyecto sin deptos: el robot sí corrió bien). `ultima_revision_at` también suma
  salvo que la haya movido una alerta (caso AJ, que actualiza la fecha directo).
- Bloqueo: una alerta de robot más de 30 minutos después de la última revisión buena
  (la gracia absorbe los avisos que un robot deja en la misma corrida de una subida
  buena: "Modelos no registrados", "Producto opcional", "Canario … anormalmente bajo").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.origen_stock import (
    FUENTES_SEMANALES, es_cuenta_robot, norm_inmobiliaria, robot_de,
)
from app.services.timeline import es_alerta, parse_fecha

try:
    from zoneinfo import ZoneInfo
    TZ_CL = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover
    TZ_CL = timezone(timedelta(hours=-4))

UMBRAL_DIAS = 3
UMBRAL_SEMANAL = 8
DIAS_URGENTE = 7
GRACIA_BLOQUEO = timedelta(minutes=30)
# Una alerta mueve ultima_revision_at en el mismo instante en que se anota; si la
# fecha de revisión cae a menos de esto de una alerta, la explicó esa alerta.
_MISMO_INSTANTE = timedelta(minutes=2)

TIPOS_REVISION_PERSONA = {"Stock revisado", "Excel Stock"}
# Eventos que nunca dicen "quién revisó el stock" (editar la ficha no es revisar stock).
_TIPOS_NO_REVISION = {"Alerta", "Edición", "Foto", "Documento", "Nota", "Publicación",
                      "Creación", "Modelo", "Otro", "Excel Resumen"}


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def es_automatico(ev: dict) -> bool:
    """El evento lo dejó un robot (aunque venga con origen_auto nulo)."""
    if ev.get("origen_auto") is True:
        return True
    texto = f"{ev.get('tipo') or ''} {ev.get('detalles') or ''}".lower()
    if "actualización automática" in texto or "actualizacion automatica" in texto:
        return True
    return es_cuenta_robot(ev.get("usuario"))


def _es_jetbrokers(ev: dict) -> bool:
    """La bajada de stock de JetBrokers está apagada desde el 10/09/2026: su rastro
    no prueba que un robot cubra hoy el proyecto."""
    texto = f"{ev.get('detalles') or ''} {ev.get('usuario') or ''}".lower()
    return "jetbrokers" in texto or "jb-scraper" in texto or "jb_importer" in texto


def es_alerta_stock_actualizado(ev: dict) -> bool:
    return es_alerta(ev) and (ev.get("titulo") or "").strip().lower().startswith("stock actualizado")


def _nombre_persona(email: Optional[str]) -> str:
    e = (email or "").strip()
    if not e or "@" not in e:
        return e or "sin registro"
    local = e.split("@")[0]
    partes = [p for p in local.replace("_", ".").split(".") if p]
    return " ".join(p.capitalize() for p in partes) or e


def motivo_legible(ev: Optional[dict]) -> Optional[str]:
    """Texto de una alerta de robot en español simple, para el equipo."""
    if not ev:
        return None
    titulo = (ev.get("titulo") or "").strip()
    detalle = (ev.get("detalles") or "").strip()
    t = f"{titulo} {detalle}".lower()
    if "safety fail" in t or "no actualizado" in t or "delta_abort" in t:
        return ("El robot frenó la subida porque el cambio de la inmobiliaria se veía raro "
                "(por ejemplo, una caída brusca de unidades); se mantiene el último stock cargado.")
    if "subida con problema" in t or "upload_failed" in t or "auth_failed" in t:
        return "El robot no pudo subir el stock (falló la conexión o el ingreso); se mantiene el último stock cargado."
    if "anormalmente bajo" in t:
        return "El robot ve muy pocas unidades disponibles: revisa si es real o si la lectura quedó incompleta."
    if "producto opcional" in t:
        return "El robot encontró un producto que no reconoce (por ejemplo, un estacionamiento opcional): revisa la ficha."
    if "modelos no registrados" in t or "modelo no registrado" in t:
        return "Hay departamentos con un modelo que no existe en la ficha: regístralo en la pestaña Modelos."
    limpio = titulo or detalle[:120]
    for viejo, nuevo in (("scraper", "robot"), ("Scraper", "Robot"), ("FAIL", "falla"),
                         ("Canario MNK", "Aviso"), ("Canario", "Aviso")):
        limpio = limpio.replace(viejo, nuevo)
    return f"El robot dejó un aviso: {limpio}" if limpio else "El robot dejó un aviso."


def grupo_publicacion(p: Any) -> str:
    """publicados | en_preparacion | desactivados (misma regla que _is_publicable)."""
    if not getattr(p, "activo", True):
        return "desactivados"
    if bool((getattr(p, "extra", None) or {}).get("publicar_en_catalogo")):
        return "publicados"
    return "en_preparacion"


def _txt_fecha(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(TZ_CL).strftime("%d/%m/%Y %H:%M")


def estado_stock(p: Any, now: Optional[datetime] = None) -> dict:
    """Estado del stock del proyecto `p` (Proyecto o un objeto con los mismos campos)."""
    now = _aware(now) or datetime.now(timezone.utc)
    extra = getattr(p, "extra", None) or {}
    inmob = getattr(p, "inmobiliaria", None)
    semanal = norm_inmobiliaria(inmob) in FUENTES_SEMANALES
    umbral = UMBRAL_SEMANAL if semanal else UMBRAL_DIAS
    robot = robot_de(inmob)

    eventos = []
    for ev in extra.get("timeline") or []:
        if isinstance(ev, dict):
            f = parse_fecha(ev.get("fecha"))
            if f is not None:
                eventos.append((f, ev))

    # ── Persona
    manuales = [(f, ev) for f, ev in eventos
                if (ev.get("tipo") or "") in TIPOS_REVISION_PERSONA and not es_automatico(ev)
                and (ev.get("usuario") or "").strip() not in ("", "sistema")]
    ok_manual = max(manuales, key=lambda x: x[0]) if manuales else None

    # ── Robot
    base = _aware(getattr(p, "stock_ok_at", None))
    if base is None and not hasattr(p, "stock_ok_at"):
        base = _aware(getattr(p, "stock_updated_at", None))
    for f, ev in eventos:
        if (es_automatico(ev) and not es_alerta(ev)) or es_alerta_stock_actualizado(ev):
            if base is None or f > base:
                base = f
    alertas_bloqueo = [(f, ev) for f, ev in eventos
                       if es_alerta(ev) and not es_alerta_stock_actualizado(ev)]
    rev = _aware(getattr(p, "ultima_revision_at", None))
    if rev is not None and not any(abs(rev - f) <= _MISMO_INSTANTE for f, _ in alertas_bloqueo):
        if base is None or rev > base:
            base = rev
    bloqueos = [(f, ev) for f, ev in alertas_bloqueo if base is None or f > base + GRACIA_BLOQUEO]
    ult_bloqueo = max(bloqueos, key=lambda x: x[0]) if bloqueos else None

    # ── Última revisión buena
    ok_at = base
    origen = "robot"
    if ok_manual and (ok_at is None or ok_manual[0] >= ok_at):
        ok_at, origen = ok_manual[0], "persona"

    dias = None
    if ok_at is not None:
        dias = (now.astimezone(TZ_CL).date() - ok_at.astimezone(TZ_CL).date()).days

    # ¿Un robot cubre ESTE proyecto? (no basta el nombre de la inmobiliaria)
    cubre_robot = any(es_automatico(ev) and not _es_jetbrokers(ev) for _, ev in eventos)

    # ── Quién
    if origen == "persona":
        por = _nombre_persona(ok_manual[1].get("usuario"))
    else:
        por = None
        if ok_at is not None:
            cercanos = [(abs(f - ok_at), ev) for f, ev in eventos
                        if (ev.get("tipo") or "") not in _TIPOS_NO_REVISION
                        and abs(f - ok_at) <= GRACIA_BLOQUEO]
            if cercanos:
                ev = min(cercanos, key=lambda x: x[0])[1]
                por = (robot or "robot") if es_automatico(ev) else _nombre_persona(ev.get("usuario"))
        if por is None:
            por = (robot or "robot") if (cubre_robot and ok_at is not None) else "sin registro"

    # ── Estado
    nota = None
    motivo = None
    reciente_bloqueo = (ult_bloqueo is not None
                        and (now - ult_bloqueo[0]) <= timedelta(days=umbral))
    if dias is not None and dias <= umbral:
        estado = "al_dia"
        if reciente_bloqueo:
            nota = motivo_legible(ult_bloqueo[1])
    elif reciente_bloqueo:
        estado = "robot_detenido"
        motivo = motivo_legible(ult_bloqueo[1])
    elif cubre_robot:
        estado = "robot_sin_actualizar"
    else:
        estado = "sin_revisar"
    if estado != "al_dia" and semanal and not reciente_bloqueo:
        desde = ok_at.astimezone(TZ_CL).strftime("%d/%m/%Y") if ok_at else "hace más de 8 días"
        motivo = (f"No ha llegado archivo nuevo de la inmobiliaria desde {desde}: pídelo, o "
                  f"revisa y marca «Revisé el stock: sin cambios».")

    grupo = grupo_publicacion(p)
    return {
        "estado": estado,
        "aplica": grupo == "publicados" and getattr(p, "deleted_at", None) is None,
        "grupo": grupo,
        "dias": dias,
        "umbral": umbral,
        "urgente": estado != "al_dia" and (dias is None or dias >= DIAS_URGENTE),
        "ok_at": ok_at.isoformat().replace("+00:00", "Z") if ok_at else None,
        "ok_at_txt": _txt_fecha(ok_at),
        "por": por,
        "motivo": motivo,
        "fuente": robot,
        "robot_detenido_nota": nota,
    }
