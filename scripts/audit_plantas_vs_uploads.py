"""Audita los 84 proyectos: modelos con planta_url vacío pero con thumb JB.
Estos requieren re-import SIN skip_assets para subir las plantas a /uploads/."""
import os, httpx
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
problemas = []
para_reimport = []
for p in listing:
    pid = p.get("id")
    if not pid or not pid.startswith("jb-"): continue
    try:
        full = cli.get(f"/proyectos/{pid}").json()
    except Exception as e:
        print(f"  err {pid}: {e}"); continue
    extra = full.get("extra") or {}
    modelos = extra.get("modelos") or []
    if not modelos: continue
    sin_url_con_thumb = 0
    sin_planta_total = 0
    con_url = 0
    for m in modelos:
        if not isinstance(m, dict): continue
        u = m.get("planta_url") or ""
        t = m.get("planta_thumb_src") or ""
        if u: con_url += 1
        elif t: sin_url_con_thumb += 1
        else: sin_planta_total += 1
    if sin_url_con_thumb > 0:
        nombre = (full.get("nombre") or "")[:35]
        problemas.append((pid, nombre, len(modelos), con_url, sin_url_con_thumb, sin_planta_total))
        para_reimport.append(pid.replace("jb-", ""))

problemas.sort(key=lambda x: -x[4])
print(f"\n=== Proyectos con modelos sin planta_url subida ({len(problemas)} proyectos) ===")
print(f"{'jb_id':<14} {'nombre':<35} {'total':>5} {'OK':>4} {'SOLO_THUMB':>10} {'VACÍO':>5}")
for pid, n, total, ok, thumb, vac in problemas:
    print(f"{pid:<14} {n:<35} {total:>5} {ok:>4} {thumb:>10} {vac:>5}")
print(f"\nTotal modelos sin planta_url: {sum(x[4] for x in problemas)}")
print(f"jb_ids para re-import:")
print(",".join(para_reimport))
