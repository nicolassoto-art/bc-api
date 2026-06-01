"""Dump del control de paginación de la tab Unidades (V.Mackenna 1796)."""
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""), headless=True,
    )
    try:
        await imp.login()
        await imp._page.goto("https://app.jetbrokers.io/projects/edit/1kvflc3m", wait_until="networkidle", timeout=60_000)
        await imp._page.wait_for_timeout(3500)
        await imp._dismiss_popups()
        await imp._click_tab("Unidades")
        await imp._page.wait_for_timeout(3000)
        info = await imp._page.evaluate(r"""() => {
            const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active, .mat-tab-body-active') || document;
            const out = {};
            // mat-paginator
            const mp = scope.querySelector('mat-paginator') || document.querySelector('mat-paginator');
            out.mat_paginator_html = mp ? mp.outerHTML.slice(0, 1200) : null;
            // cualquier elemento con 'pag' en clase
            out.pag_elements = [...scope.querySelectorAll('[class*="pag" i], [class*="Pag"]')].slice(0,5).map(e => ({tag:e.tagName, cls:e.className, txt:(e.innerText||'').slice(0,60)}));
            // selects (page size)
            out.selects = [...scope.querySelectorAll('select')].map(s => ({opts:[...s.options].map(o=>o.text.trim())}));
            // botones con flechas/números cerca de la tabla
            out.botones = [...scope.querySelectorAll('button')].map(b=>({txt:(b.innerText||'').trim().slice(0,20), aria:b.getAttribute('aria-label'), cls:(b.className||'').slice(0,50), disabled:b.disabled})).filter(b=>b.txt||b.aria).slice(0,25);
            // texto tipo "1 - 30 of 250" o "Página 1 de 9"
            out.body_pag_text = (scope.innerText.match(/\d+\s*[-–/]\s*\d+\s*(of|de)\s*\d+/gi)||[]).slice(0,5);
            return out;
        }""")
        import json
        print("=== mat-paginator ===")
        print(info.get("mat_paginator_html"))
        print("\n=== selects (page size) ===")
        print(json.dumps(info.get("selects"), ensure_ascii=False))
        print("\n=== texto paginación ===")
        print(info.get("body_pag_text"))
        print("\n=== pag elements ===")
        print(json.dumps(info.get("pag_elements"), ensure_ascii=False, indent=1))
        print("\n=== botones ===")
        for b in info.get("botones", []):
            print(f"  txt={b['txt']!r} aria={b['aria']!r} disabled={b['disabled']} cls={b['cls']!r}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
