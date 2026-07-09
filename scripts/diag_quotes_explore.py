"""
diag_quotes_explore.py — Explorador de la sección /quotes de JetBroker (server-side, solo lectura).

Corre en GitHub Actions (login automatizado, NUNCA Chrome local). `/quotes`
hoy solo se usa como Referer falso en otros diag scripts (diag_bod_raw.py,
diag_csv_batch.py, diag_euro.py) -- nunca se navegó de verdad. Objetivo:
  1. Confirmar que la ruta existe y qué UI renderiza.
  2. Catalogar qué endpoints /api/ dispara esa página (listado de
     cotizaciones, filtros, paginación) y qué campos trae cada cotización
     (cliente, rut, proyecto, unidad, UF, fecha, corredor, estado).
  3. Determinar si sirve como fuente adicional de cotizaciones (hoy
     Herramientas BC solo importa PDFs de JetBroker manualmente,
     origen=pdf_jb, en su propio sistema de cotizaciones).

Todo queda en imports/_diag_quotes/ (artefacto). NO escribe en bc-api.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag_quotes")
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
            e["body"] = txt[:8000]
        except Exception as ex:
            e["body_err"] = str(ex)[:80]
        cap.append(e)

    page.on("response", on_response)

    async def shot(name):
        try:
            await page.screenshot(path=str(OUT / name), full_page=True)
        except Exception:
            pass

    print("\n### Navegando a /quotes", flush=True)
    try:
        await page.goto("https://app.jetbrokers.io/quotes", wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(4_000)
        print(f"   ✓ url final: {page.url}", flush=True)
        await shot("01-quotes.png")
    except Exception as ex:
        print(f"   ✗ goto /quotes: {str(ex)[:120]}", flush=True)

    # DOM crudo: cuántas filas trae la tabla/lista (si existe) -- sin leer
    # contenido de celdas todavía, solo estructura.
    try:
        n_rows = await page.evaluate("""() => {
            const t = document.querySelector('table tbody');
            if (t) return {kind: 'table', rows: t.querySelectorAll('tr').length};
            const cards = document.querySelectorAll('[class*="quote"], [class*="cotiz"]');
            return {kind: 'cards?', count: cards.length};
        }""")
        print(f"   estructura DOM: {n_rows}", flush=True)
    except Exception as ex:
        print(f"   eval DOM err: {str(ex)[:80]}", flush=True)

    # Variantes de ruta por si /quotes es solo un shell y el listado real
    # vive en otra ruta (mismo patrón de prueba que diag_api_explore.py).
    for route in ("https://app.jetbrokers.io/quotes/list",
                  "https://app.jetbrokers.io/quotations",
                  "https://app.jetbrokers.io/proposals"):
        try:
            await page.goto(route, wait_until="networkidle", timeout=30_000)
            await page.wait_for_timeout(2_500)
            print(f"   ✓ goto {route} (url final: {page.url})", flush=True)
        except Exception as ex:
            print(f"   ✗ {route}: {str(ex)[:60]}", flush=True)

    page.remove_listener("response", on_response)
    await imp.close()

    (OUT / "quotes_explore_full.json").write_text(json.dumps(cap, indent=2, default=str))
    print(f"\n{'='*70}\n=== ENDPOINTS 200 CON DATOS (lo que /quotes SÍ entrega) ===\n{'='*70}", flush=True)
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
    print(f"\nHistograma global de status: {dict(Counter(c['status'] for c in cap))}", flush=True)
    print(f"Total llamadas capturadas: {len(cap)}", flush=True)
    print(f"Dump completo: imports/_diag_quotes/quotes_explore_full.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
