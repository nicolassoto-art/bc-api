"""Backfill: deriva tipologia="{d}D{b}B" para unidades-depto sin tipología,
usando dormitorios/banos del modelo registrado en extra.modelos (mismo criterio
que ya usa la plantilla de Excel al derivar tipología por modelo).

Alcance: unidades disponibles, tipo depto (no estac/bodega/pack), tipologia
vacía, cuyo `modelo` matchea (case/acentos-insensible) un modelo del proyecto
con dormitorios+banos registrados. Auditoría 2026-07-22: 2375/2377 unidades
en 30 proyectos resuelven así (legado de un import viejo que no seteaba
tipología, `tipo='apartment'` — el pipeline actual ya la deriva bien).

Uso:
    python -m scripts.backfill_tipologia_desde_modelo --dry-run
    python -m scripts.backfill_tipologia_desde_modelo --apply
"""
from __future__ import annotations
import argparse
import unicodedata

from app.db import SessionLocal
from app.models import Proyecto


def _norm(s):
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s


def _es_depto(u):
    t = (u.tipo or "").lower()
    n = u.numero or ""
    if n.startswith("E-") or "estac" in t or "parking" in t:
        return False
    if n.startswith("B-") or "bodeg" in t or t == "storage":
        return False
    if "pack" in t:
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        proyectos = db.query(Proyecto).filter(Proyecto.deleted_at.is_(None)).all()
        cambios = []  # (proyecto_id, unidad, tipologia_nueva)
        sin_resolver = []
        for p in proyectos:
            modelos = (p.extra or {}).get("modelos") or []
            mmap = {}
            for m in modelos:
                nombre = _norm(m.get("nombre") or m.get("name"))
                d, b = m.get("dormitorios"), m.get("banos")
                if nombre and d is not None and b is not None:
                    mmap[nombre] = (d, b)
            for u in p.unidades:
                if not u.disponible or not _es_depto(u) or (u.tipologia or "").strip():
                    continue
                mk = _norm(u.modelo)
                if mk in mmap:
                    d, b = mmap[mk]
                    nueva = f"{d}D{b}B"
                    cambios.append((p.id, u, nueva))
                else:
                    sin_resolver.append((p.id, u.numero, u.modelo))

        print(f"\nUnidades a corregir: {len(cambios)}")
        print(f"Sin poder resolver (modelo no matchea/sin d-b registrado): {len(sin_resolver)}")
        for pid, num, modelo in sin_resolver:
            print(f"  ⚠ {pid} · unidad {num} · modelo={modelo!r}")

        if args.apply and cambios:
            for pid, u, nueva in cambios:
                u.tipologia = nueva
            db.commit()
            print(f"\n✓ {len(cambios)} unidades actualizadas.")
        elif args.dry_run:
            print("\n(dry-run — sin cambios en BD. Re-correr con --apply.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
