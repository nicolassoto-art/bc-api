"""
diag_sniff_api.py — Captura el CONTRATO REAL de la API JB 7.43.1 (solo lectura).

Escucha todas las peticiones a jetbrokers.io/api que hace la app cuando navegas
el editor y sus pestañas. Revela:
  - el valor real de jet-brokers-version que manda la app
  - los endpoints REALES de unidades/stock/modelos (que pudieron cambiar en 7.43.1)
  - el status de cada uno

Con esto sabemos exactamente qué arreglar en fetch_api (header de versión + rutas).

Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_IDS (csv, default igfwzvh2)
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

IDS = [s.strip() for s in os.environ.get("DIAG_IDS", "igfwzvh2").split(",") if s.strip()]
KEYWORDS = ["unit", "apart", "stock", "store", "model", "available", "project", "depto", "inventory"]


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=Path("imports/_diag"),
    )
    await imp.login()
    page = imp._page
    calls: list[dict] = []

    def on_request(req):
        if "jetbrokers.io/api" in req.url:
            calls.append({
                "method": req.method,
                "url": req.url,
                "version": req.headers.get("jet-brokers-version"),
                "device": req.headers.get("device"),
                "status": None,
            })

    def on_response(resp):
        if "jetbrokers.io/api" in resp.url:
            for c in reversed(calls):
                if c["url"] == resp.url and c["status"] is None:
                    c["status"] = resp.status
                    break

    page.on("request", on_request)
    page.on("response", on_response)

    all_dump = {}
    for jb_id in IDS:
        calls.clear()
        print(f"\n{'='*70}\n=== {jb_id} ===\n{'='*70}", flush=True)
        try:
            await page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}",
                            wait_until="networkidle", timeout=60_000)
            await page.wait_for_timeout(4_000)
            await imp._dismiss_popups()
        except Exception as e:
            print(f"  goto err: {e}", flush=True)
        for tab in ["Unidades", "Stock", "Modelos", "Bodegas", "Estacionamientos"]:
            try:
                await imp._click_tab(tab)
                await page.wait_for_timeout(3_500)
                print(f"  ✓ click tab '{tab}'", flush=True)
            except Exception as e:
                print(f"  ✗ tab '{tab}': {str(e)[:60]}", flush=True)
        await page.wait_for_timeout(2_000)

        versions = sorted({c["version"] for c in calls if c["version"]})
        print(f"\n  jet-brokers-version que manda la app: {versions}", flush=True)
        print(f"  total API calls capturadas: {len(calls)}", flush=True)
        # histograma de status
        from collections import Counter
        hist = Counter(c["status"] for c in calls)
        print(f"  histograma status: {dict(hist)}", flush=True)
        # endpoints que SÍ respondieron 200 (revela cómo carga el editor)
        print(f"  --- endpoints 200 OK ---", flush=True)
        seen200 = set()
        for c in calls:
            if c["status"] != 200:
                continue
            path = c["url"].split("jetbrokers.io/api", 1)[-1]
            sig = f"{c['method']} {path.split('?')[0]}"
            if sig in seen200:
                continue
            seen200.add(sig)
            print(f"    [200] {c['method']:<5} {path[:95]}", flush=True)
        print(f"  --- endpoints relevantes (unit/stock/model/project) ---", flush=True)
        seen = set()
        for c in calls:
            path = c["url"].split("jetbrokers.io/api", 1)[-1]
            low = path.lower()
            if not any(k in low for k in KEYWORDS):
                continue
            sig = f"{c['method']} {path.split('?')[0]}"
            if sig in seen:
                continue
            seen.add(sig)
            print(f"    [{c['status']}] {c['method']:<5} {path[:95]}", flush=True)
        all_dump[jb_id] = calls.copy()

    await imp.close()
    Path("imports/_diag").mkdir(parents=True, exist_ok=True)
    Path("imports/_diag/sniff_api.json").write_text(json.dumps(all_dump, indent=2, default=str))
    print(f"\n✓ dump completo en imports/_diag/sniff_api.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
