"""Re-importa proyectos multibloque (con números de unidad duplicados).

Estos proyectos tienen departamentos en distintas torres con el mismo número.
El importador original deduplicaba por número y perdía unidades.
Tras el fix (dedup por JB unit ID), hay que re-importar con overwrite=True.

Uso:
    python scripts/reimport_multibloque.py \\
        --jb-json /path/to/jb_export_final.json \\
        --bcapi-url https://bc-api.178-105-91-29.nip.io \\
        --bcapi-email nicolas.soto@bigcapital.cl \\
        --bcapi-pass-file ~/.bcapi-admin-pass \\
        --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def find_multibloque(projects: list[dict]) -> list[dict]:
    """Devuelve proyectos que tienen números de depto duplicados (multibloque)."""
    result = []
    for p in projects:
        apts = [u for u in p.get("units", []) if u.get("type") == "apartment"]
        nums = [u["number"] for u in apts]
        if len(nums) != len(set(nums)):
            result.append(p)
    return result


def bcapi_login(url: str, email: str, password: str) -> str:
    r = httpx.post(f"{url}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def batch_import(url: str, token: str, projects: list[dict], overwrite: bool = True) -> dict:
    r = httpx.post(
        f"{url}/importador/batch",
        json={"projects": projects, "overwrite": overwrite},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jb-json", required=True, help="Path al jb_export_final.json")
    ap.add_argument("--bcapi-url", required=True)
    ap.add_argument("--bcapi-email", required=True)
    ap.add_argument("--bcapi-pass-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=10, help="Proyectos por batch")
    args = ap.parse_args()

    with open(args.jb_json) as f:
        raw = json.load(f)
    all_projects = raw if isinstance(raw, list) else raw.get("projects", [])

    multibloque = find_multibloque(all_projects)
    print(f"Proyectos multibloque detectados: {len(multibloque)}")
    for p in multibloque:
        apts = [u for u in p.get("units", []) if u.get("type") == "apartment"]
        unique_nums = len(set(u["number"] for u in apts))
        print(f"  {p['name']:45s} {len(apts):4d} apts JB → {unique_nums:4d} únicos (recupera {len(apts)-unique_nums})")

    if args.dry_run:
        total_recover = sum(
            len([u for u in p.get("units", []) if u.get("type") == "apartment"])
            - len(set(u["number"] for u in p.get("units", []) if u.get("type") == "apartment"))
            for p in multibloque
        )
        print(f"\n(dry-run) Se recuperarían {total_recover} unidades en {len(multibloque)} proyectos.")
        return

    password = Path(args.bcapi_pass_file).expanduser().read_text().strip()
    token = bcapi_login(args.bcapi_url, args.bcapi_email, password)
    print(f"\n✓ Logueado a {args.bcapi_url}\n")

    # Importar en batches
    total_ok = total_err = 0
    for i in range(0, len(multibloque), args.batch_size):
        batch = multibloque[i : i + args.batch_size]
        names = [p["name"] for p in batch]
        print(f"Batch {i//args.batch_size + 1}: {names}")
        try:
            result = batch_import(args.bcapi_url, token, batch, overwrite=True)
            print(f"  ✓ {result['created']} creados, {result['updated']} actualizados, {result['errors']} errores")
            for d in result.get("details", []):
                if d["status"] == "error":
                    print(f"    ✗ {d['name']}: {d.get('reason')}")
                elif d["status"] == "ok":
                    print(f"    ✓ {d['name']}: {d.get('units')} unidades")
            total_ok += result["updated"] + result["created"]
            total_err += result["errors"]
        except Exception as e:
            print(f"  ✗ Error en batch: {e}")
            total_err += len(batch)

    print(f"\n{'='*60}")
    print(f"Re-import completado: {total_ok} ok · {total_err} errores")


if __name__ == "__main__":
    main()
