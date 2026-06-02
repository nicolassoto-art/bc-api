"""
limpiar_modelos_sin_unidades.py — Borra modelos sin unidades asociadas y
audita los 84 proyectos en detalle.

Reglas:
  - Modelo SIN unidades asociadas → BORRAR (no aporta)
  - Unidad SIN modelo asociado en extra.modelos → REPORTAR (huérfana)
  - Modelo SIN planta_url → REPORTAR (incompleto)
"""
import os, httpx
from collections import Counter

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
print(f"Total proyectos: {len(listing)}\n")

stats = {
    "proyectos_actualizados": 0,
    "modelos_borrados": 0,
    "huerfanas_total": 0,
    "modelos_sin_planta": 0,
}
proyectos_con_huerfanas = []
proyectos_sin_planta = []

print(f"{'jb_id':<14} {'Nombre':<32} {'M':>4} {'M.→':>4} {'U':>5} {'U.huérf':>8} {'M.sin planta':>13}")
print("-" * 100)

for p in listing:
    pid = p.get("id")
    if not pid: continue
    try:
        full = cli.get(f"/proyectos/{pid}").json()
    except: continue

    extra = full.get("extra") or {}
    modelos = extra.get("modelos") or []
    if not isinstance(modelos, list): modelos = []
    unidades = full.get("unidades") or []
    nombre = (full.get("nombre") or "")[:30]
    jb_id = extra.get("jb_id", pid)

    if not modelos and not unidades:
        continue

    # Nombres usados por unidades
    modelos_usados = set()
    for u in unidades:
        mn = (u.get("modelo") or "").strip()
        if mn: modelos_usados.add(mn)

    # Modelos a conservar: los que tienen unidades
    new_modelos = []
    borrados = 0
    for m in modelos:
        if not isinstance(m, dict):
            continue
        nom = (m.get("nombre") or "").strip()
        if not nom or nom in modelos_usados:
            new_modelos.append(m)
        else:
            borrados += 1

    # Unidades huérfanas (modelo no existe en new_modelos)
    new_modelo_names = {(m.get("nombre") or "").strip() for m in new_modelos}
    huerfanas = sum(1 for u in unidades if (u.get("modelo") or "").strip() and (u.get("modelo") or "").strip() not in new_modelo_names)

    # Modelos sin planta
    sin_planta = sum(1 for m in new_modelos if not (m.get("planta_url") or m.get("planta_thumb_src")))

    flags = []
    if huerfanas: flags.append(f"⚠ {huerfanas} huérf")
    if sin_planta: flags.append(f"⚠ {sin_planta} s/planta")
    flag_str = " · ".join(flags) if flags else "✓"

    print(f"{jb_id:<14} {nombre:<32} {len(modelos):>4d} {len(new_modelos):>4d} {len(unidades):>5d} {huerfanas:>8d} {sin_planta:>13d}  {flag_str}")

    if borrados > 0:
        body = {k: full[k] for k in full if k not in ("imagenes","documentos","unidades","created_at","updated_at")}
        body["extra"] = {**extra, "modelos": new_modelos}
        try:
            r = cli.put(f"/proyectos/{pid}", json=body)
            if r.status_code in (200, 201):
                stats["proyectos_actualizados"] += 1
                stats["modelos_borrados"] += borrados
        except: pass

    stats["huerfanas_total"] += huerfanas
    stats["modelos_sin_planta"] += sin_planta
    if huerfanas: proyectos_con_huerfanas.append((jb_id, nombre, huerfanas, len(unidades)))
    if sin_planta and new_modelos: proyectos_sin_planta.append((jb_id, nombre, sin_planta, len(new_modelos)))

print(f"\n=== RESUMEN ===")
print(f"Proyectos con borrados: {stats['proyectos_actualizados']}")
print(f"Modelos sin unidades borrados: {stats['modelos_borrados']}")
print(f"Unidades huérfanas (sin modelo válido): {stats['huerfanas_total']}")
print(f"Modelos sin planta_url: {stats['modelos_sin_planta']}")

if proyectos_con_huerfanas:
    print(f"\n=== Proyectos con huérfanas ({len(proyectos_con_huerfanas)}) ===")
    for jb_id, n, h, t in proyectos_con_huerfanas:
        print(f"  {jb_id:<14} {n:<32} {h:>4}/{t:>4}")

if proyectos_sin_planta:
    print(f"\n=== Proyectos con modelos sin planta ({len(proyectos_sin_planta)}) ===")
    for jb_id, n, s, t in proyectos_sin_planta[:20]:
        print(f"  {jb_id:<14} {n:<32} {s:>3}/{t:<3} sin planta")
    if len(proyectos_sin_planta) > 20:
        print(f"  ... +{len(proyectos_sin_planta)-20} más")
