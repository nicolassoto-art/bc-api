"""Pydantic schemas: input/output shapes para los endpoints REST."""
from typing import Dict, List, Optional
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, confloat, conint, conlist, constr


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
    # Solo salida: la marca se pone y se quita por PUT /unidades/{id}/reserva-bc.
    # UnidadIn no la trae a propósito: el editor reenvía la unidad completa desde
    # copias viejas y, si el PUT normal la aceptara, borraría una reserva recién hecha.
    reserva_bc: Optional[str] = None
    reserva_bc_at: Optional[datetime] = None
    # provisoria | confirmada | no_tomada | caida (ver models.Unidad). Solo lectura:
    # lo mueve la subida del Excel («PlanOk manda», 2026-11-06).
    reserva_bc_estado: Optional[str] = None
    reserva_bc_vista_disponible_at: Optional[datetime] = None
    # Solo salida (2026-10-29, MNK sin IVA): precio normal (con IVA). Lo escribe solo
    # la subida de Excel; UnidadIn no lo trae a propósito (el PUT del editor reenvía
    # copias viejas y lo borraría).
    precio_con_iva_uf: Optional[float] = None


class ReservaBcIn(BaseModel):
    """Poner o quitar la marca "reservada por BigCapital".

    Poner: `reserva_bc` = correlativo de la reserva (RES-…).
    Quitar: `reserva_bc` = null y `esperado` = el correlativo que se libera; solo se
    quita si la marca vigente es esa (una reserva nunca libera la de otra).
    `reabrir`: al quitar, vuelve a dejar la unidad disponible (solo si esa reserva fue
    la que la sacó del stock; lo decide quien llama).
    """
    reserva_bc: Optional[str] = Field(default=None, max_length=40)
    esperado: Optional[str] = Field(default=None, max_length=40)
    reabrir: bool = False


class RevisionStockIn(BaseModel):
    """Revisión de stock hecha por una PERSONA (2026-10-05), cuerpo opcional de
    POST /proyectos/{id}/unidades/verificado.

    `registrar_evento`: deja "Stock revisado" en la historia (botón «Revisé el stock:
    sin cambios»). `archivo`: nombre del Excel de la inmobiliaria subido en el editor
    (cuenta como revisión aunque no haya cambiado nada; el editor ya anota su propio
    evento "Excel Stock", por eso ahí va registrar_evento=false).
    """
    archivo: Optional[str] = Field(default=None, max_length=200)
    detalles: Optional[str] = Field(default=None, max_length=300)
    registrar_evento: bool = False


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
    # (2026-10-29, MNK sin IVA) Precio normal (con IVA) de la misma unidad que da
    # `precio_desde_uf` (el «desde» sigue siendo `precio_lista_uf`, que en un proyecto
    # activado es el sin IVA). Null en todo proyecto sin el dato.
    precio_desde_con_iva_uf: Optional[float] = None
    # Flag extraído de extra.publicar_en_catalogo (toggle del catálogo público)
    publicar_en_catalogo: bool = False
    # Flag extraído de extra.gps_verificado — el listado lo usa para la alerta
    # "Sin ubicación verificada". Sin exponerlo, la alerta nunca se borraba aunque
    # el usuario confirmara la ubicación en el editor (el summary no lo traía).
    gps_verificado: bool = False
    # (2026-10-05) Estado del stock con el mismo cálculo del correo "proyectos sin
    # revisar" (app/services/estado_stock.py). Sin declararlo, la respuesta lo descarta.
    estado_stock: Optional[Dict[str, Any]] = None


# ── Planes de pago (extra.comercial.planes_pago) ──────────────
# (2026-11-05) Varios planes con nombre por proyecto. Los escribe SOLO
# PATCH /proyectos/{id}/planes-pago, que además valida la cuadratura con validar_planes().


class DescuentoPlan(BaseModel):
    id: constr(max_length=40)
    nombre: constr(min_length=1, max_length=60)
    pct: confloat(ge=0, le=100) | None = None
    monto: confloat(ge=0) | None = None
    tipo: constr(max_length=20) = ''
    alcance: constr(max_length=20) = ''


class PlanPago(BaseModel):
    id: constr(pattern=r'^[a-z0-9_-]{1,40}$')
    nombre: constr(strip_whitespace=True, min_length=1, max_length=60)
    orden: int = 0
    predeterminado: bool = False
    activo: bool = True
    pie_pct: confloat(ge=0, le=100)
    cuoton_inicial_pct: confloat(ge=0, le=100) = 0
    cuotas_pago_inicial: conint(ge=0, le=120) = 0
    pago_construccion_pct: confloat(ge=0, le=100) = 0
    cuotas_pre_entrega: conint(ge=0, le=120) = 0
    cuota_pre_entrega_uf: confloat(ge=0) | None = None      # mínimo por cuota, fuera del 100%
    cuotas_auto_decremento: bool = False
    cuotas_inicio_mes: conint(ge=0, le=120) | None = None
    cuoton_final_pct: confloat(ge=0, le=100) = 0
    cuotas_post_entrega: conint(ge=0, le=120) = 0
    cuotas_post_auto_decremento: bool = False
    cuotas_post_inicio_mes: conint(ge=0, le=120) | None = None
    bono_pie_pct: confloat(ge=0, le=100) = 0
    seriedad_abona_pie: bool = False
    descuentos_adicionales: conlist(DescuentoPlan, max_length=10) = []
    promocion: constr(max_length=500) = ''
    nota_pago_pie: constr(max_length=1000) = ''


class PlanesPagoIn(BaseModel):
    """Cuerpo de PATCH /proyectos/{id}/planes-pago. `planes_pago: []` borra la clave;
    `seriedad_promesa_uf: null` la borra; si no viene, queda como está."""
    planes_pago: conlist(PlanPago, max_length=20)
    seriedad_promesa_uf: float | None = None


SERIEDAD_MAX_UF = 1000


def _c(x) -> int:
    """Centésimas, igual que el navegador: la cuadratura se compara en enteros."""
    return round(float(x or 0) * 100)


def _pct(centesimas: int) -> str:
    """0,5 · 1 · 12,25 (coma decimal, sin ceros de más)."""
    return f"{centesimas / 100:g}".replace(".", ",")


def validar_planes(body: PlanesPagoIn) -> str | None:
    """Devuelve el mensaje de error (en español) o None si los planes están bien."""
    for p in body.planes_pago:
        pie = _c(p.pie_pct)
        suma = (_c(p.cuoton_inicial_pct) + _c(p.pago_construccion_pct)
                + _c(p.cuoton_final_pct) + _c(p.bono_pie_pct))
        if pie != suma:
            falta = pie - suma
            palabra = "faltan" if falta > 0 else "sobran"
            return f'El plan "{p.nombre}" no cuadra: {palabra} {_pct(abs(falta))}%'
    ids = [p.id for p in body.planes_pago]
    if len(ids) != len(set(ids)):
        return "Hay dos planes con el mismo id"
    pred = [p for p in body.planes_pago if p.predeterminado]
    if len(pred) > 1:
        return "Solo puede haber un plan predeterminado"
    if pred and not pred[0].activo:
        return "El plan predeterminado debe estar activo"
    s = body.seriedad_promesa_uf
    if s is not None and not (0 <= s <= SERIEDAD_MAX_UF):
        return f"La seriedad de la promesa debe estar entre 0 y {SERIEDAD_MAX_UF} UF"
    return None
