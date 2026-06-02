"""CRUD del catálogo maestro de inmobiliarias."""
from typing import List, Optional
import re
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import super_admin
from ..models import Inmobiliaria, Proyecto, Usuario
from ..schemas import InmobiliariaIn, InmobiliariaOut

router = APIRouter(prefix="/inmobiliarias", tags=["inmobiliarias"])


def _gen_id() -> str:
    return "inm-" + uuid.uuid4().hex[:9]


def _normalize(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _proyectos_usados_map(db: Session) -> dict:
    """count(*) de proyectos.inmobiliaria normalizado a lower+stripped."""
    rows = db.execute(
        select(Proyecto.inmobiliaria, func.count(Proyecto.id))
        .where(Proyecto.inmobiliaria.isnot(None))
        .group_by(Proyecto.inmobiliaria)
    ).all()
    out = {}
    for nombre, n in rows:
        out[_normalize(nombre)] = out.get(_normalize(nombre), 0) + (n or 0)
    return out


@router.get("", response_model=List[InmobiliariaOut])
def listar(
    q: Optional[str] = Query(None, description="Búsqueda en nombre/rut/web/direccion"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    stmt = select(Inmobiliaria)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Inmobiliaria.nombre).like(like)
            | func.lower(func.coalesce(Inmobiliaria.rut, "")).like(like)
            | func.lower(func.coalesce(Inmobiliaria.web, "")).like(like)
            | func.lower(func.coalesce(Inmobiliaria.direccion, "")).like(like)
        )
    stmt = stmt.order_by(func.lower(Inmobiliaria.nombre))
    inms = db.execute(stmt).scalars().all()
    uso = _proyectos_usados_map(db)
    out = []
    for i in inms:
        item = InmobiliariaOut.model_validate(i).model_copy(
            update={"proyectos_usados": int(uso.get(_normalize(i.nombre), 0))}
        )
        out.append(item)
    return out


@router.post("", response_model=InmobiliariaOut, status_code=201)
def crear(
    body: InmobiliariaIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(400, detail="Nombre requerido")
    # Validar duplicado case-insensitive
    exists = db.execute(
        select(Inmobiliaria).where(func.lower(Inmobiliaria.nombre) == nombre.lower())
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, detail=f"Ya existe una inmobiliaria con el nombre '{exists.nombre}'")
    i = Inmobiliaria(
        id=_gen_id(),
        nombre=nombre,
        rut=(body.rut or "").strip() or None,
        web=(body.web or "").strip() or None,
        direccion=(body.direccion or "").strip() or None,
        logo_url=(body.logo_url or "").strip() or None,
    )
    db.add(i)
    db.commit()
    db.refresh(i)
    return InmobiliariaOut.model_validate(i)


@router.put("/{inm_id}", response_model=InmobiliariaOut)
def actualizar(
    inm_id: str,
    body: InmobiliariaIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    i = db.get(Inmobiliaria, inm_id)
    if not i:
        raise HTTPException(404, detail="Inmobiliaria no encontrada")
    nuevo = body.nombre.strip()
    if not nuevo:
        raise HTTPException(400, detail="Nombre requerido")
    # Si cambia el nombre, validar duplicado en OTROS registros
    if nuevo.lower() != i.nombre.lower():
        dup = db.execute(
            select(Inmobiliaria).where(
                func.lower(Inmobiliaria.nombre) == nuevo.lower(),
                Inmobiliaria.id != inm_id,
            )
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(409, detail=f"Ya existe una inmobiliaria con el nombre '{dup.nombre}'")
    i.nombre = nuevo
    i.rut = (body.rut or "").strip() or None
    i.web = (body.web or "").strip() or None
    i.direccion = (body.direccion or "").strip() or None
    i.logo_url = (body.logo_url or "").strip() or None
    i.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(i)
    return InmobiliariaOut.model_validate(i)


@router.delete("/{inm_id}", status_code=204)
def eliminar(
    inm_id: str,
    force: bool = Query(False, description="Confirmar borrado aún si hay proyectos asociados"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    i = db.get(Inmobiliaria, inm_id)
    if not i:
        raise HTTPException(404, detail="Inmobiliaria no encontrada")
    if not force:
        uso = _proyectos_usados_map(db).get(_normalize(i.nombre), 0)
        if uso > 0:
            raise HTTPException(
                409,
                detail=f"Esta inmobiliaria está siendo usada por {uso} proyecto(s). "
                       f"Confirma con ?force=true para borrar igual.",
            )
    db.delete(i)
    db.commit()
    return None
