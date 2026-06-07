"""Reproduce el PUT del editor: toProyectoIn mete unidades/modelos/etc en extra."""
import os, json, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "vista-llacol-n-torre-b")
IN = {'nombre','inmobiliaria','comuna','region','direccion','gps_lat','gps_lon','fase',
      'modalidad','activo','disponible','fecha_entrega','ano_entrega','foto_principal_url','external_url','notas'}
BLACK = {'created_at','updated_at','stock_updated_at','documentos','imagenes'}
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=40)
p = cli.get(f"/proyectos/{PID}").json()
# simular toProyectoIn: extra = extra preexistente + top-level no-IN no-BLACK (incluye unidades/modelos/...)
extra = dict(p.get("extra") or {})
dumped = []
for k in p:
    if k in ("extra", "id") or k in IN or k in BLACK:
        continue
    extra[k] = p[k]
    if isinstance(p[k], list):
        dumped.append(f"{k}[{len(p[k])}]")
body = {k: p[k] for k in p if k in IN}
body["extra"] = extra
print(f"Arrays metidos en extra: {dumped}")
print(f"Tamaño body JSON: {len(json.dumps(body))} bytes")
r = cli.put(f"/proyectos/{PID}", json=body)
print(f"PUT (estilo editor) → {r.status_code}")
if r.status_code != 200:
    print("ERROR:", r.text[:1500])
