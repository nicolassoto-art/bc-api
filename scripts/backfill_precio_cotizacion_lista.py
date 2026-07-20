"""Backfill: fuerza comercial.precio_cotizacion='lista' en todos los proyectos
que hoy tienen 'dcto' o 'bono' (el selector "Precio en cotizador" del editor se
retiró — el precio publicado/cotizado de TODO proyecto SBC vuelve a ser SIEMPRE
precio lista, sin excepción por proyecto).

Uso (en el VPS, mismo patrón que backfill_codigo_corto.py):
    python -m scripts.backfill_precio_cotizacion_lista --dry-run   # solo muestra
    python -m scripts.backfill_precio_cotizacion_lista --apply     # actualiza BD
"""
from __future__ import annotations
import argparse

from app.db import SessionLocal
from app.models import Proyecto


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="Solo muestra qué cambiaría")
    grp.add_argument("--apply", action="store_true", help="Aplica los cambios a la BD")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = db.query(Proyecto).all()
        objetivo = []
        for p in rows:
            extra = p.extra or {}
            com = (extra.get("comercial") or {})
            modo = com.get("precio_cotizacion")
            if modo not in (None, "", "lista"):
                objetivo.append((p, modo))

        print(f"\nProyectos con precio_cotizacion != 'lista': {len(objetivo)}\n")
        for p, modo in objetivo:
            print(f"  {p.id[:40]:40} · '{modo}' → 'lista'")

        if args.apply and objetivo:
            print(f"\nAplicando {len(objetivo)} cambios...")
            for p, _modo in objetivo:
                extra = dict(p.extra or {})
                com = dict(extra.get("comercial") or {})
                com["precio_cotizacion"] = "lista"
                extra["comercial"] = com
                p.extra = extra  # reasignación completa: marca dirty el JSONB
            db.commit()
            print(f"✓ {len(objetivo)} proyectos actualizados a 'lista'.")
        elif args.dry_run:
            print("\n(dry-run — sin cambios en BD. Re-correr con --apply.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
