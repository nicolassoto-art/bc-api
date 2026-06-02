"""Diagnostica el proyecto Terrazzo: qué tiene bc-api vs qué tiene JB."""
import os, httpx, json
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

p = cli.get("/proyectos/jb-72gkwnlw").json()
print(f"Nombre: {p.get('nombre')}")
print(f"Inmobiliaria: {p.get('inmobiliaria')}")
print(f"jb_id: {(p.get('extra') or {}).get('jb_id')}")
print(f"\n=== Assets en bc-api ===")
imgs = p.get("imagenes") or []
print(f"Imágenes: {len(imgs)}")
from collections import Counter
cats = Counter((i.get("categoria") or "?") for i in imgs)
for cat, n in cats.most_common():
    print(f"  {cat}: {n}")
print(f"Documentos: {len(p.get('documentos') or [])}")
print(f"\n=== Modelos ===")
extra = p.get("extra") or {}
modelos = extra.get("modelos") or extra.get("modelos_dom") or []
print(f"Total modelos: {len(modelos)}")
for m in modelos[:5]:
    if isinstance(m, dict):
        planta = m.get("planta_url") or m.get("plano_url") or m.get("planta_thumb_src")
        print(f"  {m.get('nombre','?')}: planta={'sí' if planta else 'NO'}")
print(f"\nfoto_principal_url: {p.get('foto_principal_url')}")
print(f"updated_at: {p.get('updated_at')}")
