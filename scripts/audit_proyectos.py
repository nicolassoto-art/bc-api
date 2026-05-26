"""
audit_proyectos.py — Lista TODOS los proyectos en bc-api con stats clave.

Salida (CSV + tabla): id, nombre, inmobiliaria, jb_id, unidades, fotos, planos, documentos, modelos, updated_at
Para detectar gaps post-import.
"""
from __future__ import annotations
import csv
import os
import sys
import httpx


def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    out_csv = sys.argv[1] if len(sys.argv) > 1 else "audit_proyectos.csv"

    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)

    r = cli.get("/proyectos")
    r.raise_for_status()
    listing = r.json()
    print(f"Total proyectos en bc-api: {len(listing)}")

    rows = []
    for p in listing:
        pid = p.get("id")
        if not pid:
            continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"  ✗ {pid}: {e}")
            continue
        extra = full.get("extra") or {}
        imgs = full.get("imagenes") or []
        fotos = sum(1 for i in imgs if (i.get("categoria") or "") != "plano")
        planos = sum(1 for i in imgs if (i.get("categoria") or "") == "plano")
        unidades = full.get("unidades") or []
        documentos = full.get("documentos") or []
        modelos = (extra.get("modelos") or extra.get("modelos_dom") or [])

        rows.append({
            "id": pid,
            "nombre": full.get("nombre") or "",
            "inmobiliaria": full.get("inmobiliaria") or "",
            "jb_id": extra.get("jb_id") or "",
            "unidades": len(unidades),
            "fotos": fotos,
            "planos": planos,
            "documentos": len(documentos),
            "modelos": len(modelos),
            "updated_at": full.get("updated_at") or full.get("fecha_actualizacion") or "",
        })

    # Sort by jb_id presence then nombre
    rows.sort(key=lambda r: (not bool(r["jb_id"]), r["nombre"]))

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)
    print(f"\n✓ CSV guardado en {out_csv}")

    # Print summary table
    print(f"\n{'jb_id':12s} {'inmobiliaria':25s} {'nombre':40s} {'U':>4s} {'F':>4s} {'P':>4s} {'D':>4s} {'M':>4s}")
    print("-" * 110)
    issues = []
    for r in rows:
        flag = ""
        if r["jb_id"]:
            if r["unidades"] == 0: flag += "U!"
            if r["modelos"] == 0: flag += "M!"
            if not r["inmobiliaria"] or r["inmobiliaria"].lower() == "bigcapital":
                flag += "I!"
        line = (f"{r['jb_id']:12s} {r['inmobiliaria'][:25]:25s} {r['nombre'][:40]:40s} "
                f"{r['unidades']:>4d} {r['fotos']:>4d} {r['planos']:>4d} {r['documentos']:>4d} {r['modelos']:>4d} {flag}")
        print(line)
        if flag:
            issues.append({**r, "flag": flag})

    print(f"\nProyectos con issues: {len(issues)}/{len(rows)}")
    print("  U! = unidades vacías · M! = modelos vacíos · I! = inmobiliaria placeholder/vacía")


if __name__ == "__main__":
    main()
