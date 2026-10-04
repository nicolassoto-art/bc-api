"""Historia (timeline) de un proyecto — bc-api · 2026-10-05

La historia vive en `Proyecto.extra["timeline"]`: una lista de eventos
{id, fecha, tipo, detalles, usuario, origen_auto?, titulo?, severity?}, del más nuevo
al más viejo. La escriben el editor (cada autoguardado reenvía `extra` entero) y el
servidor (/excel/upload, /timeline/alerta, /timeline/evento, /unidades/verificado).

Dos problemas que resuelve este módulo:

1. El autoguardado del editor reemplazaba `extra` completo con la copia que tenía el
   navegador. Una alerta de robot publicada mientras la ficha estaba abierta se
   perdía en el siguiente guardado, y con ella la única señal de "robot detenido".
   `fusionar_timeline` une lo que trae el cuerpo con lo que ya tiene el servidor por
   `id`. Nadie borra eventos a propósito (el editor y los endpoints solo insertan),
   así que la unión no revive nada borrado.

2. La historia crecía sin tope: un robot bloqueado publica una alerta por corrida
   (Larrain: cada hora), ~240 KB al mes por proyecto, que viajan en cada GET y en
   cada autoguardado. `recortar_timeline` conserva todos los eventos que no son
   alertas y, de las alertas, las 100 más recientes más la última de cada título.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

MAX_ALERTAS = 100


def parse_fecha(valor: Any) -> Optional[datetime]:
    """Fecha de un evento → datetime aware UTC, o None si no se puede leer.

    Acepta lo que escriben el servidor ("2026-10-05T12:00:00.123456Z"), el editor
    (ISO con "Z" y milisegundos) y valores viejos sin zona (se asumen UTC, igual que
    las columnas de bc-api).
    """
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, str) and valor.strip():
        s = valor.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_MUY_VIEJO = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _clave_orden(ev: Any) -> datetime:
    f = parse_fecha(ev.get("fecha")) if isinstance(ev, dict) else None
    return f or _MUY_VIEJO


def es_alerta(ev: Any) -> bool:
    return isinstance(ev, dict) and (ev.get("tipo") or "") == "Alerta"


def recortar_timeline(eventos: Optional[Iterable[Any]]) -> list:
    """Tope de la historia. Conserva el orden recibido.

    Se quedan: todo evento que no es Alerta; de las Alerta, las MAX_ALERTAS más
    recientes y además la última de cada título (así nunca se pierde, por ejemplo,
    el último "Stock actualizado (…)" de un robot ni la última alerta de bloqueo).
    """
    lista = [ev for ev in (eventos or [])]
    alertas = [(i, ev) for i, ev in enumerate(lista) if es_alerta(ev)]
    if len(alertas) <= MAX_ALERTAS:
        return lista
    por_recencia = sorted(alertas, key=lambda par: _clave_orden(par[1]), reverse=True)
    quedan = {i for i, _ in por_recencia[:MAX_ALERTAS]}
    vistos_titulo = set()
    for i, ev in por_recencia:
        titulo = (ev.get("titulo") or ev.get("detalles") or "").strip().lower()
        if titulo not in vistos_titulo:
            vistos_titulo.add(titulo)
            quedan.add(i)
    return [ev for i, ev in enumerate(lista) if not es_alerta(ev) or i in quedan]


def fusionar_timeline(entrante: Optional[list], servidor: Optional[list]) -> list:
    """Historia que queda guardada después de un PUT del proyecto.

    - `entrante` None (el cuerpo no trae "timeline"): queda la del servidor.
    - Si no: todo lo que trae el cuerpo (tal cual, también eventos sin id) más los
      eventos del servidor cuyo id el cuerpo no trae. Orden por fecha, del más nuevo
      al más viejo (estable: a igual fecha manda el orden del cuerpo). Después, tope.
    """
    srv = [ev for ev in (servidor or [])]
    if entrante is None:
        return recortar_timeline(srv)
    ent = [ev for ev in entrante]
    ids_entrantes = {ev.get("id") for ev in ent if isinstance(ev, dict) and ev.get("id")}
    faltantes = [ev for ev in srv
                 if isinstance(ev, dict) and ev.get("id") and ev.get("id") not in ids_entrantes]
    if not faltantes:
        return recortar_timeline(ent)
    unidos = ent + faltantes
    unidos.sort(key=_clave_orden, reverse=True)
    return recortar_timeline(unidos)
