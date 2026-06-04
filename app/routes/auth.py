from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import httpx
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import current_user
from ..models import Usuario
from ..schemas import LoginIn, TokenOut, UserOut
from ..services.auth import create_token, verify_password
from ..settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class ExchangeIn(BaseModel):
    bc_token: str


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


@router.post("/exchange", response_model=TokenOut)
def exchange_bc_token(body: ExchangeIn, db: Session = Depends(get_db)):
    """Exchange a legacy bc_token for a bc-api JWT.

    Validates the token against the legacy api.php backend. Issues a JWT if
    the session is valid and the user has stock_admin=true or is a super admin.
    Creates a bc-api user record on first exchange if one does not exist yet.
    """
    token_str = (body.bc_token or "").strip()
    if not token_str:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token vacío")

    # Validate against legacy api.php (same VPS, internal request)
    try:
        with httpx.Client(timeout=8) as client:
            r = client.post(
                settings.legacy_api_url,
                json={"action": "check-session"},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token_str}",
                },
            )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo contactar la API legacy: {exc}",
        )

    if not r.is_success:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token legacy inválido")

    try:
        data = r.json()
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Respuesta inválida de API legacy")

    # The legacy api.php check-session returns various shapes:
    # { ok: true, email, name, user: { email, stock_admin } }
    session_ok = data.get("ok") or data.get("success") or data.get("email") or data.get("user")
    if not session_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesión legacy no activa")

    user_obj = data.get("user") or {}
    email = (data.get("email") or user_obj.get("email") or "").strip().lower()
    nombre = data.get("name") or user_obj.get("name") or email
    stock_admin: bool = bool(user_obj.get("stock_admin") or data.get("stock_admin"))

    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sin email en sesión legacy")

    is_super = email in settings.super_admins_list
    if not stock_admin and not is_super:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a Stock propio. Pedile a un superadmin que te lo habilite.",
        )

    # Find or create the user in bc-api DB so /auth/me works after exchange
    user = db.query(Usuario).filter(Usuario.email == email).first()
    if not user:
        user = Usuario(email=email, nombre=nombre, is_admin=is_super, activo=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo en bc-api")

    # Issue JWT — incluye el claim stock_admin (acceso a Stock propio sin ser super
    # admin). La dependencia stock_access lo lee para autorizar los endpoints de stock.
    jwt_token, expires_in = create_token(sub=user.email, extra={"stock_admin": bool(stock_admin or is_super)})
    user.last_login_at = datetime.utcnow()
    db.commit()

    return TokenOut(access_token=jwt_token, expires_in=expires_in)