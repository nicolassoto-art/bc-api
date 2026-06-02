"""Seed: poblar el catálogo maestro 'inmobiliarias' a partir de los nombres
distintos usados en Proyecto.inmobiliaria + datos en extra.inmobiliaria.

Caso de uso: la nueva tabla 'inmobiliarias' está vacía pero hay 19+ nombres
distintos ya cargados en proyectos importados de JB. Este script crea cada
inmobiliaria UNA vez con la info disponible.

Uso:
    python -m scripts.seed_inmobiliarias_from_proyectos --dry-run
    python -m scripts.seed_inmobiliarias_from_proyectos --apply
"""
from __future__ import annotations
import argparse
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import distinct, func
from app.db import SessionLocal
from app.models import Inmobiliaria, Proyecto


def _gen_id() -> str:
    return "inm-" + uuid.uuid4().hex[:9]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # 1. Recolectar info: por cada nombre único de inmobiliaria, guardar el
        #    "mejor" set de datos (rut/web/direccion) encontrado en algún proyecto.
        info_by_name = defaultdict(lambda: {"rut": "", "web": "", "direccion": ""})
        nombres = set()
        for p in db.query(Proyecto).filter(Proyecto.inmobiliaria.isnot(None), Proyecto.inmobiliaria != "").all():
            n = p.inmobiliaria.strip()
            if not n:
                continue
            nombres.add(n)
            ex = (p.extra or {}).get("inmobiliaria") or {}
            d = info_by_name[n]
            # Preferir valores no-vacíos; el primero gana
            if not d["rut"] and ex.get("rut"):       d["rut"] = ex["rut"]
            if not d["web"] and ex.get("web"):       d["web"] = ex["web"]
            if not d["direccion"] and ex.get("direccion"): d["direccion"] = ex["direccion"]

        # 2. Filtrar las que YA existen en la tabla (case-insensitive)
        ya = {i.nombre.strip().lower() for i in db.query(Inmobiliaria).all()}
        crear = sorted(n for n in nombres if n.lower() not in ya)

        print(f"\nNombres distintos en proyectos: {len(nombres)}")
        print(f"  • Ya en tabla 'inmobiliarias': {len(ya)}")
        print(f"  • A crear: {len(crear)}\n")

        if crear:
            print("=== Inmobiliarias a crear ===")
            for n in crear:
                d = info_by_name[n]
                rut = d['rut'] or '-'
                web = d['web'] or '-'
                print(f"  • {n:40} · rut={rut:>14} · web={web}")

        if args.apply and crear:
            print(f"\nCreando {len(crear)} inmobiliarias…")
            now = datetime.utcnow()
            for n in crear:
                d = info_by_name[n]
                inm = Inmobiliaria(
                    id=_gen_id(),
                    nombre=n,
                    rut=(d["rut"] or "").strip() or None,
                    web=(d["web"] or "").strip() or None,
                    direccion=(d["direccion"] or "").strip() or None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(inm)
            db.commit()
            print(f"✓ {len(crear)} inmobiliarias creadas.")
        elif args.dry_run:
            print("\n(dry-run — sin cambios en BD. Re-correr con --apply.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
