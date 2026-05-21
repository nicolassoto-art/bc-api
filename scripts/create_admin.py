"""Crea (o resetea password de) el usuario super admin.

Uso:
    python scripts/create_admin.py nicolas.soto@bigcapital.cl 'micontraseña'
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import Usuario  # noqa: E402
from app.services.auth import hash_password  # noqa: E402


def main():
    if len(sys.argv) != 3:
        print("Uso: python scripts/create_admin.py <email> <password>")
        sys.exit(1)
    email = sys.argv[1].lower()
    password = sys.argv[2]

    db = SessionLocal()
    try:
        u = db.query(Usuario).filter(Usuario.email == email).first()
        if u:
            u.password_hash = hash_password(password)
            u.is_admin = True
            u.activo = True
            print(f"✓ Password reseteado para {email}")
        else:
            u = Usuario(email=email, nombre=email.split("@")[0], password_hash=hash_password(password), is_admin=True, activo=True)
            db.add(u)
            print(f"✓ Usuario admin creado: {email}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
