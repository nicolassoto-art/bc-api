"""patch_totals.py — Corrige extra.fisicos.estac_totales/bodegas_totales calculados desde
los arrays reales. SIN wipe.
"""
import os, httpx

BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = [p.strip() for p in os.environ["PID_BC"].split(",") if p.strip()]
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

for pid in PIDS:
    p = cli.get(f"/proyectos/{pid}").json()
    extra = dict(p.get("extra") or {})
    fis = dict(extra.get("fisicos") or {})
    estac = len(extra.get("estacionamientos_dom") or extra.get("estacionamientos") or [])
    bod = len(extra.get("bodegas_dom") or extra.get("bodegas") or [])
    packs_n = len(extra.get("packs_dom") or extra.get("packs") or [])
    # contar unidades reales
    unidades = p.get("unidades") or []
    n_uds = len(unidades)
    # actualizar solo si están vacíos o no coinciden
    changes = []
    if estac and (not fis.get("estacionamientos_totales")) and (not fis.get("estac_totales")):
        fis["estacionamientos_totales"] = estac
        changes.append(f"estacionamientos_totales={estac}")
    if bod and not fis.get("bodegas_totales"):
        fis["bodegas_totales"] = bod
        changes.append(f"bodegas_totales={bod}")
    if n_uds and not fis.get("unidades_totales"):
        fis["unidades_totales"] = n_uds
        changes.append(f"unidades_totales={n_uds}")
    if not changes:
        print(f"{pid}: sin cambios necesarios")
        continue
    extra["fisicos"] = fis
    body = {k: p[k] for k in p
            if k not in ("id", "unidades", "imagenes", "documentos", "created_at", "updated_at", "timeline")}
    body["extra"] = extra
    r = cli.put(f"/proyectos/{pid}", json=body)
    print(f"{pid}: PUT {r.status_code} · {changes}")
