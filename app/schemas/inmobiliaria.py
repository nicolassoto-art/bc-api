"""Schemas Pydantic para el catálogo maestro de inmobiliarias."""
from __future__ import annotations
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class InmobiliariaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=255)
    rut: Optional[str] = None
    web: Optional[str] = None
    direccion: Optional[str] = None
    logo_url: Optional[str] = None


class InmobiliariaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nombre: str
    rut: Optional[str] = None
    web: Optional[str] = None
    direccion: Optional[str] = None
    logo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Stat de uso: cuántos proyectos referencian esta inmobiliaria (por nombre).
    # Se rellena en la lista, no en POST/PUT.
    proyectos_usados: int = 0
