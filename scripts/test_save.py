"""Reproduce un save (PUT) del proyecto para ver el error 422 exacto."""
import os, json, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "vista-llacol-n-torre-b")
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
p = cli.get(f"/proyectos/{PID}").json()
body = {k: v for k, v in p.items()
        if k not in ("id", "unidades", "imagenes", "documentos", "created_at", "updated_at", "timeline")}
print("Campos top-level del body:", sorted(body.keys()))
r = cli.put(f"/proyectos/{PID}", json=body)
print(f"\nPUT → {r.status_code}")
if r.status_code != 200:
    print("ERROR:", r.text[:1500])
else:
    print("OK (el PUT raw funciona — el problema está en el transform del editor)")
