"""Inspecciona la respuesta cruda de bodegas (¿trae superficie en algún campo?)."""
import os, json, asyncio, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS

PID = os.environ.get("DIAG_ID", "LKubKmn0")

async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=Path("imports/_diag"))
    await imp.login()
    await imp._page.goto(f"https://app.jetbrokers.io/projects/detail/{PID}", wait_until="networkidle", timeout=50_000)
    await imp._page.wait_for_timeout(3_000)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": f"https://app.jetbrokers.io/projects/detail/{PID}"})
    # /store/project/{id}/list/0
    r = await cli.get(f"/store/project/{PID}/list/0")
    print(f"GET /store/project/{PID}/list/0 → {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        items = d.get("stores", []) if isinstance(d, dict) else d
        print(f"  total bodegas: {len(items)}")
        if items:
            print(f"  keys item[0]: {list(items[0].keys())}")
            print(f"  ejemplos (3):")
            for it in items[:3]:
                print(f"    {json.dumps(it, ensure_ascii=False)}")
    # también probar assets (formato "X [P UF] [S m2]")
    ar = await cli.get(f"/project/{PID}/assets", headers={"Referer": "https://app.jetbrokers.io/quotes"})
    print(f"\nGET /project/{PID}/assets → {ar.status_code}")
    if ar.status_code == 200:
        d = ar.json()
        bod = d.get("stores", [])
        print(f"  bodegas en assets: {len(bod)}")
        for b in bod[:3]:
            print(f"    {json.dumps(b, ensure_ascii=False)}")
    await cli.aclose()
    await imp.close()

asyncio.run(main())
