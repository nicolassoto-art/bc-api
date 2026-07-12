"""
import_marketplace_workview.py — Importa un proyecto de marketplace/workview
(proyecto de OTRA inmobiliaria agregado a nuestro catálogo de reventa en
JetBrokers) a bc-api: General (nombre/comuna/modalidad/inmobiliaria) + Stock
(unidades) + Notas comerciales + catálogo de Documentos (metadata).

A diferencia de import_jb.py (editor propio, /projects/edit/): SIN wipe (no es
proyecto nuestro), SIN descarga de fotos/planos/documentos binarios (solo se
catalogan sus metadatos en extra._marketplace_documentos -- ver TODO abajo).

Uso:
  python3 scripts/import_marketplace_workview.py IquFoRoO [--dry-run]

Env requeridas: JETBROKERS_EMAIL, JETBROKERS_PASS, BC_API_JWT (o BC_TOKEN)
Opcional: BC_API_BASE (default https://bc-api.178-105-91-29.nip.io)

TODO futuro: descargar+subir los archivos de Documentos/JetGallery (requiere
click-por-archivo con page.expect_download(), no hay href directo -- 21+
descargas secuenciales, más carga en JB. Se dejó fuera de v1 a propósito.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.services.jb_importer import JBImporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("import_marketplace_workview")


async def get_jwt(bc_api_base: str) -> str:
    jwt = os.environ.get("BC_API_JWT")
    if jwt:
        return jwt
    bc_token = os.environ.get("BC_TOKEN")
    if not bc_token:
        raise RuntimeError("Faltan BC_API_JWT o BC_TOKEN en env")
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(f"{bc_api_base}/auth/exchange", json={"bc_token": bc_token})
    if not r.is_success:
        raise RuntimeError(f"/auth/exchange falló: HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


async def run(jb_id: str, bc_base: str, jwt: str, dry_run: bool, headless: bool = True, stock_only: bool = False) -> int:
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

        # Buscar proyecto existente por jb_id; si no existe, crear placeholder
        # (mismo patrón que run(), pero SIN wipe -- no es proyecto nuestro).
        current = await imp.find_proyecto_by_jb_id(jb_id)
        if not current:
            log.info(f"   📝 Proyecto extra.jb_id={jb_id} no existe — creando placeholder...")
            stub_body = {
                "nombre": f"JB-{jb_id}",
                "inmobiliaria": "Sin asignar",
                "modalidad": "Nuevo",
                "activo": True,
                "disponible": True,
                "extra": {"jb_id": jb_id},
            }
            r = await imp._bc_client.post("/proyectos", json=stub_body)
            if not r.is_success:
                log.error(f"✗ No se pudo crear proyecto placeholder: HTTP {r.status_code} {r.text[:300]}")
                return 1
            current = r.json()
        proyecto_id = current["id"]
        log.info(f"▶ proyecto_id={proyecto_id} (nombre actual: {current.get('nombre')!r})")

        scraped = await imp.scrape_marketplace_workview(jb_id, stock_only=stock_only)
        n_fields = imp._count_leaves(scraped)
        log.info(f"   {n_fields} campos extraídos" + (" (stock_only)" if stock_only else ""))

        unidades = imp._pending_unidades or []
        notas_chars = len((scraped.get("extra") or {}).get("notas_html") or "")
        docs_count = len((scraped.get("extra") or {}).get("_marketplace_documentos") or [])
        top = scraped.get("_top_level") or {}
        log.info(
            f"   resumen: nombre={top.get('nombre')!r} comuna={top.get('comuna')!r} "
            f"modalidad={top.get('modalidad')!r} unidades={len(unidades)} "
            f"notas_html_chars={notas_chars} documentos={docs_count}"
        )

        if dry_run:
            log.info("   (dry-run) NO se sube nada a bc-api")
            print(json.dumps({
                "proyecto_id": proyecto_id,
                "top_level": top,
                "unidades_count": len(unidades),
                "notas_html_chars": notas_chars,
                "documentos_count": docs_count,
                "sample_unidad": unidades[0] if unidades else None,
            }, indent=2, ensure_ascii=False, default=str))
            return 0

        # PUT proyecto (nombre/comuna/modalidad/inmobiliaria/notas/documentos_meta)
        await imp.put_proyecto(proyecto_id, current, scraped, modelos=[])
        log.info("   ✓ PUT /proyectos OK")

        # Subir unidades vía Excel sintético + /excel/upload (upsert+baja seguro,
        # a diferencia de upload_unidades_direct que solo POSTea -- correcto para
        # la carga inicial pero duplicaría unidades en cada corrida del sync
        # recurrente diario).
        if unidades:
            xlsx_path = imp.build_jb_style_excel(jb_id, unidades)
            result = await imp.upload_jb_excel(proyecto_id, xlsx_path)
            if result.get("status") == "error":
                log.error(f"✗ upload excel falló: {result}")
                return 1
            log.info(
                f"   ✓ unidades: {result.get('inserted', 0)} ins, {result.get('updated', 0)} upd, "
                f"{len(result.get('errors', []))} err"
            )
        else:
            log.warning("   ⚠ sin unidades parseadas — revisar selectores de Stock")

        live_check = await imp.verify_live(proyecto_id, {"unidades": len(unidades)})
        log.info(f"   verify_live: {live_check.get('live', {}).get('unidades')} unidades en bc-api")

        print(json.dumps({
            "proyecto_id": proyecto_id,
            "unidades_subidas": len(unidades),
            "notas_html_chars": notas_chars,
            "documentos_catalogados": docs_count,
            "live_verify": live_check,
        }, indent=2, ensure_ascii=False, default=str))
        return 0
    finally:
        await imp.close()


def main():
    parser = argparse.ArgumentParser(description="Importa un proyecto marketplace/workview a bc-api")
    parser.add_argument("jb_id", help="JB project ID (ej: IquFoRoO)")
    parser.add_argument("--dry-run", action="store_true", help="Scrapea y muestra el resumen, no sube nada")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--stock-only", action="store_true",
        help="Solo tab Stock (salta Condiciones Comerciales/Notas/Documentos) -- para el sync diario, menos carga en JB",
    )
    args = parser.parse_args()

    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io").rstrip("/")

    async def _main():
        jwt = await get_jwt(bc_base)
        code = await run(args.jb_id, bc_base, jwt, dry_run=args.dry_run, headless=not args.headed, stock_only=args.stock_only)
        sys.exit(code)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
