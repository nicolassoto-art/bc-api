"""Revisa Abdón Cifuentes desde vista pública: modelos + unidades."""
import os, httpx, json
from collections import Counter
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

pid = "jb-g3jwrroe"
p = cli.get(f"/proyectos/{pid}").json()
print(f"Proyecto: {p.get('nombre')} ({p.get('inmobiliaria')})")
print(f"updated_at: {p.get('updated_at')}")
print(f"foto_principal_url: {'sí' if p.get('foto_principal_url') else 'NO'}")

extra = p.get("extra") or {}
modelos = extra.get("modelos") or []
modelos_dom = extra.get("modelos_dom") or []
unidades = p.get("unidades") or []
imgs = p.get("imagenes") or []
docs = p.get("documentos") or []

print(f"\n=== Assets ===")
print(f"  Imágenes total: {len(imgs)}")
print(f"  Documentos: {len(docs)}")
cats = Counter((i.get("categoria") or "?") for i in imgs)
for cat, n in cats.most_common(): print(f"    {cat}: {n}")

print(f"\n=== Modelos ({len(modelos)}) ===")
auto_count = sum(1 for m in modelos if isinstance(m, dict) and m.get("_auto_generated"))
con_planta = sum(1 for m in modelos if isinstance(m, dict) and (m.get("planta_url") or m.get("planta_thumb_src")))
print(f"  auto-generados (placeholder): {auto_count}")
print(f"  con planta: {con_planta} / {len(modelos)}")
for m in modelos[:25]:
    if isinstance(m, dict):
        n = m.get("nombre") or "?"
        d = m.get("dormitorios") or ""
        b = m.get("banos") or ""
        planta = "sí" if (m.get("planta_url") or m.get("planta_thumb_src")) else "NO"
        auto = " (auto)" if m.get("_auto_generated") else ""
        cnt = m.get("_unidades_count", "")
        print(f"  '{n}' {d}D/{b}B  planta={planta}{auto}  uds={cnt}")

print(f"\n=== Unidades ({len(unidades)}) ===")
modelos_u = Counter((u.get("modelo") or "").strip() for u in unidades)
modelo_names = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
print(f"  modelos distintos en unidades: {len(modelos_u)}")
huerfanas = 0
for nm, cnt in modelos_u.most_common():
    match = "✓" if nm in modelo_names else "✗"
    if nm not in modelo_names: huerfanas += cnt
    print(f"    {match} '{nm}' × {cnt}")
print(f"\n  Total huérfanas: {huerfanas}")

# Sup totals
sup_ok = sum(1 for u in unidades if u.get("sup_total") and float(u.get("sup_total") or 0) > 0)
print(f"\n=== Superficies en unidades ===")
print(f"  sup_total: {sup_ok}/{len(unidades)}")
sup_int = sum(1 for u in unidades if u.get("sup_interior") and float(u.get("sup_interior") or 0) > 0)
print(f"  sup_interior: {sup_int}/{len(unidades)}")
sup_terr = sum(1 for u in unidades if u.get("sup_terraza") and float(u.get("sup_terraza") or 0) > 0)
print(f"  sup_terraza: {sup_terr}/{len(unidades)}")
