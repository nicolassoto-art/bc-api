"""inspect_stock.py — Inspección detallada de estac/bodegas/packs de un proyecto."""
import os, json, httpx
from collections import Counter
BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "los-lilenes")
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
p = cli.get(f"/proyectos/{PID}").json()
extra = p.get("extra") or {}
estac = extra.get("estacionamientos_dom") or extra.get("estacionamientos") or []
bod = extra.get("bodegas_dom") or extra.get("bodegas") or []
packs = extra.get("packs_dom") or extra.get("packs") or []
print(f"=== {p.get('nombre')} ({PID}) ===\n")
fis = extra.get("fisicos") or {}
print(f"FÍSICOS declarados en JB:")
print(f"   estac_totales: {fis.get('estacionamientos_totales')}")
print(f"   bodegas_totales: {fis.get('bodegas_totales')}")
print()
print(f"ESTACIONAMIENTOS ({len(estac)}):")
disp_e = 0
nivs = Counter()
tipos = Counter()
precios = []
for i, e in enumerate(estac):
    c = e.get("cells") or [None, e.get("numero"), e.get("precio_uf"), e.get("nivel"), e.get("tipo")]
    n = c[1] if len(c) > 1 else None
    pr = c[2] if len(c) > 2 else None
    niv = c[3] if len(c) > 3 else None
    ti = c[4] if len(c) > 4 else None
    disp = e.get("disponible", True)
    if disp: disp_e += 1
    if niv: nivs[str(niv)] += 1
    if ti: tipos[str(ti)] += 1
    if pr:
        try: precios.append(float(pr))
        except: pass
    if i < 5 or i >= len(estac) - 3:
        print(f"  {i+1:>3}. nº={n!r:8} precio={pr!r:8} nivel={niv!r:6} tipo={ti!r:8} disp={disp}")
    elif i == 5:
        print(f"  ... ({len(estac)-8} más) ...")
print(f"  → {disp_e}/{len(estac)} disponibles · niveles={dict(nivs)} · tipos={dict(tipos)}")
if precios: print(f"  → precio UF: min={min(precios)} max={max(precios)} promedio={sum(precios)/len(precios):.1f}")
print()
print(f"BODEGAS ({len(bod)}):")
disp_b = 0
sups = []
precios_b = []
for i, b in enumerate(bod):
    c = b.get("cells") or [None, b.get("numero"), b.get("precio_uf"), b.get("superficie")]
    n = c[1] if len(c) > 1 else None
    pr = c[2] if len(c) > 2 else None
    sup = c[3] if len(c) > 3 else None
    disp = b.get("disponible", True)
    if disp: disp_b += 1
    if pr:
        try: precios_b.append(float(pr))
        except: pass
    if sup:
        try: sups.append(float(sup))
        except: pass
    if i < 5 or i >= len(bod) - 3:
        print(f"  {i+1:>3}. nº={n!r:8} precio={pr!r:8} sup={sup!r:6} disp={disp}")
    elif i == 5:
        print(f"  ... ({len(bod)-8} más) ...")
print(f"  → {disp_b}/{len(bod)} disponibles")
if precios_b: print(f"  → precio UF: min={min(precios_b)} max={max(precios_b)} promedio={sum(precios_b)/len(precios_b):.1f}")
if sups: print(f"  → superficie m²: min={min(sups)} max={max(sups)} promedio={sum(sups)/len(sups):.1f}")
print()
print(f"PACKS ({len(packs)}):")
if not packs:
    print("  (sin packs)")
for i, pk in enumerate(packs[:8]):
    print(f"  {i+1:>3}. nº={pk.get('numero')!r:10} precio_uf={pk.get('precio_uf')} estac={pk.get('estacionamientos')} bodegas={pk.get('bodegas')} disp={pk.get('disponible')}")
if len(packs) > 8:
    print(f"  ... ({len(packs)-8} más) ...")
