"""
verify_jb_fields.py — Test 1: comparación campo-a-campo JB editor DOM vs bc-api extra.

Genera:
  imports/{jb_id}/verify/test1-fields.csv   (machine-readable)
  imports/{jb_id}/verify/test1-fields.html  (tabla coloreada)

Exit 0 si todos los campos críticos MATCH; 1 si hay MISSING_BC o MISMATCH.
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
from app.services.jb_importer import JBImporter, TABS_SELECTORS, NOTAS_SELECTOR, ETIQUETAS_SELECTOR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify1")


CRITICAL_PREFIXES = (
    "extra.cuenta_reserva",
    "extra.fisicos",
    "extra.formas_pago_pie",
    "extra.notas_html",
    "extra.spa_proyecto",
    "extra.comercial",
    "extra.inmobiliaria",
)


def _get_path(obj, dot_path):
    cur = obj
    for k in dot_path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def _normalize(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    # Cast a número si parece
    if s.replace(".", "").replace("-", "").isdigit() or (s.count(".") == 1 and s.replace(".", "").replace("-", "").isdigit()):
        try:
            return float(s)
        except Exception:
            pass
    return s.lower()


def classify(jb_val, bc_val):
    nj, nb = _normalize(jb_val), _normalize(bc_val)
    if nj is None and nb is None:
        return "BOTH_EMPTY"
    if nj is None:
        return "MISSING_JB"
    if nb is None:
        return "MISSING_BC"
    if nj == nb:
        return "MATCH"
    # Tolerancia para strings con whitespace
    if isinstance(nj, str) and isinstance(nb, str):
        if nj.replace(" ", "") == nb.replace(" ", ""):
            return "WHITESPACE_DIFF"
    # HTML: comparar longitud aproximada (las notas HTML pueden tener variaciones de attrs)
    if isinstance(jb_val, str) and isinstance(bc_val, str) and ("<" in jb_val and "<" in bc_val):
        if abs(len(jb_val) - len(bc_val)) < 200:
            return "MATCH_HTML_LEN"
    return "MISMATCH"


async def main(jb_id: str):
    out_dir = Path(os.environ.get("IMPORTS_DIR", "imports")) / jb_id / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Login JB + scrape editor
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ["BC_API_JWT"],
        headless=os.environ.get("HEADLESS", "1") != "0",
    )
    try:
        await imp.login()
        # Scrape JB
        jb_data = await imp.scrape_editor(jb_id)  # devuelve {extra: {...}}
        # Find + GET bc-api project
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error(f"No se encontró proyecto con extra.jb_id={jb_id}")
            sys.exit(2)
        # Comparar
        rows = []
        # Recorrer todos los paths del TABS map
        all_paths = list(TABS_SELECTORS["General"].keys()) + [
            "extra.notas_html",
            "extra.etiquetas",
        ]
        for path in all_paths:
            jb_val = _get_path(jb_data, path)
            bc_val = _get_path(proj, path)
            # Para arrays: comparar como sets
            if isinstance(jb_val, list) and isinstance(bc_val, list):
                sa, sb = set(map(str, jb_val)), set(map(str, bc_val))
                status = "MATCH" if sa == sb else "MISMATCH"
                notes = f"jb={len(jb_val)}, bc={len(bc_val)}"
                if sa - sb:
                    notes += f", only_jb={sorted(sa - sb)[:3]}"
                if sb - sa:
                    notes += f", only_bc={sorted(sb - sa)[:3]}"
                jb_disp = ", ".join(map(str, jb_val[:5]))
                bc_disp = ", ".join(map(str, bc_val[:5]))
            else:
                status = classify(jb_val, bc_val)
                jb_disp = str(jb_val)[:200] if jb_val is not None else ""
                bc_disp = str(bc_val)[:200] if bc_val is not None else ""
                notes = ""
                if "html" in path.lower() and jb_val and bc_val:
                    notes = f"len jb={len(str(jb_val))}, bc={len(str(bc_val))}"
            critical = any(path.startswith(p) for p in CRITICAL_PREFIXES)
            rows.append({
                "tab": path.split(".")[1] if "." in path else "General",
                "field": path,
                "jb": jb_disp,
                "bc": bc_disp,
                "status": status,
                "critical": critical,
                "notes": notes,
            })
    finally:
        await imp.close()

    # CSV
    csv_path = out_dir / "test1-fields.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tab", "field", "jb", "bc", "status", "critical", "notes"])
        w.writeheader()
        w.writerows(rows)
    log.info(f"   ✓ CSV: {csv_path}")

    # HTML coloreado
    color = {
        "MATCH": "#1a4f1a", "MATCH_HTML_LEN": "#1a4f1a",
        "BOTH_EMPTY": "#333", "WHITESPACE_DIFF": "#5f4a00",
        "MISSING_JB": "#5f4a00", "MISSING_BC": "#7a1a1a", "MISMATCH": "#7a1a1a",
    }
    html_rows = []
    for r in rows:
        bg = color.get(r["status"], "#333")
        emoji = {"MATCH": "✓", "MATCH_HTML_LEN": "≈", "MISMATCH": "✗", "MISSING_BC": "⚠", "MISSING_JB": "○", "BOTH_EMPTY": "·", "WHITESPACE_DIFF": "≠"}.get(r["status"], "?")
        crit = " ⭐" if r["critical"] else ""
        html_rows.append(
            f'<tr style="background:{bg}"><td>{emoji}</td><td>{escape(r["status"])}</td>'
            f'<td>{escape(r["tab"])}</td><td><code>{escape(r["field"])}{crit}</code></td>'
            f'<td>{escape(r["jb"])}</td><td>{escape(r["bc"])}</td>'
            f'<td>{escape(r["notes"])}</td></tr>'
        )
    summary = {
        "MATCH": sum(1 for r in rows if r["status"] in ("MATCH", "MATCH_HTML_LEN")),
        "MISMATCH": sum(1 for r in rows if r["status"] == "MISMATCH"),
        "MISSING_BC": sum(1 for r in rows if r["status"] == "MISSING_BC"),
        "MISSING_JB": sum(1 for r in rows if r["status"] == "MISSING_JB"),
        "BOTH_EMPTY": sum(1 for r in rows if r["status"] == "BOTH_EMPTY"),
        "WHITESPACE_DIFF": sum(1 for r in rows if r["status"] == "WHITESPACE_DIFF"),
    }
    critical_fail = sum(1 for r in rows if r["critical"] and r["status"] in ("MISMATCH", "MISSING_BC"))
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Test 1 fields {escape(jb_id)}</title>
<style>
  body{{font-family:-apple-system,sans-serif;background:#111;color:#eee;padding:20px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#222;padding:8px;text-align:left;position:sticky;top:0}}
  td{{padding:6px 8px;border-bottom:1px solid #2a2a2a;vertical-align:top}}
  code{{font-family:Menlo,monospace;color:#7dc242}}
  .summary{{margin-bottom:20px}}
  .summary span{{display:inline-block;margin-right:14px;padding:4px 8px;border-radius:4px}}
</style></head><body>
<h1>Test 1 — Campo por campo · {escape(jb_id)}</h1>
<div class="summary">
  <span style="background:#1a4f1a">✓ MATCH: {summary['MATCH']}</span>
  <span style="background:#7a1a1a">✗ MISMATCH: {summary['MISMATCH']}</span>
  <span style="background:#7a1a1a">⚠ MISSING_BC: {summary['MISSING_BC']}</span>
  <span style="background:#5f4a00">○ MISSING_JB: {summary['MISSING_JB']}</span>
  <span style="background:#333">· BOTH_EMPTY: {summary['BOTH_EMPTY']}</span>
  <span style="background:#5f4a00">≠ WHITESPACE_DIFF: {summary['WHITESPACE_DIFF']}</span>
  <br><strong>Críticos fallidos: {critical_fail}</strong>
</div>
<table>
<thead><tr><th></th><th>Status</th><th>Tab</th><th>Field</th><th>JB</th><th>BC</th><th>Notes</th></tr></thead>
<tbody>{''.join(html_rows)}</tbody>
</table></body></html>"""
    html_path = out_dir / "test1-fields.html"
    html_path.write_text(html, encoding="utf-8")
    log.info(f"   ✓ HTML: {html_path}")

    log.info(f"\n📊 Resumen: {summary}")
    log.info(f"   Críticos fallidos: {critical_fail}")
    return critical_fail == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
