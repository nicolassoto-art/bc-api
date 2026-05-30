"""Audita etiquetas (+ areas_comunes, equipamiento, entorno) por proyecto."""
import os, httpx
from collections import Counter

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
print(f"Total proyectos: {len(listing)}")

con_etiq = 0
sin_etiq = []
todas_etiquetas = Counter()
campos_chip = ["etiquetas", "areas_comunes", "equipamiento", "entorno"]
cobertura = {c: 0 for c in campos_chip}

detalle = []
for p in listing:
    pid = p.get("id")
    try:
        full = cli.get(f"/proyectos/{pid}").json()
    except Exception:
        continue
    extra = full.get("extra") or {}
    nombre = full.get("nombre") or ""
    etiq = extra.get("etiquetas") or []
    if isinstance(etiq, list) and etiq:
        con_etiq += 1
        for e in etiq:
            todas_etiquetas[str(e)] += 1
    else:
        sin_etiq.append((pid, nombre))
    for c in campos_chip:
        v = extra.get(c) or []
        if isinstance(v, list) and v:
            cobertura[c] += 1
    detalle.append((nombre, etiq))

print(f"\n=== COBERTURA ===")
for c in campos_chip:
    print(f"  {c:15s}: {cobertura[c]}/{len(listing)} proyectos")
print(f"\nProyectos SIN etiquetas: {len(sin_etiq)}")
for pid, n in sin_etiq[:30]:
    print(f"    {pid:30s} {n[:35]}")

print(f"\n=== TODAS LAS ETIQUETAS ÚNICAS ({len(todas_etiquetas)}) ===")
for et, cnt in todas_etiquetas.most_common():
    print(f"  {cnt:3d}× {et}")

print(f"\n=== DETALLE etiquetas por proyecto (con etiquetas) ===")
for nombre, etiq in detalle:
    if etiq:
        print(f"  {nombre[:35]:35s} → {etiq}")
