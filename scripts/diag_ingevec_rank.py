"""diag_ingevec_rank.py — Ranking por stock total de los 17 Ingevec pendientes."""
from __future__ import annotations
import asyncio, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS
import httpx

PROYECTOS = [
    ("El Aromo",                    "sn2K1WIY"),
    ("Nueva Esmeralda",             "LPJoCNEb"),
    ("Coronel Godoy",               "IDSvEAu8"),
    ("Edificio Serrano Capital",    "AJBqsIIi"),
    ("Matta",                       "CGFo7vDQ"),
    ("Brasil",                      "hvEkYVJq"),
    ("Don Ignacio",                 "is9kmud9"),
    ("Diagonal Paraguay 240",       "NeOU0rvU"),
    ("V.Mackenna 7589 E2",          "v8tAVcOG"),
    ("V.Mackenna 7589 E1",          "OwPhi37z"),
    ("Tocornal",                    "9MubHeQ8"),
    ("Vivaceta 864",                "IaIQ9iTH"),
    ("Centenario I",                "86YW1rPt"),
    ("Froilán Roa",                 "jfkJBrPQ"),
    ("V.Mackenna 1796",             "1kvflc3m"),
    ("Los Alerces",                 "WWMCny3E"),
    ("Santa Rosa 250",              "T8UuEf2r"),
]


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=Path("imports/_diag"))
    await imp.login()
    page = imp._page
    results = []
    for nombre, jb_id in PROYECTOS:
        await page.goto(f"https://app.jetbrokers.io/projects/detail/{jb_id}",
                        wait_until="networkidle", timeout=40_000)
        await page.wait_for_timeout(2_000)
        cookies = await imp._ctx.cookies()
        jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
        cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=20,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": f"https://app.jetbrokers.io/projects/detail/{jb_id}"})
        async def gj(ep):
            try:
                r = await cli.get(ep); return r.json() if r.status_code == 200 else None
            except Exception:
                return None
        # unidades (ambos availability)
        n_uds = 0
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
        pk_l = (await gj(f"/parking/project/{jb_id}/list/0")) or {}
        st_l = (await gj(f"/store/project/{jb_id}/list/0")) or {}
        pc_l = (await gj(f"/pack/project/{jb_id}/list/0")) or {}
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
        est = max(len(pk_l.get("parkings", []) or []), len(assets.get("parkings", []) or []))
        bod = max(len(st_l.get("stores", []) or []), len(assets.get("stores", []) or []))
        pck = max(len(pc_l.get("packs", []) or []), len(assets.get("packs", []) or []))
        total = n_uds + est + bod + pck
        await cli.aclose()
        results.append({"nombre": nombre, "jb_id": jb_id, "uds": n_uds,
                        "est": est, "bod": bod, "pck": pck, "total": total})
        print(f"   {nombre:<30} {jb_id:<11} uds={n_uds:<4} E={est:<4} B={bod:<4} P={pck:<3} → {total}", flush=True)
    await imp.close()
    print(f"\n{'═'*90}\nRANKING INGEVEC PENDIENTES (por stock total)\n{'═'*90}")
    results.sort(key=lambda r: -r["total"])
    for i, r in enumerate(results, start=1):
        print(f"  {i:>2}. {r['nombre']:<30} {r['jb_id']:<11} uds={r['uds']:<4} E={r['est']:<4} B={r['bod']:<4} P={r['pck']:<3} TOTAL={r['total']}")


if __name__ == "__main__":
    asyncio.run(main())
