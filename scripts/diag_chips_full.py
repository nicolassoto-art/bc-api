"""
diag_chips_full.py — Verificación COMPLETA de los 4 grupos de chips:
etiquetas, areas_comunes, equipamiento, entorno.

1. Lee bc-api: por proyecto, qué grupos tiene y cuáles faltan (+ jb_id exacto).
2. Para los proyectos que les falta ALGÚN grupo, scrapea JB directo y compara.
3. Reporta GAP REAL (JB tiene, bc-api no) vs correcto (JB tampoco tiene).
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter
import httpx

GROUPS = ["etiquetas", "areas_comunes", "equipamiento", "entorno"]
CHIP_GROUPS_MAP = {
    "etiquetas": ["etiqueta"],
    "areas_comunes": ["area", "areas comune"],
    "equipamiento": ["equipamiento", "terminaciones"],
    "entorno": ["entorno"],
}
CHIP_JS = r"""(groupsMap) => {
    const result = {};
    const formGroups = document.querySelectorAll('.form-group');
    for (const g of formGroups) {
        const lbl = g.querySelector('label');
        if (!lbl) continue;
        const t = (lbl.innerText || '').trim().toLowerCase();
        for (const [key, patterns] of Object.entries(groupsMap)) {
            if (patterns.some(p => t.includes(p))) {
                const labels = [...g.querySelectorAll('.ng-value-label')]
                    .map(s => (s.innerText || '').trim())
                    .filter(x => x && x !== '×' && x.length < 300);
                if (labels.length) result[key] = labels;
                break;
            }
        }
    }
    return result;
}"""


async def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

    listing = cli.get("/proyectos").json()
    print(f"Total proyectos: {len(listing)}")

    # Paso 1: leer bc-api, detectar faltantes + jb_id exacto
    faltantes = []  # (jb_id, nombre, [grupos que faltan])
    cobertura = {g: 0 for g in GROUPS}
    for p in listing:
        pid = p.get("id")
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception:
            continue
        extra = full.get("extra") or {}
        jb_id = extra.get("jb_id") or ""
        nombre = full.get("nombre") or ""
        falta = []
        for g in GROUPS:
            v = extra.get(g) or []
            if isinstance(v, list) and v:
                cobertura[g] += 1
            else:
                falta.append(g)
        if falta and jb_id:
            faltantes.append((jb_id, nombre, falta))

    print("\n=== COBERTURA bc-api ===")
    for g in GROUPS:
        print(f"  {g:15s}: {cobertura[g]}/{len(listing)}")
    print(f"\nProyectos con algún grupo faltante: {len(faltantes)}")

    # Paso 2: scrapear JB solo para los faltantes
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base, bc_jwt=jwt, headless=True,
    )
    gaps_reales = []   # (jb_id, nombre, {grupo: [valores JB que faltan]})
    try:
        await imp.login()
        for jb_id, nombre, falta in faltantes:
            try:
                url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
                await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
                await imp._page.wait_for_timeout(3_500)
                await imp._dismiss_popups()
                jb_chips = {}
                for _ in range(3):
                    res = await imp._page.evaluate(CHIP_JS, CHIP_GROUPS_MAP)
                    if res:
                        jb_chips = res
                        break
                    await imp._page.wait_for_timeout(1_500)
                # ¿JB tiene alguno de los grupos que a bc-api le faltan?
                gap = {g: jb_chips.get(g) for g in falta if jb_chips.get(g)}
                if gap:
                    gaps_reales.append((jb_id, nombre, gap))
                    print(f"  ⚠ {nombre[:28]:28s} ({jb_id}) GAP: {gap}")
                else:
                    print(f"  ✓ {nombre[:28]:28s} ({jb_id}) — JB tampoco tiene {falta}")
            except Exception as e:
                print(f"  ✗ {nombre} ({jb_id}): {e}")
    finally:
        await imp.close()

    print(f"\n===== RESUMEN FINAL =====")
    print(f"GAPS REALES (JB tiene, bc-api NO): {len(gaps_reales)} proyectos")
    for jb_id, nombre, gap in gaps_reales:
        for g, vals in gap.items():
            print(f"    {jb_id:12s} {nombre[:28]:28s} {g}: {vals}")
    if not gaps_reales:
        print("  ✅ TODO COMPLETO — bc-api tiene todos los chips que JB expone.")


if __name__ == "__main__":
    asyncio.run(main())
