"""Llamadas de las setters (Zadarma) y registro crudo de los eventos recibidos.

`zadarma_eventos` guarda cada notificación tal cual llegó (se purga a los 30 días) para
poder depurar con datos reales. `llamadas` es una fila por llamada, armada con los
eventos de inicio, fin, grabación y transcripción. Los teléfonos son datos personales:
nada de esto va a `uploads/` (público) ni a los logs.
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ZadarmaEvento(Base):
    __tablename__ = "zadarma_eventos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evento: Mapped[str] = mapped_column(String(40), index=True)
    pbx_call_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    recibido_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Llamada(Base):
    __tablename__ = "llamadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pbx_call_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    call_id_con_grabacion: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    anexo: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    setter: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    sentido: Mapped[Optional[str]] = mapped_column(String(10))            # entrante | saliente
    numero_cliente: Mapped[Optional[str]] = mapped_column(String(40))
    numero_linea: Mapped[Optional[str]] = mapped_column(String(40))
    inicio: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)  # tal cual lo informa Zadarma
    duracion_s: Mapped[Optional[int]] = mapped_column(Integer)
    resultado: Mapped[Optional[str]] = mapped_column(String(40))          # answered, no answer, busy…

    transcripcion_frases: Mapped[Optional[list]] = mapped_column(JSONB)   # [{"canal":1,"texto":"…"}, …]
    transcripcion_texto: Mapped[Optional[str]] = mapped_column(Text)
    transcripcion_idioma: Mapped[Optional[str]] = mapped_column(String(20))

    # nuevo → (llega transcripción) → pendiente → evaluando → ok | omitida | error
    estado: Mapped[str] = mapped_column(String(20), default="nuevo", index=True)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    evaluacion: Mapped[Optional[dict]] = mapped_column(JSONB)
    puntaje: Mapped[Optional[float]] = mapped_column(Float)
    version_pauta: Mapped[Optional[str]] = mapped_column(String(20))
    evaluada_en: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("ix_llamadas_setter_inicio", Llamada.setter, Llamada.inicio)
