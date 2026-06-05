"""diag_vm_typesel.py — Encuentra el selector de tipo en el Stock del workview y scrapea estac/bodegas/packs."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa

PID = os.environ.get("DIAG_ID", "utPNS9kv")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    page = imp._page
    reqs = []

    def on_req(req):
        if "jetbrokers.io/api" in req.url and req.method in ("GET", "POST"):
            reqs.append({"m": req.method, "url": req.url, "body": req.post_data})
    page.on("request", on_req)

    await page.goto(f"https://app.jetbrokers.io/marketplace/workview/{PID}", wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    # abrir tab Stock
    for sel in ('a:has-text("Stock")', '[role=tab]:has-text("Stock")', 'li:has-text("Stock")'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000); break
        except Exception:
            continue
    await page.wait_for_timeout(3_500)
    await page.screenshot(path=str(OUT / "ts-00-stock.png"), full_page=False)

    # dump de controles (selects / dropdowns / botones) en la zona de stock
    controls = await page.evaluate(r"""() => {
        const out = [];
        for (const el of document.querySelectorAll('mat-select, select, [class*=select], button, [role=button], .dropdown, mat-button-toggle')) {
            const t = (el.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim();
            const r = el.getBoundingClientRect();
            if (r.width>0 && r.height>0 && t && t.length<40)
                out.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,30), t, y: Math.round(r.y)});
        }
        return out.slice(0, 40);
    }""")
    print("### Controles visibles en Stock:", flush=True)
    for c in controls:
        print(f"   {c['tag']:12} y={c['y']:4} {c['t']!r}", flush=True)

    # intentar abrir cada mat-select y ver opciones; clickear las de tipo estac/bodega/pack
    found_rows = {}
    for attempt in range(8):
        opened = await page.evaluate(r"""() => {
            for (const s of document.querySelectorAll('mat-select:not([data-x]), select:not([data-x]), mat-button-toggle-group:not([data-x])')) {
                s.setAttribute('data-x','1'); const r=s.getBoundingClientRect();
                if (r.width>0&&r.height>0){ s.click(); return (s.innerText||'').slice(0,30); }
            }
            return null;
        }""")
        if opened is None:
            break
        await page.wait_for_timeout(1_000)
        opts = await page.evaluate(r"""() => [...document.querySelectorAll('mat-option,[role=option],option')].map(o=>(o.innerText||'').trim()).filter(Boolean).slice(0,20)""")
        if opts:
            print(f"   dropdown '{opened}' opciones: {opts}", flush=True)
        # clickear opción estac/bodega/pack
        for word in ("estacion", "bodega", "pack"):
            picked = await page.evaluate(r"""(w) => {
                for (const o of document.querySelectorAll('mat-option,[role=option],option')) {
                    if ((o.innerText||'').toLowerCase().includes(w)){ o.click(); return o.innerText.trim(); }
                }
                return null;
            }""", word)
            if picked:
                await page.wait_for_timeout(3_000)
                await page.screenshot(path=str(OUT / f"ts-{word}.png"), full_page=True)
                # scrapear filas de la tabla
                rows = await page.evaluate(r"""() => {
                    const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                    return [...scope.querySelectorAll('table tbody tr')].slice(0,5).map(tr =>
                        [...tr.querySelectorAll('td')].map(td=>(td.innerText||'').replace(/\s+/g,' ').trim()));
                }""")
                found_rows[word] = rows
                print(f"   ▸ '{picked}': {len(rows)} filas muestra → {rows[:2]}", flush=True)
                # reabrir el dropdown para la siguiente
                await page.evaluate("() => { for (const s of document.querySelectorAll('mat-select')) { s.click(); break; } }")
                await page.wait_for_timeout(800)

    page.remove_listener("request", on_req)
    await imp.close()
    print(f"\n### Requests /api durante interacción:", flush=True)
    seen = set()
    for r in reqs:
        p = r["url"].split("/api", 1)[-1].split("?")[0]
        if any(k in p.lower() for k in ("parking", "store", "pack", "units-search", "apartment")) and p not in seen:
            seen.add(p)
            print(f"   {r['m']} {p}  body={ (r['body'] or '')[:160]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
