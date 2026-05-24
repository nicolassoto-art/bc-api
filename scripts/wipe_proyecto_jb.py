"""
wipe_proyecto_jb.py — Borra TODO de un proyecto antes de re-importar limpio.

Estrategias:
  --jb-only       Borra solo lo que vino de JB:
                  - imagenes con categoria jb-* o cover
                  - extra.fisicos, .comercial, .formas_pago_pie, .cuenta_reserva,
                    .inmobiliaria, .spa_proyecto, .modelos, .modelos_dom,
                    .bodegas_dom, .estacionamientos_dom, .notas_html, .notas_text,
                    .etiquetas, .stock_type, .solicita_preaprobacion
  --full          Borra TODO incluso lo legacy:
                  - Todas las unidades del proyecto
                  - Todas las imagenes
                  - Reset extra = {jb_id: <preservado>}

Uso:
  python3 scripts/wipe_proyecto_jb.py <jb_id> --jb-only
  python3 scripts/wipe_proyecto_jb.py <jb_id> --full

Env: BC_API_BASE, BC_API_JWT (o BC_API_EMAIL+BC_API_PASSWORD)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("wipe")


# Keys de extra que SON de JB (se borran en --jb-only; se preservan otras)
JB_EXTRA_KEYS = {
    "fisicos", "comercial", "formas_pago_pie", "cuenta_reserva",
    "inmobiliaria", "spa_proyecto", "modelos", "modelos_dom",
    "bodegas_dom", "estacionamientos_dom",
    "_estacionamientos_dom", "_bodegas_dom",
    "_jb_documentos_summary", "_jb_stock_excel",
    "notas_html", "notas_text", "etiquetas", "stock_type",
    "solicita_preaprobacion", "descripcion",
    "_jb_imported_at", "_scrape_jb_editor_at",
}


async def get_jwt(bc_base: str) -> str:
    jwt = os.environ.get("BC_API_JWT")
    if jwt:
        return jwt
    email = os.environ.get("BC_API_EMAIL", "nicolas.soto@bigcapital.cl")
    password = os.environ.get("BC_API_PASSWORD")
    if not password:
        raise RuntimeError("Falta BC_API_JWT o BC_API_PASSWORD")
    async with httpx.AsyncClient(timeout=15.0) as cli:
        r = await cli.post(f"{bc_base}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def find_proyecto_by_jb_id(client: httpx.AsyncClient, jb_id: str) -> dict | None:
    """Busca proyecto cuyo extra.jb_id == jb_id."""
    r = await client.get("/proyectos")
    r.raise_for_status()
    for p in r.json():
        try:
            r2 = await client.get(f"/proyectos/{p['id']}")
            full = r2.json()
            if (full.get("extra") or {}).get("jb_id") == jb_id:
                return full
        except Exception:
            continue
    return None


async def wipe(jb_id: str, mode: str) -> dict:
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io").rstrip("/")
    jwt = await get_jwt(bc_base)
    headers = {"Authorization": f"Bearer {jwt}", "Accept": "application/json"}

    async with httpx.AsyncClient(base_url=bc_base, headers=headers, timeout=60.0) as cli:
        # Buscar proyecto
        proj = await find_proyecto_by_jb_id(cli, jb_id)
        if not proj:
            log.error(f"No se encontró proyecto con extra.jb_id={jb_id}")
            return {"error": "not_found"}
        proyecto_id = proj["id"]
        log.info(f"📦 Proyecto: {proj['nombre']} (id={proyecto_id})")

        deleted = {"imagenes": 0, "documentos": 0, "unidades": 0, "extra_keys_cleared": 0}

        # ── IMAGENES ──
        for img in proj.get("imagenes", []):
            cat = (img.get("categoria") or "").lower()
            should_delete = False
            if mode == "full":
                should_delete = True
            elif mode == "jb-only":
                should_delete = cat.startswith("jb-") or cat == "cover"
            if should_delete:
                img_id = img.get("id")
                try:
                    r = await cli.delete(f"/proyectos/{proyecto_id}/imagenes/{img_id}")
                    if r.status_code in (200, 204):
                        deleted["imagenes"] += 1
                except Exception as e:
                    log.warning(f"   delete imagen {img_id}: {e}")
        log.info(f"   🗑 Imágenes borradas: {deleted['imagenes']}")

        # ── UNIDADES (solo en --full) ──
        if mode == "full":
            for u in proj.get("unidades", []):
                try:
                    r = await cli.delete(f"/proyectos/{proyecto_id}/unidades/{u['id']}")
                    if r.status_code in (200, 204):
                        deleted["unidades"] += 1
                except Exception:
                    pass
            log.info(f"   🗑 Unidades borradas: {deleted['unidades']}")

        # ── EXTRA ──
        new_extra = dict(proj.get("extra") or {})
        if mode == "full":
            # Preservar solo jb_id
            jb_id_preserved = new_extra.get("jb_id")
            new_extra = {"jb_id": jb_id_preserved} if jb_id_preserved else {}
            deleted["extra_keys_cleared"] = len(proj.get("extra") or {}) - len(new_extra)
        else:
            # Borrar solo keys JB-managed
            for k in list(new_extra.keys()):
                if k in JB_EXTRA_KEYS:
                    del new_extra[k]
                    deleted["extra_keys_cleared"] += 1
        log.info(f"   🗑 Extra keys borradas: {deleted['extra_keys_cleared']}")

        # PUT proyecto con el extra limpio
        body = {
            "nombre": proj["nombre"],
            "inmobiliaria": proj.get("inmobiliaria"),
            "comuna": proj.get("comuna"),
            "region": proj.get("region"),
            "direccion": proj.get("direccion"),
            "gps_lat": proj.get("gps_lat"),
            "gps_lon": proj.get("gps_lon"),
            "fase": proj.get("fase"),
            "modalidad": proj.get("modalidad"),
            "activo": proj.get("activo", True),
            "disponible": proj.get("disponible", True),
            "fecha_entrega": proj.get("fecha_entrega"),
            "ano_entrega": proj.get("ano_entrega"),
            "foto_principal_url": proj.get("foto_principal_url") if mode != "full" else None,
            "external_url": proj.get("external_url"),
            "notas": proj.get("notas") if mode != "full" else None,
            "extra": new_extra,
        }
        r = await cli.put(f"/proyectos/{proyecto_id}", json=body)
        if not r.is_success:
            log.error(f"PUT falló: {r.status_code} {r.text[:200]}")

        log.info(f"\n✓ Wipe completo. Resumen: {deleted}")
        return deleted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--jb-only", action="store_const", const="jb-only", dest="mode")
    g.add_argument("--full", action="store_const", const="full", dest="mode")
    args = parser.parse_args()
    result = asyncio.run(wipe(args.jb_id, args.mode))
    print(result)


if __name__ == "__main__":
    main()
