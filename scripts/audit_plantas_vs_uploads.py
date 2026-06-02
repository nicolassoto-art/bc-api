"""Audita los 84 proyectos:
 - vacíos (0 modelos + 0 unidades)
 - modelos con planta_url vacío pero con thumb JB → necesitan re-import sin skip_assets."""
import os, httpx, time
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
problemas = []
vacios = []
para_reimport = set()
for p in listing:
    pid = p.get("id")
    if not pid or not pid.startswith("jb-"): continue
    full = None
    for _ in range(3):
        try:
            r = cli.get(f"/proyectos/{pid}")
            if r.status_code == 200: full = r.json(); break
        except Exception: pass
        time.sleep(1.5)
    if full is None:
        print(f"  err {pid}: GET fail tras 3 retries"); continue
    extra = full.get("extra") or {}
    modelos = extra.get("modelos") or []
    unidades = full.get("unidades") or []
    nombre = (full.get("nombre") or "")[:35]
    if not modelos and not unidades:
        vacios.append((pid, nombre))
        para_reimport.add(pid.replace("jb-", ""))
        continue
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
        problemas.append((pid, nombre, len(modelos), con_url, sin_url_con_thumb, sin_planta_total))
        para_reimport.add(pid.replace("jb-", ""))

print(f"\n=== Proyectos VACÍOS (0 modelos + 0 unidades) — {len(vacios)} ===")
for pid, n in vacios: print(f"  {pid:<14} {n}")

problemas.sort(key=lambda x: -x[4])
print(f"\n=== Proyectos con modelos sin planta_url subida ({len(problemas)} proyectos) ===")
print(f"{'jb_id':<14} {'nombre':<35} {'total':>5} {'OK':>4} {'SOLO_THUMB':>10} {'VACÍO':>5}")
for pid, n, total, ok, thumb, vac in problemas:
    print(f"{pid:<14} {n:<35} {total:>5} {ok:>4} {thumb:>10} {vac:>5}")
print(f"\nTotal modelos sin planta_url: {sum(x[4] for x in problemas)}")
print(f"\n=== jb_ids para re-import (vacíos + plantas) — {len(para_reimport)} ===")
print(",".join(sorted(para_reimport)))
