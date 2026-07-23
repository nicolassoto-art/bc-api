from __future__ import annotations
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    autor: str
    url: Optional[str] = None
    descripcion: str
    captura_url: Optional[str] = None
    estado: str
    resolucion_texto: Optional[str] = None
    resolucion_captura_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TicketUpdate(BaseModel):
    estado: str  # 'abierto' | 'cerrado'
