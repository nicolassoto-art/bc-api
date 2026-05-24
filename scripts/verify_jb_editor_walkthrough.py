"""
verify_jb_editor_walkthrough.py — Test 5: simulador humano clickeando tabs.

Abre BC editor + JB editor, hace click en CADA tab y verifica visualmente
si tiene contenido. Detecta empty states ("Aún no hay X", tablas sin rows,
inputs vacíos en formularios completos, etc).

Output:
  imports/{jb_id}/verify/test5-walkthrough.json
  imports/{jb_id}/verify/test5-walkthrough.html  (side-by-side + screenshots)
  imports/{jb_id}/verify/bc-tab-{name}.png       (screenshot por tab BC)
  imports/{jb_id}/verify/jb-tab-{name}.png       (screenshot por tab JB)

Exit 0 si todas las tabs con data en JB también tienen data en BC.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jb_importer import JBImporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("walkthrough")

# Mapeo BC tab → JB tab (algunos no son 1:1)
TABS_TO_CHECK = [
    # (bc_tab_name, bc_data_tab_attr, jb_label)
    ("General",         "general",      "General"),
    ("Documentos",      "documentos",   "Documentos"),
    ("Modelos",         "modelos",      "Modelos"),
    ("Unidades",        "unidades",     None),  # JB no tiene tab dedicado (van por Excel)
    ("Bodegas",         "bodegas",      "Bodegas"),
    ("Estacionamientos","estac",        "Estacionamientos"),
    ("Packs",           "packs",        "Packs"),
    ("Notas",           "notas",        "Notas"),
    ("Stock",           "stock",        "Stock"),
]

EMPTY_PATTERNS = [
    r"a[uú]n no hay",
    r"sin\s+(unidades|modelos|bodegas|estacion|documentos|fotos|notas|datos)",
    r"^—$",
    r"vac[ií]o",
    r"sin datos",
]


async def walk_bc_editor(page, jb_id: str, proyecto_id: str, bc_jwt: str, out_dir: Path) -> dict:
    """Abre BC editor, clickea cada tab, screenshot + content detection."""
    # Auth via localStorage
    await page.goto("https://herramientas.bigcapital.cl/", wait_until="domcontentloaded", timeout=30_000)
    await page.evaluate("(t) => localStorage.setItem('bc_api_token', t)", bc_jwt)
    await page.goto(
        f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto.html?id={proyecto_id}",
        wait_until="networkidle", timeout=60_000,
    )
    await page.wait_for_timeout(4_000)

    results = {}
    for bc_label, bc_tab_attr, _ in TABS_TO_CHECK:
        try:
            # Click en el tab
            await page.evaluate(f"""(attr) => {{
                const btn = document.querySelector(`[data-tab="${{attr}}"]`);
                if (btn) btn.click();
            }}""", bc_tab_attr)
            await page.wait_for_timeout(1_500)

            # Screenshot
            png_path = out_dir / f"bc-tab-{bc_tab_attr}.png"
            await page.screenshot(path=str(png_path), full_page=True)

            # Detectar content
            content_info = await page.evaluate(f"""(attr) => {{
                const el = document.querySelector(`[data-content="${{attr}}"]`);
                if (!el) return {{ visible: false }};
                const text = el.innerText.toLowerCase();
                const empty_msg = /a[uú]n no hay|sin\\s+(unidades|modelos|bodegas|estacion|documentos|fotos|notas|datos)|vac[ií]o|sin datos/i.test(text);
                const tbody = el.querySelector('tbody');
                const rows = tbody ? tbody.querySelectorAll('tr').length : 0;
                // Inputs poblados (value no vacío)
                const inputs = [...el.querySelectorAll('input:not([type="hidden"])')].filter(i => i.value && i.value.length > 0).length;
                const total_inputs = el.querySelectorAll('input:not([type="hidden"])').length;
                return {{
                    visible: true,
                    text_chars: text.length,
                    has_empty_msg: empty_msg,
                    rows,
                    inputs_filled: inputs,
                    inputs_total: total_inputs,
                    sample_text: text.substring(0, 200),
                }};
            }}""", bc_tab_attr)

            results[bc_label] = {
                "screenshot": str(png_path.name),
                **content_info,
                "has_data": not content_info.get("has_empty_msg", True) and (content_info.get("rows", 0) > 0 or content_info.get("inputs_filled", 0) > 0 or content_info.get("text_chars", 0) > 100),
            }
            log.info(f"   BC {bc_label}: rows={content_info.get('rows')} inputs_filled={content_info.get('inputs_filled')}/{content_info.get('inputs_total')} empty_msg={content_info.get('has_empty_msg')}")
        except Exception as e:
            results[bc_label] = {"error": str(e)}
            log.warning(f"   BC {bc_label} error: {e}")

    return results


async def walk_jb_editor(imp: JBImporter, jb_id: str, out_dir: Path) -> dict:
    """Abre JB editor, clickea cada tab, screenshot + content detection."""
    edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
    await imp._page.goto(edit_url, wait_until="networkidle", timeout=60_000)
    await imp._page.wait_for_timeout(4_000)

    results = {}
    for bc_label, _, jb_label in TABS_TO_CHECK:
        if not jb_label:
            results[bc_label] = {"skipped": "no JB equivalent"}
            continue
        try:
            await imp._click_tab(jb_label)
            await imp._page.wait_for_timeout(2_000)
            png_path = out_dir / f"jb-tab-{jb_label.lower()}.png"
            await imp._page.screenshot(path=str(png_path), full_page=True)
            # Detectar content
            content_info = await imp._page.evaluate("""() => {
                const body = document.body.innerText.toLowerCase();
                const text = document.body.innerText;
                const tbody = document.querySelectorAll('tbody');
                let rows = 0;
                tbody.forEach(tb => { rows += tb.querySelectorAll('tr').length; });
                const inputs = [...document.querySelectorAll('input:not([type="hidden"]):not([type="search"])')].filter(i => i.value && i.value.length > 0).length;
                return { text_chars: text.length, rows, inputs_filled: inputs };
            }""")
            results[bc_label] = {
                "screenshot": str(png_path.name),
                **content_info,
                "has_data": content_info.get("rows", 0) > 0 or content_info.get("inputs_filled", 0) > 0,
            }
            log.info(f"   JB {bc_label}: rows={content_info.get('rows')} inputs_filled={content_info.get('inputs_filled')}")
        except Exception as e:
            results[bc_label] = {"error": str(e)}
            log.warning(f"   JB {bc_label} error: {e}")
    return results


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
        # Buscar proyecto_id
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error("Proyecto no encontrado en bc-api")
            sys.exit(2)
        proyecto_id = proj["id"]

        # Walk JB editor con el page existente
        jb_results = await walk_jb_editor(imp, jb_id, out_dir)

        # Walk BC editor con browser separado
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=os.environ.get("HEADLESS", "1") != "0",
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = await browser.new_context(viewport={"width": 1440, "height": 1200})
            page = await ctx.new_page()
            bc_results = await walk_bc_editor(page, jb_id, proyecto_id, os.environ["BC_API_JWT"], out_dir)
            await browser.close()
    finally:
        await imp.close()

    # Comparar tab por tab: si JB tiene data, BC también debería
    comparison = []
    fail_count = 0
    for bc_label, _, jb_label in TABS_TO_CHECK:
        bc = bc_results.get(bc_label, {})
        jb = jb_results.get(bc_label, {})
        jb_has = jb.get("has_data", False)
        bc_has = bc.get("has_data", False)
        if jb_label is None:
            status = "BC_ONLY" if bc_has else "BOTH_EMPTY"
        elif jb_has and not bc_has:
            status = "BC_VACIO_PERO_JB_TIENE"
            fail_count += 1
        elif jb_has and bc_has:
            status = "AMBOS_OK"
        elif not jb_has and not bc_has:
            status = "AMBOS_VACIOS"
        else:
            status = "BC_TIENE_PERO_JB_NO"
        comparison.append({
            "tab": bc_label,
            "bc_rows": bc.get("rows"),
            "bc_inputs_filled": bc.get("inputs_filled"),
            "jb_rows": jb.get("rows"),
            "jb_inputs_filled": jb.get("inputs_filled"),
            "status": status,
        })

    summary = {
        "jb_id": jb_id,
        "proyecto_id": proyecto_id,
        "comparison": comparison,
        "fail_count": fail_count,
        "overall": "PASS" if fail_count == 0 else "FAIL",
    }
    (out_dir / "test5-walkthrough.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    # HTML side-by-side
    rows_html = ""
    for c in comparison:
        bg = {"AMBOS_OK": "#1a4f1a", "AMBOS_VACIOS": "#333", "BC_VACIO_PERO_JB_TIENE": "#7a1a1a", "BC_ONLY": "#5f4a00", "BC_TIENE_PERO_JB_NO": "#5f4a00"}.get(c["status"], "#333")
        bc_png = f"bc-tab-{[t[1] for t in TABS_TO_CHECK if t[0]==c['tab']][0]}.png"
        jb_png_label = [t[2] for t in TABS_TO_CHECK if t[0]==c['tab']][0]
        jb_png = f"jb-tab-{jb_png_label.lower()}.png" if jb_png_label else ""
        rows_html += f"""
