"""
diag_pipeline.py — Confirma el pipeline API-first completo de JB 7.43.1.

1. Captura el body real del POST /project/organization/{org}/list/{ts} (lista de
   proyectos de BigCapital) y lo re-ejecuta con timestamp fresco → lista completa.
2. Guarda la lista completa (todos los ids nuevos + nombres) como artefacto.
3. Toma 3 proyectos de ESA lista (garantizado accesibles) y prueba los endpoints
   de detalle → confirma 200 y captura el esquema de modelos/plantas/unidades.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS, JB_ORG (default uv13koru)
"""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
ORG = os.environ.get("JB_ORG", "uv13koru")

DETAIL_GET = [
    "/project/{id}",
    "/apartment-model/project/{id}/all",
    "/apartment-model/project/{id}/list/0",
    "/store/project/{id}/available",
    "/store/project/{id}/list/0",
    "/parking/project/{id}/available",
    "/parking/project/{id}/list/0",
    "/pack/project/{id}/available",
    "/project/{id}/tipology",
    "/project/{id}/facing",
    "/project/{id}/document/all",
]
DETAIL_POST = [
    ("/apartment/search", {"projectJsId": "{id}", "page": 0}),
    ("/apartment/search", {"project": "{id}", "page": 0}),
]


def _summ(j):
    if isinstance(j, list):
        return f"list[{len(j)}] item0keys={list(j[0].keys()) if j and isinstance(j[0], dict) else None}"
    if isinstance(j, dict):
        return f"dict keys={list(j.keys())}"
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

    # ── Capturar el body real del POST list ──
    page = imp._page
    post_body = {}

    def on_req(req):
        if f"/organization/{ORG}/list/" in req.url and req.method == "POST":
            try:
                pd = req.post_data
                if pd:
                    post_body.update(json.loads(pd))
            except Exception:
                pass
    page.on("request", on_req)
    try:
        await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=40_000)
        await page.wait_for_timeout(3_500)
    except Exception as e:
        print(f"  goto err: {str(e)[:60]}", flush=True)
    page.remove_listener("request", on_req)
    print(f"### Body real del POST list capturado: {json.dumps(post_body)[:300]}", flush=True)

    async with imp._jb_httpx() as cli:
        # ── Re-ejecutar con timestamp fresco ──
        ts = int(time.time() * 1000)
        projects = []
        for body in (post_body, {}, {"page": 0}, {"filters": {}}):
            try:
                r = await cli.post(f"/project/organization/{ORG}/list/{ts}", json=body)
                if r.status_code in (200, 201):
                    data = r.json()
                    projects = data.get("projects") if isinstance(data, dict) else data
                    if projects:
                        print(f"### Lista OK con body={json.dumps(body)[:80]} → {len(projects)} proyectos (status {r.status_code})", flush=True)
                        break
                else:
                    print(f"   list body={json.dumps(body)[:40]} → {r.status_code}", flush=True)
            except Exception as e:
                print(f"   list err: {str(e)[:60]}", flush=True)

        if projects:
            (OUT / "bigcapital_projects.json").write_text(json.dumps(projects, indent=2, ensure_ascii=False))
            print(f"\n### {len(projects)} proyectos de BigCapital guardados. Primeros 8:", flush=True)
            for p in projects[:8]:
                print(f"   {p.get('id'):12} {(p.get('name') or '')[:34]:34} {(p.get('locality') or '')[:18]:18} org={(p.get('organization') or {}).get('name')}", flush=True)

        # ── Probar detalle en 3 proyectos de la lista ──
        for p in (projects or [])[:3]:
            sid = p.get("id")
            name = p.get("name")
            print(f"\n{'='*70}\n=== DETALLE {name} (id {sid}) ===\n{'='*70}", flush=True)
            for tmpl in DETAIL_GET:
                ep = tmpl.replace("{id}", sid)
                try:
                    r = await cli.get(ep)
                    info = ""
                    if r.status_code == 200:
                        try:
                            j = r.json()
                            info = _summ(j)
                            fn = "pipe-" + sid + "-" + ep.strip("/").replace("/", "_") + ".json"
                            (OUT / fn).write_text(json.dumps(j, indent=2, ensure_ascii=False)[:40000])
                        except Exception:
                            info = f"({len(r.text)}b no-json)"
                    print(f"  [{r.status_code}] GET  {ep}   {info}", flush=True)
                except Exception as e:
                    print(f"  ERR GET {ep}: {str(e)[:40]}", flush=True)
                await asyncio.sleep(0.15)
            for ep, btmpl in DETAIL_POST:
                body = {k: (v.replace("{id}", sid) if isinstance(v, str) else v) for k, v in btmpl.items()}
                try:
                    r = await cli.post(ep, json=body)
                    info = _summ(r.json()) if r.status_code in (200, 201) else ""
                    if r.status_code in (200, 201):
                        fn = "pipe-" + sid + "-apartment_search.json"
                        (OUT / fn).write_text(json.dumps(r.json(), indent=2, ensure_ascii=False)[:40000])
                    print(f"  [{r.status_code}] POST {ep} body={body}   {info}", flush=True)
                except Exception as e:
                    print(f"  ERR POST {ep}: {str(e)[:40]}", flush=True)
                await asyncio.sleep(0.15)

    await imp.close()
    print(f"\n✓ bigcapital_projects.json + pipe-*.json en imports/_diag/", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
