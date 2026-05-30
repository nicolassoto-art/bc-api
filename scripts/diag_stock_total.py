"""
diag_stock_total.py — Para los 5 proyectos sin unidades, consulta la API JB
y dumpea TODOS los campos relacionados con stock/disponibilidad/conteo.

Objetivo: encontrar el "stock total" agregado que JB sí expone (aunque no el
detalle unidad-por-unidad), para poder hacer el cruce y mostrar el conteo
correcto en bc-api.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter

VACIOS = [
    ("sFfaXZIQ", "Vicuna Mackenna 1194"),
    ("48t1IInf", "EDIFICIO CONEXION INDEPENDENCIA"),
    ("T8UuEf2r", "Santa Rosa 250"),
    ("WWMCny3E", "Los Alerces"),
    ("1kvflc3m", "Vicuna Mackenna 1796"),
]

# Palabras clave que delatan un campo de stock/conteo
STOCK_KEYS = ("stock", "available", "total", "quantity", "count", "units",
              "apartment", "disponib", "unidad", "sold", "reserved", "free")


def find_stock_fields(obj, prefix=""):
    """Recorre recursivamente el JSON y devuelve campos numéricos cuyo nombre
    sugiere stock/conteo."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (int, float)) and any(s in kl for s in STOCK_KEYS):
                out.append((path, v))
            elif isinstance(v, str) and any(s in kl for s in STOCK_KEYS) and v.strip():
                out.append((path, v))
            elif isinstance(v, (dict, list)):
                out.extend(find_stock_fields(v, path))
    elif isinstance(obj, list) and obj:
        # Solo primer item de listas (muestra)
        out.extend(find_stock_fields(obj[0], f"{prefix}[0]"))
    return out


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""),
        headless=True,
    )
    try:
        await imp.login()
        async with imp._jb_httpx() as cli:
            # ── PRIMERO: lista de tarjetas store (tiene 'available' agregado por proyecto) ──
            ids_buscados = {jb for jb, _ in VACIOS}
            card_endpoints = [
                "/projectstore-card/projects",
                "/marketplace/projects",
                "/projects",
            ]
            for ep in card_endpoints:
                try:
                    r = await cli.get(ep)
                    if r.status_code != 200:
                        print(f"[card list] {ep} → HTTP {r.status_code}")
                        continue
                    data = r.json()
                    items = data if isinstance(data, list) else (data.get("data") or data.get("elements") or [])
                    print(f"\n[card list] {ep} → {len(items)} proyectos. Keys del [0]: {sorted(items[0].keys()) if items and isinstance(items[0],dict) else '?'}")
                    # Buscar los 5 vacíos en la lista
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        iid = it.get("id") or it.get("_id") or it.get("projectId")
                        if iid in ids_buscados:
                            stock_fields = find_stock_fields(it)
                            print(f"   ★ {iid} ({it.get('name','?')[:30]}): {stock_fields}")
                except Exception as e:
                    print(f"[card list] {ep} error: {e}")

            # Endpoints candidatos por proyecto
            for jb_id, nombre in VACIOS:
                print(f"\n{'='*70}")
                print(f"=== {nombre} ({jb_id}) ===")
                print('='*70)

                # 1. /projects/{id} — metadata principal
                try:
                    proj = (await cli.get(f"/projects/{jb_id}")).json()
                    fields = find_stock_fields(proj)
                    print(f"\n[/projects/{jb_id}] campos de stock:")
                    for path, val in fields:
                        print(f"    {path} = {val!r}")
                    # También dump top-level keys para ver qué hay
                    if isinstance(proj, dict):
                        print(f"  top-level keys: {sorted(proj.keys())}")
                except Exception as e:
                    print(f"  /projects/{jb_id} error: {e}")

                # 2. /store/.../available — conteo de items
                for ep in (f"/store/project/{jb_id}/available",
                           f"/store/project/{jb_id}",
                           f"/projectstore-card/project/{jb_id}"):
                    try:
                        r = await cli.get(ep)
                        if r.status_code != 200:
                            print(f"  {ep} → HTTP {r.status_code}")
                            continue
                        data = r.json()
                        if isinstance(data, list):
                            print(f"  {ep} → lista de {len(data)} items")
                        else:
                            fields = find_stock_fields(data)
                            print(f"  {ep} → dict, campos stock:")
                            for path, val in fields[:15]:
                                print(f"      {path} = {val!r}")
                    except Exception as e:
                        print(f"  {ep} error: {e}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
