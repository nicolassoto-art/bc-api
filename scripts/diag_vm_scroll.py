"""diag_vm_scroll.py — Scroll agresivo del Stock para cargar TODOS los tipos (estac/bodegas/packs)."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from collections import Counter
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
        u = req.url
        if any(k in u for k in ("units-search", "/parking/", "/store/", "/pack/", "apartment")):
            reqs.append({"m": req.method, "url": u, "body": req.post_data})
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

    # localizar contenedor scrolleable del stock
    await page.evaluate(r"""() => {
        window.__sc = null;
        const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
        for (const el of [scope, ...scope.querySelectorAll('*')]) {
            const cs = getComputedStyle(el);
            if (!/auto|scroll/.test(cs.overflowY)) continue;
            if (el.scrollHeight - el.clientHeight < 80) continue;
            window.__sc = el; break;
        }
        return window.__sc ? 'OK' : 'WINDOW';
    }""")
    # mover mouse al centro del contenedor
    box = await page.evaluate("""() => { const el=window.__sc||document.documentElement; const r=el.getBoundingClientRect();
        return {x:r.x+r.width/2, y:r.y+Math.min(r.height/2,300)};}""")
    if box:
        await page.mouse.move(box["x"], box["y"])

    last = 0; stable = 0; counts = []
    for step in range(60):
        for _ in range(25):
            try: await page.mouse.wheel(0, 300)
            except Exception: pass
            await page.wait_for_timeout(60)
        await page.evaluate(r"""() => {
            if (window.__sc) window.__sc.scrollTop = window.__sc.scrollHeight;
            const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
            const trs=scope.querySelectorAll('table tbody tr');
            if (trs.length) trs[trs.length-1].scrollIntoView({block:'end'});
        }""")
        await page.wait_for_timeout(1_800)
        n = await page.evaluate(r"""() => {const s=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
            return s.querySelectorAll('table tbody tr').length;}""")
        counts.append(n)
        if n == last:
            stable += 1
            if stable >= 6: break
        else:
            stable = 0; last = n
        if step % 5 == 0:
            print(f"   step {step}: {n} filas · reqs={len(reqs)}", flush=True)
    print(f"   filas finales: {last}", flush=True)
    await page.screenshot(path=str(OUT / "scroll-final.png"), full_page=True)

    # scrapear todas las filas con su columna Tipo
    data = await page.evaluate(r"""() => {
        const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
        const headers=[...scope.querySelectorAll('table thead th,table thead td')].map(h=>(h.innerText||'').trim());
        const rows=[...scope.querySelectorAll('table tbody tr')].map(tr=>
            [...tr.querySelectorAll('td')].map(td=>(td.innerText||'').replace(/\s+/g,' ').trim()));
        return {headers, rows};
    }""")
    (OUT / "scroll_rows.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n### headers: {data['headers']}", flush=True)
    # detectar columna 'tipo'
    ti = next((i for i,h in enumerate(data["headers"]) if "tipo" in h.lower()), None)
    if ti is not None:
        tipos = Counter(r[ti] if ti < len(r) else "?" for r in data["rows"])
        print(f"   distribución columna Tipo[{ti}]: {dict(tipos)}", flush=True)
    print(f"   total filas: {len(data['rows'])}", flush=True)
    for r in data["rows"][:3] + data["rows"][-3:]:
        print(f"      {r}", flush=True)

    page.remove_listener("request", on_req)
    await imp.close()
    print(f"\n### Requests (units-search/parking/store/pack):", flush=True)
    seen = set()
    for r in reqs:
        p = r["url"].split("/api", 1)[-1].split("?")[0]
        key = p + (r.get("body") or "")[:40]
        if key in seen: continue
        seen.add(key)
        print(f"   {r['m']} {p}  body={(r['body'] or '')[:140]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
