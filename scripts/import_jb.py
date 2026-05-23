"""
import_jb.py — CLI thin wrapper sobre JBImporter.

Uso:
  python3 scripts/import_jb.py Sfp8j2Sq
  python3 scripts/import_jb.py Sfp8j2Sq --dry-run --skip-assets
  python3 scripts/import_jb.py --all

Env requeridas:
  JETBROKERS_EMAIL, JETBROKERS_PASS, BC_API_JWT (o BC_TOKEN)
  Opcional: BC_API_BASE (default https://bc-api.178-105-91-29.nip.io)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Hacer importable el paquete app/ desde scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.services.jb_importer import JBImporter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("import_jb")


async def get_jwt(bc_api_base: str) -> str:
    """Obtiene un JWT — prioriza BC_API_JWT (ya fresco), sino exchange con BC_TOKEN."""
    jwt = os.environ.get("BC_API_JWT")
    if jwt:
        return jwt
    bc_token = os.environ.get("BC_TOKEN")
    if not bc_token:
        raise RuntimeError("Faltan BC_API_JWT o BC_TOKEN en env")
    log.info("🔑 Exchange BC_TOKEN → JWT...")
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(
            f"{bc_api_base}/auth/exchange",
            json={"bc_token": bc_token},
        )
    if not r.is_success:
        raise RuntimeError(f"/auth/exchange falló: HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    return data.get("access_token") or data.get("token")


async def run_one(jb_id: str, args, bc_base: str, jwt: str, headless: bool = True):
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base,
        bc_jwt=jwt,
        imports_dir=Path(os.environ.get("IMPORTS_DIR", "imports")),
        headless=headless,
    )
    try:
        await imp.login()
        rep = await imp.run(jb_id, skip_assets=args.skip_assets, dry_run=args.dry_run)
        print(json.dumps(rep.to_dict(), indent=2, default=str))
        return rep
    finally:
        await imp.close()


async def run_all(args, bc_base: str, jwt: str):
    # Listar proyectos y filtrar los que tienen extra.jb_id
    async with httpx.AsyncClient(
        base_url=bc_base,
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=30.0,
    ) as cli:
        r = await cli.get("/proyectos")
        r.raise_for_status()
        proys = r.json()

    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base,
        bc_jwt=jwt,
        imports_dir=Path(os.environ.get("IMPORTS_DIR", "imports")),
    )
    await imp.login()
    try:
        results = []
        for p in proys:
            # Cargar extra
            full = await imp.get_proyecto(p["id"])
            jb_id = (full.get("extra") or {}).get("jb_id")
            if not jb_id:
                log.info(f"  ⊘ {p['nombre']} sin extra.jb_id — skip")
                continue
            log.info(f"▶ {p['nombre']} (jb_id={jb_id})")
            try:
                rep = await imp.run(jb_id, skip_assets=args.skip_assets, dry_run=args.dry_run)
                results.append({"id": p["id"], "ok": not rep.errors, "rep": rep.to_dict()})
            except Exception as e:
                log.error(f"  ✗ {p['nombre']}: {e}")
                results.append({"id": p["id"], "ok": False, "err": str(e)})
            await asyncio.sleep(3)
        summary_file = Path(os.environ.get("IMPORTS_DIR", "imports")) / "_summary.json"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(results, indent=2, default=str))
        print(f"\n✅ Sumario en {summary_file}")
    finally:
        await imp.close()


def main():
    parser = argparse.ArgumentParser(description="Importa proyecto(s) JB → bc-api")
    parser.add_argument("jb_id", nargs="?", help="JB project ID (ej: Sfp8j2Sq)")
    parser.add_argument("--all", action="store_true", help="Iterar todos los proyectos.extra.jb_id")
    parser.add_argument("--skip-assets", action="store_true", help="No descargar/subir fotos+planos")
    parser.add_argument("--dry-run", action="store_true", help="No hacer PUT a bc-api")
    parser.add_argument("--headed", action="store_true", help="Ejecutar Playwright con browser visible (debug local)")
    args = parser.parse_args()

    if not args.all and not args.jb_id:
        parser.error("Especificar un jb_id o --all")

    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io").rstrip("/")

    async def _main():
        jwt = await get_jwt(bc_base)
        if args.all:
            await run_all(args, bc_base, jwt)
        else:
            rep = await run_one(args.jb_id, args, bc_base, jwt, headless=not args.headed)
            if rep.errors:
                sys.exit(1)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
