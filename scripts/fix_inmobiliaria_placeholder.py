"""
fix_inmobiliaria_placeholder.py — Reemplaza "BigCapital" (el broker, no una inmobiliaria)
en el campo inmobiliaria de proyectos con "Sin asignar" cuando no se haya podido
identificar la inmobiliaria real desde JB.
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
    print(f"Total proyectos: {len(listing)}")

    fixed = 0
    skipped = 0
    errors = 0
    import time
    for p in listing:
        pid = p.get("id")
        if not pid:
            continue
        # Filtrar por listing summary antes de fetchar full (evita carga inútil al VPS)
        # listing trae inmobiliaria en el summary
        summary_inmo = (p.get("inmobiliaria") or "").strip()
        if summary_inmo.lower() != "bigcapital":
            skipped += 1
            continue
        # Retry 3 veces con backoff
        full = None
        for attempt in range(3):
            try:
                r2 = cli.get(f"/proyectos/{pid}")
                if r2.status_code == 200:
                    full = r2.json()
                    break
                print(f"  ↺ {pid}: HTTP {r2.status_code} (attempt {attempt+1})")
                time.sleep(2 * (attempt + 1))
            except Exception as e:
                print(f"  ↺ {pid}: {e} (attempt {attempt+1})")
                time.sleep(2 * (attempt + 1))
        if full is None:
            print(f"  ✗ {pid}: no se pudo recuperar tras 3 intentos")
            errors += 1
            continue

        cur_inmo = (full.get("inmobiliaria") or "").strip()
        if cur_inmo.lower() != "bigcapital":
            skipped += 1
            continue

        # PUT con inmobiliaria = "Sin asignar" preservando todo lo demás
        body = {**full, "inmobiliaria": "Sin asignar"}
        # Remover campos que el PUT no debe recibir
        for k in ("imagenes", "documentos", "unidades", "created_at", "updated_at"):
            body.pop(k, None)
        try:
            r2 = cli.put(f"/proyectos/{pid}", json=body)
            if r2.status_code in (200, 201):
                print(f"  ✓ {pid:30s} {full.get('nombre','')[:40]:40s} BigCapital → Sin asignar")
                fixed += 1
            else:
                print(f"  ✗ {pid}: HTTP {r2.status_code} {r2.text[:150]}")
                errors += 1
        except Exception as e:
            print(f"  ✗ {pid}: {e}")
            errors += 1

    print(f"\nFixed: {fixed} · Skipped: {skipped} · Errors: {errors}")


if __name__ == "__main__":
    main()
