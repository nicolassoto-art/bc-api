"""Borra todos los modelos con _auto_generated=true en TODOS los proyectos."""
import os, httpx
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

listing = cli.get("/proyectos").json()
total_borrados = 0
proyectos_afectados = 0
for p in listing:
    pid = p.get("id")
    if not pid: continue
    try: full = cli.get(f"/proyectos/{pid}").json()
    except: continue
    extra = full.get("extra") or {}
    modelos = extra.get("modelos") or []
    if not isinstance(modelos, list): continue
    new_modelos = [m for m in modelos if not (isinstance(m, dict) and m.get("_auto_generated"))]
    n_borrados = len(modelos) - len(new_modelos)
    if n_borrados == 0: continue
    body = {k: full[k] for k in full if k not in ("imagenes","documentos","unidades","created_at","updated_at")}
    body["extra"] = {**extra, "modelos": new_modelos}
    try:
        r = cli.put(f"/proyectos/{pid}", json=body)
        if r.status_code in (200, 201):
            print(f"  ✓ {pid:30s} -{n_borrados} placeholders")
            total_borrados += n_borrados
            proyectos_afectados += 1
    except Exception as e:
        print(f"  ✗ {pid}: {e}")

print(f"\n=== {total_borrados} placeholders borrados en {proyectos_afectados} proyectos ===")
