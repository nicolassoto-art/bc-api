"""
verify_dom_diff.py — Test 6: Comparación DOM directa JB ↔ BC editor.

Determinístico, sin AI Vision, sin screenshots, sin cropping.
Para cada tab del editor:
  1. Extrae del DOM de JB: {labels: {nombre→valor}, rows: [[celdas]], headers: [cols]}
  2. Extrae lo mismo del DOM de BC editor
  3. Compara con set diff y reporta:
     - labels solo en JB / solo en BC / con valores distintos
     - filas con data en JB no presentes en BC (y al revés)
     - columnas distintas en tablas

Output:
  imports/{jb_id}/verify/test6-dom-diff.json
  imports/{jb_id}/verify/test6-dom-diff.html
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
log = logging.getLogger("dom-diff")


# Tabs a comparar
TABS_TO_CHECK = [
    # (bc_data_tab_attr, jb_tab_label)
    ("general",     "General"),
    ("documentos",  "Documentos"),
    ("modelos",     "Modelos"),
    ("bodegas",     "Bodegas"),
    ("estac",       "Estacionamientos"),
    ("packs",       "Packs"),
    ("notas",       "Notas"),
    ("stock",       "Stock"),
]


def _norm_label(s: str) -> str:
    """Normaliza label: lowercase, sin tildes, sin parénteses ni asteriscos,
    sin sufijos de unidad (%, UF, m²) ni hints (Enter para añadir, etc)."""
    if not s:
        return ""
    s = str(s).strip().lower()
    repl = str.maketrans("áéíóúñ", "aeioun")
    s = s.translate(repl)
    # Eliminar parenthesis con contenido: "Pie (%)" → "pie", "Etiquetas (Enter...)" → "etiquetas"
    s = re.sub(r"\([^)]*\)", "", s)
    # Eliminar asterisco obligatorio
    s = s.replace("*", "")
    # Eliminar sufijos comunes
    for suf in (" uf", " clp", " %", " m²", " m2", " m^2"):
        if s.endswith(suf): s = s[:-len(suf)]
    # Aliases comunes (JB ↔ BC)
    aliases = {
        "estac. totales": "estacionamientos totales",
        "estac totales": "estacionamientos totales",
        "estac.": "estacionamientos",
        "ano de entrega": "ano entrega",
        "ano entrega": "ano entrega",
        "fecha de entrega": "fecha entrega",
        "solicita preaprobacion": "solicita preaprobacion",
        "cuoton inicial": "cuoton inicial",
        "cuoton final": "cuoton final",
    }
    s = " ".join(s.split())
    return aliases.get(s, s)


def _norm_value(s) -> str:
    """Normaliza un valor para comparación: trim, lowercase, sin signos."""
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    # Quitar sufijos comunes (UF, %, $) y comas/puntos para números
    sl = s.lower()
    repl = str.maketrans("áéíóúñ", "aeioun")
    sl = sl.translate(repl)
    # Intentar parsear como número
    try:
        n = float(sl.replace("$", "").replace("uf", "").replace("%", "").replace(".", "").replace(",", "."))
        if n == int(n):
            return str(int(n))
        return str(n)
    except Exception:
        return " ".join(sl.split())


EXTRACT_JS = """(scopeSelector) => {
    // Encontrar el contenedor del tab
    let scope = null;
    if (scopeSelector) {
        scope = document.querySelector(scopeSelector);
    }
    if (!scope) {
        scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active, .mat-tab-body-active, [class*="tab-body-active"]')
             || document.querySelector('main, [role="main"], app-projects-edit')
             || document.body;
    }

    // 1) Labels y values: cada input/select/textarea/ng-select con su label cercano
    const visible = (el) => {
        if (!el.offsetParent && el.tagName !== 'OPTION') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const findLabel = (el) => {
        if (el.id) {
            const l = document.querySelector(`label[for="${el.id}"]`);
            if (l && l.innerText) return l.innerText.trim();
        }
        let p = el.parentElement;
        for (let h = 0; h < 6 && p; h++) {
            const lbl = p.querySelector('label, .col-form-label');
            if (lbl && !lbl.contains(el)) {
                const t = lbl.innerText.trim();
                if (t) return t;
            }
            p = p.parentElement;
        }
        return '';
    };
    const findSection = (el) => {
        let node = el.parentElement;
        while (node && node !== document.body) {
            if (node.classList && (node.classList.contains('card') || node.classList.contains('sp-section') || node.classList.contains('panel'))) {
                const h = node.querySelector(':scope > .card-header, :scope > .sp-section-title, :scope > header, :scope > h3, :scope > h4');
                if (h) {
                    const t = h.innerText.trim().split('\\n')[0].trim();
                    if (t) return t;
                }
            }
            node = node.parentElement;
        }
        return '';
    };

    const fields = [];
    const inputs = scope.querySelectorAll('input:not([type="hidden"]):not([type="search"]):not([type="checkbox"]), select, textarea, mat-select, ng-select, .ng-select, [role="combobox"]');
    inputs.forEach(el => {
        if (!visible(el)) return;
        let v = '';
        if (el.tagName === 'SELECT') {
            v = el.options[el.selectedIndex]?.text || el.value || '';
        } else if (el.tagName === 'NG-SELECT' || el.tagName === 'MAT-SELECT' || el.classList.contains('ng-select') || el.getAttribute('role') === 'combobox') {
            const isMulti = el.classList && el.classList.contains('ng-select-multiple');
            if (isMulti) {
                v = [...el.querySelectorAll('.ng-value-label')].map(s => (s.innerText||'').trim()).filter(t => t && t !== '×').join(', ');
            } else {
                const ng = el.querySelector('.ng-value:not(.ng-placeholder)');
                if (ng) {
                    const spans = [...ng.querySelectorAll('span')].filter(s => s.innerText && !s.classList.contains('ng-value-icon') && !s.classList.contains('ng-clear') && !s.classList.contains('ng-arrow'));
                    v = (spans[spans.length-1]?.innerText || ng.innerText || '').trim();
                } else {
                    v = (el.querySelector('.mat-mdc-select-value-text')?.innerText || '').trim();
                }
            }
        } else {
            v = (el.value || '').trim();
        }
        const label = findLabel(el);
        if (!label) return;
        if (/^(seleccion|elegir|placeholder|×)$/i.test(v)) v = '';
        const section = findSection(el);
        fields.push({label, section, value: v});
    });

    // Etiquetas/chips: ng-select-multiple
    const chips = {};
    scope.querySelectorAll('.form-group, .sp-field').forEach(g => {
        const lbl = g.querySelector('label, .col-form-label, .sp-field-label');
        if (!lbl) return;
        const t = (lbl.innerText || '').trim();
        if (!/etiqueta/i.test(t)) return;
        const tags = [...g.querySelectorAll('.ng-value-label, .sp-chip')].map(s => (s.innerText||'').trim()).filter(x => x && x !== '×');
        if (tags.length) chips[t] = tags;
    });

    // 2) Tablas: extraer headers + rows
    const tables = [];
    scope.querySelectorAll('table').forEach(tbl => {
        const rect = tbl.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const headers = [...tbl.querySelectorAll('thead th')].map(th => (th.innerText || '').trim()).filter(t => t);
        const rows = [];
        tbl.querySelectorAll('tbody tr').forEach(tr => {
            const cells = [...tr.querySelectorAll('td')].map(td => {
                const inp = td.querySelector('input, select, textarea');
                if (inp) {
                    if (inp.tagName === 'SELECT') return inp.options[inp.selectedIndex]?.text || inp.value || '';
                    return inp.value || '';
                }
                // Para iconos: detectar check/close
                const html = td.innerHTML || '';
                if (/check|done|sp-pill-green/i.test(html) && !/close|clear/i.test(html)) return 'sí';
                if (/close|clear|sp-pill-(grey|red)/i.test(html)) return 'no';
                return (td.innerText || '').trim();
            });
            if (cells.some(c => c)) rows.push(cells);
        });
        if (headers.length || rows.length) tables.push({headers, rows});
    });

    // 3) Empty state detection
    const emptyMsg = (() => {
        const empty = scope.querySelector('.sp-empty, .empty, [class*="empty"]');
        return empty ? empty.innerText.trim().slice(0, 80) : '';
    })();

    return {fields, chips, tables, emptyMsg, _scope_text_len: (scope.innerText || '').length};
}"""


def load_jb_data_from_import(jb_id: str) -> dict:
    """Carga los datos JB del scrape exhaustivo del importer.
    Mucho más confiable que re-scrapear JB en vivo (Angular asincrónico, popups, etc).
    Lee:
      _debug_scrape/labels_found.json     → fields globales (todos los tabs)
      _debug_scrape/tab-modelos_rows.json → rows del tab Modelos
      _debug_scrape/tab-bodegas_rows.json → rows tab Bodegas
      _debug_scrape/tab-estac_rows.json   → rows tab Estac
    """
    base = Path(os.environ.get("IMPORTS_DIR", "imports")) / jb_id / "_debug_scrape"
    fields_all = []
    chips_all = {}
    if (base / "labels_found.json").exists():
        fields_all = json.loads((base / "labels_found.json").read_text())

    # Por tab: filtrar fields por section
    def fields_for(section_patterns):
        """fields cuya section matchea alguno de los patrones (case-insensitive)."""
        result = []
        for f in fields_all:
            s = (f.get("section") or "").lower()
            if any(p in s for p in section_patterns) or section_patterns == ["__all__"]:
                result.append({"label": f["label"], "section": f.get("section", ""), "value": f.get("value", "")})
        return result

    # General fields: secciones General, Condiciones Comerciales, Formas pagar, Reserva, Inmobiliaria, SPA, Portada
    general_sections = ["general", "condiciones", "formas", "reserva", "inmobiliaria", "spa", "portada"]
    general_fields = fields_for(general_sections)

    # Etiquetas chips
    etiquetas = next((f for f in fields_all if (f.get("label", "") or "").lower().startswith("etiquetas")), None)
    if etiquetas:
        chips_all["Etiquetas"] = [s.strip() for s in (etiquetas.get("value", "") or "").split(",") if s.strip()]
    # Si no, intentar leer de la BD (extra.etiquetas)
    # Skip: el diff comparará vs BC chips, BC chips se leen del DOM

    def table_rows(filename):
        p = base / filename
        if not p.exists(): return []
        rows_data = json.loads(p.read_text())
        # rows_data es lista de {cells, links, imgs, ...}
        return [{"cells": r.get("cells", [])} for r in rows_data if r.get("cells")]

    modelos_rows = table_rows("tab-modelos_rows.json")
    bodegas_rows = table_rows("tab-bodegas_rows.json")
    estac_rows = table_rows("tab-estac_rows.json")

    # Build JB data per tab
    return {
        "general":     {"fields": general_fields, "chips": chips_all, "tables": []},
        "documentos":  {"fields": [], "chips": {}, "tables": []},  # Documentos se compara contra imagenes en BC
        "modelos":     {"fields": [], "chips": {}, "tables": [
            {"headers": ["Nombre", "Cotiza Bodega", "Cotiza Estac.", "Cotiza Pack", "Plano"], "rows": [r["cells"] for r in modelos_rows]}
        ]},
        "bodegas":     {"fields": [], "chips": {}, "tables": [
            {"headers": ["Número", "Precio UF", "Superficie m²", "Disponible"],
             "rows": [r["cells"] for r in bodegas_rows]}
        ]},
        "estac":       {"fields": [], "chips": {}, "tables": [
            {"headers": ["Número", "Precio UF", "Nivel", "Tipo", "Disponible"],
             "rows": [r["cells"] for r in estac_rows]}
        ]},
        "packs":       {"fields": [], "chips": {}, "tables": []},
        "notas":       {"fields": fields_for(["notas"]), "chips": {}, "tables": []},
        "stock":       {"fields": fields_for(["stock"]), "chips": {}, "tables": []},
    }


async def scrape_jb_tab(imp: JBImporter, tab_label: str) -> dict:
    """[DEPRECATED en favor de load_jb_data_from_import]"""
    return {}


async def scrape_bc_tab(page, bc_tab_attr: str) -> dict:
    """Click un tab en BC editor y extraer estructura DOM."""
    try:
        await page.evaluate("""(attr) => {
            const btn = document.querySelector(`[data-tab="${attr}"]`);
            if (btn) btn.click();
        }""", bc_tab_attr)
        await page.wait_for_timeout(1_200)
        result = await page.evaluate(EXTRACT_JS, f'[data-content="{bc_tab_attr}"]')
        return result or {}
    except Exception as e:
        log.warning(f"   BC {bc_tab_attr}: {e}")
        return {"error": str(e)}


def diff_tab(jb: dict, bc: dict) -> dict:
    """Compara estructura JB vs BC. Retorna {labels_only_jb, labels_only_bc, value_diffs, ...}"""
    if jb.get("error") or bc.get("error"):
        return {"error": f"jb={jb.get('error')} bc={bc.get('error')}"}

    # Labels: dedup por label. ng-select expone 4 elementos por label (1 real + 3 wrappers
    # vacíos). Quedarnos con el PRIMER valor no-vacío.
    def collect_labels(fields):
        out = {}
        for f in fields or []:
            if not f.get("label"): continue
            nl = _norm_label(f["label"])
            if not nl: continue
            v = f.get("value", "") or ""
            existing = out.get(nl, "")
            # Solo sobreescribir si current es vacío y new tiene algo
            if not existing and v:
                out[nl] = v
            elif nl not in out:
                out[nl] = v
        return out

    jb_labels = collect_labels(jb.get("fields"))
    bc_labels = collect_labels(bc.get("fields"))

    only_jb_labels = sorted(set(jb_labels.keys()) - set(bc_labels.keys()))
    only_bc_labels = sorted(set(bc_labels.keys()) - set(jb_labels.keys()))

    # Para labels en ambos: comparar valores
    value_diffs = []
    common = set(jb_labels.keys()) & set(bc_labels.keys())
    for lbl in sorted(common):
        jv = _norm_value(jb_labels[lbl])
        bv = _norm_value(bc_labels[lbl])
        if jv != bv:
            value_diffs.append({"label": lbl, "jb": jb_labels[lbl][:60], "bc": bc_labels[lbl][:60]})

    # Tablas: usar el primer cell NO-VACÍO + NO-CHECKBOX como key.
    # JB tiene checkbox en col 0 ("on"/""); BC no.
    NOISE_CELLS = {"", "on", "off", "true", "false", "—", "-", "sí", "no", "si"}
    def row_key(row):
        for cell in row or []:
            v = _norm_value(cell)
            # Skip checkbox cells y bool noise
            if v and v not in NOISE_CELLS and not v.startswith("//"):
                # Skip si parece URL/path
                if "/" in v and len(v) > 20:
                    continue
                return v
        return None

    def collect_table_keys(tables):
        keys = set()
        for t in tables or []:
            for row in t.get("rows") or []:
                k = row_key(row)
                if k: keys.add(k)
        return keys

    jb_table_keys = collect_table_keys(jb.get("tables"))
    bc_table_keys = collect_table_keys(bc.get("tables"))
    table_rows_only_jb = sorted(jb_table_keys - bc_table_keys)
    table_rows_only_bc = sorted(bc_table_keys - jb_table_keys)

    # Headers de tablas
    def collect_headers(tables):
        h = []
        for t in tables or []:
            h.extend([_norm_label(x) for x in (t.get("headers") or []) if x])
        return h

    jb_headers = collect_headers(jb.get("tables"))
    bc_headers = collect_headers(bc.get("tables"))
    headers_only_jb = sorted(set(jb_headers) - set(bc_headers))
    headers_only_bc = sorted(set(bc_headers) - set(jb_headers))

    # Chips: agrupar por label normalizado para mergear "Etiquetas" y "Etiquetas (Enter para añadir)"
    def merge_chips(chips_dict):
        out = {}
        for k, vals in (chips_dict or {}).items():
            nk = _norm_label(k)
            out.setdefault(nk, set()).update(_norm_value(x).replace(" ×", "").replace("×", "").strip() for x in vals)
        return {k: {v for v in s if v} for k, s in out.items()}

    jb_chips = merge_chips(jb.get("chips") or {})
    bc_chips = merge_chips(bc.get("chips") or {})
    chips_diff = []
    all_chip_keys = set(jb_chips.keys()) | set(bc_chips.keys())
    for k in all_chip_keys:
        jb_set = jb_chips.get(k, set())
        bc_set = bc_chips.get(k, set())
        if jb_set != bc_set:
            chips_diff.append({"label": k, "only_jb": sorted(jb_set - bc_set), "only_bc": sorted(bc_set - jb_set)})

    total_diffs = (
        len(only_jb_labels) + len(only_bc_labels) + len(value_diffs)
        + len(table_rows_only_jb) + len(table_rows_only_bc)
        + len(headers_only_jb) + len(headers_only_bc)
        + len(chips_diff)
    )

    return {
        "only_jb_labels": only_jb_labels,
        "only_bc_labels": only_bc_labels,
        "value_diffs": value_diffs,
        "table_rows_only_jb": table_rows_only_jb,
        "table_rows_only_bc": table_rows_only_bc,
        "headers_only_jb": headers_only_jb,
        "headers_only_bc": headers_only_bc,
        "chips_diff": chips_diff,
        "common_labels": len(common),
        "total_diffs": total_diffs,
        "passed": total_diffs == 0,
    }


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

    results = {}
    try:
        await imp.login()
        proj = await imp.find_proyecto_by_jb_id(jb_id)
        if not proj:
            log.error("Proyecto no encontrado")
            sys.exit(2)
        proyecto_id = proj["id"]

        # JB data viene del scrape exhaustivo que el importer ya hizo
        log.info("📡 Cargando JB data del _debug_scrape/...")
        jb_data = load_jb_data_from_import(jb_id)
        log.info(f"   ✓ JB: General={len(jb_data['general']['fields'])} fields, "
                 f"Modelos={len(jb_data['modelos']['tables'][0]['rows']) if jb_data['modelos']['tables'] else 0} rows, "
                 f"Bodegas={len(jb_data['bodegas']['tables'][0]['rows']) if jb_data['bodegas']['tables'] else 0} rows, "
                 f"Estac={len(jb_data['estac']['tables'][0]['rows']) if jb_data['estac']['tables'] else 0} rows")

        # Now BC editor with separate browser
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=os.environ.get("HEADLESS", "1") != "0",
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 1200},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="es-CL",
            )
            page = await ctx.new_page()
            await page.goto("https://herramientas.bigcapital.cl/", wait_until="domcontentloaded", timeout=30_000)
            await page.evaluate("(t) => localStorage.setItem('bc_api_token', t)", os.environ["BC_API_JWT"])
            await page.goto(
                f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto.html?id={proyecto_id}",
                wait_until="networkidle", timeout=60_000,
            )
            await page.wait_for_timeout(5_000)
            # Wait for CDN challenge
            for _ in range(12):
                txt = (await page.evaluate("() => document.body.innerText || ''")).lower()
                if "please wait" in txt or "verificando" in txt:
                    await page.wait_for_timeout(5_000)
                else:
                    break

            bc_data = {}
            for bc_attr, _ in TABS_TO_CHECK:
                log.info(f"📡 BC tab: {bc_attr}")
                bc_data[bc_attr] = await scrape_bc_tab(page, bc_attr)
            await browser.close()
    finally:
        await imp.close()

    # Diff per tab
    comparison = []
    fail_count = 0
    total_diffs_all = 0
    for bc_attr, jb_label in TABS_TO_CHECK:
        d = diff_tab(jb_data.get(bc_attr, {}), bc_data.get(bc_attr, {}))
        d["tab"] = jb_label
        d["bc_attr"] = bc_attr
        comparison.append(d)
        if not d.get("passed"):
            fail_count += 1
            total_diffs_all += d.get("total_diffs", 0)

    summary = {
        "jb_id": jb_id,
        "proyecto_id": proyecto_id,
        "comparison": comparison,
        "fail_count": fail_count,
        "total_diffs": total_diffs_all,
        "tabs_ok": len(TABS_TO_CHECK) - fail_count,
        "tabs_total": len(TABS_TO_CHECK),
        "paridad_pct": int((len(TABS_TO_CHECK) - fail_count) * 100 / len(TABS_TO_CHECK)),
        "overall_passed": fail_count == 0,
    }
    (out_dir / "test6-dom-diff.json").write_text(json.dumps({**summary, "_raw_jb": jb_data, "_raw_bc": bc_data}, indent=2, ensure_ascii=False))

    # HTML report
    rows_html = ""
    for c in comparison:
        bg = "#1a4f1a" if c.get("passed") else "#5a1a1a"
        details = ""
        if c.get("error"):
            details = f"<div style='color:#f88'>ERROR: {escape(c['error'])}</div>"
        else:
            blocks = []
            if c.get("only_jb_labels"):
                blocks.append(f"<div><b style='color:#ff9'>Labels solo en JB ({len(c['only_jb_labels'])}):</b> {escape(', '.join(c['only_jb_labels'][:8]))}</div>")
            if c.get("only_bc_labels"):
                blocks.append(f"<div><b style='color:#9fe'>Labels solo en BC ({len(c['only_bc_labels'])}):</b> {escape(', '.join(c['only_bc_labels'][:8]))}</div>")
            if c.get("value_diffs"):
                vd = "; ".join(f"{x['label']}: JB='{x['jb']}' / BC='{x['bc']}'" for x in c['value_diffs'][:6])
                blocks.append(f"<div><b style='color:#f99'>Valores distintos ({len(c['value_diffs'])}):</b> {escape(vd)}</div>")
            if c.get("headers_only_jb") or c.get("headers_only_bc"):
                blocks.append(f"<div><b>Headers JB-only:</b> {escape(', '.join(c['headers_only_jb']))} | <b>BC-only:</b> {escape(', '.join(c['headers_only_bc']))}</div>")
            if c.get("table_rows_only_jb"):
                blocks.append(f"<div><b>Filas tabla solo en JB ({len(c['table_rows_only_jb'])}):</b> {escape(', '.join(c['table_rows_only_jb'][:10]))}</div>")
            if c.get("table_rows_only_bc"):
                blocks.append(f"<div><b>Filas tabla solo en BC ({len(c['table_rows_only_bc'])}):</b> {escape(', '.join(c['table_rows_only_bc'][:10]))}</div>")
            if c.get("chips_diff"):
                for cd in c['chips_diff']:
                    blocks.append(f"<div><b>Chips '{escape(cd['label'])}':</b> JB-only={escape(', '.join(cd['only_jb']))} BC-only={escape(', '.join(cd['only_bc']))}</div>")
            details = "".join(blocks) or "<div style='color:#7dc242'>✓ Sin diferencias</div>"
        rows_html += f"""
<tr style='background:{bg}'>
  <td><b>{escape(c['tab'])}</b></td>
  <td>{'✅ OK' if c.get('passed') else '❌ MISMATCH'}</td>
  <td>{c.get('total_diffs','?')}</td>
  <td>{c.get('common_labels','?')}</td>
  <td>{details}</td>
</tr>"""

    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>DOM diff {escape(jb_id)}</title>
<style>body{{font-family:-apple-system;background:#111;color:#eee;padding:20px;font-size:13px}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
td,th{{padding:10px;border-bottom:1px solid #333;vertical-align:top;text-align:left}}
.summary{{font-size:18px;padding:14px;background:#222;border-radius:6px;margin-bottom:10px}}
</style></head><body>
<h1>Test 6 — DOM diff JB ↔ BC editor</h1>
<div class='summary'>Paridad: <b>{summary['tabs_ok']}/{summary['tabs_total']}</b> ({summary['paridad_pct']}%) · Diffs totales: {total_diffs_all}</div>
<table><thead><tr><th>Tab</th><th>Status</th><th>Diffs</th><th>Labels matches</th><th>Detalle</th></tr></thead>{rows_html}</table>
</body></html>"""
    (out_dir / "test6-dom-diff.html").write_text(html, encoding="utf-8")

    log.info(f"\n📊 DOM diff: paridad {summary['paridad_pct']}% ({summary['tabs_ok']}/{summary['tabs_total']}) · diffs totales: {total_diffs_all}")
    for c in comparison:
        if not c.get("passed"):
            log.info(f"   ❌ {c['tab']}: {c.get('total_diffs',0)} diffs")
    return summary['overall_passed']


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jb_id")
    args = parser.parse_args()
    ok = asyncio.run(main(args.jb_id))
    sys.exit(0 if ok else 1)
