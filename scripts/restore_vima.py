import os, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
# probar varios endpoints
for ep in ("/proyectos/vima/restaurar", "/proyectos/papelera/vima/restaurar", "/proyectos/vima/recover", "/proyectos/papelera/vima"):
    for method in ("POST", "PUT", "PATCH"):
        r = cli.request(method, ep)
        print(f"  {method} {ep} → {r.status_code}: {r.text[:200]}")
        if r.status_code in (200, 201, 204):
            print("  ✓ RESTAURADO")
            # verificar
            r2 = cli.get("/proyectos/vima")
            print(f"  GET /proyectos/vima → {r2.status_code}")
            exit()
print("\nNinguno funcionó. Listar rutas disponibles:")
r = cli.get("/")
print(r.text[:500])
