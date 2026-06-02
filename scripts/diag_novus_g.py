"""Diag Novus Torre G — qué modelos vs qué usan las unidades."""
import os, httpx
from collections import Counter
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

p = cli.get("/proyectos/jb-4kny8vbw").json()
print(f"Proyecto: {p.get('nombre')}")
print(f"Inmobiliaria: {p.get('inmobiliaria')}\n")

extra = p.get("extra") or {}
modelos = extra.get("modelos") or []
modelos_dom = extra.get("modelos_dom") or []
unidades = p.get("unidades") or []

print(f"=== Modelos en extra.modelos ({len(modelos)}) ===")
for m in modelos[:25]:
    if isinstance(m, dict):
        n = m.get("nombre") or "?"
        d = m.get("dormitorios") or ""
        b = m.get("banos") or ""
        planta = "sí" if (m.get("planta_url") or m.get("planta_thumb_src")) else "NO"
        auto = " (auto)" if m.get("_auto_generated") else ""
        print(f"  {n:25s} {d}D/{b}B  planta={planta}{auto}")

print(f"\n=== Modelos en extra.modelos_dom ({len(modelos_dom)}) ===")
for m in modelos_dom[:10]:
    if isinstance(m, dict):
        n = m.get("nombre") or "?"
        planta = "sí" if (m.get("planta_url") or m.get("planta_thumb_src")) else "NO"
        print(f"  {n}: planta={planta}")

print(f"\n=== Unidades.modelo distintos ({len(unidades)} unidades) ===")
unidad_modelos = Counter((u.get("modelo") or "").strip() for u in unidades)
for nm, cnt in unidad_modelos.most_common(30):
    print(f"  '{nm}' × {cnt}")
