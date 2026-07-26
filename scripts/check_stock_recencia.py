"""check_stock_recencia.py — Lista proyectos que matchean un filtro de inmobiliaria
y su fecha de última actualización de stock (solo lectura).

Uso: FILTRO="aj urbana" python3 scripts/check_stock_recencia.py
"""
import json
import os

import httpx

BC = "https://bc-api.178-105-91-29.nip.io"
FILTRO = os.environ.get("FILTRO", "").strip().lower()
jwt = os.environ["BC_API_JWT"]

cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
r = cli.get("/proyectos")
print(f"GET /proyectos -> HTTP {r.status_code}, {len(r.json()) if r.is_success else '?'} proyectos totales")
if not r.is_success:
    print(r.text[:500])
    raise SystemExit(1)

proyectos = r.json()
matches = [p for p in proyectos if FILTRO in (p.get("inmobiliaria") or "").lower() or FILTRO in (p.get("nombre") or "").lower()]
print(f"\nMatches para {FILTRO!r}: {len(matches)}\n")
for p in sorted(matches, key=lambda x: x.get("stock_updated_at") or ""):
    print(json.dumps({
        "id": p.get("id"),
        "nombre": p.get("nombre"),
        "inmobiliaria": p.get("inmobiliaria"),
        "disponible": p.get("disponible"),
        "unidades_total": p.get("unidades_total"),
        "unidades_disponibles": p.get("unidades_disponibles"),
        "updated_at": p.get("updated_at"),
        "stock_updated_at": p.get("stock_updated_at"),
        "ultima_revision_at": p.get("ultima_revision_at"),
    }, ensure_ascii=False, default=str))
