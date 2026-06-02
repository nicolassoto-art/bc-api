"""
scrape_superficies_individual.py — Para los 5 proyectos sin desglose
(Conexión Independencia, Los Alerces, Santa Rosa, V.Mackenna 1796, Almanova):

  1. Navega al editor JB del proyecto, tab Unidades, scrollea TODO (igual que
     el importer) y construye mapa {numero → jb_unit_id} desde los links de
     la tabla (href: /units/edit/{id}).
  2. GET unidades del proyecto en bc-api.
  3. Por cada unidad bc-api con número en el mapa, abre /units/edit/{jb_unit_id},
     lee Sup Interior/Terraza/Logia/Jardín, hace PUT a bc-api.
"""
from __future__ import annotations
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter
import httpx

TARGETS = [
    ("jb-48t1iinf", "48t1IInf", "Conexión Independencia"),
    ("jb-wwmcny3e", "WWMCny3E", "Los Alerces"),
    ("jb-t8uuef2r", "T8UuEf2r", "Santa Rosa 250"),
    ("jb-1kvflc3m", "1kvflc3m", "Vicuña Mackenna 1796"),
    ("jb-q8rwqxao", "q8RwqXao", "Almanova"),
]


async def build_numero_to_unitid_map(imp: JBImporter, jb_proj_id: str) -> dict[str, str]:
    """Scrapea la tab Unidades y devuelve {numero → jb_unit_id} desde href."""
    url = f"https://app.jetbrokers.io/projects/edit/{jb_proj_id}"
    await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
    await imp._page.wait_for_timeout(3000)
    await imp._dismiss_popups()
    await imp._click_tab("Unidades")
    await imp._page.wait_for_timeout(2500)
    # Disparar scroll humano: usar la misma lógica del importer
    rows = await imp._scrape_unidades_paginated(max_steps=80)
    mapa: dict[str, str] = {}
    for r in rows:
        cells = r.get("cells") or []
        headers = r.get("headers") or []
        if not cells or not headers: continue
        row_d = {(h or "").strip().lower(): (c or "").strip() for h, c in zip(headers, cells)}
        numero = row_d.get("número") or row_d.get("numero") or ""
        if not numero: continue
        for link in r.get("links") or []:
            m = re.search(r"/units?/(?:edit|view|detail)/([A-Za-z0-9_-]{6,14})", str(link))
            if m:
                mapa[numero] = m.group(1)
                break
    return mapa


async def read_unit_surfaces(imp, jb_unit_id: str) -> dict:
    """Abre /units/edit/{id} y lee Total/Interior/Terraza/Logia/Jardín."""
    url = f"https://app.jetbrokers.io/units/edit/{jb_unit_id}"
    await imp._page.goto(url, wait_until="domcontentloaded", timeout=20_000)
    await imp._page.wait_for_timeout(900)
    # Lectura por LABEL (insensible a tildes/typos)
    return await imp._page.evaluate(r"""() => {
        function norm(s){
            return (s||'').toString().normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/\./g,'').replace(/\s+/g,' ').trim();
        }
        const targets = {
            sup_total:    ['superficie total','sup total'],
            sup_interior: ['superficie interior','sup interior'],
            sup_terraza:  ['superficie terraza','superfice terraza','sup terraza'],
            sup_logia:    ['superficie logia','sup logia'],
            sup_jardin:   ['superficie jardin','sup jardin','superficie jardín'],
        };
        const out = {};
        const labels = [...document.querySelectorAll('label, mat-label, .mat-form-field-label, .form-group label, .form-label')];
        for (const lbl of labels) {
            const t = norm(lbl.innerText || lbl.textContent || '');
            for (const [k, candidates] of Object.entries(targets)) {
                if (out[k] != null) continue;
                if (!candidates.some(c => t === c || t.startsWith(c))) continue;
                // input asociado: en form-group o siguiente
                let p = lbl;
                for (let i=0; i<6 && p; i++) {
                    const inp = p.querySelector('input');
                    if (inp) {
                        const v = (inp.value || '').replace(/\./g,'').replace(',', '.').trim();
                        if (v && !isNaN(parseFloat(v))) {
                            out[k] = parseFloat(v);
                            break;
                        }
                    }
                    p = p.parentElement;
                }
            }
        }
        return out;
    }""")


async def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=bc_base, bc_jwt=jwt, headless=True,
    )
    try:
        await imp.login()
        for pid, jb_proj_id, nombre in TARGETS:
            print(f"\n{'='*60}\n=== {nombre} ({pid}) ===")
            try:
                full = cli.get(f"/proyectos/{pid}").json()
            except Exception as e:
                print(f"  ✗ get: {e}"); continue
            unidades = full.get("unidades") or []
            print(f"  {len(unidades)} unidades en bc-api")

            print(f"  → mapeando numero→jb_unit_id desde JB...")
            try:
                mapa = await build_numero_to_unitid_map(imp, jb_proj_id)
                print(f"  ✓ {len(mapa)} unidades JB encontradas con jb_unit_id")
            except Exception as e:
                print(f"  ✗ mapeo: {e}"); continue

            ok, skip_no_id, skip_no_data, err = 0, 0, 0, 0
            for i, u in enumerate(unidades, 1):
                num = str(u.get("numero") or "")
                jb_uid = mapa.get(num)
                if not jb_uid:
                    skip_no_id += 1
                    continue
                try:
                    surfs = await read_unit_surfaces(imp, jb_uid)
                    # Filtrar valores nuevos (no machacar ST si ya tenía)
                    patch = {}
                    for k, v in surfs.items():
                        if v is None or v == 0: continue
                        if u.get(k) and float(u.get(k) or 0) > 0: continue  # ya tiene
                        patch[k] = v
                    if not patch:
                        skip_no_data += 1
                        continue
                    # PUT unidad con campos completos + patch
                    body = {
                        "numero": u.get("numero"),
                        "modelo": u.get("modelo") or "",
                        "tipologia": u.get("tipologia") or "",
                        "tipo": u.get("tipo") or "Depto",
                        "orientacion": u.get("orientacion") or "",
                        "sup_total": u.get("sup_total"),
                        "sup_interior": u.get("sup_interior"),
                        "sup_terraza": u.get("sup_terraza"),
                        "sup_logia": u.get("sup_logia"),
                        "sup_jardin": u.get("sup_jardin"),
                        "precio_lista_uf": u.get("precio_lista_uf"),
                        "precio_final_uf": u.get("precio_final_uf"),
                        "descuento_pct": u.get("descuento_pct") or 0,
                        "bono_pie_pct": u.get("bono_pie_pct") or 0,
                        "estac_flag": u.get("estac_flag") or "optional",
                        "bodega_flag": u.get("bodega_flag") or "optional",
                        "pack_flag": u.get("pack_flag") or "optional",
                        "disponible": u.get("disponible", True),
                        **patch,
                    }
                    r = cli.put(f"/proyectos/{pid}/unidades/{u.get('id')}", json=body)
                    if r.status_code in (200, 201):
                        ok += 1
                        if ok <= 5 or ok % 10 == 0:
                            print(f"  [{i}/{len(unidades)}] #{num} ({jb_uid}): +{list(patch.keys())} valores={patch}")
                    else:
                        err += 1
                        if err <= 3:
                            print(f"  ✗ PUT #{num}: HTTP {r.status_code} {r.text[:120]}")
                except Exception as e:
                    err += 1
                    if err <= 3:
                        print(f"  ✗ #{num}: {e}")
            print(f"  → OK={ok} sin_id={skip_no_id} sin_data={skip_no_data} err={err}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
