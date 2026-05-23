"""
verify_jb_visual.py — Test 3: screenshots side-by-side de JB editor vs BC vista.

Genera:
  imports/{jb_id}/verify/jb-{tab}.png        (JB editor por tab)
  imports/{jb_id}/verify/bc-{tab}.png        (BC vista por tab)
  imports/{jb_id}/verify/test3-visual.html   (grid side-by-side)

No tiene exit-code de fail — es review humano. Si Playwright revienta, exit 1.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.services.jb_importer import JBImporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify3")

JB_TABS = ["General", "Modelos", "Notas", "Fotos", "Documentos"]
BC_TABS = ["general", "modelos", "stock", "documentos", "notas", "fotos"]


async def screenshot_jb_tabs(imp: JBImporter, jb_id: str, out_dir: Path) -> dict[str, Path]:
    edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
    await imp._page.goto(edit_url, wait_until="networkidle", timeout=60_000)
    await imp._page.wait_for_timeout(4_000)
    paths: dict[str, Path] = {}
    for tab in JB_TABS:
        try:
            if tab != "General":
                await imp._click_tab(tab)
                await imp._page.wait_for_timeout(2_000)
            png = out_dir / f"jb-{tab}.png"
            await imp._page.screenshot(path=str(png), full_page=True)
            paths[tab] = png
            log.info(f"   📸 JB/{tab}: {png.name}")
        except Exception as e:
            log.warning(f"   JB tab {tab} → {e}")
    return paths


async def screenshot_bc_tabs(jb_id: str, proyecto_id: str, bc_token: str, out_dir: Path) -> dict[str, Path]:
    """Usa una segunda página de Playwright (reusar mismo browser para ahorrar)."""
    # Importar a través del JBImporter context activo
    # Lo más simple: launch otro Playwright effímero
    from playwright.async_api import async_playwright

    paths: dict[str, Path] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=os.environ.get("HEADLESS", "1") != "0",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        # Inyectar bc_token y bc_api_token en localStorage del dominio herramientas
        page = await ctx.new_page()
        # Primero navegar al dominio para poder setear localStorage
        await page.goto("https://herramientas.bigcapital.cl/", wait_until="domcontentloaded", timeout=30_000)
        await page.evaluate(
            "(t) => { localStorage.setItem('bc_token', t); localStorage.setItem('bc_user_email','nicolas.soto@bigcapital.cl'); }",
            bc_token,
        )
        # Cargar la vista
        vista_url = f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto-vista.html?id={proyecto_id}"
        await page.goto(vista_url, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(4_000)
        # Auth gate puede tardar (exchange BC token → JWT)
        await page.wait_for_timeout(3_000)

        for tab in BC_TABS:
            try:
                if tab != "general":
                    try:
                        await page.click(f'[data-tab="{tab}"]', timeout=4_000)
                        await page.wait_for_timeout(1_500)
                    except Exception:
                        pass
                png = out_dir / f"bc-{tab}.png"
                await page.screenshot(path=str(png), full_page=True)
                paths[tab] = png
                log.info(f"   📸 BC/{tab}: {png.name}")
            except Exception as e:
                log.warning(f"   BC tab {tab} → {e}")
        await browser.close()
    return paths


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
    bc_token = os.environ.get("BC_TOKEN", "")
    try:
        await imp.login()
        jb_paths = await screenshot_jb_tabs(imp, jb_id, out_dir)
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error(f"No se encontró proyecto con extra.jb_id={jb_id}")
            sys.exit(2)
        bc_paths = await screenshot_bc_tabs(jb_id, proj["id"], bc_token, out_dir) if bc_token else {}
        if not bc_paths:
            log.warning("BC_TOKEN no disponible, omito screenshots BC")
    finally:
        await imp.close()

    # HTML side-by-side
    rows_html = []
    # Mapeo de JB tab → BC tab (best-effort)
    pairs = [
        ("General", "general"),
        ("Modelos", "modelos"),
        ("Fotos", "fotos"),
        ("Notas", "notas"),
        ("Documentos", "documentos"),
    ]
    for jb_tab, bc_tab in pairs:
        jb_img = jb_paths.get(jb_tab)
        bc_img = bc_paths.get(bc_tab) if bc_paths else None
        jb_src = f"jb-{jb_tab}.png" if jb_img else ""
        bc_src = f"bc-{bc_tab}.png" if bc_img else ""
        jb_html_img = f'<img src="{jb_src}">' if jb_src else '<em>n/a</em>'
        bc_html_img = f'<img src="{bc_src}">' if bc_src else '<em>n/a</em>'
        rows_html.append(
            f"<h2>{escape(jb_tab)} ↔ {escape(bc_tab)}</h2>"
            f'<div class="row">'
            f'<div><h3>JetBrokers</h3>{jb_html_img}</div>'
            f'<div><h3>BigCapital</h3>{bc_html_img}</div>'
            f"</div>"
        )
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Test 3 visual {escape(jb_id)}</title>
<style>
  body{{font-family:-apple-system,sans-serif;background:#111;color:#eee;padding:20px}}
  .row{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:30px}}
  .row > div{{background:#1a1a1a;padding:10px;border-radius:8px}}
  img{{max-width:100%;border:1px solid #333;border-radius:4px}}
  h2{{border-bottom:1px solid #333;padding-bottom:6px;margin-top:40px}}
  h3{{font-size:13px;color:#aaa;margin:0 0 8px 0;text-transform:uppercase;letter-spacing:0.5px}}
</style></head><body>
<h1>Test 3 — Visual side-by-side · {escape(jb_id)}</h1>
<p>Comparación visual JetBrokers editor vs BigCapital proyecto-vista. Review manual.</p>
{''.join(rows_html)}
</body></html>"""
    html_path = out_dir / "test3-visual.html"
    html_path.write_text(html, encoding="utf-8")
    log.info(f"   ✓ HTML: {html_path}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
