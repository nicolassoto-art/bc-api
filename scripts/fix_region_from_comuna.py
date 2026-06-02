"""Backfill: deducir Proyecto.region desde Proyecto.comuna.

Muchos proyectos importados de JetBrokers vienen sin 'region' porque JB solo
guarda la comuna. Como Chile tiene mapeo comuna→región fijo, este script
recorre los proyectos sin región y la rellena desde el catálogo.

Uso:
    python -m scripts.fix_region_from_comuna --dry-run   # solo muestra
    python -m scripts.fix_region_from_comuna --apply     # actualiza BD

Mantener sincronizado con src/stock-interno/data/datasets.js
(comunas_por_region) — son la misma fuente de verdad.
"""
from __future__ import annotations
import argparse
import sys
import unicodedata
from datetime import datetime

from app.db import SessionLocal
from app.models import Proyecto


# Espejo del catálogo del frontend (datasets.js).
COMUNAS_POR_REGION: dict[str, list[str]] = {
    "Metropolitana": [
        "Santiago","Providencia","Las Condes","Vitacura","Lo Barnechea","Ñuñoa","La Reina",
        "Macul","Peñalolén","Maipú","La Florida","Puente Alto","San Miguel","San Joaquín",
        "Estación Central","Quinta Normal","Independencia","Recoleta","Huechuraba","Conchalí",
        "Renca","Cerro Navia","Pudahuel","Lo Prado","Quilicura","Colina","Lampa","Tiltil",
        "San Bernardo","Buin","Paine","Calera de Tabaco",
    ],
    "Valparaíso": [
        "Valparaíso","Viña del Mar","Concón","Quilpué","Villa Alemana","Reñaca","Quintero",
        "Puchuncaví","San Antonio","Casablanca","Limache","Olmué",
    ],
    "Biobío": [
        "Concepción","Talcahuano","San Pedro de la Paz","Hualpén","Chiguayante","Penco",
        "Tomé","Coronel","Lota","Los Ángeles","Hualqui",
    ],
    "Ñuble": ["Chillán","Chillán Viejo","San Carlos","Bulnes","Yungay"],
    "O'Higgins": ["Rancagua","Machalí","Graneros","San Fernando","Santa Cruz"],
    "Maule": ["Talca","Curicó","Linares","Maule","San Clemente"],
    "La Araucanía": ["Temuco","Padre Las Casas","Villarrica","Pucón","Angol"],
    "Los Ríos": ["Valdivia","La Unión","Río Bueno","Paillaco"],
    "Los Lagos": ["Puerto Montt","Puerto Varas","Osorno","Castro","Ancud","Frutillar","Llanquihue"],
    "Coquimbo": ["La Serena","Coquimbo","Ovalle","Vicuña"],
    "Antofagasta": ["Antofagasta","Calama","Mejillones","Tocopilla"],
    "Tarapacá": ["Iquique","Alto Hospicio","Pozo Almonte"],
    "Atacama": ["Copiapó","Caldera","Vallenar"],
    "Aysén": ["Coyhaique","Puerto Aysén"],
    "Magallanes": ["Punta Arenas","Puerto Natales"],
    "Arica y Parinacota": ["Arica","Putre"],
}


def _norm(s: str) -> str:
    """Lowercase + strip + sin tildes (para matchear 'Ñuñoa' con 'nunoa')."""
    if not s:
        return ""
    n = unicodedata.normalize("NFD", str(s).strip().lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


# Índice invertido: norm(comuna) → region
COMUNA_TO_REGION: dict[str, str] = {}
for region, comunas in COMUNAS_POR_REGION.items():
    for c in comunas:
        COMUNA_TO_REGION[_norm(c)] = region


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="Solo muestra qué cambiaría")
    grp.add_argument("--apply", action="store_true", help="Aplica los cambios a la BD")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        candidatos = (
            db.query(Proyecto)
            .filter((Proyecto.region.is_(None)) | (Proyecto.region == ""))
            .filter(Proyecto.comuna.isnot(None))
            .all()
        )
        sin_match = []
        cambios = []
        for p in candidatos:
            r = COMUNA_TO_REGION.get(_norm(p.comuna))
            if r:
                cambios.append((p.id, p.nombre, p.comuna, r))
            else:
                sin_match.append((p.id, p.nombre, p.comuna))

        print(f"\nProyectos sin región: {len(candidatos)}")
        print(f"  • Deducibles:  {len(cambios)}")
        print(f"  • Sin match:   {len(sin_match)}\n")

        if cambios:
            print("=== Cambios a aplicar ===")
            for pid, nom, com, reg in cambios[:30]:
                print(f"  {pid[:24]:24} · {nom[:30]:30} · comuna='{com}' → region='{reg}'")
            if len(cambios) > 30:
                print(f"  ...y {len(cambios) - 30} más")

        if sin_match:
            print("\n=== Sin match (revisar a mano) ===")
            for pid, nom, com in sin_match[:20]:
                print(f"  {pid[:24]:24} · {nom[:30]:30} · comuna='{com}'")
            if len(sin_match) > 20:
                print(f"  ...y {len(sin_match) - 20} más")

        if args.apply and cambios:
            print(f"\nAplicando {len(cambios)} cambios...")
            now = datetime.utcnow()
            for pid, _, _, reg in cambios:
                p = db.get(Proyecto, pid)
                if p and (not p.region):
                    p.region = reg
                    p.updated_at = now
            db.commit()
            print(f"✓ {len(cambios)} proyectos actualizados.")
        elif args.dry_run:
            print("\n(dry-run — sin cambios en BD. Re-correr con --apply.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
