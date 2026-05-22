"""JWT + password hashing."""
from typing import Optional, Tuple
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from ..settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def create_token(*, sub: str, extra: Optional[dict] = None) -> Tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    ttl = timedelta(hours=settings.jwt_ttl_hours)
    exp = datetime.utcnow() + ttl
    payload = {"sub": sub, "exp": exp, **(extra or {})}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(ttl.total_seconds())


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
