"""Probar endpoints de DETALLE de modelo JB para encontrar las superficies (Sup Total, Interior, Terraza, Logia, Jardín)."""
from __future__ import annotations
import asyncio, os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter


async def main():
    jb_id = os.environ.get("JB_ID", "1kvflc3m")
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""), headless=True,
    )
    try:
        await imp.login()
        async with imp._jb_httpx() as cli:
            # 1) Lista de modelos
            r = await cli.get(f"/apartment-model/project/{jb_id}/all")
            modelos = r.json() if isinstance(r.json(), list) else []
            print(f"Modelos: {len(modelos)}")
            if not modelos:
                return
            m = modelos[0]
            mid = m.get("id")
            mname = m.get("name", "?")
            print(f"\nProbando endpoints de detalle para modelo: {mname} ({mid})")

            candidatos = [
                f"/apartment-model/{mid}",
                f"/apartment-model/{mid}/detail",
                f"/apartment-model/{mid}/surfaces",
                f"/apartment-model/{mid}/all",
                f"/apartment-model/detail/{mid}",
                f"/apartment-model/project/{jb_id}/{mid}",
            ]
            for ep in candidatos:
                try:
                    rr = await cli.get(ep)
                    if rr.status_code != 200:
                        print(f"  {ep} → HTTP {rr.status_code}")
                        continue
                    j = rr.json()
                    if isinstance(j, dict):
                        # Buscar campos surface*
                        surf_keys = [k for k in j.keys() if "surf" in k.lower() or "sup" in k.lower() or "interior" in k.lower() or "terraza" in k.lower() or "logia" in k.lower() or "jardin" in k.lower()]
                        print(f"  ✅ {ep}: keys total={len(j)} · surf-like keys={surf_keys}")
                        if surf_keys:
                            for sk in surf_keys:
                                print(f"      {sk} = {j[sk]}")
                        else:
                            # Dump las primeras 15 keys para inspeccionar
                            print(f"      keys[:15]: {list(j.keys())[:15]}")
                            print(f"      sample: {json.dumps(j, ensure_ascii=False)[:400]}")
                    else:
                        print(f"  {ep}: respuesta no dict ({type(j).__name__})")
                except Exception as e:
                    print(f"  {ep}: ERR {e}")

            # 2) También capturar XHR al abrir tab Modelos del editor
            print("\n=== Captura XHR al abrir tab Modelos ===")
            xhrs = []
            async def on_resp(resp):
                try:
                    u = resp.url
                    if "/api/" not in u or resp.status != 200: return
                    if "json" not in resp.headers.get("content-type","").lower(): return
                    j = await resp.json()
                    if isinstance(j, dict) and any(k for k in j.keys() if "surf" in k.lower() or "sup" in k.lower()):
                        xhrs.append((u, sorted(j.keys())[:20]))
                    elif isinstance(j, list) and j and isinstance(j[0], dict):
                        if any(k for k in j[0].keys() if "surf" in k.lower() or "sup" in k.lower()):
                            xhrs.append((u, sorted(j[0].keys())[:20]))
                except Exception: pass

            imp._page.on("response", on_resp)
            await imp._page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}", wait_until="networkidle", timeout=60_000)
            await imp._page.wait_for_timeout(3000)
            await imp._dismiss_popups()
            await imp._click_tab("Modelos")
            await imp._page.wait_for_timeout(4000)
            # Hacer click en el primer modelo (puede abrir detalle con superficies)
            try:
                await imp._page.evaluate("""() => {
                    const rows = document.querySelectorAll('mat-tab-body.mat-mdc-tab-body-active table tbody tr');
                    if (rows.length) rows[0].click();
                }""")
                await imp._page.wait_for_timeout(3000)
            except Exception: pass
            imp._page.remove_listener("response", on_resp)
            for u, ks in xhrs:
                print(f"  🔗 {u}")
                print(f"     keys: {ks}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
