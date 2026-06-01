"""Vuelca los controles de paginación de la tab Unidades de un proyecto JB."""
from __future__ import annotations
import asyncio, os, sys
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
    xhrs = []
    async def on_resp(resp):
        try:
            u = resp.url
            if "/api/" not in u or resp.status != 200: return
            if "json" not in resp.headers.get("content-type","").lower(): return
            j = await resp.json()
            items = j if isinstance(j, list) else (j.get("data") or j.get("elements") or j.get("content") or [])
            n = len(items) if isinstance(items, list) else 0
            ks = sorted(items[0].keys()) if (isinstance(items, list) and items and isinstance(items[0], dict)) else []
            xhrs.append((u.replace("https://app.jetbrokers.io/api",""), n, ks))
        except Exception: pass
    try:
        await imp.login()
        imp._page.on("response", on_resp)
        await imp._page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}", wait_until="networkidle", timeout=60_000)
        await imp._page.wait_for_timeout(3500)
        await imp._dismiss_popups()
        await imp._click_tab("Unidades")
        await imp._page.wait_for_timeout(3000)
        # Probar click en "Buscar" (puede cargar todas las unidades)
        await imp._page.evaluate("""() => {
            const b=[...document.querySelectorAll('button,a')].find(x=>/^(buscar|filtrar|aplicar)$/i.test((x.innerText||'').trim()));
            if(b) b.click();
        }""")
        await imp._page.wait_for_timeout(3000)
        print("=== XHRs /api durante tab Unidades ===")
        for u, n, ks in xhrs:
            print(f"  [{n:>4}] {u[:70]}  keys={ks[:8]}")
        imp._page.remove_listener("response", on_resp)
        info = await imp._page.evaluate(r"""() => {
            const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
            const out = {};
            // selects (page-size?)
            out.selects = [...scope.querySelectorAll('select')].map(s => ({
                opts: [...s.options].map(o => o.text.trim())
            }));
            // mat-paginator
            const pag = scope.querySelector('mat-paginator');
            out.mat_paginator = pag ? pag.innerText.replace(/\n+/g,' | ').slice(0,200) : null;
            // cualquier elemento con 'pag' en clase
            out.pag_like = [...scope.querySelectorAll('[class*="paginat" i], [class*="pagination" i], ngb-pagination, .page-item, .pager')]
                .slice(0,5).map(e => ({cls: e.className, txt: (e.innerText||'').trim().slice(0,80)}));
            // botones del footer / con números
            const btns = [...scope.querySelectorAll('button, a, li, span')].filter(b => b.offsetParent);
            out.num_btns = btns.filter(b => /^\d{1,3}$/.test((b.innerText||'').trim())).map(b => (b.innerText||'').trim()).slice(0,20);
            // texto tipo "1 - 30 de 250" o "Mostrando"
            const bodyTxt = (scope.innerText||'');
            const m = bodyTxt.match(/(\d+\s*[-–]\s*\d+\s*(de|of|\/)\s*\d+)|mostrando[^\n]{0,40}|p[áa]gina[^\n]{0,30}/i);
            out.counter_text = m ? m[0] : null;
            // contar filas actuales
            const tables=[...scope.querySelectorAll('table')]; let bn=0;
            tables.forEach(t=>{const r=t.querySelectorAll('tbody tr').length; if(r>bn)bn=r;});
            out.rows_now = bn;
            // footer HTML (últimos 600 chars del scope)
            out.footer_html = scope.innerHTML.slice(-1200).replace(/\s+/g,' ');
            return out;
        }""")
        import json
        print(json.dumps(info, ensure_ascii=False, indent=2)[:3500])
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
