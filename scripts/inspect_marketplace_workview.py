"""
inspect_marketplace_workview.py — Reconocimiento de una URL /marketplace/workview/{id}
de JetBrokers (proyecto de OTRA inmobiliaria, listado en el marketplace, no editable
por nosotros vía /projects/edit/{id} -- esa ruta rebota a login sin permisos de edición).

No asume estructura: solo login real, navega, dumpea texto+HTML+screenshot de la
página inicial, y prueba clickear labels de tabs conocidos (Notas, Stock, Unidades,
Modelos, Condiciones, etc.) tomando screenshot de cada uno que encuentre. Objetivo:
entender QUÉ datos son visibles en marketplace/workview antes de escribir un scraper
específico (el pipeline actual solo sabe scrapear /projects/edit/, editor propio).

Uso:
  python3 scripts/inspect_marketplace_workview.py IquFoRoO

Env requeridas: JETBROKERS_EMAIL, JETBROKERS_PASS
Salida: imports/_inspect/<jb_id>/  (screenshot inicial + por tab, texto, HTML, botones encontrados)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jb_importer import JBImporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("inspect_workview")

TAB_CANDIDATES = [
    "General",
    "Stock",
    "Documentos",
    "Notas",
    "Arriendos",
    "JetGallery",
    "Comisiones",
    "Timeline",
]


async def run(jb_id: str, headless: bool = True) -> None:
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT") or "placeholder",
        imports_dir=Path(os.environ.get("IMPORTS_DIR", "imports")),
        headless=headless,
    )
    out_dir = imp.imports_dir / "_inspect" / jb_id
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        await imp.login()

        url = f"https://app.jetbrokers.io/marketplace/workview/{jb_id}"
        log.info(f"📂 Navegando a {url}")
        await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
        await imp._page.wait_for_timeout(5_000)
        await imp._dismiss_popups()

        final_url = imp._page.url
        log.info(f"   URL final tras navegar: {final_url}")

        html = await imp._page.content()
        (out_dir / "initial.html").write_text(html, encoding="utf-8")
        await imp._page.screenshot(path=str(out_dir / "initial.png"), full_page=True)

        text = await imp._page.evaluate("() => document.body.innerText")
        (out_dir / "initial_text.txt").write_text(text, encoding="utf-8")

        # Listar todos los botones/links visibles con texto (para saber qué se puede clickear)
        buttons = await imp._page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('button, a, [role="tab"]').forEach(el => {
                const t = (el.innerText || '').trim();
                const r = el.getBoundingClientRect();
                if (t && r.width > 0 && r.height > 0) out.push(t.slice(0, 60));
            });
            return [...new Set(out)];
        }""")
        (out_dir / "botones_visibles.json").write_text(json.dumps(buttons, indent=2, ensure_ascii=False))
        log.info(f"   {len(buttons)} botones/links visibles distintos")

        # Probar cada tab candidato, screenshot si lo encuentra
        tabs_found = []
        for tab in TAB_CANDIDATES:
            try:
                await imp._click_tab(tab)
                await imp._page.wait_for_timeout(2_000)
                safe_name = tab.lower().replace(" ", "-")
                await imp._page.screenshot(path=str(out_dir / f"tab-{safe_name}.png"), full_page=True)
                tab_text = await imp._page.evaluate("() => document.body.innerText")
                (out_dir / f"tab-{safe_name}_text.txt").write_text(tab_text, encoding="utf-8")
                tabs_found.append(tab)
                log.info(f"   ✓ tab encontrado y capturado: {tab}")
            except Exception:
                continue

        summary = {
            "jb_id": jb_id,
            "url_solicitada": url,
            "url_final": final_url,
            "tabs_encontrados": tabs_found,
            "n_botones_visibles": len(buttons),
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        log.info(f"✓ Resumen: {json.dumps(summary, ensure_ascii=False)}")
    finally:
        await imp.close()


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 scripts/inspect_marketplace_workview.py <jb_id>")
        sys.exit(2)
    jb_id = sys.argv[1]
    headless = os.environ.get("HEADLESS", "1") != "0"
    asyncio.run(run(jb_id, headless=headless))


if __name__ == "__main__":
    main()
