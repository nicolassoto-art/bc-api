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


EXTRACT_JS = """(attr) => {
    let el;
    if (attr) {
        // BC: el contenedor del tab tiene data-content="..."
        el = document.querySelector(`[data-content="${attr}"]`);
    } else {
        // JB: el tab visible es mat-tab-body-active, mat-tab-body con class active, o card-body
        el = document.querySelector('mat-tab-body.mat-mdc-tab-body-active, .mat-tab-body-active, [class*="tab-body-active"]')
          || document.querySelector('mat-card mat-card-content, .card-body, .tab-pane.active')
          || document.body;
        // Si terminamos en body, intentar restringir excluyendo sidebar/nav
        if (el === document.body) {
            const main = document.querySelector('main, [role="main"], .main-content, app-projects-edit');
            if (main) el = main;
        }
    }
    if (!el) return null;
    const text = el.innerText || '';
    const html = el.innerHTML || '';
    const tbody = el.querySelectorAll('tbody');
    const rows = [];
    tbody.forEach(tb => {
        tb.querySelectorAll('tr').forEach(tr => {
            const cells = [...tr.querySelectorAll('td, th')].map(td => {
                // Si la celda tiene un input, leer el value; sino innerText
                const inp = td.querySelector('input, select');
                if (inp) {
                    if (inp.tagName === 'SELECT') return inp.options[inp.selectedIndex]?.text || inp.value;
                    return inp.value;
                }
                return (td.innerText || '').trim();
            });
            // Skip rows que son solo headers o vacías
            if (cells.some(c => c && c.length > 0)) rows.push(cells);
        });
    });
    // Form fields (label → value) — TODOS, incluyendo vacíos y 0
    const fields = [];
    el.querySelectorAll('input:not([type="hidden"]):not([type="search"]), select, textarea, mat-select').forEach(inp => {
        let v = inp.value || (inp.options ? inp.options[inp.selectedIndex]?.text : '') || '';
        if (inp.tagName === 'MAT-SELECT') {
            v = (inp.querySelector('.mat-mdc-select-value-text, span')?.innerText || '').trim();
        }
        // No skip por valor vacío — el LABEL importa también
        if (/^(seleccionar|seleccione)/i.test(v)) v = '';
        // Buscar label
        let label = '';
        if (inp.id) {
            const l = document.querySelector(`label[for="${inp.id}"]`);
            if (l) label = l.innerText.trim();
        }
        if (!label) {
            let p = inp.parentElement;
            for (let h = 0; h < 5 && p; h++) {
                const lbl = p.querySelector('label');
                if (lbl && !lbl.contains(inp)) { label = lbl.innerText.trim(); break; }
                p = p.parentElement;
            }
        }
        if (label) fields.push({label, value: (v||'').trim()});
    });

    // RENDER INTEGRITY CHECKS
    // Detección HTML raw: tags visibles como texto (<p>, <br>, &nbsp; literal)
    const text_lower = text.toLowerCase();
    const html_raw_detected = /<\\/?(p|br|div|span|strong|em|ul|li|h[1-6])[ >]/i.test(text)
        || /&(nbsp|amp|lt|gt|quot);/i.test(text);

    // Imágenes presentes en el tab (relevante para Modelos, Fotos)
    const imgs = [...el.querySelectorAll('img')]
        .filter(i => i.src && !i.src.startsWith('data:') && i.naturalWidth !== 0)
        .map(i => ({src: i.src, w: i.naturalWidth, h: i.naturalHeight}));
    const broken_imgs = [...el.querySelectorAll('img')]
        .filter(i => i.complete && i.naturalWidth === 0 && i.src && !i.src.startsWith('data:'))
        .length;

    // Empty states detectados
    const empty_msgs = [];
    el.querySelectorAll('.empty, .sp-empty, .no-data, [class*="empty"]').forEach(e => {
        const t = (e.innerText || '').trim();
        if (t) empty_msgs.push(t.slice(0, 80));
    });

    return {
        text_chars: text.length,
        rows_count: rows.length,
        rows,
        fields,
        html_raw_detected,
        imgs_count: imgs.length,
        broken_imgs,
        empty_msgs
    };
}"""


