"""Proyecto + entidades hijas (unidades, imágenes, documentos).

El modelo refleja la estructura del seed-pinar.js actual del stock-interno,
con campos nuevos (fase, activo, stock_last_upload) y los renombrados.
Los datos "libres" del proyecto (etiquetas, comercial, equipamiento, etc.)
viven como JSONB para flexibilidad sin migrar el schema en cada cambio.
"""
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Proyecto(Base):
    __tablename__ = "proyectos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug-like, ej. "pinar-1"
    nombre: Mapped[str] = mapped_column(String(255), index=True)
    inmobiliaria: Mapped[str | None] = mapped_column(String(255))
    comuna: Mapped[str | None] = mapped_column(String(120), index=True)
    region: Mapped[str | None] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(255))
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lon: Mapped[float | None] = mapped_column(Float)

    fase: Mapped[str | None] = mapped_column(String(80), index=True)  # Verde / En construcción / etc
    modalidad: Mapped[str | None] = mapped_column(String(80))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)

    fecha_entrega: Mapped[str | None] = mapped_column(String(80))  # "Inmediata" / "Mar 2027"
    ano_entrega: Mapped[int | None] = mapped_column(Integer)

    foto_principal_url: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)

    # Datos flexibles que no merecen columna propia:
    #   etiquetas, comercial, pago, equipamiento, areas_comunes, entorno,
    #   descripcion, condiciones_especiales, promocion_*, reserva_*, arriendos
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Última subida de Excel: {filename, at, inserted, updated, errors}
    stock_last_upload: Mapped[dict | None] = mapped_column(JSONB)

    notas: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    unidades: Mapped[list["Unidad"]] = relationship(back_populates="proyecto", cascade="all, delete-orphan")
    imagenes: Mapped[list["Imagen"]] = relationship(back_populates="proyecto", cascade="all, delete-orphan")
    documentos: Mapped[list["Documento"]] = relationship(back_populates="proyecto", cascade="all, delete-orphan")


class Unidad(Base):
    __tablename__ = "unidades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(ForeignKey("proyectos.id", ondelete="CASCADE"), index=True)
    numero: Mapped[str] = mapped_column(String(40))
    modelo: Mapped[str | None] = mapped_column(String(80))
    tipologia: Mapped[str | None] = mapped_column(String(80))
    tipo: Mapped[str | None] = mapped_column(String(40), default="Depto")
    orientacion: Mapped[str | None] = mapped_column(String(20))

    sup_total: Mapped[float | None] = mapped_column(Float)
    sup_interior: Mapped[float | None] = mapped_column(Float)
    sup_terraza: Mapped[float | None] = mapped_column(Float)
    sup_logia: Mapped[float | None] = mapped_column(Float)
    sup_jardin: Mapped[float | None] = mapped_column(Float)

    precio_lista_uf: Mapped[float | None] = mapped_column(Float)
    descuento_pct: Mapped[float] = mapped_column(Float, default=0)
    bono_pie_pct: Mapped[float] = mapped_column(Float, default=0)
    precio_final_uf: Mapped[float | None] = mapped_column(Float)

    estac_flag: Mapped[str] = mapped_column(String(20), default="optional")
    bodega_flag: Mapped[str] = mapped_column(String(20), default="optional")
    pack_flag: Mapped[str] = mapped_column(String(20), default="optional")

    disponible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="unidades")


class Imagen(Base):
    __tablename__ = "imagenes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(ForeignKey("proyectos.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)  # /uploads/<proyecto>/<uuid>.<ext>
    categoria: Mapped[str] = mapped_column(String(40), default="Otro")  # Exterior, Departamento, etc.
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int | None] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="imagenes")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(ForeignKey("proyectos.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str | None] = mapped_column(String(60))  # Brochure, Plano, SPA, Póliza, etc.
    url: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int | None] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="documentos")
