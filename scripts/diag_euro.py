"""diag_euro.py — Diagnóstico rápido de los 8 proyectos de Euro para ver cuál tiene más stock."""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS
import httpx

PROYECTOS = [
    ("Edificio Mapocho 3521 Edificio A", "FxGIdSga"),
    ("Santa Elena 1670 MBI",             "EZljonhe"),
    ("Vicuña Mackenna 1432",             "PsqVqc03"),
    ("Rosas 1444",                       "b7Aniv5k"),
    ("Guillermo Mann 1401",              "Dw5PBsEd"),
    ("Independencia 4745",               "qlkZufJk"),
    ("Edificio Vitro",                   "Xm0ZQPxk"),
    ("Jose Pedro Alessandri 1498",       "R5cTUSc8"),
]


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=Path("imports/_diag_euro"))
    await imp.login()
    page = imp._page
    results = []
    for nombre, jb_id in PROYECTOS:
        print(f"\n--- {nombre} ({jb_id}) ---", flush=True)
        await page.goto(f"https://app.jetbrokers.io/projects/detail/{jb_id}",
                        wait_until="networkidle", timeout=40_000)
        await page.wait_for_timeout(2_000)
        cookies = await imp._ctx.cookies()
        jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
        cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": f"https://app.jetbrokers.io/projects/detail/{jb_id}"})

        async def gj(ep):
            try:
                r = await cli.get(ep)
                return r.status_code, (r.json() if r.status_code == 200 else None)
            except Exception:
                return -1, None

        s_det, det = await gj(f"/project/{jb_id}/detail")
        s_mod, mods = await gj(f"/apartment-model/project/{jb_id}/all")
        n_mod = len(mods) if isinstance(mods, list) else 0
        n_mod_pl = sum(1 for m in (mods or []) if m.get("blueprint"))
        # unidades — ambos availability
        n_uds = 0
        if s_det == 200:
            for av in (None, "available"):
                try:
                    ts = int(time.time() * 1000)
                    body = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
                            "projectId": jb_id, "availability": av, "number": None, "element": 0, "elements": 9999}
                    r = await cli.post(f"/apartment/project-detail-search/{ts}", json=body)
                    if r.status_code in (200, 201):
                        u = (r.json() or {}).get("apartments", [])
                        if len(u) > n_uds: n_uds = len(u)
                except Exception:
                    pass
        # estac/bodegas via list y assets
        _, pk_l = await gj(f"/parking/project/{jb_id}/list/0")
        _, st_l = await gj(f"/store/project/{jb_id}/list/0")
        pk_l_n = len((pk_l or {}).get("parkings", [])) if isinstance(pk_l, dict) else 0
        st_l_n = len((st_l or {}).get("stores", [])) if isinstance(st_l, dict) else 0
        ac = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=20,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": "https://app.jetbrokers.io/quotes"})
        try:
            r = await ac.get(f"/project/{jb_id}/assets")
            assets = r.json() if r.status_code == 200 else {}
        except Exception:
            assets = {}
        await ac.aclose()
        pk_a_n = len((assets or {}).get("parkings", []) or [])
        st_a_n = len((assets or {}).get("stores", []) or [])
        pc_a_n = len((assets or {}).get("packs", []) or [])
        est_max = max(pk_l_n, pk_a_n)
        bod_max = max(st_l_n, st_a_n)
        # stock_score: unidades + estac + bodegas + packs (peso = stock total)
        stock_total = n_uds + est_max + bod_max + pc_a_n
        await cli.aclose()
        results.append({
            "nombre": nombre, "jb_id": jb_id, "status": s_det,
            "dev": (det or {}).get("developerName"), "loc": (det or {}).get("locality"),
            "mod": n_mod, "mod_pl": n_mod_pl, "uds": n_uds,
            "est": est_max, "bod": bod_max, "pck": pc_a_n,
            "stock_total": stock_total,
        })
        print(f"   dev={(det or {}).get('developerName')!r} loc={(det or {}).get('locality')!r} "
              f"mod={n_mod}({n_mod_pl}p) uds={n_uds} estac={est_max} bod={bod_max} packs={pc_a_n} "
              f"→ STOCK TOTAL: {stock_total}", flush=True)

    await imp.close()

    print(f"\n{'═'*100}")
    print(f"RANKING POR STOCK TOTAL (uds + estac + bod + packs)")
    print(f"{'═'*100}")
    results.sort(key=lambda r: -r["stock_total"])
    print(f"{'#':<3} {'Proyecto':<35} {'JB ID':<10} {'Mod(pl)':<9} {'Uds':<5} {'Est':<4} {'Bod':<4} {'Pck':<4} {'TOTAL'}")
    print("─" * 100)
    for i, r in enumerate(results, start=1):
        mark = " ⭐" if i == 1 else ""
        print(f"{i:<3} {r['nombre'][:34]:<35} {r['jb_id']:<10} {r['mod']}({r['mod_pl']}){' '*(5-len(str(r['mod']))-len(str(r['mod_pl'])))} "
              f"{r['uds']:<5} {r['est']:<4} {r['bod']:<4} {r['pck']:<4} {r['stock_total']}{mark}")
    Path("imports/_diag_euro").mkdir(parents=True, exist_ok=True)
    Path("imports/_diag_euro/ranking.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
