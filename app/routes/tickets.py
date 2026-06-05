"""Tickets de reporte de fallas (Fase 5).

- POST  /tickets        → crear (cualquier usuario autenticado). multipart:
  descripcion (Form, requerido), url (Form, opcional), file (captura, opcional).
- GET   /tickets        → listar (super_admin). ?estado=abierto|cerrado opcional.
- PATCH /tickets/{id}   → cambiar estado abierto/cerrado (super_admin).

Al crear, manda email inmediato al admin (reusa email_service · Fase 2).
"""
from __future__ import annotations
from typing import List, Optional
import uuid
from pathlib import Path
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import current_user, super_admin
from ..models import Ticket, Usuario
from ..schemas import TicketOut, TicketUpdate
from ..settings import settings
from ..services import email_service

router = APIRouter(prefix="/tickets", tags=["tickets"])

# Capturas: solo imágenes.
ALLOWED_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def crear(
    background_tasks: BackgroundTasks,
    descripcion: str = Form(...),
    url: str = Form(""),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(current_user),
):
    """Crea un ticket. Cualquier usuario autenticado de Herramientas puede hacerlo."""
    desc = (descripcion or "").strip()
    if not desc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="La descripción es obligatoria")

    tid = "tkt-" + uuid.uuid4().hex[:10]
    captura_url: Optional[str] = None

    if file is not None and (file.filename or ""):
        if file.content_type not in ALLOWED_MIMES:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Captura no permitida: {file.content_type}. Solo imágenes (JPG/PNG/WEBP/GIF).",
            )
        body = await file.read()
        if len(body) > settings.max_upload_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"La captura supera {settings.max_upload_mb} MB",
            )
        ext = ALLOWED_MIMES[file.content_type]
        tdir: Path = settings.upload_path / "tickets"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{tid}{ext}").write_bytes(body)
        captura_url = f"/uploads/tickets/{tid}{ext}"

    t = Ticket(
        id=tid,
        autor=user.email,
        url=((url or "").strip()[:1000] or None),
        descripcion=desc,
        captura_url=captura_url,
        estado="abierto",
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # Email inmediato al admin (fire-and-forget; no bloquea ni rompe si SMTP off).
    background_tasks.add_task(
        email_service.notify_ticket, t.autor, t.url or "", t.descripcion, bool(t.captura_url)
    )
    return t


@router.get("", response_model=List[TicketOut])
def listar(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    """Lista tickets (solo super admin). ?estado=abierto|cerrado para filtrar."""
    q = db.query(Ticket)
    if estado in ("abierto", "cerrado"):
        q = q.filter(Ticket.estado == estado)
    return q.order_by(Ticket.created_at.desc()).all()


@router.patch("/{ticket_id}", response_model=TicketOut)
def actualizar(
    ticket_id: str,
    body: TicketUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    """Cambia el estado de un ticket (abierto/cerrado). Solo super admin."""
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")
    if body.estado not in ("abierto", "cerrado"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Estado inválido (abierto|cerrado)")
    t.estado = body.estado
    db.commit()
    db.refresh(t)
    return t
