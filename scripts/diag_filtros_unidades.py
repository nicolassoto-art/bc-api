"""Inspecciona el estado de la tab Unidades: filtros activos, contadores,
botones ocultos, y screenshots antes/después del scroll."""
from __future__ import annotations
import asyncio, os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter


async def main():
    jb_id = os.environ.get("JB_ID", "1kvflc3m")
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""), headless=True,
    )
    try:
        await imp.login()
        await imp._page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}", wait_until="networkidle", timeout=60_000)
        await imp._page.wait_for_timeout(3500)
        await imp._dismiss_popups()
        await imp._click_tab("Unidades")
        await imp._page.wait_for_timeout(4000)

        # Screenshot inicial
        await imp._page.screenshot(path="/tmp/unidades-1-inicial.png", full_page=True)

        # Inspeccionar filtros, inputs, checkboxes activos
        info = await imp._page.evaluate(r"""() => {
            const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
            const out = {};
            // 1) Todos los inputs/checkboxes en la tab con su estado
            out.inputs = [...scope.querySelectorAll('input, mat-checkbox, mat-slide-toggle')].slice(0,30).map(el => ({
                type: el.tagName.toLowerCase() + (el.type ? ':' + el.type : ''),
                checked: el.checked || el.getAttribute('aria-checked') === 'true' || el.classList.contains('mat-checkbox-checked') || el.classList.contains('mat-mdc-checkbox-checked'),
                value: (el.value || '').slice(0,40),
                aria_label: el.getAttribute('aria-label') || '',
                placeholder: el.placeholder || '',
                ngreflectName: el.getAttribute('ng-reflect-name') || '',
                // Buscar label asociado
                near_text: (() => {
                    let p = el.parentElement;
                    for (let i = 0; i < 4 && p; i++) {
                        const lbl = p.querySelector('label, mat-label, .mat-form-field-label');
                        if (lbl) return (lbl.innerText || '').trim().slice(0,40);
                        p = p.parentElement;
                    }
                    return '';
                })(),
            }));
            // 2) Chips/filtros activos visibles
            out.chips = [...scope.querySelectorAll('mat-chip, .mat-chip, .chip, .filter-chip, .ng-value')].slice(0,20).map(c => (c.innerText||'').trim()).filter(Boolean);
            // 3) Selects activos
            out.selects = [...scope.querySelectorAll('mat-select, select')].map(s => ({
                value: (s.innerText || s.value || '').trim().slice(0,40),
                aria: s.getAttribute('aria-label') || '',
            }));
            // 4) Contadores visibles en cualquier lado (ej "57 de 250", "Mostrando 30")
            const txt = scope.innerText || '';
            out.counter_matches = (txt.match(/\d+\s*(de|of|\/)\s*\d+/g) || []).slice(0,5);
            // 5) Botones con texto que puede ser "Ver más", "Cargar todo", etc
            out.botones_relevantes = [...scope.querySelectorAll('button, a')].slice(0,40).map(b => (b.innerText||'').trim()).filter(t => t && t.length < 40 && /buscar|filtrar|aplicar|cargar|mostrar|ver m|todo|all|reset|limpiar|borrar|exportar|descargar|excel/i.test(t));
            // 6) Filas actuales de la tabla
            const trs = scope.querySelectorAll('table tbody tr');
            out.rows_now = trs.length;
            // 7) Si hay un select con "Disponible / No Disponible / Todos" - el típico filtro de stock
            out.disp_select = (() => {
                const sels = [...scope.querySelectorAll('mat-select, .ng-select')];
                for (const s of sels) {
                    const t = (s.innerText || '').trim().toLowerCase();
                    if (/disponible|todos|todas/.test(t)) return t.slice(0,80);
                }
                return null;
            })();
            return out;
        }""")
        print(json.dumps(info, ensure_ascii=False, indent=2)[:4000])

        # Intentar HACER CLICK en cualquier botón "Buscar"/"Filtrar"/"Aplicar"
        print("\n=== Intentando click 'Buscar' (lupa) ===")
        clicked = await imp._page.evaluate(r"""() => {
            // Buscar icon lupa o botón Buscar/Filtrar
            const cands = [...document.querySelectorAll('button, a, mat-icon')];
            for (const el of cands) {
                if (!el.offsetParent) continue;
                const t = (el.innerText || '').trim().toLowerCase();
                const fonticon = (el.getAttribute('fonticon') || '').toLowerCase();
                if (t === 'buscar' || t === 'filtrar' || t === 'aplicar' || fonticon === 'search' || fonticon === 'manage_search') {
                    let p = el;
                    for (let i=0; i<5 && p; i++) {
                        if (p.tagName === 'BUTTON' || p.tagName === 'A') { p.click(); return t || fonticon; }
                        p = p.parentElement;
                    }
                    el.click();
                    return t || fonticon;
                }
            }
            return null;
        }""")
        print(f"  clicked: {clicked}")
        await imp._page.wait_for_timeout(3000)
        # Re-contar filas tras click
        n2 = await imp._page.evaluate("() => document.querySelectorAll('mat-tab-body.mat-mdc-tab-body-active table tbody tr').length")
        print(f"  filas tras click: {n2}")
        await imp._page.screenshot(path="/tmp/unidades-2-tras-click.png", full_page=True)

        # Si hay un select "Disponible", intentar cambiarlo a "Todos"
        print("\n=== Intentando cambiar filtro Disponible → Todos ===")
        changed = await imp._page.evaluate(r"""async () => {
            const sels = [...document.querySelectorAll('mat-select')];
            for (const s of sels) {
                const t = (s.innerText || '').trim().toLowerCase();
                if (!/disponible|stock|estado/.test(t)) continue;
                s.click();
                await new Promise(r => setTimeout(r, 600));
                // Buscar opción "Todos" en el panel desplegado
                const opts = [...document.querySelectorAll('mat-option')];
                for (const o of opts) {
                    const ot = (o.innerText || '').trim().toLowerCase();
                    if (/^(todos|todas|all|sin filtrar)$/.test(ot) || ot === '') {
                        o.click();
                        return 'changed: ' + ot;
                    }
                }
                // Cerrar
                document.body.click();
            }
            return null;
        }""")
        print(f"  {changed}")
        await imp._page.wait_for_timeout(2500)
        n3 = await imp._page.evaluate("() => document.querySelectorAll('mat-tab-body.mat-mdc-tab-body-active table tbody tr').length")
        print(f"  filas tras cambio: {n3}")
        await imp._page.screenshot(path="/tmp/unidades-3-todos.png", full_page=True)

    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
