"""CRUD de proyectos."""
from typing import List, Optional
import re
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func, Integer
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps.auth import service_token, stock_access
from ..models import Proyecto, Unidad, Usuario
from ..schemas import ProyectoIn, ProyectoOut, ProyectoSummary

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s or "proyecto-" + uuid.uuid4().hex[:6]


# ── Catálogo público (Cloudflare Worker) ────────────────────────────────────
# Estos endpoints los consume SOLO el worker con el token de servicio. Devuelven
# proyectos con publicar_en_catalogo=true (flag guardado en extra por el editor).
# El extra se "aplana" al top-level para que el worker lea estacionamientos/
# bodegas/modelos/comercial directamente. Se enmascaran campos sensibles.

# Claves de `extra` SEGURAS para el catálogo público. Allow-list (fail-closed):
# si el importador agrega una clave nueva, NO se filtra hasta listarla acá.
# Reemplaza la vieja deny-list que apuntaba a nombres inexistentes (rut/numero/
# rut_spa) y dejaba pasar titular_rut, numero_cuenta, link_pago, spa_proyecto.rut,
# notas internas y el path del Excel de stock.
_PUBLIC_EXTRA_KEYS = {
    "external_id", "publicar_en_catalogo",
    "modelos", "estacionamientos", "bodegas",
    "etiquetas", "equipamiento", "areas_comunes", "entorno",
    "descripcion", "constructora", "modalidad", "fisicos",
    # Notas comerciales del proyecto. Salen al worker (server-side, autenticado
    # con service token); el worker decide si reenviarlas al navegador solo en
    # bcStockToCatalogoDetalle (broker logueado), NO en bcStockToCatalogoPublic.
    "notas_html", "notas_text",
}
# Subcampos de `comercial` que el catálogo necesita; el resto (promo_broker,
# tipo_descuento, márgenes, etc.) NO sale.
_PUBLIC_COMERCIAL_KEYS = {
    "pie_pct", "cuoton_inicial_pct", "cuoton_final_pct",
    "cuotas_pre_entrega", "cuotas_post_entrega", "valor_reserva_clp",
}


def _public_extra(extra: dict) -> dict:
    """Allow-list: SOLO las claves seguras de extra van al catálogo público."""
    src = extra or {}
    e = {k: src[k] for k in _PUBLIC_EXTRA_KEYS if k in src}
    com = src.get("comercial")
    if isinstance(com, dict):
        e["comercial"] = {k: v for k, v in com.items() if k in _PUBLIC_COMERCIAL_KEYS}
    return e


def _unidad_dict(u: Unidad) -> dict:
    return {
        "id": u.id, "numero": u.numero, "modelo": u.modelo, "tipologia": u.tipologia,
        "tipo": u.tipo, "orientacion": u.orientacion,
        "sup_total": u.sup_total, "sup_interior": u.sup_interior, "sup_terraza": u.sup_terraza,
        "sup_logia": u.sup_logia, "sup_jardin": u.sup_jardin,
        "precio_lista_uf": u.precio_lista_uf, "precio_final_uf": u.precio_final_uf,
        "descuento_pct": u.descuento_pct, "bono_pie_pct": u.bono_pie_pct,
        "disponible": u.disponible,
    }


def _proyecto_public_dict(p: Proyecto) -> dict:
    """Forma que el worker espera: extra aplanado + unidades + relaciones, enmascarado."""
    extra = p.extra or {}
    d = {
        "id": p.id,
        "external_id": extra.get("external_id") or p.id,
        "publicar_en_catalogo": bool(extra.get("publicar_en_catalogo")),
        "nombre": p.nombre,
        "inmobiliaria": p.inmobiliaria,
        "comuna": p.comuna,
        "region": p.region,
        "direccion": p.direccion,
        "gps_lat": p.gps_lat,
        "gps_lon": p.gps_lon,
        "fase": p.fase,
        "modalidad": p.modalidad,
        "fecha_entrega": p.fecha_entrega,
        "ano_entrega": p.ano_entrega,
        "foto_principal_url": p.foto_principal_url,
        "unidades": [_unidad_dict(u) for u in (p.unidades or [])],
        "imagenes": [
            {"id": im.id, "url": im.url, "categoria": im.categoria, "es_principal": im.es_principal}
            for im in (p.imagenes or [])
        ],
        "documentos": [
            {"id": dc.id, "tipo": dc.tipo, "detalles": dc.nombre, "url": dc.url}
            for dc in (p.documentos or [])
        ],
    }
    # Aplanar SOLO las claves seguras de extra (allow-list, fail-closed):
    # estacionamientos, bodegas, modelos, comercial[sanitizado], etiquetas,
    # equipamiento, areas_comunes, entorno, descripcion, constructora, fisicos.
    for k, v in _public_extra(extra).items():
        if k not in d:
            d[k] = v
    return d


