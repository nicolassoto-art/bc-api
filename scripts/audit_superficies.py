"""Auditoría real: cuántos deptos de cada proyecto tienen cada superficie."""
import os, httpx
from collections import defaultdict

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
print(f"Total proyectos en bc-api: {len(listing)}\n")

resumen = []
gaps = []  # proyectos con deptos sin sup_total
gaps_detalle = []  # proyectos sin sup_interior/terraza/etc

for p in sorted(listing, key=lambda x: (x.get("inmobiliaria") or "", x.get("nombre") or "")):
    pid = p.get("id")
    if not pid: continue
    try:
        full = cli.get(f"/proyectos/{pid}").json()
    except Exception:
        continue
    nombre = (full.get("nombre") or "")[:35]
    inmo = (full.get("inmobiliaria") or "")[:18]
    unidades = full.get("unidades") or []
    U = len(unidades)
    if U == 0:
        continue
    con_sup_total = sum(1 for u in unidades if u.get("sup_total") and float(u.get("sup_total") or 0) > 0)
    con_sup_interior = sum(1 for u in unidades if u.get("sup_interior") and float(u.get("sup_interior") or 0) > 0)
    con_sup_terraza = sum(1 for u in unidades if u.get("sup_terraza") and float(u.get("sup_terraza") or 0) > 0)
    con_sup_logia = sum(1 for u in unidades if u.get("sup_logia") and float(u.get("sup_logia") or 0) > 0)
    con_sup_jardin = sum(1 for u in unidades if u.get("sup_jardin") and float(u.get("sup_jardin") or 0) > 0)
    resumen.append({
        "id": pid, "nombre": nombre, "inmo": inmo, "U": U,
        "ST": con_sup_total, "SI": con_sup_interior, "STe": con_sup_terraza, "SL": con_sup_logia, "SJ": con_sup_jardin,
    })
    if con_sup_total < U:
        gaps.append((pid, nombre, U, con_sup_total))
    if con_sup_total > 0 and con_sup_interior == 0:
        gaps_detalle.append((pid, nombre, "sin sup_interior"))

# Header
print(f"{'Inmobiliaria':<18} {'Proyecto':<35} {'Total':>5} {'ST':>5} {'SInt':>5} {'STerr':>5} {'SLog':>5} {'SJar':>5}")
print("-"*100)
for r in resumen:
    flag = ""
    if r["ST"] < r["U"]: flag = " ⚠ ST"
    elif r["SI"] == 0 and r["U"] > 0: flag = " ⚠ sin detalle"
    print(f"{r['inmo']:<18} {r['nombre']:<35} {r['U']:>5} {r['ST']:>5} {r['SI']:>5} {r['STe']:>5} {r['SL']:>5} {r['SJ']:>5}{flag}")

print("\n=== RESUMEN ===")
total_u = sum(r["U"] for r in resumen)
total_st = sum(r["ST"] for r in resumen)
total_si = sum(r["SI"] for r in resumen)
print(f"Total deptos: {total_u}")
print(f"  con Sup Total (m²):    {total_st} ({100*total_st//max(total_u,1)}%)")
print(f"  con Sup Interior:      {total_si} ({100*total_si//max(total_u,1)}%)")
print(f"  con Sup Terraza:       {sum(r['STe'] for r in resumen)} ({100*sum(r['STe'] for r in resumen)//max(total_u,1)}%)")
print(f"  con Sup Logia:         {sum(r['SL'] for r in resumen)} ({100*sum(r['SL'] for r in resumen)//max(total_u,1)}%)")
print(f"  con Sup Jardín:        {sum(r['SJ'] for r in resumen)} ({100*sum(r['SJ'] for r in resumen)//max(total_u,1)}%)")

print(f"\nProyectos con deptos SIN Sup Total: {len(gaps)}")
for pid, nombre, total, con in gaps[:10]:
    print(f"  {pid}: {nombre} ({con}/{total})")
if len(gaps) > 10: print(f"  ... +{len(gaps)-10}")

print(f"\nProyectos con Sup Total pero SIN Sup Interior (sin desglose): {len(gaps_detalle)}")
for pid, nombre, _ in gaps_detalle[:15]:
    print(f"  {pid}: {nombre}")
if len(gaps_detalle) > 15: print(f"  ... +{len(gaps_detalle)-15}")
