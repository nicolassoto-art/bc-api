"""Catálogo maestro de inmobiliarias.

Antes vivía en localStorage del navegador de cada super-admin (bomba de tiempo:
se perdía al cambiar de equipo, modo incógnito o limpiar caché). Ahora persiste
en bc-api para que todos los super-admin vean el mismo catálogo.
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Inmobiliaria(Base):
    __tablename__ = "inmobiliarias"

    # id slug ('inm-xxxxxxx') generado por el server al crear
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    rut: Mapped[Optional[str]] = mapped_column(String(40))
    web: Mapped[Optional[str]] = mapped_column(String(500))
    direccion: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
