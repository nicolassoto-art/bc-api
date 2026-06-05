"""
diag_detail.py — Caza el endpoint de DETALLE de proyecto en la API pública JB 7.43.1.

JB migró a IDs nuevos (store-card ids tipo 'XZvaYdNg'). Los slugs viejos dan 404.
Este script:
  1. Baja el catálogo completo /projectstore-card/projects (todos los ids nuevos).
  2. Para un proyecto objetivo (match por nombre), prueba MUCHAS formas de endpoint
     de detalle con el ID NUEVO → encuentra cuál entrega modelos/plantas/fotos/unidades.
  3. Además navega la ficha pública en la UI y captura el tráfico real (passive).
  4. Guarda catalog.json + los bodies de detalle como artefactos.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_TARGETS (csv nombres).
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
TARGET_NAMES = [s.strip().lower() for s in os.environ.get("DIAG_TARGETS", "Vivaceta,Serrano,Rioja").split(",") if s.strip()]

GET_CANDIDATES = [
    "/project/{id}",
    "/projectstore-card/project/{id}",
    "/projectstore-card/{id}",
    "/projectstore/{id}",
    "/store/project/{id}",
    "/store/project/{id}/available",
    "/store/project/{id}/list/0",
    "/apartment-model/project/{id}/all",
    "/apartment-model/project/{id}/list/0",
    "/apartment/project/{id}/all",
    "/apartment/project/{id}/list/0",
    "/parking/project/{id}/available",
    "/pack/project/{id}/available",
    "/project/{id}/tipology",
    "/project/{id}/facing",
    "/project/{id}/gallery",
    "/project/{id}/image/all",
    "/project/{id}/images",
    "/project/{id}/document/all",
    "/project/{id}/model/all",
    "/project/{id}/apartment-model/all",
]
POST_CANDIDATES = [
    ("/apartment/search", {"projectJsId": "{id}"}),
    ("/apartment/search", {"projectId": "{id}"}),
    ("/apartment/search", {"project": "{id}"}),
]


def _summ(j):
    if isinstance(j, list):
        return f"list[{len(j)}] item0keys={list(j[0].keys())[:30] if j and isinstance(j[0], dict) else None}"
    if isinstance(j, dict):
        return f"dict keys={list(j.keys())[:35]}"
    return type(j).__name__


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=OUT,
    )
    await imp.login()

    async with imp._jb_httpx() as cli:
        r = await cli.get("/projectstore-card/projects")
        cat = r.json() if r.status_code == 200 else []
        (OUT / "catalog.json").write_text(json.dumps(cat, indent=2, ensure_ascii=False))
        print(f"### Catálogo: {len(cat)} proyectos (status {r.status_code})\n", flush=True)

        # elegir objetivos por nombre
        targets = []
        for p in cat:
            n = (p.get("name") or "").strip()
            if any(k in n.lower() for k in TARGET_NAMES):
                targets.append((n, p.get("id"), (p.get("organization") or {}).get("name")))
        print(f"### Objetivos encontrados ({len(targets)}):", flush=True)
        for n, sid, org in targets[:10]:
            print(f"   {sid:14} {n:35} org={org}", flush=True)

        # probar endpoints de detalle con el ID NUEVO
        for n, sid, org in targets[:2]:
            print(f"\n{'='*70}\n=== DETALLE: {n} (id nuevo {sid}) ===\n{'='*70}", flush=True)
            for tmpl in GET_CANDIDATES:
                ep = tmpl.replace("{id}", sid)
                try:
                    rr = await cli.get(ep)
                    info = ""
                    if rr.status_code == 200:
                        try:
                            j = rr.json()
                            info = _summ(j)
                            fn = "detail-" + sid + "-" + ep.strip("/").replace("/", "_") + ".json"
                            (OUT / fn).write_text(json.dumps(j, indent=2, ensure_ascii=False)[:30000])
                        except Exception:
                            info = f"(no-json, {len(rr.text)} bytes)"
                    print(f"  [{rr.status_code}] GET  {ep}   {info}", flush=True)
                except Exception as e:
                    print(f"  ERR  GET {ep}: {str(e)[:50]}", flush=True)
                await asyncio.sleep(0.2)
            for ep, btmpl in POST_CANDIDATES:
                body = {k: (v.replace("{id}", sid) if isinstance(v, str) else v) for k, v in btmpl.items()}
                try:
                    rr = await cli.post(ep, json=body)
                    info = _summ(rr.json()) if rr.status_code in (200, 201) else ""
                    print(f"  [{rr.status_code}] POST {ep} body={body}   {info}", flush=True)
                except Exception as e:
                    print(f"  ERR  POST {ep}: {str(e)[:50]}", flush=True)
                await asyncio.sleep(0.2)

    # ── Passive: navegar la ficha pública en la UI y capturar tráfico ──
    page = imp._page
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and resp.request.method in ("GET", "POST"):
            cap.append({"m": resp.request.method, "url": resp.url, "status": resp.status})
    page.on("response", on_resp)

    if targets:
        sid = targets[0][1]
        print(f"\n### Navegando ficha pública UI para {sid} ...", flush=True)
        for route in (f"https://app.jetbrokers.io/store/project/{sid}",
                      f"https://app.jetbrokers.io/projectstore/{sid}",
                      f"https://app.jetbrokers.io/catalog/project/{sid}"):
            cap.clear()
            try:
                await page.goto(route, wait_until="networkidle", timeout=40_000)
                await page.wait_for_timeout(3_500)
                await imp._dismiss_popups()
                await page.screenshot(path=str(OUT / f"detail-ui-{route.rsplit('/',2)[-2]}.png"), full_page=True)
                rel = [c for c in cap if any(k in c["url"].lower() for k in
                       ("apartment", "model", "store", "project/", "parking", "pack", "tipolog", "facing"))]
                print(f"   {route} (final {page.url}) → {len(rel)} llamadas relevantes:", flush=True)
                seen = set()
                for c in rel:
                    p = c["url"].split("/api", 1)[-1].split("?")[0]
                    if p in seen: continue
                    seen.add(p)
                    print(f"      [{c['status']}] {c['m']} {p}", flush=True)
            except Exception as e:
                print(f"   {route}: {str(e)[:60]}", flush=True)

    await imp.close()
    print(f"\n✓ catalog.json + detail-*.json en imports/_diag/", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
