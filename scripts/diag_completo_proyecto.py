"""
diag_completo_proyecto.py — Compara TODO lo que bc-api tiene vs lo que JB expone
para proyectos específicos. Busca qué NO importamos.

Revisa: unidades, bodegas, estac, packs, documentos, modelos, notas, comisión,
arriendos, y todas las keys de extra. Scrapea JB editor tab por tab.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter
import httpx

# Proyectos a investigar (jb_id exacto, id bc-api)
TARGETS = [
    ("1kvflc3m", "jb-1kvflc3m", "Vicuña Mackenna 1796"),
    ("T8UuEf2r", "jb-t8uuef2r", "Santa Rosa 250"),
]


async def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

    # ── Lo que bc-api tiene ──
    for jb_id, pid, nombre in TARGETS:
        print(f"\n{'='*70}\n=== bc-api: {nombre} ({pid}) ===")
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"  error: {e}"); continue
        extra = p.get("extra") or {}
        print(f"  unidades (filas):     {len(p.get('unidades') or [])}")
        print(f"  documentos:           {len(p.get('documentos') or [])}")
        print(f"  imagenes:             {len(p.get('imagenes') or [])}")
        print(f"  extra.bodegas_dom:    {len(extra.get('bodegas_dom') or [])}")
        print(f"  extra.estacionamientos_dom: {len(extra.get('estacionamientos_dom') or [])}")
        print(f"  extra.modelos:        {len(extra.get('modelos') or [])}")
        fis = extra.get('fisicos') or {}
        print(f"  fisicos.unidades_totales: {fis.get('unidades_totales')}")
        print(f"  fisicos.estac_totales:    {fis.get('estacionamientos_totales')}")
        print(f"  fisicos.bodegas_totales:  {fis.get('bodegas_totales')}")
        print(f"  TODAS las keys de extra: {sorted(extra.keys())}")

    # ── Lo que JB expone (scrape editor) ──
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base, bc_jwt=jwt, headless=True,
    )
    try:
        await imp.login()
        for jb_id, pid, nombre in TARGETS:
            print(f"\n{'='*70}\n=== JB editor: {nombre} ({jb_id}) ===")
            # API units
            try:
                async with imp._jb_httpx() as c:
                    units = []
                    for ep in (f"/store/project/{jb_id}/available", f"/apartment-model/project/{jb_id}/all"):
                        try:
                            r = await c.get(ep)
                            if r.status_code == 200:
                                d = r.json()
                                items = d if isinstance(d, list) else (d.get('data') or [])
                                print(f"  API {ep}: {len(items)} items")
                                if items and isinstance(items[0], dict):
                                    print(f"      keys: {sorted(items[0].keys())}")
                                    print(f"      sample: { {k:items[0].get(k) for k in list(items[0].keys())[:8]} }")
                        except Exception as e:
                            print(f"  API {ep}: {e}")
            except Exception as e:
                print(f"  API err: {e}")

            # Interceptar XHR de la tab Unidades (busca endpoint con surfaces)
            captured_xhr = []
            async def on_resp(resp):
                try:
                    u = resp.url
                    if "/api/" not in u or resp.status != 200: return
                    if "json" not in resp.headers.get("content-type", "").lower(): return
                    j = await resp.json()
                    items = j if isinstance(j, list) else (j.get("data") or j.get("elements") or [])
                    if isinstance(items, list) and items and isinstance(items[0], dict):
                        ks = set(items[0].keys())
                        # ¿tiene superficies?
                        if any("surface" in k.lower() or "sup" in k.lower() for k in ks):
                            captured_xhr.append((u, len(items), sorted(ks), items[0]))
                except Exception: pass

            # Navegar editor y contar filas por tab
            try:
                imp._page.on("response", on_resp)
                await imp._page.goto(f"https://app.jetbrokers.io/projects/edit/{jb_id}", wait_until="networkidle", timeout=60_000)
                await imp._page.wait_for_timeout(3_500)
                await imp._dismiss_popups()
                for tab in ["Unidades", "Bodegas", "Estacionamientos", "Packs"]:
                    try:
                        await imp._click_tab(tab)
                        await imp._page.wait_for_timeout(2_500)
                        info = await imp._page.evaluate("""() => {
                            const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active, .mat-tab-body-active') || document;
                            const tables = [...scope.querySelectorAll('table')];
                            let best=null,bn=0; tables.forEach(t=>{const r=t.querySelectorAll('tbody tr').length; if(r>bn){bn=r;best=t;}});
                            if(!best) return {n:0};
                            const headers=[...best.querySelectorAll('thead th')].map(h=>(h.innerText||'').trim());
                            const r0=[...(best.querySelector('tbody tr')?.querySelectorAll('td')||[])].map(c=>(c.innerText||'').trim());
                            return {n:bn, headers, r0};
                        }""")
                        print(f"  TAB {tab}: {info.get('n')} filas · headers={info.get('headers')}")
                        if tab == "Unidades":
                            print(f"       row0={info.get('r0')}")
                    except Exception as e:
                        print(f"  TAB {tab}: {e}")
                imp._page.remove_listener("response", on_resp)
                print(f"  --- XHR con superficies capturados ({len(captured_xhr)}) ---")
                for u, n, ks, sample in captured_xhr:
                    print(f"    🔗 {u}")
                    print(f"       {n} items · keys: {ks}")
                    print(f"       sample: {json.dumps(sample, ensure_ascii=False)[:300]}")
            except Exception as e:
                print(f"  editor nav err: {e}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
