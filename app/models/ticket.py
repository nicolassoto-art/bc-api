"""Tickets de reporte de fallas (Fase 5).

Cualquier usuario autenticado de Herramientas puede crear uno (descripción +
captura opcional). Solo super-admin lista y cierra. Email inmediato al admin.
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Ticket(Base):
    __tablename__ = "tickets"

    # id slug ('tkt-xxxxxxxxxx') generado por el server al crear
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    autor: Mapped[str] = mapped_column(String(255), index=True)         # email de quien reporta
    url: Mapped[Optional[str]] = mapped_column(String(1000))            # página donde ocurrió
    descripcion: Mapped[str] = mapped_column(Text)
    captura_url: Mapped[Optional[str]] = mapped_column(String(1000))    # /uploads/tickets/... o None
    estado: Mapped[str] = mapped_column(String(20), default="abierto", index=True)  # abierto|cerrado

    # Resolución (2026-07-23): qué se hizo y captura de prueba, quedan visibles
    # en el ticket cerrado — no solo el estado. Se setean al resolver, se
    # conservan si se reabre y se vuelve a resolver (última resolución gana).
    resolucion_texto: Mapped[Optional[str]] = mapped_column(Text)
    resolucion_captura_url: Mapped[Optional[str]] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
