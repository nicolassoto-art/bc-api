"""Gestión diaria de las setters a partir de sus llamadas (Zadarma).

Por setter y día: primera y última llamada, llamadas, contestadas, minutos hablados,
tiempo entre llamadas, detenciones (huecos de `detencion_min` o más sin llamar),
productividad, calidad (puntaje del evaluador) y semáforo contra las metas.
Las horas son las que informa Zadarma (hora local de la cuenta, Chile).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Optional

from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..models.llamada import Llamada
from ..settings import settings

import json

CORTA_S = 20          # contestada pero menos de 20 s: buzón o cuelgue
CONVERSACION_S = 60   # conversación real


def _fin(ll: Llamada) -> datetime:
    return ll.inicio + timedelta(seconds=ll.duracion_s or 0)


def _hhmm(d: Optional[datetime]) -> Optional[str]:
    return d.strftime("%H:%M") if d else None


def _semaforo(valor: float, meta: float) -> Optional[str]:
    if not meta:
        return None
    if valor >= meta:
        return "verde"
    return "amarillo" if valor >= meta * 0.6 else "rojo"


def resumen_setter(nombre: str, anexo: str, llamadas: list[Llamada], detencion_min: int,
                   meta_llamadas: Optional[int] = None, meta_agendadas: Optional[int] = None) -> dict:
    # Fuera las pruebas de audio al 4444 (no son gestión con clientes).
    ll = sorted([x for x in llamadas if x.inicio and x.numero_cliente != "4444"], key=lambda x: x.inicio)
    contestadas = [x for x in ll if x.resultado == "answered"]
    hablado_s = sum(x.duracion_s or 0 for x in contestadas)
    out = {
        "setter": nombre, "anexo": anexo,
        "llamadas": len(ll),
        "salientes": sum(1 for x in ll if x.sentido == "saliente"),
        "entrantes": sum(1 for x in ll if x.sentido == "entrante"),
        "contestadas": len(contestadas),
        "cortas": sum(1 for x in contestadas if (x.duracion_s or 0) < CORTA_S),
        "conversaciones": sum(1 for x in contestadas if (x.duracion_s or 0) >= CONVERSACION_S),
        "minutos_hablados": round(hablado_s / 60, 1),
        "duracion_promedio_s": round(hablado_s / len(contestadas)) if contestadas else None,
        "primera": _hhmm(ll[0].inicio) if ll else None,
        "ultima": _hhmm(max(_fin(x) for x in ll)) if ll else None,
        "jornada_min": None, "entre_llamadas_prom_min": None, "entre_llamadas_mediana_min": None,
        "detenciones": [], "detencion_total_min": 0, "detencion_mayor_min": 0,
        "llamadas_por_hora": None, "pct_hablando": None,
        "evaluadas": 0, "puntaje_promedio": None, "agendadas_en_llamada": 0,
        "linea_tiempo": [{"inicio": _hhmm(x.inicio), "fin": _hhmm(_fin(x)),
                          "contestada": x.resultado == "answered", "id": x.id} for x in ll],
    }
    if ll:
        inicio_dia, fin_dia = ll[0].inicio, max(_fin(x) for x in ll)
        jornada_s = (fin_dia - inicio_dia).total_seconds()
        out["jornada_min"] = round(jornada_s / 60)
        huecos, fin_previo = [], _fin(ll[0])
        for x in ll[1:]:
            gap = (x.inicio - fin_previo).total_seconds()
            if gap > 0:
                huecos.append(gap)
                if gap >= detencion_min * 60:
                    out["detenciones"].append({"desde": _hhmm(fin_previo), "hasta": _hhmm(x.inicio), "min": round(gap / 60)})
            fin_previo = max(fin_previo, _fin(x))
        if huecos:
            out["entre_llamadas_prom_min"] = round(sum(huecos) / len(huecos) / 60, 1)
            out["entre_llamadas_mediana_min"] = round(median(huecos) / 60, 1)
        out["detencion_total_min"] = sum(d["min"] for d in out["detenciones"])
        out["detencion_mayor_min"] = max((d["min"] for d in out["detenciones"]), default=0)
        if jornada_s >= 60:
            out["llamadas_por_hora"] = round(len(ll) / (jornada_s / 3600), 1)
            out["pct_hablando"] = round(100 * hablado_s / jornada_s)
    evaluadas = [x for x in ll if x.estado == "ok" and x.puntaje is not None]
    out["evaluadas"] = len(evaluadas)
    if evaluadas:
        out["puntaje_promedio"] = round(sum(x.puntaje for x in evaluadas) / len(evaluadas), 1)
    out["agendadas_en_llamada"] = sum(1 for x in ll if (x.evaluacion or {}).get("resultado_llamada") == "agendo")
    out["tasa_contacto"] = round(100 * len(contestadas) / len(ll)) if ll else None
    out["semaforo"] = {
        "llamadas": _semaforo(len(ll), meta_llamadas if meta_llamadas is not None else settings.meta_llamadas_dia),
        "agendadas": _semaforo(out["agendadas_en_llamada"], meta_agendadas if meta_agendadas is not None else settings.meta_agendadas_dia),
    }
    return out


METAS_LIMITES = {"llamadas": (1, 500), "agendadas": (0, 50), "detencion_min": (3, 120)}


def metas() -> dict:
    """Metas diarias y minutos de detención: las que fijó Nicolás en la página
    (estado/metas_llamadas.json) o, si no hay, las de settings."""
    base = {"llamadas": settings.meta_llamadas_dia, "agendadas": settings.meta_agendadas_dia,
            "detencion_min": settings.detencion_min}
    try:
        with open(settings.state_path / "metas_llamadas.json", encoding="utf-8") as f:
            guardadas = json.load(f)
    except (OSError, ValueError):
        return base
    for k, (lo, hi) in METAS_LIMITES.items():
        v = guardadas.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
            base[k] = v
    return base


def guardar_metas(nuevas: dict) -> dict:
    """Valida y guarda las metas. Lanza ValueError si algo está fuera de rango."""
    actuales = metas()
    for k, (lo, hi) in METAS_LIMITES.items():
        if k in nuevas and nuevas[k] is not None:
            v = nuevas[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise ValueError(f"{k} debe ser un número entero entre {lo} y {hi}")
            actuales[k] = v
    destino = settings.state_path / "metas_llamadas.json"
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(actuales), encoding="utf-8")
    tmp.replace(destino)
    return actuales


REUNIONES_VACIAS = {"agendadas": 0, "reuniones_del_dia": 0, "asistidas": 0, "inasistencias": 0,
                    "canceladas": 0, "pendientes": 0, "sin_resultado": 0}


def cargar_reuniones() -> dict:
    """Conteos de reuniones de las setters que deja la tarea del servidor
    (scripts/extraer_reuniones_setters.py) a partir de la foto de GHL. {} si no hay."""
    try:
        with open(settings.state_path / "reuniones_setters.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def reuniones_de(datos: dict, fecha: date, anexo: str) -> Optional[dict]:
    if not datos:
        return None
    r = {**REUNIONES_VACIAS, **((datos.get("por_dia") or {}).get(fecha.isoformat(), {}).get(anexo) or {})}
    cerradas = r["asistidas"] + r["inasistencias"]
    r["tasa_asistencia"] = round(100 * r["asistidas"] / cerradas) if cerradas else None
    return r


def _llamadas_del_dia(db: Session, fecha: date, anexos: list[str]) -> list[Llamada]:
    ini = datetime.combine(fecha, datetime.min.time())
    return (db.query(Llamada)
            .filter(Llamada.anexo.in_(anexos), Llamada.inicio >= ini, Llamada.inicio < ini + timedelta(days=1))
            .all())


def gestion_dia(db: Session, fecha: date, anexos: Optional[list[str]] = None) -> list[dict]:
    setters = settings.zadarma_anexos_map
    anexos = anexos or list(setters)
    todas = _llamadas_del_dia(db, fecha, anexos)
    m = metas()
    reuniones = cargar_reuniones()
    out = []
    for a in anexos:
        r = resumen_setter(setters.get(a, a), a, [x for x in todas if x.anexo == a], m["detencion_min"],
                           m["llamadas"], m["agendadas"])
        r["metas"] = {"llamadas": m["llamadas"], "agendadas": m["agendadas"]}
        r["reuniones"] = reuniones_de(reuniones, fecha, a)
        r["reuniones_actualizadas"] = reuniones.get("generado")
        if r["reuniones"] is not None:
            r["semaforo"]["agendadas"] = _semaforo(r["reuniones"]["agendadas"], m["agendadas"])
        out.append(r)
    return out


def gestion_rango(db: Session, desde: date, hasta: date, anexos: Optional[list[str]] = None) -> list[dict]:
    dias, d = [], desde
    while d <= hasta and len(dias) < 62:
        for r in gestion_dia(db, d, anexos):
            r["tiene_actividad"] = bool(r["llamadas"] or (r.get("reuniones") or {}).get("agendadas")
                                        or (r.get("reuniones") or {}).get("reuniones_del_dia"))
            r.pop("linea_tiempo", None)
            r.pop("detenciones", None)
            dias.append({"fecha": d.isoformat(), **r})
        d += timedelta(days=1)
    return dias


def mejor_horario(db: Session, desde: date, hasta: date, anexos: Optional[list[str]] = None) -> list[dict]:
    anexos = anexos or list(settings.zadarma_anexos_map)
    filas = (db.query(Llamada)
             .filter(Llamada.anexo.in_(anexos), Llamada.sentido == "saliente",
                     Llamada.inicio >= datetime.combine(desde, datetime.min.time()),
                     Llamada.inicio < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
             .all())
    por_hora: dict[int, list[int]] = {}
    for x in filas:
        h = por_hora.setdefault(x.inicio.hour, [0, 0])
        h[0] += 1
        h[1] += 1 if x.resultado == "answered" else 0
    return [{"hora": f"{h:02d}:00", "llamadas": v[0], "contestadas": v[1],
             "tasa_contacto": round(100 * v[1] / v[0]) if v[0] else None}
            for h, v in sorted(por_hora.items())]


# ── Alertas del día ──────────────────────────────────────────────────────────
CHILE = ZoneInfo("America/Santiago")
INICIO_JORNADA_H = 10     # sin llamadas pasadas las 10:00 → alerta
CIERRE_JORNADA_H = 18     # sin agendadas pasadas las 18:00 → alerta
DETENIDA_ALERTA_MIN = 30  # detención en curso de 30 min o más (entre 9:00 y 19:00)


def alertas(db: Session, ahora: Optional[datetime] = None) -> list[dict]:
    """Alertas de HOY por setter (lunes a viernes). `ahora` = hora de Chile (naive)."""
    ahora = ahora or datetime.now(CHILE).replace(tzinfo=None)
    if ahora.weekday() >= 5:
        return []
    out = []
    for g in gestion_dia(db, ahora.date()):
        nombre = g["setter"]
        if ahora.hour >= INICIO_JORNADA_H and not g["llamadas"]:
            out.append({"setter": nombre, "tipo": "sin_llamadas", "nivel": "rojo",
                        "texto": f"{nombre} aún no hace llamadas hoy (son las {ahora:%H:%M})."})
            continue
        if g["ultima"] and 9 <= ahora.hour < 19:
            h, m = map(int, g["ultima"].split(":"))
            parada = (ahora - ahora.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 60
            if parada >= DETENIDA_ALERTA_MIN:
                out.append({"setter": nombre, "tipo": "detenida", "nivel": "amarillo",
                            "texto": f"{nombre} lleva {round(parada)} minutos sin llamar (última llamada a las {g['ultima']})."})
        reu = g.get("reuniones")
        agendadas = reu["agendadas"] if reu is not None else g["agendadas_en_llamada"]
        if ahora.hour >= CIERRE_JORNADA_H and g["llamadas"] and not agendadas:
            out.append({"setter": nombre, "tipo": "sin_agendadas", "nivel": "amarillo",
                        "texto": f"{nombre} no ha agendado reuniones hoy."})
    return out


# ── Calidad por paso del script ──────────────────────────────────────────────
PASOS_ETIQUETA = {"apertura": "Apertura", "dolor": "Conectar con el dolor", "propuesta_valor": "Propuesta de valor",
                  "calificacion": "Calificación financiera", "cierre": "Cierre y agendamiento"}
REGLAS_ETIQUETA = {"nombro_proyecto_en_apertura": "Nombró el proyecto en la apertura",
                   "rut_antes_de_agendar": "Pidió el RUT antes de agendar",
                   "ofrecio_dos_horarios": "No ofreció dos horarios",
                   "aviso_recordatorio_whatsapp": "No avisó del recordatorio por WhatsApp"}


def calidad(db: Session, desde: date, hasta: date, anexos: Optional[list[str]] = None) -> list[dict]:
    """Por setter: puntaje promedio de cada paso del script y cuántas veces se incumplió cada regla."""
    setters = settings.zadarma_anexos_map
    anexos = anexos or list(setters)
    filas = (db.query(Llamada)
             .filter(Llamada.anexo.in_(anexos), Llamada.estado == "ok",
                     Llamada.inicio >= datetime.combine(desde, datetime.min.time()),
                     Llamada.inicio < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
             .all())
    out = []
    for a in anexos:
        propias = [x for x in filas if x.anexo == a]
        pasos = {k: [] for k in PASOS_ETIQUETA}
        reglas = {k: 0 for k in REGLAS_ETIQUETA}
        for x in propias:
            ev = x.evaluacion or {}
            for p in ev.get("pasos") or []:
                if p.get("paso") in pasos and p.get("cumple") != "no_aplica" and isinstance(p.get("puntaje"), (int, float)):
                    pasos[p["paso"]].append(p["puntaje"])
            rg = ev.get("reglas") or {}
            reglas["nombro_proyecto_en_apertura"] += 1 if rg.get("nombro_proyecto_en_apertura") is True else 0
            reglas["rut_antes_de_agendar"] += 1 if rg.get("rut_antes_de_agendar") is True else 0
            reglas["ofrecio_dos_horarios"] += 1 if rg.get("ofrecio_dos_horarios") == "no" else 0
            reglas["aviso_recordatorio_whatsapp"] += 1 if rg.get("aviso_recordatorio_whatsapp") == "no" else 0
        out.append({
            "setter": setters.get(a, a), "anexo": a, "evaluadas": len(propias),
            "puntaje_promedio": round(sum(x.puntaje for x in propias if x.puntaje is not None) / len(propias), 1) if propias else None,
            "pasos": [{"paso": k, "etiqueta": PASOS_ETIQUETA[k], "promedio": round(sum(v) / len(v)) if v else None, "n": len(v)}
                      for k, v in pasos.items()],
            "reglas": [{"regla": k, "etiqueta": REGLAS_ETIQUETA[k], "veces": n} for k, n in reglas.items()],
        })
    return out
