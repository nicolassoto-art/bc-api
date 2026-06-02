import os, httpx, json
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
r = cli.get("/proyectos/jb-iaiq9ith")
print(f"status: {r.status_code}")
print(f"body[:300]: {r.text[:300]}")
if r.status_code == 200:
    p = r.json()
    print(f"\nnombre: {p.get('nombre')}")
    print(f"inmobiliaria: {p.get('inmobiliaria')}")
    print(f"unidades: {len(p.get('unidades') or [])}")
    print(f"imagenes: {len(p.get('imagenes') or [])}")
    extra = p.get("extra") or {}
    print(f"extra.modelos: {len(extra.get('modelos') or [])}")
    print(f"updated_at: {p.get('updated_at')}")
else:
    # buscar en listing
    listing = cli.get("/proyectos").json()
    for q in listing:
        if "iaiq" in (q.get("id") or "").lower() or "vivaceta" in (q.get("nombre") or "").lower():
            print(f"  encontrado: id={q.get('id')} nombre={q.get('nombre')} und={q.get('unidades_total')}")
