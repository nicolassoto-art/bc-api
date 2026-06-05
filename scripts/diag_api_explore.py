"""
diag_api_explore.py — Explorador PROFUNDO de la API JB (server-side, solo lectura).

Corre en GitHub Actions (login automatizado, NUNCA Chrome local). Objetivo:
  1. Resolver el 404: navegar como usuario REAL (lista → proyecto) y ver qué
     endpoints responden 200 con datos en la versión 7.43.1.
  2. Catalogar QUÉ entrega la API (modelos, plantas, fotos, descripción, unidades)
     → eso NO lo necesita el scraper.
  3. Detectar qué NO entrega la API → eso sí lo saca el scraper.

Captura el CUERPO de cada respuesta /api/ (truncado) + sus keys JSON, y screenshots
de las pestañas Modelos/Unidades para ver si la sesión headless renderiza datos.

Todo queda en imports/_diag/ (artefacto). NO escribe en bc-api.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_IDS (csv, default igfwzvh2,lmvjgz7f)
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

IDS = [s.strip() for s in os.environ.get("DIAG_IDS", "igfwzvh2,lmvjgz7f").split(",") if s.strip()]
OUT = Path("imports/_diag")
OUT.mkdir(parents=True, exist_ok=True)


def _keys_of(txt: str):
    try:
        j = json.loads(txt)
    except Exception:
        return None
    if isinstance(j, dict):
        return {"type": "dict", "keys": list(j.keys())[:40]}
    if isinstance(j, list):
        sample = j[0] if j and isinstance(j[0], dict) else None
        return {"type": f"list[{len(j)}]", "item_keys": list(sample.keys())[:40] if sample else None}
    return {"type": type(j).__name__}


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=OUT,
    )
    await imp.login()
    page = imp._page
    cap: list[dict] = []

    async def on_response(resp):
        if "jetbrokers.io/api" not in resp.url:
            return
        e = {"method": resp.request.method, "url": resp.url, "status": resp.status}
        try:
            txt = await resp.text()
            e["len"] = len(txt)
            e["json"] = _keys_of(txt)
            e["body"] = txt[:6000]
        except Exception as ex:
            e["body_err"] = str(ex)[:80]
        cap.append(e)

    page.on("response", on_response)

    async def shot(name):
        try:
            await page.screenshot(path=str(OUT / name), full_page=True)
        except Exception:
            pass

    # ── 1. Dashboard ──
    print("\n### 1. Dashboard tras login", flush=True)
    await page.wait_for_timeout(3_000)
    await shot("01-dashboard.png")

    # ── 2. Lista de proyectos (Catálogo / stock del broker) ──
    print("### 2. Navegando a lista de proyectos", flush=True)
    for route in ("https://app.jetbrokers.io/projects",
                  "https://app.jetbrokers.io/catalog",
                  "https://app.jetbrokers.io/store"):
        try:
            await page.goto(route, wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(3_500)
            print(f"   ✓ goto {route} (url final: {page.url})", flush=True)
            await shot(f"02-list-{route.rsplit('/',1)[-1]}.png")
        except Exception as ex:
            print(f"   ✗ {route}: {str(ex)[:60]}", flush=True)

    # ── 3. Por cada id objetivo: editor + tabs ──
    for jb_id in IDS:
        print(f"\n### 3. Proyecto {jb_id}", flush=True)
        cap_mark = len(cap)
        try:
            await page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}",
                            wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(4_000)
            await imp._dismiss_popups()
            await shot(f"03-{jb_id}-general.png")
        except Exception as ex:
            print(f"   goto editor err: {str(ex)[:80]}", flush=True)
        for tab in ("Modelos", "Unidades", "Stock", "Fotos", "Documentos"):
            try:
                await imp._click_tab(tab)
                await page.wait_for_timeout(3_000)
                n = await page.evaluate("""() => {
                    const s = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                    return s.querySelectorAll('table tbody tr').length;
                }""")
                print(f"   tab {tab:<12} → {n} filas tbody", flush=True)
                await shot(f"03-{jb_id}-{tab.lower()}.png")
            except Exception as ex:
                print(f"   tab {tab}: {str(ex)[:50]}", flush=True)
        # status de los endpoints que se llamaron para ESTE proyecto
        proj_calls = cap[cap_mark:]
        hist = Counter(c["status"] for c in proj_calls)
        print(f"   status de {len(proj_calls)} llamadas: {dict(hist)}", flush=True)

    page.remove_listener("response", on_response)
    await imp.close()

    # ── Dump + resumen ──
    (OUT / "api_explore_full.json").write_text(json.dumps(cap, indent=2, default=str))
    print(f"\n{'='*70}\n=== ENDPOINTS 200 OK CON DATOS (lo que la API SÍ entrega) ===\n{'='*70}", flush=True)
    seen = set()
    for c in cap:
        if c["status"] != 200:
            continue
        path = c["url"].split("jetbrokers.io/api", 1)[-1].split("?")[0]
        sig = f"{c['method']} {path}"
        if sig in seen:
            continue
        seen.add(sig)
        j = c.get("json") or {}
        print(f"  [{c['method']}] {path}", flush=True)
        print(f"       → {j.get('type','?')}  keys={j.get('keys') or j.get('item_keys')}", flush=True)
    print(f"\n{'='*70}\n=== ENDPOINTS 404 (contrato roto/cambiado) ===\n{'='*70}", flush=True)
    seen404 = set()
    for c in cap:
        if c["status"] != 404:
            continue
        path = c["url"].split("jetbrokers.io/api", 1)[-1].split("?")[0]
        if path in seen404:
            continue
        seen404.add(path)
        print(f"  [{c['method']}] {path}", flush=True)
    # histograma global
    print(f"\nHistograma global de status: {dict(Counter(c['status'] for c in cap))}", flush=True)
    print(f"Total llamadas capturadas: {len(cap)}", flush=True)
    print(f"Dump completo: imports/_diag/api_explore_full.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
