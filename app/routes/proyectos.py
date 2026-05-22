"""CRUD de proyectos."""
from typing import List, Optional
import re
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, Integer
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps.auth import super_admin
from ..models import Proyecto, Unidad, Usuario
from ..schemas import ProyectoIn, ProyectoOut, ProyectoSummary

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s or "proyecto-" + uuid.uuid4().hex[:6]


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

    out = []
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
        out.append(
            ProyectoSummary.model_validate(p).model_copy(
                update={"unidades_total": int(total), "unidades_disponibles": int(disp)}
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
