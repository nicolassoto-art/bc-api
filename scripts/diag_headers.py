"""
diag_headers.py — Captura los headers REALES que manda el navegador en stock-selectors/
units-search/files (que SÍ devuelven 200/201 vía navegador) y los replica en httpx para
descubrir qué header le falta a httpx (que da 401/400).

Flujo robusto: catálogo → clic en tarjeta → workview → clic tab Stock (mantiene sesión).
Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa: E402
import httpx  # noqa: E402

KEYS = ["stock-selectors", "units-search", "marketplace/files"]


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=Path("imports/_diag"),
    )
    await imp.login()
    page = imp._page
    reqs = {}
    status = {}

    def on_req(req):
        for k in KEYS:
            if k in req.url and k not in reqs:
                reqs[k] = {"url": req.url, "method": req.method,
                           "headers": dict(req.headers), "post_data": req.post_data}

    def on_resp(resp):
        for k in KEYS:
            if k in resp.url and k not in status:
                status[k] = resp.status

    page.on("request", on_req)
    page.on("response", on_resp)

    # catálogo → clic primera tarjeta → workview → tab Stock
    await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(3_000)
    await imp._dismiss_popups()
    await page.wait_for_timeout(1_000)
    try:
        await page.locator(".card-img-top.clickable").first.click(timeout=6_000)
    except Exception as e:
        print(f"click card err: {e}", flush=True)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    wv_url = page.url
    print(f"### workview url: {wv_url}", flush=True)
    tabs = await page.evaluate(r"""() => {
        const out=[];
        for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab]')) {
            const t=(el.innerText||'').replace(/\s+/g,' ').trim();
            if (t && /stock|unidad|disponib/i.test(t) && t.length<25){const r=el.getBoundingClientRect();
              if(r.width>0&&r.height>0) out.push({t,cx:Math.round(r.x+r.width/2),cy:Math.round(r.y+r.height/2)});}
        }
        return out;
    }""")
    if tabs:
        await page.mouse.click(tabs[0]["cx"], tabs[0]["cy"])
        await page.wait_for_timeout(4_000)
    page.remove_listener("request", on_req)

    m = re.search(r"workview/([A-Za-z0-9]+)", wv_url)
    pid = m.group(1) if m else None
    print(f"### pid: {pid}\n", flush=True)

    for k in KEYS:
        if k not in reqs:
            print(f"=== {k}: NO capturado ===", flush=True)
            continue
        v = reqs[k]
        print(f"=== {k}  [resp status: {status.get(k)}] ===", flush=True)
        print(f"   {v['method']} {v['url'].split('/api',1)[-1][:90]}", flush=True)
        hh = {kk: ("Bearer …(len %d)" % len(vv) if kk.lower() == "authorization" else vv)
              for kk, vv in v["headers"].items()}
        print(f"   headers: {json.dumps(hh)}", flush=True)
        if v.get("post_data"):
            print(f"   post_data: {v['post_data'][:300]}", flush=True)
        print(flush=True)

    # Replicar stock-selectors con headers del navegador vs JB_HEADERS variantes
    if pid and "stock-selectors" in reqs:
        bh = {k: val for k, val in reqs["stock-selectors"]["headers"].items()
              if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
        bh["authorization"] = f"Bearer {imp._jb_token}"
        url = f"https://app.jetbrokers.io/api/marketplace/stock-selectors/{pid}"
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(url, headers=bh)
            print(f"### httpx con headers EXACTOS del navegador → {r.status_code}", flush=True)
        h2 = {**JB_HEADERS, "jet-brokers-version": "7.43.1",
              "Authorization": f"Bearer {imp._jb_token}", "Referer": wv_url}
        async with httpx.AsyncClient(timeout=20.0) as c:
            r2 = await c.get(url, headers=h2)
            print(f"### httpx JB_HEADERS + Referer=workview → {r2.status_code}", flush=True)
        # diferencia de headers: qué tiene el navegador que NO tiene JB_HEADERS
        extra = {k: v for k, v in reqs["stock-selectors"]["headers"].items()
                 if k.lower() not in {kk.lower() for kk in JB_HEADERS} and k.lower() != "authorization"}
        print(f"### headers que el navegador manda y JB_HEADERS NO: {json.dumps(extra)}", flush=True)

    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
