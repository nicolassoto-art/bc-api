"""
diag_auth.py — Resuelve el 401: ¿es el header de versión (7.42.0 vs 7.43.1) o el token?

1. Captura los HEADERS REALES que manda la app en una llamada 200 (/projectstore-card/projects)
   — sin filtrar el token completo a los logs (solo longitud + prefijo).
2. Prueba los endpoints de detalle con el ID nuevo usando v7.42.0 vs v7.43.1.
3. Si la app usa un token distinto al de localStorage, prueba también con ese.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_ID (default XZvaYdNg)
"""
from __future__ import annotations
import asyncio, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa: E402
import httpx  # noqa: E402

TEST_ID = os.environ.get("DIAG_ID", "XZvaYdNg")
ENDPOINTS = [
    "/project/{id}",
    "/apartment-model/project/{id}/all",
    "/apartment-model/project/{id}/list/0",
    "/store/project/{id}/available",
    "/project/{id}/tipology",
]


def _mask(tok: str) -> str:
    if not tok:
        return "(vacío)"
    return f"len={len(tok)} pref={tok[:6]}… suf=…{tok[-4:]}"


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=Path("imports/_diag"),
    )
    await imp.login()
    ls_token = imp._jb_token
    print(f"\nToken localStorage: {_mask(ls_token)}", flush=True)

    # ── Capturar headers REALES de la app en una llamada 200 ──
    page = imp._page
    app_headers = {}

    def on_req(req):
        if "jetbrokers.io/api/projectstore-card/projects" in req.url:
            app_headers.update(req.headers)
    page.on("request", on_req)
    try:
        await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=40_000)
        await page.wait_for_timeout(3_000)
    except Exception as e:
        print(f"  goto catalog err: {str(e)[:60]}", flush=True)
    page.remove_listener("request", on_req)

    print("\n### Headers que manda la APP (llamada 200):", flush=True)
    app_auth = app_headers.get("authorization", "")
    app_token = app_auth.replace("Bearer ", "").strip() if app_auth else ""
    interesting = ["jet-brokers-version", "device", "organization", "x-organization",
                   "x-org", "content-type", "accept", "origin", "referer", "user-agent"]
    for k in interesting:
        if k in app_headers:
            print(f"   {k}: {app_headers[k][:60]}", flush=True)
    print(f"   authorization token: {_mask(app_token)}", flush=True)
    print(f"   ¿app token == localStorage token? {app_token == ls_token}", flush=True)
    # listar TODAS las keys de headers que manda la app (sin valores sensibles)
    print(f"   (todas las header-keys de la app: {sorted(app_headers.keys())})", flush=True)

    # ── Probar endpoints con v7.42.0 vs v7.43.1, token localStorage ──
    tokens = {"localStorage": ls_token}
    if app_token and app_token != ls_token:
        tokens["app"] = app_token

    for tname, tok in tokens.items():
        for ver in ("7.42.0", "7.43.1"):
            h = {**JB_HEADERS, "jet-brokers-version": ver, "Authorization": f"Bearer {tok}"}
            print(f"\n### token={tname} · version={ver}", flush=True)
            async with httpx.AsyncClient(base_url=JB_API_BASE, headers=h, timeout=20.0) as cli:
                for tmpl in ENDPOINTS:
                    ep = tmpl.replace("{id}", TEST_ID)
                    try:
                        r = await cli.get(ep)
                        extra = ""
                        if r.status_code == 200:
                            try:
                                j = r.json()
                                if isinstance(j, list):
                                    extra = f"list[{len(j)}]"
                                elif isinstance(j, dict):
                                    extra = f"dict keys={list(j.keys())[:18]}"
                            except Exception:
                                extra = f"{len(r.text)}b"
                        print(f"   [{r.status_code}] {ep}   {extra}", flush=True)
                    except Exception as e:
                        print(f"   ERR {ep}: {str(e)[:40]}", flush=True)

    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
