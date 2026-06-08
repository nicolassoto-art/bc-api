import os, httpx, json
from collections import Counter
BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "los-lilenes")
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
p = cli.get(f"/proyectos/{PID}").json()
modelos = (p.get("extra") or {}).get("modelos") or []
unidades = p.get("unidades") or []
print(f"=== {PID} ===")
print(f"  modelos: {len(modelos)}")
for m in modelos:
    print(f"    • nombre={m.get('nombre')!r:30} d={m.get('dormitorios')} b={m.get('banos')}")
mnames = {m.get("nombre") for m in modelos}
print(f"\n  nombres de modelos (set): {mnames}")
print(f"\n  unidades: {len(unidades)}")
modelos_en_unidades = Counter(u.get("modelo") for u in unidades)
print(f"  distribución 'modelo' en unidades (top 10):")
for nm, cnt in modelos_en_unidades.most_common(10):
    en_modelos = nm in mnames
    print(f"    {nm!r:40}: {cnt:>4} unidades   {'✓ matchea modelo' if en_modelos else '✗ HUÉRFANA'}")