<tr style="background:{bg}">
  <td><b>{escape(c['tab'])}</b></td>
  <td>{escape(c['status'])}</td>
  <td>BC: rows={c['bc_rows']}, inputs={c['bc_inputs_filled']}<br>JB: rows={c['jb_rows']}, inputs={c['jb_inputs_filled']}</td>
</tr>
<tr>
  <td colspan="3">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div><h4>BC editor</h4><img src="{escape(bc_png)}" style="max-width:100%;border:1px solid #333"></div>
      <div><h4>JB editor</h4>{'<img src="' + escape(jb_png) + '" style="max-width:100%;border:1px solid #333">' if jb_png else '<em>n/a</em>'}</div>
    </div>
  </td>
</tr>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Test 5 walkthrough {escape(jb_id)}</title>
<style>body{{font-family:-apple-system;background:#111;color:#eee;padding:20px}}table{{width:100%;border-collapse:collapse}}td{{padding:8px;border-bottom:1px solid #333;vertical-align:top}}</style>
</head><body>
<h1>Test 5 — Editor walkthrough (BC vs JB)</h1>
<p>Overall: <strong>{summary['overall']}</strong> · Tabs con BC vacío pero JB con data: <strong>{fail_count}</strong></p>
<table>{rows_html}</table>
</body></html>"""
    (out_dir / "test5-walkthrough.html").write_text(html, encoding="utf-8")
    log.info(f"\n📊 Walkthrough: {summary['overall']} ({fail_count} tabs con BC vacío)")
    return fail_count == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
