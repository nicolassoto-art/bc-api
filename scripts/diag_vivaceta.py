"""Diagnostica Vivaceta 864: caso del depto con modelo '1d1b' sin planta."""
import os, httpx
from collections import Counter

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

p = cli.get("/proyectos/jb-iaiq9ith").json()
extra = p.get("extra") or {}
modelos = extra.get("modelos") or []
unidades = p.get("unidades") or []

print(f"=== Vivaceta 864 ({p.get('id')}) ===\n")

# Buscar TODOS los modelos cuyo nombre tenga "1d1b" (insensitive)
print(f"=== Modelos con '1d1b' (case-insensitive, {len(modelos)} total) ===")
for m in modelos:
    if not isinstance(m, dict): continue
    n = (m.get("nombre") or "").strip()
    if "1d1b" not in n.lower(): continue
    planta = "sí" if (m.get("planta_url") or m.get("planta_thumb_src")) else "NO"
    print(f"  '{n}' planta={planta}  url={(m.get('planta_url') or '')[:60]}")

# Mostrar TODOS los nombres de modelos
print(f"\n=== Todos los nombres de modelos ({len(modelos)}) ===")
nombres_m = sorted([(m.get("nombre") or "?").strip() for m in modelos if isinstance(m, dict)])
for n in nombres_m: print(f"  '{n}'")

# Buscar unidades con modelo '1d1b' (insensitive)
print(f"\n=== Unidades con modelo '1d1b' (case-insensitive) ===")
for u in unidades:
    m = (u.get("modelo") or "").strip()
    if "1d1b" in m.lower():
        print(f"  #{u.get('numero'):>6s}  modelo='{m}'  tipologia='{u.get('tipologia')}'")

# Contar todos los modelos en unidades (case exacto)
print(f"\n=== Modelos distintos usados por unidades (case exacto) ===")
u_modelos = Counter((u.get("modelo") or "").strip() for u in unidades)
for nm, cnt in u_modelos.most_common(): print(f"  '{nm}' × {cnt}")

# Test de match case-sensitive vs case-insensitive
print(f"\n=== Mismatch case-sensitive ===")
m_names_exact = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
m_names_lower = {n.lower() for n in m_names_exact}
for nm in u_modelos:
    if not nm: continue
    if nm in m_names_exact:
        continue  # match exacto
    if nm.lower() in m_names_lower:
        # match solo case-insensitive
        match_real = [n for n in m_names_exact if n.lower() == nm.lower()][0]
        print(f"  ⚠ '{nm}' (en unidades) ≠ '{match_real}' (en modelos)  · {u_modelos[nm]} unidades afectadas")
    else:
        print(f"  ✗ '{nm}' HUÉRFANA (no existe ni case-insensitive)")
