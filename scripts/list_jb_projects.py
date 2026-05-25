"""
list_jb_projects.py — Lista TODOS los proyectos del broker en JB.

Output: JSON con [{jb_id, nombre, comuna, ...}] de cada proyecto disponible.
Usado para el batch import de los ~80 proyectos.

Estrategias en orden:
  1. JB API: GET /projects (si existe)
  2. JB page scrape: navegar a /projects y extraer del DOM
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.jb_importer import JBImporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("list_jb")


async def list_via_api(imp: JBImporter) -> list[dict]:
    """Intenta varios endpoints API conocidos de JB."""
    candidates = [
        "/projects",
        "/projects/all",
        f"/projects/owner/{imp.org_id}" if imp.org_id else None,
        f"/store/owner/{imp.org_id}/projects" if imp.org_id else None,
        "/api/projects",
    ]
    candidates = [c for c in candidates if c]
    async with imp._jb_httpx() as cli:
        for path in candidates:
            try:
                r = await cli.get(path)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else (data.get("data") or data.get("projects") or data.get("elements") or [])
                    if items:
                        log.info(f"   ✓ API {path}: {len(items)} proyectos")
                        return items
            except Exception as e:
                log.debug(f"   {path} → {e}")
    return []


async def list_via_dom(imp: JBImporter) -> list[dict]:
    """Scrape DOM del Catálogo (vista Tabla) en JB.
    Aplica filtro Disponible=Sí + JetStock=No (= stock propio BigCapital).
    Itera todas las páginas via paginación.
    """
    # Probar varias URLs del catálogo
    urls = [
        "https://app.jetbrokers.io/catalog/projects",
        "https://app.jetbrokers.io/catalog",
        "https://app.jetbrokers.io/projects/catalog",
        "https://app.jetbrokers.io/projects",  # fallback
    ]
    for url in urls:
        try:
            await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
            await imp._page.wait_for_timeout(3_000)
            await imp._dismiss_popups()
            # Verificar que aterrizó en algo sensible
            content = await imp._page.evaluate("() => document.body.innerText.toLowerCase()")
            if "proyectos" in content or "stock" in content or "inmobiliaria" in content:
                log.info(f"   ✓ Cargó {url}")
                break
        except Exception as e:
            log.debug(f"   {url} → {e}")
    else:
        log.warning("   No se pudo cargar catálogo")
        return []

    # Intentar cambiar a vista "Tabla" (en lugar de Listado/Mapa)
    try:
        await imp._page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button, a, span')];
            const tabla = btns.find(b => (b.innerText||'').trim().toLowerCase() === 'tabla');
            if (tabla) tabla.click();
        }""")
        await imp._page.wait_for_timeout(2_000)
    except Exception:
        pass

    # Verificar filtros activos. Si JetStock filter no aplicado, agregar.
    # JB filter chips son spans con texto "JetStock: No"
    has_jetstock_filter = await imp._page.evaluate("""() => {
        return document.body.innerText.toLowerCase().includes('jetstock');
    }""")
    log.info(f"   Filtros aplicados (JetStock visible): {has_jetstock_filter}")

    # Cambiar page size si hay dropdown
    try:
        await imp._page.evaluate("""() => {
            document.querySelectorAll('select').forEach(s => {
                const opts = [...s.options];
                const big = opts.reverse().find(o => /^(100|200|500|todos|all)$/i.test(o.text.trim()) || (parseInt(o.text)||0) >= 100);
                if (big) { s.value = big.value; s.dispatchEvent(new Event('change', {bubbles:true})); }
            });
        }""")
        await imp._page.wait_for_timeout(1_500)
    except Exception:
        pass

    # Paginar — iterar mientras haya botón "next"
    all_items: list[dict] = []
    seen = set()
    for page_n in range(20):  # safety cap 20 pages
        # Scroll para cargar
        await imp._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await imp._page.wait_for_timeout(800)

        page_items = await imp._page.evaluate(r"""() => {
            const out = [];
            // Links a /projects/edit/{id}
            document.querySelectorAll('a[href*="/projects/edit/"], a[href*="/projects/view/"], a[href*="/projects/details/"]').forEach(a => {
                const m = a.href.match(/\/projects\/(?:edit|view|details)\/([A-Za-z0-9_-]{6,12})/);
                if (m) {
                    const tr = a.closest('tr, .card, mat-card');
                    let nombre = '';
                    let comuna = '';
                    let inmo = '';
                    if (tr) {
                        const cells = [...tr.querySelectorAll('td, .cell')].map(c => (c.innerText||'').trim()).filter(Boolean);
                        // Heuristic: Inmobiliaria | Nombre | Comuna | ...
                        if (cells.length >= 3) {
                            inmo = cells[0];
                            nombre = cells[1];
                            comuna = cells[2];
                        }
                    }
                    if (!nombre) nombre = (a.innerText||'').trim().split('\n')[0];
                    out.push({jb_id: m[1], nombre, comuna, inmobiliaria: inmo});
                }
            });
            return out;
        }""")
        new_count = 0
        for it in page_items:
            if it["jb_id"] not in seen:
                seen.add(it["jb_id"])
                all_items.append(it)
                new_count += 1
        log.info(f"   página {page_n+1}: +{new_count} (total {len(all_items)})")
        if new_count == 0:
            break
        # Click next
        clicked = await imp._page.evaluate(r"""() => {
            const sels = [
                'button[aria-label*="next" i]:not([disabled])',
                'button[aria-label*="siguiente" i]:not([disabled])',
                '.pagination-next:not(.disabled)',
                'li.next:not(.disabled) a',
                'fa-icon[data-icon="chevron-right"]',
            ];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent) {
                    const c = el.closest('button, a, li') || el;
                    c.click();
                    return true;
                }
            }
            // Buscar por texto
            const all = [...document.querySelectorAll('button, a, li')];
            const next = all.find(b => /^(siguiente|next|›|»|>)$/i.test((b.innerText||'').trim()) && !b.disabled && !b.classList.contains('disabled'));
            if (next) { next.click(); return true; }
            return false;
        }""")
        if not clicked:
            break
        await imp._page.wait_for_timeout(1_200)

    log.info(f"   ✓ DOM: {len(all_items)} proyectos totales")
    return all_items


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="jb_projects.json")
    args = parser.parse_args()

    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""),
        headless=os.environ.get("HEADLESS", "1") != "0",
    )

    try:
        await imp.login()
        log.info("🔍 Listando proyectos JB...")

        items = await list_via_api(imp)
        if not items:
            log.info("   API no disponible, scrape DOM...")
            items = await list_via_dom(imp)

        # Normalizar: extraer jb_id, nombre
        normalized = []
        for it in items:
            jb_id = (
                it.get("jb_id")
                or it.get("id")
                or it.get("_id")
                or it.get("project_id")
            )
            if not jb_id:
                continue
            normalized.append({
                "jb_id": str(jb_id),
                "nombre": it.get("nombre") or it.get("name") or it.get("title") or "",
                "comuna": (it.get("location") or {}).get("commune") or it.get("comuna") or "",
            })

        # Dedup
        seen = set()
        unique = []
        for it in normalized:
            if it["jb_id"] not in seen:
                seen.add(it["jb_id"])
                unique.append(it)

        log.info(f"\n📋 Total proyectos únicos: {len(unique)}")
        for it in unique[:10]:
            log.info(f"  {it['jb_id']:12s} {it['nombre'][:50]}")
        if len(unique) > 10:
            log.info(f"  ... +{len(unique)-10} más")

        Path(args.out).write_text(json.dumps(unique, indent=2, ensure_ascii=False))
        log.info(f"\n✓ Guardado en {args.out}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
