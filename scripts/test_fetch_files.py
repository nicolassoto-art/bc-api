"""test_fetch_files.py — Prueba si fetch_project_files()/download_assets() funcionan
para un proyecto marketplace (no editable vía /projects/edit/) como Laguna Centro.
Si funciona, se puede reusar TODA la pipeline de fotos/plantas ya probada en
84+ proyectos propios, en vez de escribir una nueva desde cero.

Uso: python3 scripts/test_fetch_files.py IquFoRoO
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jb_importer import JBImporter


async def main(jb_id: str):
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT") or "placeholder",
        imports_dir=Path("imports"),
    )
    try:
        await imp.login()
        files = await imp.fetch_project_files(jb_id)
        print(f"fetch_project_files({jb_id!r}) -> {len(files)} archivos")
        for f in files[:10]:
            print(" ", json.dumps(f, ensure_ascii=False, default=str)[:200])
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
