"""diag_stock_extra.py — Encuentra endpoints de estacionamientos/bodegas/packs (proyectos propios)."""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

PID = os.environ.get("DIAG_ID", "exrBr6Tp")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)

GETS = [
    "/parking/project/{id}/all", "/parking/project/{id}/list/0", "/parking/project/{id}/available",
    "/store/project/{id}/all", "/store/project/{id}/list/0", "/store/project/{id}/available",
    "/pack/project/{id}/all", "/pack/project/{id}/list/0", "/pack/project/{id}/available",
    "/project/{id}/parking", "/project/{id}/store", "/project/{id}/totals",
]
POSTS = [
    ("/parking/project-detail-search/{ts}", {"projectId": "{id}", "element": 0, "elements": 9999}),
    ("/store/project-detail-search/{ts}", {"projectId": "{id}", "element": 0, "elements": 9999}),
    ("/apartment/project-detail-search/{ts}", {"projectId": "{id}", "type": "parking", "element": 0, "elements": 9999, "tipologies": [], "order": "ASC", "models": [], "facings": [], "availability": None, "number": None}),
    ("/apartment/project-detail-search/{ts}", {"projectId": "{id}", "type": "storage", "element": 0, "elements": 9999, "tipologies": [], "order": "ASC", "models": [], "facings": [], "availability": None, "number": None}),
]


def summ(j):
    if isinstance(j, list):
        return f"list[{len(j)}] " + (json.dumps(j[0], ensure_ascii=False)[:200] if j else "")
    if isinstance(j, dict):
        ks = list(j.keys())
        out = f"dict {ks[:12]}"
        for k in ("apartments", "elements", "data", "parkings", "stores"):
            if isinstance(j.get(k), list):
                out += f" · {k}[{len(j[k])}] " + (json.dumps(j[k][0], ensure_ascii=False)[:200] if j[k] else "")
        return out
    return str(j)[:80]


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    await imp._page.goto(f"https://app.jetbrokers.io/projects/detail/{PID}", wait_until="networkidle", timeout=50_000)
    await imp._page.wait_for_timeout(3_000)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1", "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": f"https://app.jetbrokers.io/projects/detail/{PID}"})
    print(f"### {PID}\n", flush=True)
    for tmpl in GETS:
        ep = tmpl.replace("{id}", PID)
        try:
            r = await cli.get(ep)
            print(f"  [{r.status_code}] GET  {ep}   {summ(r.json()) if r.status_code==200 else ''}", flush=True)
        except Exception as e:
            print(f"  ERR GET {ep}: {str(e)[:40]}", flush=True)
    for tmpl, body in POSTS:
        ep = tmpl.replace("{ts}", str(int(time.time()*1000)))
        b = {k: (v.replace("{id}", PID) if isinstance(v, str) else v) for k, v in body.items()}
        try:
            r = await cli.post(ep, json=b)
            print(f"  [{r.status_code}] POST {tmpl.split('{')[0]} type={b.get('type','-')}   {summ(r.json()) if r.status_code in (200,201) else ''}", flush=True)
        except Exception as e:
            print(f"  ERR POST {ep}: {str(e)[:40]}", flush=True)
    await cli.aclose(); await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