def _is_publicable(p: Proyecto) -> bool:
    extra = p.extra or {}
    return bool(extra.get("publicar_en_catalogo")) and p.activo


@router.get("/public")
def listar_publicos(db: Session = Depends(get_db), _: bool = Depends(service_token)):
    """Lista proyectos con publicar_en_catalogo=true (consume el worker)."""
    proys = db.execute(
        select(Proyecto)
        .options(selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos))
        .where(Proyecto.activo == True)  # noqa: E712
        .order_by(Proyecto.updated_at.desc())
    ).scalars().all()
    return [_proyecto_public_dict(p) for p in proys if _is_publicable(p)]


@router.get("/public/{external_id}")
def detalle_publico(external_id: str, db: Session = Depends(get_db), _: bool = Depends(service_token)):
    """Detalle de UN proyecto publicado, por external_id (o id propio como fallback)."""
    proys = db.execute(
        select(Proyecto)
        .options(selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos))
        .where(Proyecto.activo == True)  # noqa: E712
    ).scalars().all()
    for p in proys:
        if not _is_publicable(p):
            continue
        ext = (p.extra or {}).get("external_id")
        if external_id in (ext, p.id):
            return _proyecto_public_dict(p)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no publicado")


@router.get("", response_model=List[ProyectoSummary])
def listar(
    q: Optional[str] = Query(None, description="Búsqueda en nombre/inmobiliaria/comuna"),
    activo: Optional[bool] = None,
    fase: Optional[str] = None,
    comuna: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    stmt = select(Proyecto)
    if activo is not None:
        stmt = stmt.where(Proyecto.activo == activo)
    if fase:
        stmt = stmt.where(Proyecto.fase == fase)
    if comuna:
        stmt = stmt.where(Proyecto.comuna == comuna)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Proyecto.nombre).like(like)
            | func.lower(Proyecto.inmobiliaria).like(like)
            | func.lower(Proyecto.comuna).like(like)
        )
    stmt = stmt.order_by(Proyecto.updated_at.desc())
    proys = db.execute(stmt).scalars().all()

    # Conteos de unidades por proyecto en 1 query (no N+1)
    rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.count(Unidad.id),
            func.sum(func.cast(Unidad.disponible, Integer)),
        ).group_by(Unidad.proyecto_id)
    ).all()
    counts = {pid: (total or 0, disp or 0) for pid, total, disp in rows}

    # Precio mínimo de unidades disponibles por proyecto (1 query, no N+1)
    precio_rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.min(
                func.coalesce(Unidad.precio_final_uf, Unidad.precio_lista_uf)
            ),
        )
        .where(Unidad.disponible == True)
        .where(func.coalesce(Unidad.precio_final_uf, Unidad.precio_lista_uf) > 0)
        .group_by(Unidad.proyecto_id)
    ).all()
    precios_min = {pid: precio for pid, precio in precio_rows if precio}

    # Foto fallback: si Proyecto.foto_principal_url está vacío (importados JB),
    # priorizar FACHADA real ('jb-foto', '', 'fachada', 'exterior') sobre plantas
    # ('jb-planta-*') y otros assets. min(id) alfabético elegía a veces
    # 'jb-planta-3d1b' antes que 'jb-foto' (problema reportado en Alto Buzeta).
    from ..models import Imagen
    all_imgs = db.execute(
        select(Imagen.id, Imagen.proyecto_id, Imagen.url, Imagen.categoria).order_by(Imagen.id)
    ).all()

    def _is_facade(cat: str) -> bool:
        c = (cat or "").lower()
        return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c

    # Por proyecto: si hay alguna con categoría de fachada, esa gana (la primera
    # por id). Si no, usar la primera imagen sin discriminar.
    img_url_by_pid: dict[str, str] = {}
    img_facade_by_pid: dict[str, str] = {}
    for r in all_imgs:
        if r.proyecto_id not in img_url_by_pid:
            img_url_by_pid[r.proyecto_id] = r.url  # primera de cualquier tipo
        if _is_facade(r.categoria) and r.proyecto_id not in img_facade_by_pid:
            img_facade_by_pid[r.proyecto_id] = r.url
    # Merge: la fachada gana si existe; si no, la primera cualquiera.
    img_url_by_pid = {**img_url_by_pid, **img_facade_by_pid}

    out = []
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
        extra = p.extra or {}
        comercial = extra.get("comercial") or {}
        # NOTA: NO inflar unidades_total con extra.fisicos.unidades_totales.
        # Ese campo es el total del EDIFICIO, no stock disponible a la venta.
        # Proyectos sin detalle publicado en JB deben mostrar "sin stock" (0),
        # no el tamaño del edificio (que confunde). El total del edificio queda
        # disponible en la ficha (tab General) como dato informativo.
        # Foto principal: si no hay foto_principal_url, fallback a la primera imagen.
        foto = p.foto_principal_url or img_url_by_pid.get(p.id) or None
        out.append(
            ProyectoSummary.model_validate(p).model_copy(
                update={
                    "unidades_total": int(total),
                    "unidades_disponibles": int(disp),
                    "pie_pct": comercial.get("pie_pct"),
                    "precio_desde_uf": precios_min.get(p.id),
                    "publicar_en_catalogo": bool(extra.get("publicar_en_catalogo")),
                    "foto_principal_url": foto,
                }
            )
        )
    return out


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def detalle(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = db.get(
        Proyecto,
        proyecto_id,
        options=[selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos)],
    )
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    # Fallback de foto: si foto_principal_url está vacía pero hay imágenes,
    # priorizar la FACHADA REAL (categoria='jb-foto' / 'fachada' / vacía) por
    # encima de plantas ('jb-planta-*'). Si no hay fachada categorizada, usar
    # la primera por id como último recurso. Mutar el objeto SQLAlchemy es
    # seguro acá porque no llamamos commit().
    if not p.foto_principal_url and p.imagenes:
        def _is_facade(im):
            c = (im.categoria or "").lower()
            return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c
        ordered = sorted(p.imagenes, key=lambda im: im.id)
        facade = next((im for im in ordered if _is_facade(im)), None)
        p.foto_principal_url = (facade.url if facade else ordered[0].url)
    return p


