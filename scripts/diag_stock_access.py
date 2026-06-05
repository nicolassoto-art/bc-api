"""Diagnóstico (solo lectura) del acceso a Stock para usuarios stock_admin no-super.

Corre DENTRO del VPS (como el usuario del servicio, en INSTALL_DIR) vía el workflow
`diag-stock-access.yml`. Para cada usuario objetivo:
  1. Reporta si existe + está activo en la BD de bc-api y si es super admin.
  2. Emite un JWT con el claim `stock_admin=True` (idéntico a lo que produce
     /auth/exchange para un usuario con permiso de stock) y consulta GET /proyectos
     contra el servicio real (127.0.0.1:8011). Esperado: HTTP 200 + los proyectos.
  3. Control negativo: un JWT SIN el claim (y sin ser super) → esperado HTTP 403.

NO escribe nada en la base de datos. NO toca producción salvo lecturas GET.
"""
from __future__ import annotations
import json
import traceback

import httpx

from app.db import SessionLocal
from app.models import Usuario
from app.services.auth import create_token
from app.settings import settings

BASE = "http://127.0.0.1:8011"
EMAILS = [
    "cristopher.jaramillo@bigcapital.cl",
    "alvaro.meneses@bigcapital.cl",
]


def _get(token: str):
    r = httpx.get(
        f"{BASE}/proyectos",
        headers={"Authorization": f"Bearer {token}"},
        timeout=25,
    )
    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text[:200]
    return r.status_code, body


def main() -> None:
    print("================ DIAG stock_access ================")
    print("super_admins configurados:", settings.super_admins_list)
    db = SessionLocal()
    try:
        for em in EMAILS:
            print(f"\n----- {em} -----")
            try:
                u = (
                    db.query(Usuario)
                    .filter(Usuario.email == em)
                    .first()
                )
                exists = u is not None
                active = bool(u and u.activo)
                is_super = bool(
                    u and (u.is_admin or em.lower() in settings.super_admins_list)
                )
                print(
                    f"existe_en_bcapi={exists}  activo={active}  is_admin={bool(u and u.is_admin)}  is_super={is_super}"
                )

                if not (exists and active):
                    # El usuario se crea/activa en su primer ingreso (exchange).
                    tok, _ = create_token(sub=em, extra={"stock_admin": True})
                    code, body = _get(tok)
                    print(
                        f"  CON claim stock_admin -> HTTP {code} "
                        f"(401 = aún no provisionado; se crea en el primer login)"
                    )
                    continue

                # Test principal: token CON claim (como lo emite /auth/exchange)
                tok, _ = create_token(sub=em, extra={"stock_admin": True})
                code, body = _get(tok)
                if code == 200 and isinstance(body, list):
                    nombres = [p.get("nombre") for p in body][:8]
                    print(
                        f"  CON claim stock_admin -> HTTP 200 | proyectos={len(body)} | {nombres}"
                    )
                else:
                    print(f"  CON claim stock_admin -> HTTP {code} | {str(body)[:200]}")

                # Control negativo: token SIN claim y sin ser super
                tok2, _ = create_token(sub=em, extra={"stock_admin": False})
                code2, body2 = _get(tok2)
                esperado = "200 (es super)" if is_super else "403"
                detalle = body2.get("detail") if isinstance(body2, dict) else str(body2)[:120]
                print(
                    f"  SIN claim (control)   -> HTTP {code2} (esperado {esperado}) | {detalle}"
                )
            except Exception:
                print("  ERROR en este usuario:")
                traceback.print_exc()
    finally:
        db.close()
    print("\n================ FIN DIAG ================")


if __name__ == "__main__":
    main()
