from __future__ import annotations
import logging
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
log = logging.getLogger(__name__)


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

    # Validate against legacy api.php (check-session). (2026-06-09) ROBUSTEZ:
    # probar VARIAS URLs candidatas, no solo legacy_api_url. El login del sitio
    # usa /api.php (raíz); existe una copia vieja en /backend/api.php con OTRO
    # almacén de sesiones. Tras un redeploy del api.php raíz, los tokens nuevos
    # eran válidos para el sitio pero bc-api los rechazaba (validaba contra la
    # ruta vieja) → el editor de stock-interno no cargaba para NINGÚN
    # stock_admin. Ahora se prueba la lista en orden y gana la primera que valide.
    _candidatas = []
    for _u in [
        settings.legacy_api_url,
        "https://herramientas.bigcapital.cl/api.php",      # raíz público (el del login)
        "https://herramientas.bigcapital.cl/backend/api.php",
        "http://127.0.0.1/api.php",
    ]:
        if _u and _u not in _candidatas:
            _candidatas.append(_u)

    r = None
    last_exc = None
    for _url in _candidatas:
        try:
            with httpx.Client(timeout=8) as client:
                resp = client.post(
                    _url,
                    json={"action": "check-session"},
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token_str}",
                    },
                )
            if resp.is_success:
                r = resp
                break
            # 401/403 = esta URL no tiene la sesión; probar la siguiente.
            r = resp  # guardar la última por si todas fallan
        except Exception as exc:
            last_exc = exc
            continue

    if r is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo contactar la API legacy: {last_exc}",
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
    # (2026-06-13) Todo corredor con sesión legacy válida obtiene JWT. El claim
    # stock_admin (abajo) decide el acceso a Stock propio; los endpoints sensibles
    # (editor, listado, PUT, papelera) lo exigen vía la dependencia stock_access.
    # Un corredor SIN stock_admin igual recibe token para leer datos benignos: su
    # perfil (/auth/me), crear tickets, y el plan de pago del catálogo
    # (/proyectos/{id}/comercial, solo-lectura). Antes esto daba 403 y dejaba sin
    # token al corredor normal → el catálogo le mostraba el plan recortado del worker.

    # Find or create the user in bc-api DB so /auth/me works after exchange
    user = db.query(Usuario).filter(Usuario.email == email).first()
    if not user:
        user = Usuario(email=email, nombre=nombre, is_admin=is_super, activo=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.activo:
        # (2026-06-17) La AUTORIDAD del acceso es users.json (legacy), no esta
        # tabla. Una fila inactiva acá NO debe bloquear a un usuario que tiene
        # sesión legacy válida y stock_admin (o es super): era el bug "tengo el
        # permiso en admin pero me pide clave" — el exchange daba 401 y el front
        # caía al modal de contraseña. Reactivamos el espejo en vez de rechazar.
        if stock_admin or is_super:
            user.activo = True
            db.commit()
            db.refresh(user)
            log.info("exchange: reactivado usuario inactivo con acceso legacy: %s", email)
        else:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo en bc-api")

    # Issue JWT — incluye el claim stock_admin (acceso a Stock propio sin ser super
    # admin). La dependencia stock_access lo lee para autorizar los endpoints de stock.
    jwt_token, expires_in = create_token(sub=user.email, extra={"stock_admin": bool(stock_admin or is_super)})
    user.last_login_at = datetime.utcnow()
    db.commit()

    return TokenOut(access_token=jwt_token, expires_in=expires_in)