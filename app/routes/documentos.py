"""Upload / list / patch / delete de documentos (Brochure, Plano, SPA, etc.) por
proyecto. Mismo patrón que imagenes.py pero sobre la tabla `documentos`.

Archivos en disco bajo {UPLOAD_DIR}/<proyecto_id>/<uuid>.<ext>, servidos como
estáticos en /uploads/... La URL devuelta es relativa.
"""
from __future__ import annotations
from typing import List, Optional
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import stock_access
from ..models import Proyecto, Documento, Usuario
from ..schemas import DocumentoOut
from ..settings import settings

router = APIRouter(prefix="/proyectos/{proyecto_id}/documentos", tags=["documentos"])

# Documentos: PDF (brochure/plano/SPA/reglamento) + imágenes (planos escaneados).
ALLOWED_MIMES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _ensure_project(db: Session, proyecto_id: str) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


@router.get("", response_model=List[DocumentoOut])
def listar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    _ensure_project(db, proyecto_id)
    return (
        db.query(Documento)
        .filter(Documento.proyecto_id == proyecto_id)
        .order_by(Documento.created_at)
        .all()
    )


@router.post("", response_model=List[DocumentoOut], status_code=status.HTTP_201_CREATED)
async def subir(
    proyecto_id: str,
    files: List[UploadFile] = File(...),
    tipo: str = Form("Otro"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    _ensure_project(db, proyecto_id)
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Sin archivos")

    proj_dir: Path = settings.upload_path / proyecto_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    created: List[Documento] = []
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
        doc_id = "doc-" + uuid.uuid4().hex[:10]
        fpath = proj_dir / f"{doc_id}{ext}"
        fpath.write_bytes(body)

        doc = Documento(
            id=doc_id,
            proyecto_id=proyecto_id,
            nombre=f.filename or f"{doc_id}{ext}",
            tipo=tipo,
            url=f"/uploads/{proyecto_id}/{doc_id}{ext}",
            bytes=len(body),
            mime=f.content_type,
        )
        db.add(doc)
        created.append(doc)

    db.commit()
    for doc in created:
        db.refresh(doc)
    return created


class DocumentoUrlIn(BaseModel):
    url: str
    nombre: str = ""
    tipo: str = "Otro"


@router.post("/url", response_model=DocumentoOut, status_code=status.HTTP_201_CREATED)
def registrar_url(
    proyecto_id: str,
    body: DocumentoUrlIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Registra un documento por URL externa (sin subir archivo)."""
    _ensure_project(db, proyecto_id)
    doc_id = "doc-" + uuid.uuid4().hex[:10]
    doc = Documento(
        id=doc_id,
        proyecto_id=proyecto_id,
        nombre=body.nombre or (body.url.rstrip("/").split("/")[-1]) or doc_id,
        tipo=body.tipo,
        url=body.url,
        bytes=0,
        mime="application/external",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


class DocumentoUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None


@router.patch("/{documento_id}", response_model=DocumentoOut)
def actualizar(
    proyecto_id: str,
    documento_id: str,
    body: DocumentoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    _ensure_project(db, proyecto_id)
    doc = db.get(Documento, documento_id)
    if not doc or doc.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    if body.nombre is not None:
        doc.nombre = body.nombre
    if body.tipo is not None:
        doc.tipo = body.tipo
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    proyecto_id: str,
    documento_id: str,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    _ensure_project(db, proyecto_id)
    doc = db.get(Documento, documento_id)
    if not doc or doc.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    # Borrar archivo físico (best-effort; las URLs externas no tienen archivo local)
    try:
        rel = doc.url.lstrip("/").replace("uploads/", "", 1)
        fpath = settings.upload_path / rel
        if fpath.exists():
            fpath.unlink()
    except Exception:
        pass
    db.delete(doc)
    db.commit()
