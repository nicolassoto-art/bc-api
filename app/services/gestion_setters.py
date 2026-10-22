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

from sqlalchemy.orm import Session

from ..models.llamada import Llamada
from ..settings import settings

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


def resumen_setter(nombre: str, anexo: str, llamadas: list[Llamada], detencion_min: int) -> dict:
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
        "llamadas": _semaforo(len(ll), settings.meta_llamadas_dia),
        "agendadas": _semaforo(out["agendadas_en_llamada"], settings.meta_agendadas_dia),
    }
    return out


def _llamadas_del_dia(db: Session, fecha: date, anexos: list[str]) -> list[Llamada]:
    ini = datetime.combine(fecha, datetime.min.time())
    return (db.query(Llamada)
            .filter(Llamada.anexo.in_(anexos), Llamada.inicio >= ini, Llamada.inicio < ini + timedelta(days=1))
            .all())


def gestion_dia(db: Session, fecha: date, anexos: Optional[list[str]] = None) -> list[dict]:
    setters = settings.zadarma_anexos_map
    anexos = anexos or list(setters)
    todas = _llamadas_del_dia(db, fecha, anexos)
    det = settings.detencion_min
    return [resumen_setter(setters.get(a, a), a, [x for x in todas if x.anexo == a], det) for a in anexos]


def gestion_rango(db: Session, desde: date, hasta: date, anexos: Optional[list[str]] = None) -> list[dict]:
    dias, d = [], desde
    while d <= hasta and len(dias) < 62:
        for r in gestion_dia(db, d, anexos):
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
