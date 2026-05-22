from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import current_user
from ..models import Usuario
from ..schemas import LoginIn, TokenOut, UserOut
from ..services.auth import create_token, verify_password
from ..settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == body.email.lower()).first()
    if not user or not user.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    token, expires_in = create_token(sub=user.email)
    user.last_login_at = datetime.utcnow()
    db.commit()
    return TokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: Usuario = Depends(current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        nombre=user.nombre,
        is_admin=user.is_admin or user.email.lower() in settings.super_admins_list,
    )