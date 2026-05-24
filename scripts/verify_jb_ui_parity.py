"""
verify_jb_ui_parity.py — Test 4: comparación UI campo-por-campo.

Abre BC vista + JB editor en paralelo (Playwright headless), extrae todos los
pares label/value de cada página, los normaliza y compara.

Reporta:
  imports/{jb_id}/verify/test4-ui-parity.csv     (machine-readable)
  imports/{jb_id}/verify/test4-ui-parity.html    (tabla coloreada)

Exit 0 si todos los campos críticos coinciden visualmente.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.services.jb_importer import JBImporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify4")


def normalize(s: str) -> str:
    """Normaliza valor para comparación: lowercase, sin acentos, sin espacios extra."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    repl = str.maketrans("áéíóúñ", "aeioun")
    s = s.translate(repl)
    # Quitar separadores: $, ., comas, espacios múltiples
    s = " ".join(s.split())
    # Casts numéricos: "20,00" == "20" == "20.00"
    try:
        n = float(s.replace(",", ".").replace("$", "").replace("uf", "").strip())
        s = str(int(n)) if n == int(n) else str(n)
    except Exception:
        pass
    return s


async def scrape_jb_general(imp: JBImporter, jb_id: str) -> list[dict]:
    """Scrape el tab General del editor JB. Retorna lista de {section, label, value}."""
    edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
    await imp._page.goto(edit_url, wait_until="networkidle", timeout=60_000)
    await imp._page.wait_for_timeout(4_000)
    pairs = await imp._page.evaluate("""() => {
        const out = [];
        const visible = el => {
            if (!el.offsetParent && el.tagName !== 'OPTION') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const findLabel = (el) => {
            if (el.id) {
                const l = document.querySelector(`label[for="${el.id}"]`);
                if (l) return l.innerText.trim();
            }
            let p = el.parentElement; let hops = 0;
            while (p && hops < 5) {
                const lbl = p.querySelector('label');
                if (lbl && !lbl.contains(el)) {
                    const t = lbl.innerText.trim();
                    if (t) return t;
                }
                const prev = p.previousElementSibling;
                if (prev && prev.tagName === 'LABEL') return prev.innerText.trim();
                p = p.parentElement; hops++;
            }
            return (el.placeholder || el.getAttribute?.('aria-label') || '').trim();
        };
        const findSection = (el) => {
            let node = el.parentElement;
            while (node && node !== document.body) {
                if (node.classList && node.classList.contains('card')) {
                    const h = node.querySelector(':scope > .card-header');
                    if (h) return h.innerText.trim().split('\\n')[0].trim();
                }
                node = node.parentElement;
            }
            return '';
        };
        const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
        inputs.forEach(el => {
            if (!visible(el)) return;
            let v = el.value;
            if (el.tagName === 'SELECT') v = el.options[el.selectedIndex]?.text || el.value;
            if (v == null || v === '' || v === '0') return;
            const label = findLabel(el);
            if (!label) return;
            out.push({section: findSection(el), label, value: v});
        });
        return out;
    }""")
    return pairs


