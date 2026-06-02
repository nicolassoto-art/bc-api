"""
audit_assets_vs_jb.py — Audita fotos+plantas en bc-api y compara con JB.

1. Lista proyectos con 0 fotos O 0 plantas en bc-api.
2. Para esos: abre tab Documentos en JB y cuenta fotos+plantas reales.
3. Reporta: si JB tiene > bc-api → REGRESIÓN (re-import necesario)
                   si JB == 0 → OK (JB tampoco tiene).
"""
from __future__ import annotations
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter
import httpx


async def count_jb_assets(imp: JBImporter, jb_id: str) -> dict:
    """Navega a /projects/edit/{jb_id} → tab Documentos y cuenta tipos."""
    url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
    await imp._page.goto(url, wait_until="networkidle", timeout=45_000)
    await imp._page.wait_for_timeout(2500)
    await imp._dismiss_popups()
    try:
        await imp._click_tab("Documentos")
    except Exception:
        return {"err": "no_tab"}
    await imp._page.wait_for_timeout(2500)
    # Cargar todas las filas (paginación)
    try:
        await imp._load_all_table_rows()
    except Exception:
        pass
    # Contar filas y clasificar por tipo (la columna Tipo dice "Fotos áreas comunes", "Fotos modelos", etc)
    return await imp._page.evaluate(r"""() => {
        const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
        const trs = scope.querySelectorAll('table tbody tr');
        const out = {total: trs.length, fotos: 0, planos: 0, docs: 0, tipos: {}};
        trs.forEach(tr => {
            const cells = [...tr.querySelectorAll('td')].map(c => (c.innerText||'').trim());
            const tipo = (cells.find(c => /foto|plano|plant|video|doc|brochure|mapa|cotiza/i.test(c)) || '').toLowerCase();
            out.tipos[tipo] = (out.tipos[tipo]||0) + 1;
            if (/plano|plant/.test(tipo)) out.planos++;
            else if (/foto|video|imagen/.test(tipo)) out.fotos++;
            else out.docs++;
        });
        return out;
    }""")


async def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

    listing = cli.get("/proyectos").json()
    print(f"Total proyectos en bc-api: {len(listing)}\n")

    # Paso 1: encontrar proyectos con 0 fotos o 0 plantas
    candidatos = []
    for p in listing:
        try:
            full = cli.get(f"/proyectos/{p['id']}").json()
        except Exception: continue
        imgs = full.get("imagenes") or []
        fotos = sum(1 for i in imgs if (i.get("categoria") or "") != "plano" and not (i.get("categoria") or "").startswith("jb-planta"))
        planos = sum(1 for i in imgs if "plano" in (i.get("categoria") or "") or (i.get("categoria") or "").startswith("jb-planta"))
        jb_id = (full.get("extra") or {}).get("jb_id") or ""
        if (fotos == 0 or planos == 0) and jb_id:
            candidatos.append({"pid": p["id"], "jb_id": jb_id, "nombre": full.get("nombre","")[:35], "inmo": (full.get("inmobiliaria") or "")[:15], "fotos": fotos, "planos": planos})

    print(f"=== Proyectos con 0 fotos o 0 plantas en bc-api: {len(candidatos)} ===\n")
    for c in candidatos:
        print(f"  {c['jb_id']:12s} {c['inmo']:15s} {c['nombre']:35s} F={c['fotos']:>3d} P={c['planos']:>3d}")

    if not candidatos:
        print("✅ Nada que revisar.")
        return

    # Paso 2: scrape JB
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base, bc_jwt=jwt, headless=True,
    )
    print(f"\n=== Comparando con JB ({len(candidatos)} proyectos a revisar) ===\n")
    print(f"{'jb_id':<12} {'Nombre':<35} {'bc F/P':<10} {'JB F/P':<10} {'Veredicto':<25}")
    print("-" * 100)
    regresiones = []
    try:
        await imp.login()
        for c in candidatos:
            try:
                info = await count_jb_assets(imp, c["jb_id"])
                if "err" in info:
                    bcfp = f"{c['fotos']}/{c['planos']}"
                    print(f"  {c['jb_id']:<12} {c['nombre']:<35} {bcfp:<10} -          err={info['err']}")
                    continue
                jb_f = info.get("fotos", 0)
                jb_p = info.get("planos", 0)
                bc_f = c["fotos"]; bc_p = c["planos"]
                # Veredicto
                missing_f = jb_f - bc_f
                missing_p = jb_p - bc_p
                if missing_f > 0 or missing_p > 0:
                    veredicto = f"⚠ REGRESIÓN (faltan F={missing_f} P={missing_p})"
                    regresiones.append({**c, "jb_fotos": jb_f, "jb_planos": jb_p, "missing_f": missing_f, "missing_p": missing_p})
                else:
                    veredicto = "✓ OK (JB tampoco tiene)"
                print(f"  {c['jb_id']:<12} {c['nombre']:<35} {f'{bc_f}/{bc_p}':<10} {f'{jb_f}/{jb_p}':<10} {veredicto}")
            except Exception as e:
                print(f"  {c['jb_id']:<12} {c['nombre']:<35} ERROR: {str(e)[:50]}")
    finally:
        await imp.close()

    print(f"\n=== RESUMEN ===")
    print(f"Regresiones (re-import necesario): {len(regresiones)}")
    for r in regresiones:
        print(f"  → {r['jb_id']} ({r['nombre']}): faltan F={r['missing_f']} P={r['missing_p']}")


if __name__ == "__main__":
    asyncio.run(main())
