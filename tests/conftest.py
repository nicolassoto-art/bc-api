"""Fixtures: cliente FastAPI + DB de test + usuario admin con token."""
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Usuario
from app.services.auth import create_token, hash_password


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def admin(db):
    """Crea (o reutiliza) un admin de tests y devuelve (user, headers con bearer)."""
    email = "admin@test.local"
    u = db.query(Usuario).filter(Usuario.email == email).first()
    if not u:
        u = Usuario(email=email, nombre="Admin", password_hash=hash_password("test1234"), is_admin=True, activo=True)
        db.add(u)
        db.commit()
    token, _ = create_token(sub=email)
    return u, {"Authorization": f"Bearer {token}"}
