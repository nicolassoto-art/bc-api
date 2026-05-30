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
from ..deps.auth import super_admin, service_token
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

_SENSITIVE_EXTRA_KEYS = {"comision_admin", "timeline"}


def _mask_extra(extra: dict) -> dict:
    """Quita del extra los campos que NO deben salir al catálogo público."""
    e = {k: v for k, v in (extra or {}).items() if k not in _SENSITIVE_EXTRA_KEYS}
    cr = e.get("cuenta_reserva")
    if isinstance(cr, dict):
        e["cuenta_reserva"] = {k: v for k, v in cr.items() if k not in ("rut", "numero")}
    spa = e.get("spa_proyecto")
    if isinstance(spa, dict):
        e["spa_proyecto"] = {k: v for k, v in spa.items() if k != "rut_spa"}
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
    extra = _mask_extra(p.extra or {})
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
    # Aplanar el resto del extra (estacionamientos, bodegas, modelos, comercial,
    # etiquetas, equipamiento, areas_comunes, entorno, descripcion, constructora…)
    for k, v in extra.items():
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
    _: Usuario = Depends(super_admin),
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

    out = []
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
        extra = p.extra or {}
        comercial = extra.get("comercial") or {}
        # Cruce de stock: si no hay detalle unidad-por-unidad (total contado = 0),
        # usar el total agregado del editor JB (extra.fisicos.unidades_totales).
        # JB no publica el detalle de algunos proyectos pero sí el total del edificio.
        if total == 0:
            try:
                agg = int((extra.get("fisicos") or {}).get("unidades_totales") or 0)
            except (TypeError, ValueError):
                agg = 0
            if agg > 0:
                total = agg  # mostrar el agregado como total; disp queda 0 (sin detalle)
        out.append(
            ProyectoSummary.model_validate(p).model_copy(
                update={
                    "unidades_total": int(total),
                    "unidades_disponibles": int(disp),
                    "pie_pct": comercial.get("pie_pct"),
                    "precio_desde_uf": precios_min.get(p.id),
                }
            )
        )
    return out


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def detalle(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
    p = db.get(
        Proyecto,
        proyecto_id,
        options=[selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos)],
    )
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


@router.post("", response_model=ProyectoOut, status_code=status.HTTP_201_CREATED)
def crear(body: ProyectoIn, db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
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
    _: Usuario = Depends(super_admin),
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
def eliminar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
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
    _: Usuario = Depends(super_admin),
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
        }
    )