def normalize_val(s):
    """Normalize values for comparison."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    # Quitar separadores de miles y normalizar decimal
    repl = str.maketrans("áéíóúñ", "aeioun")
    s = s.translate(repl)
    s = " ".join(s.split())
    # "20,00" → "20", "200.000" → "200000"
    try:
        if "," in s:
            n = float(s.replace(".", "").replace(",", "."))
        elif s.count(".") >= 1 and all(len(p) == 3 for p in s.split(".")[1:]):
            n = float(s.replace(".", ""))
        else:
            n = float(s)
        s = str(int(n)) if n == int(n) else str(n)
    except Exception:
        pass
    return s


async def walk_bc_editor(page, jb_id: str, proyecto_id: str, bc_jwt: str, out_dir: Path) -> dict:
    """Abre BC editor, clickea cada tab, screenshot + extrae datos."""
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
            await page.evaluate("""(attr) => {
                const btn = document.querySelector(`[data-tab="${attr}"]`);
                if (btn) btn.click();
            }""", bc_tab_attr)
            await page.wait_for_timeout(1_500)
            png_path = out_dir / f"bc-tab-{bc_tab_attr}.png"
            await page.screenshot(path=str(png_path), full_page=True)
            info = await page.evaluate(EXTRACT_JS, bc_tab_attr)
            if info is None:
                results[bc_label] = {"error": "no content element"}
                continue
            info["screenshot"] = str(png_path.name)
            info["has_data"] = info.get("rows_count", 0) > 0 or len(info.get("fields", [])) > 0
            results[bc_label] = info
            log.info(f"   BC {bc_label}: rows={info['rows_count']} fields={len(info.get('fields',[]))}")
        except Exception as e:
            results[bc_label] = {"error": str(e)}
            log.warning(f"   BC {bc_label} error: {e}")
    return results


async def walk_jb_editor(imp: JBImporter, jb_id: str, out_dir: Path) -> dict:
    """Abre JB editor, clickea cada tab, screenshot + extrae datos."""
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
            info = await imp._page.evaluate(EXTRACT_JS, None)
            if info is None:
                results[bc_label] = {"error": "no content"}
                continue
            info["screenshot"] = str(png_path.name)
            info["has_data"] = info.get("rows_count", 0) > 0 or len(info.get("fields", [])) > 0
            results[bc_label] = info
            log.info(f"   JB {bc_label}: rows={info['rows_count']} fields={len(info.get('fields',[]))}")
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

    # Comparar tab por tab — DATA POR DATA, no solo has_data
    comparison = []
    fail_count = 0
    for bc_label, _, jb_label in TABS_TO_CHECK:
        bc = bc_results.get(bc_label, {})
        jb = jb_results.get(bc_label, {})
        jb_has = jb.get("has_data", False)
        bc_has = bc.get("has_data", False)

        # Comparar VALUES extraídos: rows (sets de celdas normalizadas) + fields (label/value)
        def collect_values(d):
            vals = set()
            for row in d.get("rows", []) or []:
                for cell in row:
                    n = normalize_val(cell)
                    if n and len(n) > 0:
                        vals.add(n)
            for f in d.get("fields", []) or []:
                n = normalize_val(f.get("value", ""))
                if n: vals.add(n)
            return vals

        # LEVEL 2: comparar LABELS (no solo values) — detecta campos faltantes en BC
        def collect_labels(d):
            labels = set()
            for f in d.get("fields", []) or []:
                lbl = (f.get("label") or "").strip().lower()
                lbl = " ".join(lbl.split())
                # Normalizar acentos
                repl = str.maketrans("áéíóúñ", "aeioun")
                lbl = lbl.translate(repl)
                if lbl and len(lbl) >= 3:
                    labels.add(lbl)
            return labels

        jb_vals = collect_values(jb)
        bc_vals = collect_values(bc)
        jb_labels = collect_labels(jb)
        bc_labels = collect_labels(bc)

        only_jb = jb_vals - bc_vals  # valores en JB que NO están en BC
        only_bc = bc_vals - jb_vals
        common = jb_vals & bc_vals
        labels_only_jb = jb_labels - bc_labels  # campos que JB pide y BC no tiene
        labels_common = jb_labels & bc_labels

        # LEVEL 3: render integrity — flags
        render_issues = []
        if bc.get("html_raw_detected") and not jb.get("html_raw_detected"):
            render_issues.append("BC muestra HTML como texto raw (etiquetas <p> o &nbsp; visibles)")
        if bc_label in ("Modelos", "Fotos"):
            jb_imgs = jb.get("imgs_count", 0)
            bc_imgs = bc.get("imgs_count", 0)
            if jb_imgs > 0 and bc_imgs == 0:
                render_issues.append(f"BC sin imágenes (JB tiene {jb_imgs})")
            elif jb_imgs > 0 and bc_imgs < jb_imgs * 0.5:
                render_issues.append(f"BC con pocas imágenes: {bc_imgs} vs JB {jb_imgs}")
        if bc.get("broken_imgs", 0) > 0:
            render_issues.append(f"BC tiene {bc['broken_imgs']} imágenes rotas")

        # Status
        if jb_label is None:
            status = "BC_ONLY" if bc_has else "BOTH_EMPTY"
        elif jb_has and not bc_has:
            status = "BC_VACIO_PERO_JB_TIENE"
            fail_count += 1
        elif jb_has and bc_has:
            # Ambos con data — chequear si los VALORES coinciden
            coverage = len(common) / max(len(jb_vals), 1)
            lbl_coverage = len(labels_common) / max(len(jb_labels), 1) if jb_labels else 1.0
            if coverage >= 0.8 and lbl_coverage >= 0.7 and not render_issues:
                status = f"AMBOS_OK (vals {coverage*100:.0f}% / labels {lbl_coverage*100:.0f}%)"
            else:
                bits = []
                if coverage < 0.8: bits.append(f"vals {coverage*100:.0f}%")
                if lbl_coverage < 0.7: bits.append(f"labels {lbl_coverage*100:.0f}%")
                if render_issues: bits.append("RENDER")
                status = f"MISMATCH ({', '.join(bits)})"
                fail_count += 1
        elif not jb_has and not bc_has:
            status = "AMBOS_VACIOS"
        else:
            status = "BC_TIENE_PERO_JB_NO"

        # Render issues fuera de comparación normal también cuentan como fail
        if render_issues and "MISMATCH" not in status and "VACIO" not in status:
            status += " · RENDER_ISSUE"
            fail_count += 1

        comparison.append({
            "tab": bc_label,
            "bc_rows_count": bc.get("rows_count"),
            "jb_rows_count": jb.get("rows_count"),
            "bc_fields": len(bc.get("fields", []) or []),
            "jb_fields": len(jb.get("fields", []) or []),
            "common_values": len(common),
            "only_jb_count": len(only_jb),
            "only_bc_count": len(only_bc),
            "only_jb_sample": sorted(only_jb)[:8],
            "only_bc_sample": sorted(only_bc)[:8],
            "labels_common": len(labels_common),
            "labels_only_jb_count": len(labels_only_jb),
            "labels_only_jb_sample": sorted(labels_only_jb)[:8],
            "render_issues": render_issues,
            "bc_imgs": bc.get("imgs_count", 0),
            "jb_imgs": jb.get("imgs_count", 0),
            "bc_html_raw": bc.get("html_raw_detected", False),
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

    # HTML side-by-side con diff data
    rows_html = ""
    for c in comparison:
        bg = "#1a4f1a" if c["status"].startswith("AMBOS_OK") else \
             "#7a1a1a" if "VACIO_PERO_JB" in c["status"] or "MISMATCH" in c["status"] else \
             "#333"
        bc_png = f"bc-tab-{[t[1] for t in TABS_TO_CHECK if t[0]==c['tab']][0]}.png"
        jb_png_label = [t[2] for t in TABS_TO_CHECK if t[0]==c['tab']][0]
        jb_png = f"jb-tab-{jb_png_label.lower()}.png" if jb_png_label else ""
        only_jb_html = ""
        if c.get("only_jb_count", 0) > 0:
            only_jb_html = f"<div style='font-size:11px;color:#ff9'><b>Valores en JB pero NO en BC ({c['only_jb_count']}):</b> {escape(', '.join(c.get('only_jb_sample', [])))}</div>"
        only_bc_html = ""
        if c.get("only_bc_count", 0) > 0:
            only_bc_html = f"<div style='font-size:11px;color:#9ef'><b>Valores en BC pero NO en JB ({c['only_bc_count']}):</b> {escape(', '.join(c.get('only_bc_sample', [])))}</div>"
        labels_html = ""
        if c.get("labels_only_jb_count", 0) > 0:
            labels_html = f"<div style='font-size:11px;color:#fc9'><b>LABELS en JB pero NO en BC ({c['labels_only_jb_count']}):</b> {escape(', '.join(c.get('labels_only_jb_sample', [])))}</div>"
        render_html = ""
        if c.get("render_issues"):
            render_html = "<div style='font-size:11px;color:#f88'><b>⚠ RENDER:</b> " + escape(' · '.join(c['render_issues'])) + "</div>"
        imgs_html = f"<div style='font-size:11px;color:#aaa'>imgs BC={c.get('bc_imgs',0)} JB={c.get('jb_imgs',0)}</div>" if (c.get('bc_imgs',0) or c.get('jb_imgs',0)) else ""
        rows_html += f"""
<tr style="background:{bg}">
  <td><b>{escape(c['tab'])}</b></td>
  <td>{escape(c['status'])}</td>
  <td>
    BC: rows={c['bc_rows_count']}, fields={c['bc_fields']} · JB: rows={c['jb_rows_count']}, fields={c['jb_fields']}<br>
    <span style='color:#7dc242'>Match values: {c['common_values']} · Match labels: {c.get('labels_common',0)}</span>
    {render_html}
    {labels_html}
    {only_jb_html}
    {only_bc_html}
    {imgs_html}
  </td>
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
