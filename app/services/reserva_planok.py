"""«PlanOk manda»: la marca de reserva de la intranet es PROVISORIA — bc-api · 2026-11-06

Decisión de Nicolás (6-nov-2026). Hasta hoy una unidad con `reserva_bc` quedaba oculta
para siempre aunque PlanOk la volviera a ofrecer (caso real: 44C, 54D y 18D, reservas
que PlanOk dejó «Caducada» y que nuestro catálogo seguía escondiendo). Ahora la marca
oculta la unidad solo hasta que PlanOk la muestre tomada o 24 h como máximo; lo que diga
la lectura horaria de PlanOk (el Excel que sube el scraper) es la verdad.

Estados de `Unidad.reserva_bc_estado`, que mueve cada subida completa del Excel:

    provisoria  recién reservada; oculta ≤ 24 h mientras el robot o Operaciones la toma.
    confirmada  PlanOk ya no la ofrece (la tomamos): sigue oculta.
    no_tomada   24 h y PlanOk la sigue ofreciendo: reaparece en el catálogo.
    caida       estaba tomada y PlanOk la volvió a ofrecer en 2 subidas seguidas
                (≥ 30 min entre ambas): reaparece en el catálogo.

`no_tomada` y `caida` se mantienen hasta que una persona actúe (anular en la intranet
quita la marca). Si PlanOk la vuelve a tomar (deja de ofrecerla) pasa a `confirmada` y
se oculta de nuevo. La marca misma NUNCA se borra aquí.

Marca anterior a este cambio (estado null): se interpreta `confirmada` si tiene más de
24 h y `provisoria` si no.

Las 2 subidas seguidas se cuentan con un solo timestamp
(`reserva_bc_vista_disponible_at`): la primera subida en que una confirmada aparece
ofrecida lo anota; si la siguiente subida también la trae, y pasaron ≥ 30 min, queda
caída; si en el medio una subida no la trae, el timestamp se borra y se cuenta de nuevo.
Los 30 min evitan que un reintento de la misma subida (502 → reenvío) cuente doble.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

ESTADO_PROVISORIA = "provisoria"
ESTADO_CONFIRMADA = "confirmada"
ESTADO_NO_TOMADA = "no_tomada"
ESTADO_CAIDA = "caida"

PLAZO_PROVISORIA = timedelta(hours=24)
SEPARACION_MINIMA = timedelta(minutes=30)


def estado_efectivo(u, ahora: datetime) -> str:
    """Estado de la marca; para una marca anterior a este cambio, por su edad."""
    if u.reserva_bc_estado:
        return u.reserva_bc_estado
    if u.reserva_bc_at is None or ahora - u.reserva_bc_at > PLAZO_PROVISORIA:
        return ESTADO_CONFIRMADA
    return ESTADO_PROVISORIA


def aplicar_lectura(u, ofrecida: bool, ahora: datetime) -> tuple[bool, Optional[str]]:
    """Actualiza el estado de la marca de `u` según la lectura de PlanOk.

    `ofrecida`: la unidad viene disponible en el Excel de esta subida. Devuelve
    (disponible, texto del evento de timeline o None si el estado no cambió).
    Solo para unidades con `reserva_bc` y subidas completas (no parciales).
    """
    antes = estado_efectivo(u, ahora)
    res = u.reserva_bc
    num = u.numero
    evento = None

    if not ofrecida:
        u.reserva_bc_vista_disponible_at = None
        u.reserva_bc_estado = ESTADO_CONFIRMADA
        if antes == ESTADO_PROVISORIA:
            evento = f"{num}: reserva tomada en PlanOk ({res}), sigue fuera del catálogo"
        elif antes in (ESTADO_NO_TOMADA, ESTADO_CAIDA):
            evento = f"{num}: PlanOk volvió a tomar la unidad ({res}), sale del catálogo"
        return False, evento

    if antes == ESTADO_CONFIRMADA:
        vista = u.reserva_bc_vista_disponible_at
        u.reserva_bc_estado = ESTADO_CONFIRMADA
        if vista is None:
            u.reserva_bc_vista_disponible_at = ahora
            return False, None
        if ahora - vista < SEPARACION_MINIMA:
            return False, None
        u.reserva_bc_estado = ESTADO_CAIDA
        u.reserva_bc_vista_disponible_at = None
        return True, f"{num}: reserva caída en PlanOk ({res}), vuelve a estar disponible"

    if antes == ESTADO_PROVISORIA:
        u.reserva_bc_estado = ESTADO_PROVISORIA
        if u.reserva_bc_at is not None and ahora - u.reserva_bc_at <= PLAZO_PROVISORIA:
            return False, None
        u.reserva_bc_estado = ESTADO_NO_TOMADA
        return True, (f"{num}: reserva no tomada en PlanOk en 24 h ({res}), "
                      "vuelve a estar disponible")

    # no_tomada / caida: PlanOk la sigue ofreciendo, sigue disponible.
    return True, None
