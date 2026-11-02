"""Upload / list / delete de imágenes por proyecto.

Las imágenes se guardan en disco bajo {UPLOAD_DIR}/<proyecto_id>/<uuid>.<ext>
y se sirven como estáticos por nginx/Caddy en /uploads/...

URL devuelta al frontend: relativa ("/uploads/<proyecto>/<uuid>.<ext>") para
que el navegador resuelva contra el dominio actual de la API.
"""
from __future__ import annotations
from typing import List
import ipaddress
import socket
import uuid
from urllib.parse import urlparse

import httpx
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Body
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import stock_access
from ..models import Proyecto, Imagen, Usuario
from ..schemas import ImagenOut, ImagenUpdate
from ..settings import settings

router = APIRouter(prefix="/proyectos/{proyecto_id}/imagenes", tags=["imagenes"])

ALLOWED_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    # PDFs aceptados — el frontend los muestra en tab Documentos cuando categoria
    # empieza con "jb-doc" o cualquier categoría no-imagen.
    "application/pdf": ".pdf",
}


def _ensure_project(db: Session, proyecto_id: str) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


@router.get("", response_model=List[ImagenOut])
def listar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
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
    _: Usuario = Depends(stock_access),
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


class ImagenUrlIn(BaseModel):
    url: str
    categoria: str = "Otro"
    es_principal: bool = False


@router.post("/url", response_model=ImagenOut, status_code=status.HTTP_201_CREATED)
def registrar_url(
    proyecto_id: str,
    body: ImagenUrlIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Registra una imagen por URL externa (sin subir archivo).
    Útil para importar fotos de JetBrokers u otros servicios externos.
    """
    proy = _ensure_project(db, proyecto_id)

    if body.es_principal:
        for other in db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).all():
            other.es_principal = False

    img_id = "img-" + uuid.uuid4().hex[:10]
    img = Imagen(
        id=img_id,
        proyecto_id=proyecto_id,
        url=body.url,
        categoria=body.categoria,
        es_principal=body.es_principal,
        orden=db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).count(),
        bytes=0,
        mime="image/external",
    )
    if body.es_principal:
        proy.foto_principal_url = body.url

    db.add(img)
    db.commit()
    db.refresh(img)
    return img


def _tipo_imagen(b: bytes) -> str:
    """Tipo real por los primeros bytes (algunos sitios mandan application/octet-stream)."""
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return ""


def _host_publico(url: str) -> bool:
    """Solo https y hosts con IP pública: el servidor nunca descarga de su red interna."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname:
        return False
    try:
        for info in socket.getaddrinfo(u.hostname, 443):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except Exception:
        return False
    return True


def _es_externa(img: Imagen) -> bool:
    return bool(img.url) and not img.url.startswith("/uploads/") and img.mime != "application/pdf"


@router.post("/traer-externas")
def traer_externas(
    proyecto_id: str,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """(02-nov-2026) Botón «Traer fotos externas a nuestro servidor» de la ficha. Descarga cada foto que hoy es
    un enlace a otro sitio, la guarda en nuestro disco y la foto pasa a apuntar a la copia propia (mismo id,
    categoría, orden y portada). Las que el servidor no puede bajar (p. ej. JetBrokers bloquea su IP) se
    devuelven con ok=false: la ficha las intenta desde el navegador con POST /{imagen_id}/archivo."""
    proy = _ensure_project(db, proyecto_id)
    proj_dir: Path = settings.upload_path / proyecto_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    resultados = []
    externas = [i for i in db.query(Imagen).filter(Imagen.proyecto_id == proyecto_id).all() if _es_externa(i)]
    with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 BigCapital"}) as cli:
        for img in externas:
            r = {"id": img.id, "url": img.url, "ok": False}
            try:
                if not _host_publico(img.url):
                    r["motivo"] = "dirección no permitida"
                else:
                    resp = cli.get(img.url)
                    body = resp.content
                    tipo = _tipo_imagen(body[:16])
                    if resp.status_code != 200:
                        r["motivo"] = f"el sitio respondió {resp.status_code}"
                    elif not tipo:
                        r["motivo"] = "no es una imagen"
                    elif len(body) > settings.max_upload_bytes:
                        r["motivo"] = f"supera {settings.max_upload_mb} MB"
                    else:
                        ext = ALLOWED_MIMES[tipo]
                        (proj_dir / f"{img.id}{ext}").write_bytes(body)
                        anterior = img.url
                        img.url = f"/uploads/{proyecto_id}/{img.id}{ext}"
                        img.mime = tipo
                        img.bytes = len(body)
                        if proy.foto_principal_url == anterior or img.es_principal:
                            proy.foto_principal_url = img.url
                        r.update(ok=True, nueva_url=img.url)
            except Exception as e:  # un sitio caído no detiene a los demás
                r["motivo"] = "no se pudo descargar"
            resultados.append(r)
    db.commit()
    return {"total": len(externas), "traidas": sum(1 for r in resultados if r["ok"]), "resultados": resultados}


@router.post("/{imagen_id}/archivo", response_model=ImagenOut)
async def reemplazar_archivo(
    proyecto_id: str,
    imagen_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """(02-nov-2026) Trae a nuestro disco una foto que hoy es un enlace externo (JetBrokers, sitios de
    inmobiliarias): guarda el archivo subido y la foto pasa a apuntar a la copia propia. Conserva id,
    categoría, orden y portada. Si la foto ya era propia, reemplaza su archivo (se borra el anterior)."""
    proy = _ensure_project(db, proyecto_id)
    img = db.get(Imagen, imagen_id)
    if not img or img.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Imagen no encontrada")
    if file.content_type not in ALLOWED_MIMES or file.content_type == "application/pdf":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Tipo no permitido: {file.content_type}")
    body = await file.read()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Supera {settings.max_upload_mb} MB")
    proj_dir: Path = settings.upload_path / proyecto_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    ext = ALLOWED_MIMES[file.content_type]
    url_anterior = img.url or ""
    fpath = proj_dir / f"{imagen_id}{ext}"
    fpath.write_bytes(body)
    nueva_url = f"/uploads/{proyecto_id}/{imagen_id}{ext}"
    # Archivo propio anterior con otra extensión: se borra (best-effort).
    if url_anterior.startswith("/uploads/") and url_anterior != nueva_url:
        try:
            viejo = settings.upload_path / url_anterior.lstrip("/").replace("uploads/", "", 1)
            if viejo.exists():
                viejo.unlink()
        except Exception:
            pass
    img.url = nueva_url
    img.mime = file.content_type
    img.bytes = len(body)
    if proy.foto_principal_url == url_anterior or img.es_principal:
        proy.foto_principal_url = nueva_url
    db.commit()
    db.refresh(img)
    return img


@router.patch("/{imagen_id}", response_model=ImagenOut)
def actualizar(
    proyecto_id: str,
    imagen_id: str,
    body: ImagenUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
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
    _: Usuario = Depends(stock_access),
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
