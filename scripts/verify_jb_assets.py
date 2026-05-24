"""
verify_jb_assets.py — Test 2: paridad de assets (fotos, planos, documentos).

1. Cuenta items en JB editor (fotos, docs) y modelos con blueprint
2. Cuenta items en bc-api (imagenes, documentos, extra.modelos con plano_url)
3. Para cada URL en bc-api: HEAD request, confirmar 200 + bytes>1KB

Genera: imports/{jb_id}/verify/test2-assets.json
Exit 0 si counts JB==BC y todas las URLs viven.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify2")


async def head_url(url: str, timeout: float = 15.0) -> dict:
    if not url or not str(url).startswith(("http://", "https://", "/")):
        return {"url": url, "alive": False, "reason": "invalid_url"}
    full_url = url
    if url.startswith("/"):
        full_url = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io").rstrip("/") + url
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            r = await cli.head(full_url)
            if r.status_code == 405:  # algunos servers no soportan HEAD
                r = await cli.get(full_url)
            size = int(r.headers.get("content-length") or 0)
            ctype = r.headers.get("content-type", "")
            alive = r.status_code == 200 and size > 1024
            return {
                "url": url,
                "alive": alive,
                "status": r.status_code,
                "content_type": ctype,
                "size": size,
            }
    except Exception as e:
        return {"url": url, "alive": False, "reason": str(e)[:120]}


async def count_jb_assets(imp: JBImporter, jb_id: str) -> dict:
    """Navegar JB editor → tab Documentos → contar por tipo (fotos/planos/docs)."""
    page = imp._page
    edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
    if not page.url.startswith(edit_url):
        await page.goto(edit_url, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(4_000)

    counts = {"fotos": 0, "documentos": 0, "modelos_con_plano": 0}

    # Todo vive en el tab Documentos. Clasificar por columna "Tipo" + extensión
    try:
        await imp._click_tab("Documentos")
        await page.wait_for_timeout(2_500)
        rows = await page.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            let best = null, bestN = 0;
            tables.forEach(t => {
                const n = t.querySelectorAll('tbody tr').length;
                if (n > bestN) { best = t; bestN = n; }
            });
            if (!best) return [];
            return [...best.querySelectorAll('tbody tr')].map(tr => {
                const cells = [...tr.querySelectorAll('td')].map(c => c.innerText.trim());
                return cells;
            });
        }""")
        for cells in rows:
            tipo = (cells[2] if len(cells) > 2 else "").lower()
            ext = (cells[4] if len(cells) > 4 else "").lower()
            if "foto" in tipo or "imagen" in tipo or ext in ("jpg", "jpeg", "png", "webp", "gif"):
                counts["fotos"] += 1
            elif "planta" in tipo or "plano" in tipo or "subter" in tipo:
                counts["modelos_con_plano"] += 1
            else:
                counts["documentos"] += 1
        log.info(f"   📄 Documentos table: {len(rows)} rows → {counts['fotos']} fotos, {counts['modelos_con_plano']} planos, {counts['documentos']} docs")
    except Exception as e:
        log.warning(f"   contar JB documentos → {e}")

    return counts


async def main(jb_id: str):
    out_dir = Path(os.environ.get("IMPORTS_DIR", "imports")) / jb_id / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)

    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ["BC_API_JWT"],
        headless=os.environ.get("HEADLESS", "1") != "0",
    )
    try:
        await imp.login()
        # Counts JB
        jb_counts = await count_jb_assets(imp, jb_id)
        # bc-api project
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error(f"No se encontró proyecto con extra.jb_id={jb_id}")
            sys.exit(2)

        # Counts BC
        imagenes = proj.get("imagenes") or []
        documentos = proj.get("documentos") or []
        # Algunos sistemas guardan docs como categoria=documento en imagenes (fallback)
        docs_in_imagenes = [i for i in imagenes if (i.get("categoria") or "").startswith("doc")]
        modelos_bc = (proj.get("extra") or {}).get("modelos") or []
        modelos_con_plano_bc = sum(1 for m in modelos_bc if m.get("plano_url"))

        # HEAD a cada URL
        all_urls = []
        all_urls += [i.get("url") for i in imagenes if i.get("url")]
        all_urls += [d.get("url") for d in documentos if d.get("url")]
        all_urls += [m.get("plano_url") for m in modelos_bc if m.get("plano_url")]
        all_urls = [u for u in all_urls if u]

        log.info(f"🔗 HEAD a {len(all_urls)} URLs...")
        head_results = await asyncio.gather(*(head_url(u) for u in all_urls))

        broken = [r for r in head_results if not r["alive"]]
        all_alive = len(broken) == 0

        # Resultado
        bc_fotos = len(imagenes) - len(docs_in_imagenes) - len([i for i in imagenes if (i.get("categoria") or "").startswith("plano")])
        bc_docs = len(documentos) + len(docs_in_imagenes)
        result = {
            "jb_id": jb_id,
            "proyecto_id": proj.get("id"),
            "fotos": {
                "jb": jb_counts["fotos"],
                "bc": max(0, bc_fotos),
                "match": jb_counts["fotos"] == max(0, bc_fotos),
            },
            "documentos": {
                "jb": jb_counts["documentos"],
                "bc": bc_docs,
                "match": jb_counts["documentos"] == bc_docs,
            },
            "planos": {
                "jb": jb_counts["modelos_con_plano"],
                "bc": modelos_con_plano_bc,
                "match": jb_counts["modelos_con_plano"] == modelos_con_plano_bc,
            },
            "urls_checked": len(all_urls),
            "urls_alive": len(all_urls) - len(broken),
            "all_urls_alive": all_alive,
            "broken_urls": broken[:20],
        }
        # Estado overall
        ok_counts = result["fotos"]["match"] and result["planos"]["match"] and result["documentos"]["match"]
        result["status"] = "OK" if (ok_counts and all_alive) else "FAIL"

        out_file = out_dir / "test2-assets.json"
        out_file.write_text(json.dumps(result, indent=2))
        log.info(f"   ✓ JSON: {out_file}")
        log.info(f"   📊 Status: {result['status']}")
        log.info(f"      fotos JB={jb_counts['fotos']} BC={max(0,bc_fotos)} → {'✓' if result['fotos']['match'] else '✗'}")
        log.info(f"      docs JB={jb_counts['documentos']} BC={bc_docs} → {'✓' if result['documentos']['match'] else '✗'}")
        log.info(f"      planos JB={jb_counts['modelos_con_plano']} BC={modelos_con_plano_bc} → {'✓' if result['planos']['match'] else '✗'}")
        log.info(f"      URLs alive: {result['urls_alive']}/{result['urls_checked']}")

        return result["status"] == "OK"
    finally:
        await imp.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
