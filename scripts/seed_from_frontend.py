"""Importa proyectos del seed-pinar.js (frontend stock-interno) a la DB Postgres.

Uso:
    python scripts/seed_from_frontend.py /path/to/Herramientas\\ BC/src/stock-interno/data/seed-pinar.js

Convierte:
    window.BC_SEED_PROJECTS = [ {...}, {...} ];
en una lista Python parseable y la inserta vía SQLAlchemy upsert (delete + insert).

Si no se pasa argumento, usa el path por defecto en este Mac.
"""
import json
import re
import sys
import uuid
from pathlib import Path

# Permitir correr desde la raíz del repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import Proyecto, Unidad, Imagen, Documento  # noqa: E402

DEFAULT_PATH = "/Users/nicolas/Documents/Claude/Projects/Herramientas BC/src/stock-interno/data/seed-pinar.js"

# Campos planos del proyecto que mapean directo a columnas
DIRECT_FIELDS = {
    "nombre", "inmobiliaria", "comuna", "region", "direccion",
    "gps_lat", "gps_lon", "fase", "modalidad", "activo", "disponible",
    "fecha_entrega", "ano_entrega", "foto_principal_url", "external_url",
    "notas",
}


def parse_seed(js_path: Path) -> list[dict]:
    text = js_path.read_text(encoding="utf-8")
    # Extraer el array JS — desde [ hasta ]; del primer asignamiento
    m = re.search(r"window\.BC_SEED_PROJECTS\s*=\s*(\[[\s\S]*?\]);?\s*(?:window\.|\Z)", text)
    if not m:
        raise SystemExit("No encontré 'window.BC_SEED_PROJECTS = [...]' en el archivo")
    raw = m.group(1)
    # JSON-like; tolerar trailing commas borrándolas
    raw = re.sub(r",(\s*[}\]])", r"\1", raw)
    return json.loads(raw)


def seed(js_path: Path) -> None:
    projects = parse_seed(js_path)
    db = SessionLocal()
    try:
        for src in projects:
            pid = src.get("id") or "p-" + uuid.uuid4().hex[:8]
            # Wipe si existe
            existing = db.get(Proyecto, pid)
            if existing:
                db.delete(existing)
                db.flush()

            # Separar campos directos vs extra
            extra = {}
            direct = {}
            for k, v in src.items():
                if k in DIRECT_FIELDS:
                    direct[k] = v
                elif k in ("id", "imagenes", "unidades", "documentos", "stock_last_upload",
                           "created_at", "updated_at", "external_id", "estado", "stock"):
                    pass  # ignorados o procesados aparte
                else:
                    extra[k] = v

            # Compat: si viene 'estado' viejo, mapear a 'fase'
            if "fase" not in direct and src.get("estado"):
                direct["fase"] = src["estado"]

            p = Proyecto(id=pid, extra=extra, **direct)
            db.add(p)
            db.flush()

            # Unidades
            for u in (src.get("unidades") or []):
                db.add(Unidad(
                    id=u.get("id") or "u-" + uuid.uuid4().hex[:10],
                    proyecto_id=pid,
                    numero=str(u.get("numero", "")),
                    modelo=u.get("modelo"),
                    tipologia=u.get("tipologia"),
                    tipo=u.get("tipo", "Depto"),
                    orientacion=u.get("orientacion"),
                    sup_total=u.get("sup_total"),
                    sup_interior=u.get("sup_interior"),
                    sup_terraza=u.get("sup_terraza"),
                    sup_logia=u.get("sup_logia"),
                    sup_jardin=u.get("sup_jardin"),
                    precio_lista_uf=u.get("precio_lista_uf"),
                    descuento_pct=u.get("descuento_pct") or 0,
                    bono_pie_pct=u.get("bono_pie_pct") or 0,
                    precio_final_uf=u.get("precio_final_uf"),
                    estac_flag=u.get("estac_flag", "optional"),
                    bodega_flag=u.get("bodega_flag", "optional"),
                    pack_flag=u.get("pack_flag", "optional"),
                    disponible=bool(u.get("disponible", True)),
                ))

            # Imágenes
            for i, im in enumerate(src.get("imagenes") or []):
                db.add(Imagen(
                    id=im.get("id") or "img-" + uuid.uuid4().hex[:10],
                    proyecto_id=pid,
                    url=im.get("url", ""),
                    categoria=im.get("categoria", "Otro"),
                    es_principal=bool(im.get("es_principal", 0)),
                    orden=im.get("orden", i),
                ))

            # Documentos
            for d in (src.get("documentos") or []):
                db.add(Documento(
                    id=d.get("id") or "doc-" + uuid.uuid4().hex[:10],
                    proyecto_id=pid,
                    nombre=d.get("nombre") or d.get("filename") or "Documento",
                    tipo=d.get("tipo"),
                    url=d.get("url", ""),
                ))

            print(f"  · {pid:20s} → {len(src.get('unidades') or []):3d} unidades, "
                  f"{len(src.get('imagenes') or []):3d} fotos, "
                  f"{len(src.get('documentos') or []):2d} docs")

        db.commit()
        print(f"\n✓ {len(projects)} proyecto(s) importado(s) a la DB")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_PATH)
    if not path.exists():
        raise SystemExit(f"Archivo no encontrado: {path}")
    print(f"Importando desde: {path}")
    seed(path)
