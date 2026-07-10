"""
find_jb_project.py — Busca un proyecto por NOMBRE en el catálogo JetBrokers (login real,
navegación manual), para casos donde el proyecto no aparece en el listado filtrado
estándar (list_jb_projects.py aplica Disponible=Sí + JetStock=No por defecto).

A diferencia de list_jb_projects.py, este script:
  1. Intenta usar el buscador de texto de la tabla (si existe) para acotar sin paginar todo.
  2. Si no hay buscador, quita los chips de filtro visibles (Disponible/JetStock/etc.)
     para no excluir proyectos no-disponibles, y pagina TODO el catálogo.
  3. Filtra client-side por substring (case/tilde-insensitive) contra el nombre buscado.

Uso:
  python3 scripts/find_jb_project.py "Laguna Centro"

Env requeridas: JETBROKERS_EMAIL, JETBROKERS_PASS
Salida: imprime matches (jb_id, nombre, inmobiliaria) + guarda
  imports/_find/<query-slug>/matches.json y screenshot del catálogo.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jb_importer import JBImporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("find_jb_project")

CATALOG_URLS = [
    "https://app.jetbrokers.io/catalog/projects",
    "https://app.jetbrokers.io/catalog",
    "https://app.jetbrokers.io/projects/catalog",
    "https://app.jetbrokers.io/projects",
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.strip().lower())


async def _goto_catalog(imp: JBImporter) -> bool:
    for url in CATALOG_URLS:
        try:
            await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
            await imp._page.wait_for_timeout(3_000)
            await imp._dismiss_popups()
            content = await imp._page.evaluate("() => document.body.innerText.toLowerCase()")
            if "proyectos" in content or "stock" in content or "inmobiliaria" in content:
                log.info(f"   ✓ Cargó {url}")
                return True
        except Exception as e:
            log.debug(f"   {url} → {e}")
    return False


async def _try_search_box(imp: JBImporter, query: str) -> bool:
    """Intenta escribir en un input de búsqueda de la tabla. True si encontró uno."""
    selectors = [
        'input[placeholder*="Buscar" i]',
        'input[placeholder*="Search" i]',
        'input[type="search"]',
        'input[aria-label*="buscar" i]',
        'input[aria-label*="search" i]',
    ]
    for sel in selectors:
        try:
            loc = imp._page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=3_000)
                await loc.fill(query, timeout=3_000)
                await imp._page.wait_for_timeout(2_000)
                log.info(f"   ✓ Buscador encontrado ({sel}), tipeado: {query!r}")
                return True
        except Exception:
            continue
    log.info("   (sin buscador de texto visible en la tabla)")
    return False


async def _quitar_filtros(imp: JBImporter) -> None:
    """Cierra chips de filtro (ej. 'Disponible: Sí', 'JetStock: No') para no excluir
    proyectos no-disponibles del listado."""
    try:
        removed = await imp._page.evaluate("""() => {
            let n = 0;
            document.querySelectorAll('mat-chip, mat-chip-row, .mat-chip').forEach(chip => {
                const closeBtn = chip.querySelector('[matChipRemove], .mat-chip-remove, [aria-label*="remove" i]');
                if (closeBtn) { try { closeBtn.click(); n++; } catch(e){} }
            });
            return n;
        }""")
        if removed:
            log.info(f"   ✓ {removed} chip(s) de filtro removido(s)")
            await imp._page.wait_for_timeout(1_500)
    except Exception as e:
        log.debug(f"   quitar filtros → {e}")


async def _extraer_filas(imp: JBImporter) -> list[dict]:
    return await imp._page.evaluate(r"""() => {
        const out = [];
        const links = document.querySelectorAll('a[href*="/projects/edit/"], a[href*="/projects/view/"], a[href*="/projects/details/"]');
        const seen = new Set();
        links.forEach(a => {
            const m = a.href.match(/\/projects\/(?:edit|view|details)\/([A-Za-z0-9_-]{6,12})/);
            if (!m) return;
            const jb_id = m[1];
            if (seen.has(jb_id)) return;
            seen.add(jb_id);
            let row = a.closest('tr, [role="row"], .row, .mat-row, [class*="row"]');
            let cells = [];
            if (row) {
                cells = [...row.querySelectorAll('td, [role="cell"], [role="gridcell"], .cell, [class*="cell"]')]
                    .map(c => (c.innerText||'').trim());
            }
            if (cells.length < 2) {
                let p = a.parentElement;
                for (let i=0; i<6 && p; i++) {
                    const siblings = [...p.children].map(c => (c.innerText||'').trim()).filter(Boolean);
                    if (siblings.length >= 4) { cells = siblings; break; }
                    p = p.parentElement;
                }
            }
            const nonEmpty = cells.filter(c => c && c.length > 0);
            out.push({
                jb_id: jb_id,
                nombre: nonEmpty[0] || (a.innerText||'').trim(),
                inmobiliaria: nonEmpty[1] || '',
                comuna: nonEmpty[2] || '',
                _cells: cells.slice(0, 12),
            });
        });
        return out;
    }""")


async def _paginar_y_juntar(imp: JBImporter, max_pages: int = 40) -> list[dict]:
    all_items: list[dict] = []
    seen = set()
    for page_n in range(max_pages):
        await imp._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await imp._page.wait_for_timeout(700)
        page_items = await _extraer_filas(imp)
        new_count = 0
        for it in page_items:
            if it["jb_id"] not in seen:
                seen.add(it["jb_id"])
                all_items.append(it)
                new_count += 1
        log.info(f"   página {page_n + 1}: +{new_count} (total {len(all_items)})")
        if new_count == 0 and page_n > 0:
            break
        clicked = await imp._page.evaluate(r"""() => {
            const sels = [
                'button[aria-label*="next" i]:not([disabled])',
                'button[aria-label*="siguiente" i]:not([disabled])',
                '.pagination-next:not(.disabled)',
                'li.next:not(.disabled) a',
            ];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent) { (el.closest('button, a, li') || el).click(); return true; }
            }
            const all = [...document.querySelectorAll('button, a, li')];
            const next = all.find(b => /^(siguiente|next|›|»|>)$/i.test((b.innerText||'').trim()) && !b.disabled && !b.classList.contains('disabled'));
            if (next) { next.click(); return true; }
            return false;
        }""")
        if not clicked:
            break
        await imp._page.wait_for_timeout(1_200)
    return all_items


async def buscar(query: str, headless: bool = True) -> list[dict]:
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT") or "placeholder",  # no se usa bc-api acá
        imports_dir=Path(os.environ.get("IMPORTS_DIR", "imports")),
        headless=headless,
    )
    try:
        await imp.login()
        if not await _goto_catalog(imp):
            raise RuntimeError("No se pudo cargar el catálogo JB")

        # Vista Tabla
        try:
            await imp._page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button, a, span')];
                const tabla = btns.find(b => (b.innerText||'').trim().toLowerCase() === 'tabla');
                if (tabla) tabla.click();
            }""")
            await imp._page.wait_for_timeout(2_000)
        except Exception:
            pass

        out_dir = imp.imports_dir / "_find" / re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        out_dir.mkdir(parents=True, exist_ok=True)

        found_via_search = await _try_search_box(imp, query)
        await imp._page.screenshot(path=str(out_dir / "catalogo.png"), full_page=True)

        if found_via_search:
            items = await _extraer_filas(imp)
            q_norm = _norm(query)
            matches = [it for it in items if q_norm in _norm(it.get("nombre", ""))]
            if matches:
                (out_dir / "matches.json").write_text(json.dumps(matches, indent=2, ensure_ascii=False))
                return matches
            log.info("   buscador no filtró nada útil, cae a paginar todo el catálogo")

        # Fallback: quitar filtros + paginar TODO y filtrar client-side
        await _quitar_filtros(imp)
        all_items = await _paginar_y_juntar(imp)
        (out_dir / "catalogo_completo.json").write_text(json.dumps(all_items, indent=2, ensure_ascii=False))
        log.info(f"   catálogo completo (sin filtro): {len(all_items)} proyectos")

        q_norm = _norm(query)
        matches = [it for it in all_items if q_norm in _norm(it.get("nombre", ""))]
        (out_dir / "matches.json").write_text(json.dumps(matches, indent=2, ensure_ascii=False))
        return matches
    finally:
        await imp.close()


def main():
    parser = argparse.ArgumentParser(description="Busca un proyecto por nombre en el catálogo JetBrokers")
    parser.add_argument("query", help='Texto a buscar, ej: "Laguna Centro"')
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    matches = asyncio.run(buscar(args.query, headless=not args.headed))
    print(json.dumps(matches, indent=2, ensure_ascii=False))
    if not matches:
        log.error(f"✗ Sin matches para {args.query!r}")
        sys.exit(1)
    log.info(f"✓ {len(matches)} match(es) para {args.query!r}")


if __name__ == "__main__":
    main()
