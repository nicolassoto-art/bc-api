"""diag_mkt_types.py — Captura el body de units-search al filtrar por tipo + distribución de tipos."""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

PID = os.environ.get("DIAG_ID", "utPNS9kv")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
REF = f"https://app.jetbrokers.io/marketplace/workview/{PID}"


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    page = imp._page
    bodies = []

    def on_req(req):
        if "units-search" in req.url and req.method == "POST":
            try:
                bodies.append(json.loads(req.post_data or "{}"))
            except Exception:
                pass
    page.on("request", on_req)

    await page.goto(REF, wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    # clic en el tab Stock (texto exacto)
    await page.evaluate(r"""() => {
        for (const el of document.querySelectorAll('a,button,[role=tab],.nav-link,li,span,div')) {
            if ((el.innerText||'').trim() === 'Stock'){ el.click(); return true; }
        }
        return false;
    }""")
    await page.wait_for_timeout(3_500)
    await page.screenshot(path=str(OUT / "mkt-stocktab.png"), full_page=True)
    # abrir cada mat-select / dropdown y clickear sus opciones (para gatillar filtros por tipo)
    for _ in range(6):
        opened = await page.evaluate(r"""() => {
            const sels = document.querySelectorAll('mat-select:not([data-done]), select:not([data-done]), [class*=select]:not([data-done])');
            for (const s of sels){ s.setAttribute('data-done','1'); const r=s.getBoundingClientRect();
              if(r.width>0&&r.height>0){ s.click(); return true; } }
            return false;
        }""")
        await page.wait_for_timeout(1_200)
        # clickear opciones visibles
        await page.evaluate(r"""() => {
            for (const o of document.querySelectorAll('mat-option, option, [role=option], li')) {
                const t=(o.innerText||'').toLowerCase();
                if (/estacion|bodega|pack|parking|storage/.test(t)){ o.click(); return t; }
            }
            return null;
        }""")
        await page.wait_for_timeout(2_000)
        if not opened:
            break
    page.remove_listener("request", on_req)

    print(f"### Bodies de units-search capturados ({len(bodies)}):", flush=True)
    for b in bodies:
        print(f"   type={b.get('type')!r} availability={b.get('availability')!r} models={b.get('models')}", flush=True)

    # distribución de tipos en la respuesta sin filtro
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1", "Authorization": f"Bearer {imp._jb_token}", "Referer": REF})
    ts = int(time.time()*1000)
    body = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
            "projectId": PID, "availability": None, "number": None, "element": 0, "elements": 9999}
    r = await cli.post(f"/marketplace/units-search/{ts}", json=body)
    apts = (r.json() or {}).get("apartments", []) if r.status_code in (200, 201) else []
    print(f"\n### units-search type=None → {len(apts)} resultados", flush=True)
    print(f"   distribución 'type': {dict(Counter(a.get('type') for a in apts))}", flush=True)
    # probar valores de type alternativos
    for t in ("PARKING", "Parking", "parkingSpace", "warehouse", "cellar", "deposit", "bodega", "estacionamiento"):
        ts = int(time.time()*1000)
        b2 = {**body, "type": t}
        rr = await cli.post(f"/marketplace/units-search/{ts}", json=b2)
        n = len((rr.json() or {}).get("apartments", [])) if rr.status_code in (200, 201) else f"HTTP{rr.status_code}"
        print(f"   type={t!r} → {n}", flush=True)
    await cli.aclose(); await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