@router.post("", response_model=ProyectoOut, status_code=status.HTTP_201_CREATED)
def crear(body: ProyectoIn, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    pid = body.id or slugify(body.nombre)
    if db.get(Proyecto, pid):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya existe un proyecto con id '{pid}'")
    data = body.model_dump(exclude={"id"})
    p = Proyecto(id=pid, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{proyecto_id}", response_model=ProyectoOut)
def actualizar(
    proyecto_id: str,
    body: ProyectoIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    db.delete(p)
    db.commit()


class _EstadoBody(BaseModel):
    activo: bool


@router.patch("/{proyecto_id}/estado", response_model=ProyectoSummary)
def set_estado(
    proyecto_id: str,
    body: _EstadoBody,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Activa (activo=true) o desactiva (activo=false) un proyecto. Usado por el validador."""
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    p.activo = body.activo
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    total, disp = db.execute(
        select(func.count(Unidad.id), func.sum(func.cast(Unidad.disponible, Integer)))
        .where(Unidad.proyecto_id == proyecto_id)
    ).one()
    extra = p.extra or {}
    comercial = extra.get("comercial") or {}
    return ProyectoSummary.model_validate(p).model_copy(
        update={
            "unidades_total": int(total or 0),
            "unidades_disponibles": int(disp or 0),
            "pie_pct": comercial.get("pie_pct"),
            "publicar_en_catalogo": bool((p.extra or {}).get("publicar_en_catalogo")),
        }
    )


class _PublicarBody(BaseModel):
    publicar: bool


@router.patch("/{proyecto_id}/publicar")
def set_publicar(
    proyecto_id: str,
    body: _PublicarBody,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Marca/desmarca un proyecto para el catálogo público (extra.publicar_en_catalogo).
    Toggle liviano desde la lista de stock — toca SOLO el flag, no unidades ni nada más."""
    from sqlalchemy.orm.attributes import flag_modified
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    extra = dict(p.extra or {})
    extra["publicar_en_catalogo"] = bool(body.publicar)
    p.extra = extra
    flag_modified(p, "extra")
    p.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": p.id, "publicar_en_catalogo": bool(body.publicar)}
