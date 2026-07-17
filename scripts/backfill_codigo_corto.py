"""Backfill: asigna codigo_corto ("A1", "A2", ...) a los proyectos existentes
que todavía no lo tienen, en orden de created_at ascendente (el más viejo = A1).

Uso (en el VPS, mismo patrón que fix_region_from_comuna.py):
    python -m scripts.backfill_codigo_corto --dry-run   # solo muestra
    python -m scripts.backfill_codigo_corto --apply     # actualiza BD
"""
from __future__ import annotations
import argparse

from app.db import SessionLocal
from app.models import Proyecto


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="Solo muestra qué asignaría")
    grp.add_argument("--apply", action="store_true", help="Aplica los cambios a la BD")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        max_n = 0
        for (c,) in db.query(Proyecto.codigo_corto).filter(Proyecto.codigo_corto.isnot(None)).all():
            if c and c[:1] == "A" and c[1:].isdigit():
                max_n = max(max_n, int(c[1:]))

        pendientes = (
            db.query(Proyecto)
            .filter(Proyecto.codigo_corto.is_(None))
            .order_by(Proyecto.created_at.asc())
            .all()
        )
        print(f"\nProyectos sin codigo_corto: {len(pendientes)} (ya asignados hasta A{max_n})\n")

        asignaciones = []
        n = max_n
        for p in pendientes:
            n += 1
            asignaciones.append((p.id, p.nombre, f"A{n}"))

        for pid, nom, code in asignaciones[:30]:
            print(f"  {code:6} · {pid[:32]:32} · {nom[:40]}")
        if len(asignaciones) > 30:
            print(f"  ...y {len(asignaciones) - 30} más")

        if args.apply and asignaciones:
            print(f"\nAplicando {len(asignaciones)} asignaciones...")
            for pid, _, code in asignaciones:
                p = db.get(Proyecto, pid)
                if p and not p.codigo_corto:
                    p.codigo_corto = code
            db.commit()
            print(f"✓ {len(asignaciones)} proyectos actualizados (hasta A{n}).")
        elif args.dry_run:
            print("\n(dry-run — sin cambios en BD. Re-correr con --apply.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
