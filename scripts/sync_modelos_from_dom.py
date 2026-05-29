"""
sync_modelos_from_dom.py — Sincroniza extra.modelos desde extra.modelos_dom
para todos los proyectos donde extra.modelos esté vacío pero modelos_dom tenga data.

Útil cuando el importer dejó extra.modelos = [] pero el editor necesita ver
los modelos (lo hace via api-client.js fallback, pero auditorías y queries
directas a la API esperan extra.modelos populado).
"""
from __future__ import annotations
import os
import sys
import httpx


def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)

    r = cli.get("/proyectos")
    r.raise_for_status()
    listing = r.json()
    print(f"📚 Total proyectos: {len(listing)}")

    fixed = 0
    skipped = 0
    errors = 0
    for p in listing:
        pid = p.get("id")
        if not pid:
            continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"  ✗ {pid}: GET error {e}")
            errors += 1
            continue

        extra = full.get("extra") or {}
        modelos = extra.get("modelos") or []
        modelos_dom = extra.get("modelos_dom") or []

        # Solo intervenir si modelos vacío y modelos_dom tiene data
        if modelos or not modelos_dom:
            skipped += 1
            continue

        # Shape
        shaped = []
        for i, m in enumerate(modelos_dom):
            if not isinstance(m, dict):
                continue
            mid = m.get("id") or m.get("planta_id") or f"jb-dom-{i}"
            shaped.append({**m, "id": mid})

        if not shaped:
            skipped += 1
            continue

        # PUT
        body = {**full, "extra": {**extra, "modelos": shaped}}
        for k in ("imagenes", "documentos", "unidades", "created_at", "updated_at"):
            body.pop(k, None)
        try:
            r2 = cli.put(f"/proyectos/{pid}", json=body)
            if r2.status_code in (200, 201):
                print(f"  ✓ {pid:35s} {(full.get('nombre') or '')[:35]:35s} +{len(shaped)} modelos")
                fixed += 1
            else:
                print(f"  ✗ {pid}: HTTP {r2.status_code} {r2.text[:150]}")
                errors += 1
        except Exception as e:
            print(f"  ✗ {pid}: PUT {e}")
            errors += 1

    print(f"\nResultado: {fixed} fixed · {skipped} skipped · {errors} errors")


if __name__ == "__main__":
    main()
