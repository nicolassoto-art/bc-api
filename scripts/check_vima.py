import os, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
lst = cli.get("/proyectos").json()
print(f"Total proyectos: {len(lst)}")
for p in lst:
    n = (p.get("nombre") or "").lower()
    extra_jb = (p.get("extra") or {}).get("jb_id")
    if "vima" in n or extra_jb == "uRZc07TE":
        print(f"  id={p.get('id')!r} nombre={p.get('nombre')!r} inmob={p.get('inmobiliaria')!r} jb_id={extra_jb!r}")
# probar POST manualmente
print("\n=== Probar POST /proyectos con stub ViMa ===")
stub = {"nombre": "ViMa", "inmobiliaria": "Ingevec", "modalidad": "Nuevo", "activo": True, "disponible": True, "extra": {"jb_id": "uRZc07TE"}}
r = cli.post("/proyectos", json=stub)
print(f"  POST status: {r.status_code}")
print(f"  body: {r.text[:500]}")
