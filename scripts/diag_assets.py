"""diag_assets.py — Inspecciona /project/{id}/assets (estac/bodegas/packs vía cotización)."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

PID = os.environ.get("DIAG_ID", "utPNS9kv")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    # navegar al flujo de cotización para establecer contexto
    await imp._page.goto(f"https://app.jetbrokers.io/marketplace/workview/{PID}", wait_until="networkidle", timeout=50_000)
    await imp._page.wait_for_timeout(3_000)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}

    for ref in ("quotes", f"marketplace/workview/{PID}"):
        cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1", "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": f"https://app.jetbrokers.io/{ref}"})
        r = await cli.get(f"/project/{PID}/assets")
        print(f"\n### GET /project/{PID}/assets (Referer={ref}) → {r.status_code}", flush=True)
        if r.status_code == 200:
            j = r.json()
            (OUT / "assets.json").write_text(json.dumps(j, indent=2, ensure_ascii=False))
            if isinstance(j, dict):
                for k, v in j.items():
                    if isinstance(v, list):
                        print(f"   {k}: list[{len(v)}]  item0={json.dumps(v[0], ensure_ascii=False)[:200] if v else ''}", flush=True)
                    else:
                        print(f"   {k}: {type(v).__name__} = {str(v)[:60]}", flush=True)
            elif isinstance(j, list):
                print(f"   list[{len(j)}] item0={json.dumps(j[0], ensure_ascii=False)[:250] if j else ''}", flush=True)
            await cli.aclose()
            break
        await cli.aclose()

    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
