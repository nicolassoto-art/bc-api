"""Pydantic schemas: input/output shapes para los endpoints REST."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ── Unidad ────────────────────────────────────────────────────

class UnidadIn(BaseModel):
    numero: str
    modelo: str | None = None
    tipologia: str | None = None
    tipo: str | None = "Depto"
    orientacion: str | None = None
    sup_total: float | None = None
    sup_interior: float | None = None
    sup_terraza: float | None = None
    sup_logia: float | None = None
    sup_jardin: float | None = None
    precio_lista_uf: float | None = None
    descuento_pct: float = 0
    bono_pie_pct: float = 0
    precio_final_uf: float | None = None
    estac_flag: str = "optional"
    bodega_flag: str = "optional"
    pack_flag: str = "optional"
    disponible: bool = True


class UnidadOut(UnidadIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    proyecto_id: str


# ── Imagen ────────────────────────────────────────────────────

class ImagenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    proyecto_id: str
    url: str
    categoria: str
    es_principal: bool
    orden: int
    bytes: int | None = None
    mime: str | None = None
    created_at: datetime


class ImagenUpdate(BaseModel):
    categoria: str | None = None
    es_principal: bool | None = None
    orden: int | None = None


# ── Documento ─────────────────────────────────────────────────

class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    proyecto_id: str
    nombre: str
    tipo: str | None
    url: str
    bytes: int | None = None
    mime: str | None = None
    created_at: datetime


# ── Proyecto ──────────────────────────────────────────────────

class ProyectoBase(BaseModel):
    nombre: str
    inmobiliaria: str | None = None
    comuna: str | None = None
    region: str | None = None
    direccion: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    fase: str | None = None
    modalidad: str | None = None
    activo: bool = True
    disponible: bool = True
    fecha_entrega: str | None = None
    ano_entrega: int | None = None
    foto_principal_url: str | None = None
    external_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    notas: str | None = None


class ProyectoIn(ProyectoBase):
    id: str | None = None  # opcional al crear; el server genera slug si falta


class ProyectoOut(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stock_last_upload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    unidades: list[UnidadOut] = []
    imagenes: list[ImagenOut] = []
    documentos: list[DocumentoOut] = []


class ProyectoSummary(BaseModel):
    """Vista resumida para el listado — sin unidades/imagenes para no inflar el payload."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    nombre: str
    inmobiliaria: str | None
    comuna: str | None
    fase: str | None
    activo: bool
    disponible: bool
    fecha_entrega: str | None
    foto_principal_url: str | None
    updated_at: datetime
    unidades_total: int = 0
    unidades_disponibles: int = 0
