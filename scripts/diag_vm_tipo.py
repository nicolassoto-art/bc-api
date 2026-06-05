"""diag_vm_tipo.py — Usa el ng-select 'Tipo' del Stock para scrapear estac/bodegas/packs."""
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
        if "units-search" in req.url or "/parking/" in req.url or "/store/" in req.url or "/pack/" in req.url:
            reqs.append({"m": req.method, "url": req.url, "body": req.post_data})
    page.on("request", on_req)

    await page.goto(f"https://app.jetbrokers.io/marketplace/workview/{PID}", wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    for sel in ('a:has-text("Stock")', '[role=tab]:has-text("Stock")', 'li:has-text("Stock")'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000); break
        except Exception:
            continue
    await page.wait_for_timeout(3_500)

    # ubicar el ng-select cuyas opciones incluyan 'Estacionamiento'
    ngs = page.locator(".ng-select")
    n = await ngs.count()
    print(f"### {n} ng-select encontrados", flush=True)
    tipo_idx = None
    for i in range(n):
        try:
            await ngs.nth(i).click()
            await page.wait_for_timeout(900)
            opts = await page.evaluate(r"""() => [...document.querySelectorAll('.ng-dropdown-panel .ng-option,.ng-option-label')].map(o=>(o.innerText||'').trim()).filter(Boolean)""")
            print(f"   ng-select[{i}] opciones: {opts[:12]}", flush=True)
            if any("estacion" in o.lower() or "bodega" in o.lower() for o in opts):
                tipo_idx = i
                await page.keyboard.press("Escape")
                break
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
        except Exception as e:
            print(f"   ng[{i}] err: {str(e)[:40]}", flush=True)

    if tipo_idx is None:
        print("   ✗ no encontré el selector de Tipo", flush=True)
        await imp.close(); return

    results = {}
    for word in ("Estacionamiento", "Bodega", "Pack"):
        try:
            await ngs.nth(tipo_idx).click()
            await page.wait_for_timeout(900)
            picked = await page.evaluate(r"""(w) => {
                for (const o of document.querySelectorAll('.ng-dropdown-panel .ng-option, .ng-option')) {
                    if ((o.innerText||'').toLowerCase().includes(w.toLowerCase())){ o.click(); return o.innerText.trim(); }
                }
                return null;
            }""", word)
            if not picked:
                print(f"   '{word}' no está en opciones", flush=True); continue
            await page.wait_for_timeout(3_500)
            await page.screenshot(path=str(OUT / f"tipo-{word.lower()}.png"), full_page=True)
            # scrapear: headers + filas
            data = await page.evaluate(r"""() => {
                const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                const headers = [...scope.querySelectorAll('table thead th, table thead td')].map(h=>(h.innerText||'').trim());
                const rows = [...scope.querySelectorAll('table tbody tr')].map(tr =>
                    [...tr.querySelectorAll('td')].map(td=>(td.innerText||'').replace(/\s+/g,' ').trim()));
                return {headers, rows};
            }""")
            results[word] = data
            print(f"\n   ▸ {word}: {len(data['rows'])} filas · headers={data['headers']}", flush=True)
            for r in data["rows"][:4]:
                print(f"        {r}", flush=True)
        except Exception as e:
            print(f"   '{word}' err: {str(e)[:50]}", flush=True)

    page.remove_listener("request", on_req)
    (OUT / "tipo_scrape.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    await imp.close()

    print(f"\n### Requests durante selección de tipo:", flush=True)
    seen = set()
    for r in reqs:
        p = r["url"].split("/api", 1)[-1].split("?")[0]
        if p in seen: continue
        seen.add(p)
        print(f"   {r['m']} {p}  body={(r['body'] or '')[:150]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
