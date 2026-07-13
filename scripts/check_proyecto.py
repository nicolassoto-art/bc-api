"""check_proyecto.py — Lectura pura de un proyecto en bc-api (GET, sin escribir nada).

Uso: PID=<proyecto_id> python3 scripts/check_proyecto.py
"""
import json
import os

import httpx

BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ["PID"]
jwt = os.environ["BC_API_JWT"]

cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
r = cli.get(f"/proyectos/{PID}")
print(f"GET /proyectos/{PID} -> HTTP {r.status_code}")
if r.status_code != 200:
    print(r.text[:500])
    raise SystemExit(1)

p = r.json()
extra = p.get("extra") or {}
unidades = p.get("unidades") or []

print(f"\n=== {p.get('nombre')!r} ({PID}) ===")
print(f"inmobiliaria: {p.get('inmobiliaria')!r}")
print(f"comuna: {p.get('comuna')!r}")
print(f"modalidad: {p.get('modalidad')!r}")
print(f"disponible: {p.get('disponible')}")
print(f"unidades: {len(unidades)}")
print(f"notas_html chars: {len(extra.get('notas_html') or '')}")
print(f"notas_text chars: {len(extra.get('notas_text') or '')}")
print(f"extra.comercial: {json.dumps(extra.get('comercial') or {}, ensure_ascii=False)}")
print(f"extra._marketplace_documentos: {len(extra.get('_marketplace_documentos') or [])} items")
print(f"extra._marketplace_workview: {extra.get('_marketplace_workview')}")
print(f"extra keys: {sorted(extra.keys())}")
print(f"extra.modelos: {json.dumps(extra.get('modelos'), ensure_ascii=False, default=str)}")
print(f"imagenes: {len(p.get('imagenes') or [])} items")
if unidades:
    print(f"\nsample unidad[0]: {json.dumps(unidades[0], ensure_ascii=False, default=str)}")