async def scrape_bc_vista(proyecto_id: str, bc_api_jwt: str) -> list[dict]:
    """Scrape BC vista. Inyecta bc_api_token directo en localStorage para saltar login."""
    from playwright.async_api import async_playwright
    pairs = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=os.environ.get("HEADLESS", "1") != "0",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1200})
        page = await ctx.new_page()
        # Set JWT directo (auth-gate.js lo lee de localStorage.bc_api_token)
        await page.goto("https://herramientas.bigcapital.cl/", wait_until="domcontentloaded", timeout=30_000)
        await page.evaluate("(t) => localStorage.setItem('bc_api_token', t)", bc_api_jwt)
        await page.goto(
            f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto-vista.html?id={proyecto_id}",
            wait_until="networkidle", timeout=60_000,
        )
        await page.wait_for_timeout(4_000)
        # Extraer todos los pares de pv-kv tables (k/v rows)
        pairs = await page.evaluate("""() => {
            const out = [];
            // pv-kv tables: tabla con tr> td.pv-kv-k + td.pv-kv-v
            document.querySelectorAll('table.pv-kv tr').forEach(tr => {
                const k = tr.querySelector('.pv-kv-k')?.innerText.trim();
                const v = tr.querySelector('.pv-kv-v')?.innerText.trim();
                if (k && v && v !== '—') {
                    // Buscar el card padre para usar como "section"
                    const card = tr.closest('.pv-card');
                    const section = card?.querySelector('.pv-card-title')?.innerText.trim() || '';
                    out.push({section, label: k, value: v});
                }
            });
            // Loc info
            document.querySelectorAll('.pv-loc-row').forEach(row => {
                const k = row.querySelector('.pv-loc-k')?.innerText.trim();
                const v = row.querySelector('.pv-loc-v')?.innerText.trim();
                if (k && v) out.push({section: 'Ubicación', label: k, value: v});
            });
            return out;
        }""")
        await browser.close()
    return pairs


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
        jb_pairs = await scrape_jb_general(imp, jb_id)
        log.info(f"   JB: {len(jb_pairs)} pares")

        # Buscar proyecto_id
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error("Proyecto no encontrado")
            sys.exit(2)
        proyecto_id = proj["id"]

        bc_jwt = os.environ.get("BC_API_JWT", "")
        if not bc_jwt:
            log.warning("BC_API_JWT no disponible, omito scrape BC vista")
            bc_pairs = []
        else:
            bc_pairs = await scrape_bc_vista(proyecto_id, bc_jwt)
            log.info(f"   BC vista: {len(bc_pairs)} pares")
    finally:
        await imp.close()

    # Comparar
    # Crear índice por label normalizado
    def key_of(p): return f"{normalize(p['label'])}"
    jb_by_label = {}
    for p in jb_pairs:
        jb_by_label.setdefault(key_of(p), []).append(p)
    bc_by_label = {}
    for p in bc_pairs:
        bc_by_label.setdefault(key_of(p), []).append(p)

    all_labels = sorted(set(jb_by_label) | set(bc_by_label))
    rows = []
    for label in all_labels:
        jb_items = jb_by_label.get(label, [])
        bc_items = bc_by_label.get(label, [])
        # Si hay múltiples, intentar alinear por section
        for i, jb_p in enumerate(jb_items):
            bc_p = bc_items[i] if i < len(bc_items) else None
            jb_v = jb_p.get("value", "")
            bc_v = bc_p.get("value", "") if bc_p else ""
            n_jb = normalize(jb_v)
            n_bc = normalize(bc_v)
            if not bc_p:
                status = "MISSING_BC"
            elif not jb_v:
                status = "MISSING_JB"
            elif n_jb == n_bc:
                status = "MATCH"
            else:
                status = "MISMATCH"
            rows.append({
                "label": jb_p.get("label", "") or (bc_p and bc_p.get("label", "")),
                "jb_section": jb_p.get("section", ""),
                "jb_value": jb_v,
                "bc_section": bc_p.get("section", "") if bc_p else "",
                "bc_value": bc_v,
                "status": status,
            })
        # Labels que están en BC pero no en JB
        for j in range(len(jb_items), len(bc_items)):
            rows.append({
                "label": bc_items[j].get("label", ""),
                "jb_section": "", "jb_value": "",
                "bc_section": bc_items[j].get("section", ""),
                "bc_value": bc_items[j].get("value", ""),
                "status": "ONLY_BC",
            })

    # CSV
    csv_path = out_dir / "test4-ui-parity.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["label", "jb_section", "jb_value", "bc_section", "bc_value", "status"])
        w.writeheader()
        w.writerows(rows)

    # HTML
    color = {"MATCH": "#1a4f1a", "MISMATCH": "#7a1a1a", "MISSING_BC": "#7a1a1a", "MISSING_JB": "#5f4a00", "ONLY_BC": "#5f4a00"}
    summary = {
        "MATCH": sum(1 for r in rows if r["status"] == "MATCH"),
        "MISMATCH": sum(1 for r in rows if r["status"] == "MISMATCH"),
        "MISSING_BC": sum(1 for r in rows if r["status"] == "MISSING_BC"),
        "MISSING_JB": sum(1 for r in rows if r["status"] == "MISSING_JB"),
        "ONLY_BC": sum(1 for r in rows if r["status"] == "ONLY_BC"),
    }
    rows_html = ""
    for r in rows:
        bg = color.get(r["status"], "#333")
        rows_html += (
            f'<tr style="background:{bg}">'
            f'<td>{escape(r["status"])}</td>'
            f'<td>{escape(r["label"])}</td>'
            f'<td>{escape(r["jb_section"])}</td>'
            f'<td>{escape(r["jb_value"][:80])}</td>'
            f'<td>{escape(r["bc_section"])}</td>'
            f'<td>{escape(r["bc_value"][:80])}</td>'
            f'</tr>'
        )
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Test 4 UI parity {escape(jb_id)}</title>
<style>
  body{{font-family:-apple-system;background:#111;color:#eee;padding:20px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#222;padding:8px;text-align:left}}
  td{{padding:6px 8px;border-bottom:1px solid #2a2a2a;vertical-align:top}}
  .summary span{{display:inline-block;margin-right:14px;padding:4px 8px;border-radius:4px}}
</style></head><body>
<h1>Test 4 — UI Parity (BC vista vs JB editor) · {escape(jb_id)}</h1>
<div class="summary">
  <span style="background:#1a4f1a">✓ MATCH: {summary['MATCH']}</span>
  <span style="background:#7a1a1a">✗ MISMATCH: {summary['MISMATCH']}</span>
  <span style="background:#7a1a1a">⚠ MISSING_BC: {summary['MISSING_BC']}</span>
  <span style="background:#5f4a00">○ MISSING_JB: {summary['MISSING_JB']}</span>
  <span style="background:#5f4a00">+ ONLY_BC: {summary['ONLY_BC']}</span>
</div>
<table>
<thead><tr><th>Status</th><th>Label</th><th>JB Section</th><th>JB Value</th><th>BC Section</th><th>BC Value</th></tr></thead>
<tbody>{rows_html}</tbody>
</table></body></html>"""
    (out_dir / "test4-ui-parity.html").write_text(html, encoding="utf-8")
    log.info(f"   ✓ HTML: {out_dir / 'test4-ui-parity.html'}")
    log.info(f"   📊 {summary}")
    # Pass si MISMATCH + MISSING_BC == 0
    critical_fail = summary["MISMATCH"] + summary["MISSING_BC"]
    return critical_fail == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
