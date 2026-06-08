"""diag_rosas.py — Inspecciona modelos crudos de Rosas 1444 (5 mod / 1 planta distinta)."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=Path("imports/_diag"))
    await imp.login()
    await imp._page.goto("https://app.jetbrokers.io/projects/detail/b7Aniv5k",
                         wait_until="networkidle", timeout=45_000)
    await imp._page.wait_for_timeout(3_000)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": "https://app.jetbrokers.io/projects/detail/b7Aniv5k"})

    r = await cli.get("/apartment-model/project/b7Aniv5k/all")
    print(f"GET apartment-model → {r.status_code}", flush=True)
    if r.status_code == 200:
        models = r.json()
        print(f"\n{len(models)} modelos crudos:", flush=True)
        bps = []
        for i, m in enumerate(models):
            bp = m.get("blueprint")
            print(f"  [{i+1}] id={m.get('id')!r:12} name={m.get('name')!r:35} "
                  f"rooms={m.get('rooms')} baths={m.get('bathrooms')} "
                  f"blueprint={json.dumps(bp, ensure_ascii=False) if bp else 'null'}", flush=True)
            bps.append(bp)
        print(f"\nResumen blueprints:")
        print(f"  total con blueprint != null: {sum(1 for b in bps if b)}")
        bp_ids = set()
        for b in bps:
            if isinstance(b, dict): bp_ids.add(b.get("id"))
            elif isinstance(b, str): bp_ids.add(b)
        print(f"  blueprints únicos (ids distintos): {len(bp_ids)} → {bp_ids}")

    # detail (cover)
    r2 = await cli.get("/project/b7Aniv5k/detail")
    if r2.status_code == 200:
        det = r2.json()
        print(f"\nDETAIL cover: {det.get('cover')!r}")
    await cli.aclose()
    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
