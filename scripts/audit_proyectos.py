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
            r2 = cli.get(f"/proyectos/{pid}")
            if r2.status_code != 200:
                print(f"  ✗ {pid}: HTTP {r2.status_code} {r2.text[:120]}")
                continue
            full = r2.json()
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

    # ── Auditoría detallada UNIDADES + MODELOS ─────────────────────────
    print("\n\n========================")
    print("DETALLE UNIDADES + MODELOS")
    print("========================\n")
    for p in listing:
        pid = p.get("id")
        if not pid:
            continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception:
            continue
        extra = full.get("extra") or {}
        unidades = full.get("unidades") or []
        modelos = (extra.get("modelos") or extra.get("modelos_dom") or [])
        jb_id = extra.get("jb_id") or ""
        nombre = full.get("nombre") or ""

        # Issues por unidad
        u_issues = []
        if unidades:
            sin_modelo = sum(1 for u in unidades if not (u.get("modelo") or "").strip())
            sin_precio = sum(1 for u in unidades if not u.get("precio_lista_uf"))
            sin_sup = sum(1 for u in unidades if not u.get("sup_total"))
            sin_tipologia = sum(1 for u in unidades if not (u.get("tipologia") or "").strip())
            if sin_modelo: u_issues.append(f"sin_modelo={sin_modelo}")
            if sin_precio: u_issues.append(f"sin_precio={sin_precio}")
            if sin_sup: u_issues.append(f"sin_sup={sin_sup}")
            if sin_tipologia: u_issues.append(f"sin_tip={sin_tipologia}")

        # Issues por modelo
        m_issues = []
        if modelos:
            sin_nombre = sum(1 for m in (modelos if isinstance(modelos, list) else []) if isinstance(m, dict) and not (m.get("nombre") or m.get("name") or "").strip())
            sin_plano = sum(1 for m in (modelos if isinstance(modelos, list) else []) if isinstance(m, dict) and not (m.get("plano_url") or m.get("blueprint") or ""))
            if sin_nombre: m_issues.append(f"sin_nombre={sin_nombre}")
            if sin_plano: m_issues.append(f"sin_plano={sin_plano}")

        status_u = "✅" if unidades and not u_issues else ("⚠" if u_issues else "❌")
        status_m = "✅" if modelos and not m_issues else ("⚠" if m_issues else "❌")
        u_detail = f" [{', '.join(u_issues)}]" if u_issues else ""
        m_detail = f" [{', '.join(m_issues)}]" if m_issues else ""
        print(f"{jb_id:12s} {nombre[:40]:40s} U:{status_u} {len(unidades):>4d}{u_detail}  M:{status_m} {len(modelos) if isinstance(modelos, list) else 0:>3d}{m_detail}")


if __name__ == "__main__":
    main()
