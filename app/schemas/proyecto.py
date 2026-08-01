"""Pydantic schemas: input/output shapes para los endpoints REST."""
from typing import Dict, List, Optional
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ── Unidad ────────────────────────────────────────────────────

class UnidadIn(BaseModel):
    numero: str
    modelo: Optional[str] = None
    tipologia: Optional[str] = None
    tipo: Optional[str] = "Depto"
    orientacion: Optional[str] = None
    sup_total: Optional[float] = None
    sup_interior: Optional[float] = None
    sup_terraza: Optional[float] = None
    sup_logia: Optional[float] = None
    sup_jardin: Optional[float] = None
    precio_lista_uf: Optional[float] = None
    # (2026-08-01) Optional: `None` = "esta unidad no tiene dato propio" y es un
    # estado VÁLIDO y distinto de 0 en el resto del sistema — la columna en DB es
    # nullable, la carga por Excel ya inserta None (PRESERVAR_SI_VACIO), y el
    # editor lo distingue explícitamente (`u.descuento_pct != null` decide si
    # muestra el dato de la unidad o cae al descuento de la ficha del proyecto).
    # Solo este schema forzaba float, así que un PUT no podía dejar la unidad
    # "sin dato" (422) y quedaba clavada en 0 → el editor mostraba 0% tapando el
    # descuento real de la ficha. Regla: el dato por-unidad gana sobre el default
    # de la matriz; sin dato por-unidad, manda la matriz.
    descuento_pct: Optional[float] = None
    bono_pie_pct: Optional[float] = None
    precio_final_uf: Optional[float] = None
    estac_flag: str = "optional"
    bodega_flag: str = "optional"
    pack_flag: str = "optional"
    arriendo_garantizado: Optional[float] = None
    arriendo_moneda: Optional[str] = None  # "CLP" | "UF"
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
    bytes: Optional[int] = None
    mime: Optional[str] = None
    created_at: datetime


class ImagenUpdate(BaseModel):
    categoria: Optional[str] = None
    es_principal: Optional[bool] = None
    orden: Optional[int] = None


# ── Documento ─────────────────────────────────────────────────

class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    proyecto_id: str
    nombre: str
    tipo: Optional[str]
    url: str
    bytes: Optional[int] = None
    mime: Optional[str] = None
    created_at: datetime


# ── Proyecto ──────────────────────────────────────────────────

class ProyectoBase(BaseModel):
    nombre: str
    inmobiliaria: Optional[str] = None
    comuna: Optional[str] = None
    region: Optional[str] = None
    direccion: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    fase: Optional[str] = None
    modalidad: Optional[str] = None
    activo: bool = True
    disponible: bool = True
    fecha_entrega: Optional[str] = None
    ano_entrega: Optional[int] = None
    foto_principal_url: Optional[str] = None
    external_url: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    notas: Optional[str] = None


class ProyectoIn(ProyectoBase):
    id: Optional[str] = None  # opcional al crear; el server genera slug si falta


class ProyectoOut(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    codigo_corto: Optional[str] = None
    stock_last_upload: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    stock_updated_at: Optional[datetime] = None
    ultima_revision_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    unidades: List[UnidadOut] = []
    imagenes: List[ImagenOut] = []
    documentos: List[DocumentoOut] = []


class ProyectoSummary(BaseModel):
    """Vista resumida para el listado — sin unidades/imagenes para no inflar el payload."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    codigo_corto: Optional[str] = None
    nombre: str
    inmobiliaria: Optional[str]
    comuna: Optional[str]
    fase: Optional[str]
    activo: bool
    disponible: bool
    fecha_entrega: Optional[str]
    ano_entrega: Optional[int] = None
    foto_principal_url: Optional[str]
    external_url: Optional[str] = None
    updated_at: datetime
    stock_updated_at: Optional[datetime] = None
    ultima_revision_at: Optional[datetime] = None
    unidades_total: int = 0
    unidades_disponibles: int = 0
    # Campos extraídos de extra.comercial para el listado
    pie_pct: Optional[float] = None
    precio_desde_uf: Optional[float] = None
    # Flag extraído de extra.publicar_en_catalogo (toggle del catálogo público)
    publicar_en_catalogo: bool = False
    # Flag extraído de extra.gps_verificado — el listado lo usa para la alerta
    # "Sin ubicación verificada". Sin exponerlo, la alerta nunca se borraba aunque
    # el usuario confirmara la ubicación en el editor (el summary no lo traía).
    gps_verificado: bool = False
