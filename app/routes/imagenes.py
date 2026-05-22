"""Upload / list / delete de imágenes por proyecto.

Las imágenes se guardan en disco bajo {UPLOAD_DIR}/<proyecto_id>/<uuid>.<ext>
y se sirven como estáticos por nginx/Caddy en /uploads/...

URL devuelta al frontend: relativa ("/uploads/<proyecto>/<uuid>.<ext>") para
que el navegador resuelva contra el dominio actual de la API.
"""
from __future__ import annotations
from typing import List
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import super_admin
from ..models import Proyecto, Imagen, Usuario
from ..schemas import ImagenOut, ImagenUpdate
from ..settings import settings

router = APIRouter(prefix="/proyectos/{proyecto_id}/imagenes", tags=["imagenes"])

ALLOWED_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _ensure_project(db: Session, proyecto_id: str) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


@router.get("", response_model=List[ImagenOut])
def listar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
    _ensure_project(db, proyecto_id)
    return (
        db.query(Imagen)
        .filter(Imagen.proyecto_id == proyecto_id)
        .order_by(Imagen.es_principal.desc(), Imagen.orden, Imagen.created_at)
        .all()
    )


@router.post("", response_model=List[ImagenOut], status_code=status.HTTP_201_CREATED)
async def subir(
    proyecto_id: str,
    files: List[UploadFile] = File(...),
    categoria: str = Form("Otro"),
    es_principal: bool = Form(False),
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    proy = _ensure_project(db, proyecto_id)
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Sin archivos")

    proj_dir: Path = settings.upload_path / proyecto_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    created: List[Imagen] = []
    for f in files:
        if f.content_type not in ALLOWED_MIMES:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Tipo no permitido: {f.content_type}. Aceptados: {', '.join(ALLOWED_MIMES.keys())}",
            )
        body = await f.read()
        if len(body) > settings.max_upload_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo '{f.filename}' supera {settings.max_upload_mb} MB",
            )
        ext = ALLOWED_MIMES[f.content_type]
        img_id = "img-" + uuid.uuid4().hex[:10]
        fpath = proj_dir / f"{img_id}{ext}"
        fpath.write_bytes(body)

        # Si se marca esta como principal, desmarcar las demás del proyecto
        if es_principal and len(created) == 0:
            for other in db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).all():
                other.es_principal = False

        img = Imagen(
            id=img_id,
            proyecto_id=proyecto_id,
            url=f"/uploads/{proyecto_id}/{img_id}{ext}",
            categoria=categoria,
            es_principal=(es_principal and len(created) == 0),
            orden=db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).count() + len(created),
            bytes=len(body),
            mime=f.content_type,
        )
        # Si era la primera y se marcó principal, también actualizar el proyecto
        if img.es_principal:
            proy.foto_principal_url = img.url
        db.add(img)
        created.append(img)

    db.commit()
    for img in created:
        db.refresh(img)
    return created


@router.patch("/{imagen_id}", response_model=ImagenOut)
def actualizar(
    proyecto_id: str,
    imagen_id: str,
    body: ImagenUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    proy = _ensure_project(db, proyecto_id)
    img = db.get(Imagen, imagen_id)
    if not img or img.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Imagen no encontrada")

    if body.categoria is not None:
        img.categoria = body.categoria
    if body.orden is not None:
        img.orden = body.orden
    if body.es_principal is True:
        # Desmarcar las demás y marcar esta + actualizar proyecto
        for other in db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).all():
            other.es_principal = False
        img.es_principal = True
        proy.foto_principal_url = img.url
    elif body.es_principal is False and img.es_principal:
        img.es_principal = False
        if proy.foto_principal_url == img.url:
            proy.foto_principal_url = None

    db.commit()
    db.refresh(img)
    return img


@router.delete("/{imagen_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    proyecto_id: str,
    imagen_id: str,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    proy = _ensure_project(db, proyecto_id)
    img = db.get(Imagen, imagen_id)
    if not img or img.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Imagen no encontrada")

    # Borrar archivo físico (best-effort)
    try:
        rel = img.url.lstrip("/").replace("uploads/", "", 1)
        fpath = settings.upload_path / rel
        if fpath.exists():
            fpath.unlink()
    except Exception:
        pass  # no romper el delete por fs

    # Si era principal, limpiar referencia del proyecto
    if proy.foto_principal_url == img.url:
        proy.foto_principal_url = None

    db.delete(img)
    db.commit()
