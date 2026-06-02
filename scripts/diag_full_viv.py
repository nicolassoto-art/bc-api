import os, httpx, json
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
p = cli.get("/proyectos/jb-iaiq9ith").json()
print(f"nombre: {p.get('nombre')}")
print(f"inmobiliaria: {p.get('inmobiliaria')}")
print(f"comuna: {p.get('comuna')}")
print(f"foto_principal_url: {'sí' if p.get('foto_principal_url') else 'NO'}")
print(f"unidades: {len(p.get('unidades') or [])}")
print(f"imagenes: {len(p.get('imagenes') or [])}")
print(f"documentos: {len(p.get('documentos') or [])}")
extra = p.get("extra") or {}
print(f"\nextra keys: {list(extra.keys())[:20]}")
print(f"extra.modelos: {len(extra.get('modelos') or [])}")
print(f"extra.modelos_dom: {len(extra.get('modelos_dom') or [])}")
print(f"extra.fisicos: {json.dumps(extra.get('fisicos') or {}, indent=1)[:200]}")
print(f"updated_at: {p.get('updated_at')}")
