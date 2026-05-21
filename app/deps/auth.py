"""FastAPI dependencies for auth: extract user from Authorization header."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..services.auth import decode_token
from ..settings import settings

bearer = HTTPBearer(auto_error=True)


def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        payload = decode_token(creds.credentials)
        email = payload.get("sub")
        if not email:
            raise JWTError("missing sub")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    user = db.query(Usuario).filter(Usuario.email == email, Usuario.activo == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    return user


def super_admin(user: Usuario = Depends(current_user)) -> Usuario:
    if not user.is_admin and user.email.lower() not in settings.super_admins_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Requiere permisos de super admin")
    return user
