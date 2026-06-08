import os, httpx, json
from collections import Counter
BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "los-lilenes")
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
# GET unidades directamente
r = cli.get(f"/proyectos/{PID}/unidades")
print(f"GET /proyectos/{PID}/unidades → {r.status_code}")
if r.status_code == 200:
    uds = r.json()
    print(f"Total: {len(uds)}")
    # distribución de modelo
    by_modelo = Counter(u.get("modelo") for u in uds)
    print(f"distribución 'modelo' en endpoint dedicado: {dict(by_modelo)}")
    # primeras 3 con modelo vacío
    sin_m = [u for u in uds if not u.get("modelo")]
    print(f"\nPrimeras 3 unidades SIN modelo (campos crudos):")
    for u in sin_m[:3]:
        print(f"  {json.dumps(u, ensure_ascii=False)[:300]}")
    print(f"\nPrimeras 2 unidades CON modelo:")
    con_m = [u for u in uds if u.get("modelo")]
    for u in con_m[:2]:
        print(f"  {json.dumps(u, ensure_ascii=False)[:300]}")
