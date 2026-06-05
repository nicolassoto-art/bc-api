"""diag_vm_scroll2.py — Scroll del Stock (tarjetas) hasta el final; scrapea todos los tipos."""
from __future__ import annotations
import asyncio, json, os, re, sys
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
    apis = []
    page.on("request", lambda r: apis.append((r.method, r.url, r.post_data))
            if any(k in r.url for k in ("units-search", "/parking/", "/store/", "/pack/", "apartment")) else None)

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

    # detectar selector de tarjeta = clase más repetida entre elementos con texto 'Optional'/'UF'
    card_sel = await page.evaluate(r"""() => {
        const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
        const cnt={};
        for (const el of scope.querySelectorAll('div,li,article')) {
            const t=el.innerText||'';
            if (!/UF/.test(t) || t.length>400) continue;
            const r=el.getBoundingClientRect();
            if (r.height<40||r.height>260||r.width<200) continue;
            for (const c of (el.className||'').toString().split(/\s+/)) if(c) cnt[c]=(cnt[c]||0)+1;
        }
        const best=Object.entries(cnt).sort((a,b)=>b[1]-a[1])[0];
        return best ? '.'+best[0] : null;
    }""")
    print(f"### selector de tarjeta: {card_sel}", flush=True)

    async def count_cards():
        return await page.evaluate("""(s) => { if(!s) return 0;
            const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
            return scope.querySelectorAll(s).length; }""", card_sel)

    # localizar contenedor scrolleable
    await page.evaluate(r"""(s) => {
        window.__sc=null;
        const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
        let node = s ? scope.querySelector(s) : null;
        while (node && node!==document.body) {
            const cs=getComputedStyle(node);
            if (/auto|scroll/.test(cs.overflowY) && node.scrollHeight-node.clientHeight>80){window.__sc=node;break;}
            node=node.parentElement;
        }
        if(!window.__sc){ for(const el of [scope,...scope.querySelectorAll('*')]){const cs=getComputedStyle(el);
            if(/auto|scroll/.test(cs.overflowY)&&el.scrollHeight-el.clientHeight>80){window.__sc=el;break;}}}
        return window.__sc?'OK':'WIN';
    }""", card_sel)
    box = await page.evaluate("""() => {const el=window.__sc||document.documentElement;const r=el.getBoundingClientRect();
        return {x:r.x+r.width/2,y:r.y+Math.min(r.height/2,300)};}""")
    if box: await page.mouse.move(box["x"], box["y"])

    last=0; stable=0
    for step in range(80):
        for _ in range(20):
            try: await page.mouse.wheel(0, 400)
            except Exception: pass
            await page.wait_for_timeout(50)
        await page.evaluate("""() => { if(window.__sc) window.__sc.scrollTop=window.__sc.scrollHeight; }""")
        await page.wait_for_timeout(1_500)
        n = await count_cards()
        if n == last:
            stable += 1
            if stable >= 8: break
        else:
            stable = 0; last = n
        if step % 5 == 0:
            print(f"   step {step}: {n} tarjetas · apis={len(apis)}", flush=True)
    print(f"   tarjetas finales: {last}", flush=True)
    await page.screenshot(path=str(OUT / "scroll2-final.png"), full_page=True)

    cards = await page.evaluate(r"""(s) => {
        const scope=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
        return [...scope.querySelectorAll(s)].map(el=>(el.innerText||'').replace(/\s+/g,' ').trim());
    }""", card_sel)
    (OUT / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2))
    # clasificar por palabra clave de tipo
    tipos = Counter()
    for c in cards:
        cl = c.lower()
        if "estacion" in cl: tipos["estacionamiento"] += 1
        elif "bodega" in cl: tipos["bodega"] += 1
        elif "pack" in cl and "pack " not in cl[:40]: tipos["pack"] += 1
        elif "depto" in cl or "depart" in cl: tipos["depto"] += 1
        else: tipos["?"] += 1
    print(f"\n### {len(cards)} tarjetas · tipos (heurística): {dict(tipos)}", flush=True)
    print(f"   primeras 2: {cards[:2]}", flush=True)
    print(f"   últimas 4: {cards[-4:]}", flush=True)

    await imp.close()
    print(f"\n### APIs (units-search/parking/store/pack):", flush=True)
    seen = set()
    for m, u, b in apis:
        p = u.split("/api", 1)[-1].split("?")[0]
        k = p + (b or "")[:40]
        if k in seen: continue
        seen.add(k)
        print(f"   {m} {p}  body={(b or '')[:130]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
