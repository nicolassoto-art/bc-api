"""
diag_etiquetas_jb.py — Scrapea las ETIQUETAS directo del editor JB para los 18
proyectos que en bc-api no tienen etiquetas. Confirma si es gap del scrape
(JB sí las tiene) o si JB genuinamente no tiene.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter

# 18 proyectos sin etiquetas en bc-api (jb_id case original)
SIN_ETIQ = [
    ("48t1IInf", "Conexión Independencia"),
    ("m9zXfNHe", "Pionera Parque Cerrillos"),
    ("zOHnfOQJ", "Edificio Borja Plaza"),
    ("dX4Rddfn", "Fuentes de Lomas II"),
    ("86YW1rPt", "Centenario I"),
    ("exrBr6Tp", "Etapa 2 Portal del Pinar"),
    ("IgfWZVh2", "Condominio La Rioja"),
    ("SUWJ0Rye", "Missouri 3885"),
    ("iB3uhp34", "Zapadores 1821"),
    ("tvFyLEMz", "Portal del Pinar"),
    ("ksHJwBab", "Bulnes 138"),
    ("dr6uuHkX", "Altos de Collao"),
    ("1gaVJbKl", "Fuentes de Lomas IV"),
    ("hSeBHnw1", "Fuentes de Lomas III"),
    ("hw9SoClo", "Plaza Victoria"),
    ("HvNRYfwm", "Santa Elena 236"),
    ("OHpd4zbx", "MiraOlas Peñuelas"),
    ("3Av5Af58", "MiraOlas Peñuelas 2ª"),
]

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
CHIP_GROUPS = {"etiquetas": ["etiqueta"]}


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", ""),
        headless=True,
    )
    con_jb = []
    sin_jb = []
    try:
        await imp.login()
        for jb_id, nombre in SIN_ETIQ:
            try:
                url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
                await imp._page.goto(url, wait_until="networkidle", timeout=60_000)
                await imp._page.wait_for_timeout(4_000)
                await imp._dismiss_popups()
                # Reintento de lectura tras esperar render de chips
                etiquetas = []
                for _ in range(3):
                    res = await imp._page.evaluate(CHIP_JS, CHIP_GROUPS)
                    etiquetas = res.get("etiquetas") or []
                    if etiquetas:
                        break
                    await imp._page.wait_for_timeout(2_000)
                if etiquetas:
                    con_jb.append((jb_id, nombre, etiquetas))
                    print(f"  ✅ {nombre[:30]:30s} ({jb_id}): {etiquetas}")
                else:
                    sin_jb.append((jb_id, nombre))
                    print(f"  ⚪ {nombre[:30]:30s} ({jb_id}): JB tampoco tiene")
            except Exception as e:
                print(f"  ✗ {nombre} ({jb_id}): {e}")
        print(f"\n===== RESUMEN =====")
        print(f"GAP REAL (JB sí tiene, bc-api no): {len(con_jb)}")
        for jb_id, nombre, et in con_jb:
            print(f"    {jb_id:12s} {nombre[:30]:30s} → {et}")
        print(f"\nSin etiquetas en JB tampoco (correcto): {len(sin_jb)}")
        for jb_id, nombre in sin_jb:
            print(f"    {jb_id:12s} {nombre}")
    finally:
        await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
