import os, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
# GET directo
r = cli.get("/proyectos/vima")
print(f"GET /proyectos/vima → {r.status_code}")
print(f"  body: {r.text[:600]}")
# papelera?
try:
    p = cli.get("/proyectos/papelera").json()
    print(f"\nPapelera: {len(p)} proyectos")
    for x in p:
        if "vima" in (x.get("nombre") or "").lower() or x.get("id") == "vima":
            print(f"  EN PAPELERA: id={x.get('id')!r} nombre={x.get('nombre')!r} deleted_at={x.get('deleted_at')}")
except Exception as e:
    print(f"papelera err: {e}")
