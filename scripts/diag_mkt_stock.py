"""diag_mkt_stock.py — Encuentra endpoints de estac/bodegas/packs en MARKETPLACE (reventa)."""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

PID = os.environ.get("DIAG_ID", "utPNS9kv")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
REF = f"https://app.jetbrokers.io/marketplace/workview/{PID}"

GETS = [
    "/parking/project/{id}/list/0", "/parking/project/{id}/available",
    "/store/project/{id}/list/0", "/store/project/{id}/available",
    "/pack/project/{id}/list/0", "/pack/project/{id}/available",
    "/marketplace/parking/{id}/list/0", "/marketplace/store/{id}/list/0", "/marketplace/pack/{id}/list/0",
]
POSTS = [
    ("/marketplace/units-search/{ts}", "parking"), ("/marketplace/units-search/{ts}", "storage"),
    ("/marketplace/units-search/{ts}", "pack"), ("/marketplace/units-search/{ts}", "parkingSlot"),
]


def summ(j):
    if isinstance(j, list):
        return f"list[{len(j)}] " + (json.dumps(j[0], ensure_ascii=False)[:160] if j else "")
    if isinstance(j, dict):
        out = f"dict {list(j.keys())[:8]}"
        for k in ("parkings", "stores", "packs", "apartments", "elements"):
            if isinstance(j.get(k), list):
                out += f" {k}[{len(j[k])}]" + (" " + json.dumps(j[k][0], ensure_ascii=False)[:150] if j[k] else "")
        return out
    return str(j)[:60]


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    page = imp._page
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and any(k in resp.url.lower() for k in
                ("parking", "store", "pack", "stock", "unit", "apartment", "marketplace")):
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = (await resp.text())[:4000]
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    # navegar workview + clic en tabs/sub-tabs de stock
    await page.goto(REF, wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    for _ in range(10):
        clicked = await page.evaluate(r"""() => {
            const re=/stock|unidad|disponib|estacion|bodega|pack|parking/i;
            const done=window.__c||(window.__c=new Set());
            for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab],span,div,li')) {
                const s=(el.innerText||'').replace(/\s+/g,' ').trim();
                if (s && re.test(s) && s.length<24 && !done.has(s)){const r=el.getBoundingClientRect();
                  if(r.width>0&&r.height>0){done.add(s); el.click(); return s;}}
            }
            return null;
        }""")
        if not clicked:
            break
        await page.wait_for_timeout(2_500)
        print(f"   clic: {clicked!r}", flush=True)
    await page.screenshot(path=str(OUT / "mkt-stock.png"), full_page=True)

    # cliente httpx con Referer workview para probes activos
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1", "Authorization": f"Bearer {imp._jb_token}", "Referer": REF})
    page.remove_listener("response", on_resp)

    print(f"\n### PASIVO — endpoints capturados del navegador:", flush=True)
    seen = set()
    for c in cap:
        p = c["url"].split("/api", 1)[-1].split("?")[0]
        sig = f"{c['m']} {p}"
        if sig in seen: continue
        seen.add(sig)
        try:
            info = summ(json.loads(c["body"])) if c["status"] in (200, 201) and c.get("body") else ""
        except Exception:
            info = "(parse)"
        print(f"   [{c['status']}] {c['m']:4} {p[:60]}   {info}", flush=True)

    print(f"\n### ACTIVO — probes con Referer workview:", flush=True)
    for tmpl in GETS:
        ep = tmpl.replace("{id}", PID)
        try:
            r = await cli.get(ep)
            print(f"   [{r.status_code}] GET  {ep}   {summ(r.json()) if r.status_code==200 else ''}", flush=True)
        except Exception as e:
            print(f"   ERR {ep}: {str(e)[:40]}", flush=True)
    for tmpl, typ in POSTS:
        ep = tmpl.replace("{ts}", str(int(time.time()*1000)))
        b = {"tipologies": [], "type": typ, "order": "ASC", "models": [], "facings": [],
             "projectId": PID, "availability": None, "number": None, "element": 0, "elements": 9999}
        try:
            r = await cli.post(ep, json=b)
            print(f"   [{r.status_code}] POST units-search type={typ}   {summ(r.json()) if r.status_code in (200,201) else ''}", flush=True)
        except Exception as e:
            print(f"   ERR POST {typ}: {str(e)[:40]}", flush=True)
    await cli.aclose(); await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
