"""FastAPI dependencies for auth: extract user from Authorization header."""
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..services.auth import decode_token
from ..settings import settings

bearer = HTTPBearer(auto_error=True)
# Bearer opcional: el endpoint público valida un token de servicio (no JWT de
# usuario). auto_error=False para devolver 401/503 propios en vez de 403 genérico.
bearer_optional = HTTPBearer(auto_error=False)


def service_token(
    creds: HTTPAuthorizationCredentials = Depends(bearer_optional),
) -> bool:
    """Valida el token de servicio del Cloudflare Worker (catálogo público).

    Comparación de tiempo constante (anti timing-attack). Si el token no está
    configurado en el servidor, el endpoint queda deshabilitado (503).
    """
    expected = (settings.bc_api_service_token or "").strip()
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Catálogo público no configurado")
    got = (creds.credentials if creds else "") or ""
    if not secrets.compare_digest(got, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token de servicio inválido")
    return True


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
