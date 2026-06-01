"""Dump simple del paginador de la tab Unidades (V.Mackenna 1796)."""
import asyncio, os, sys, json
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

        # mat-paginator outerHTML
        mp = await imp._page.evaluate("() => { const m = document.querySelector('mat-paginator'); return m ? m.outerHTML : 'NO_MAT_PAGINATOR'; }")
        print("=== mat-paginator HTML ===")
        print(mp[:2000])

        # page-size selects
        sels = await imp._page.evaluate("() => [...document.querySelectorAll('select')].map(s => [...s.options].map(o => o.text.trim()))")
        print("\n=== selects ===")
        print(json.dumps(sels, ensure_ascii=False))

        # botones con aria-label
        btns = await imp._page.evaluate("() => [...document.querySelectorAll('button')].map(b => ({txt:(b.innerText||'').trim().slice(0,15), aria:b.getAttribute('aria-label'), dis:b.disabled})).filter(b => (b.aria||'').toLowerCase().includes('next') || (b.aria||'').toLowerCase().includes('sig') || (b.aria||'').toLowerCase().includes('page') || (b.aria||'').toLowerCase().includes('pág'))")
        print("\n=== botones next/page ===")
        print(json.dumps(btns, ensure_ascii=False))

        # texto de rango (innerText con números)
        rng = await imp._page.evaluate("() => { const m = document.querySelector('mat-paginator'); return m ? m.innerText : ''; }")
        print("\n=== mat-paginator innerText ===")
        print(rng)
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
