"""Backup diario del stock (proyectos + unidades + imagenes + documentos).

Corre por cron en el VPS (NUNCA como loop local — se pierde al dormir/cerrar
el Mac). Vuelca TODO en un solo JSON con fecha y hora, para poder revertir a
mano si algún import/bug corrompe datos (motivación: bug real de Excel que
mezcló estacionamientos/bodegas en Unidades, 2026-07-21).

Uso (en el VPS):
    python -m scripts.backup_stock_diario

Guarda en /opt/bc-api/backups/stock/YYYY-MM-DD_HHMMSS.json.gz — NUNCA bajo
uploads/ (ese directorio se sirve público en /uploads, un backup ahí quedaría
descargable por cualquiera). Borra backups con más de RETENTION_DAYS días.
"""
from __future__ import annotations
import gzip
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app.db import SessionLocal
from app.models import Proyecto

BACKUP_DIR = Path("/opt/bc-api/backups/stock")
RETENTION_DAYS = 90


def _serializar_unidad(u) -> dict:
    return {
        "id": u.id, "numero": u.numero, "modelo": u.modelo, "tipologia": u.tipologia,
        "tipo": u.tipo, "orientacion": u.orientacion,
        "sup_total": u.sup_total, "sup_interior": u.sup_interior,
        "sup_terraza": u.sup_terraza, "sup_logia": u.sup_logia, "sup_jardin": u.sup_jardin,
        "precio_lista_uf": u.precio_lista_uf, "descuento_pct": u.descuento_pct,
        "bono_pie_pct": u.bono_pie_pct, "precio_final_uf": u.precio_final_uf,
        "estac_flag": u.estac_flag, "bodega_flag": u.bodega_flag, "pack_flag": u.pack_flag,
        "disponible": u.disponible,
    }


def _serializar_imagen(im) -> dict:
    return {"id": im.id, "url": im.url, "categoria": im.categoria, "es_principal": im.es_principal}


def _serializar_documento(d) -> dict:
    return {"id": d.id, "nombre": d.nombre, "url": d.url, "tipo": d.tipo}


def _serializar_proyecto(p: Proyecto) -> dict:
    return {
        "id": p.id, "codigo_corto": p.codigo_corto, "nombre": p.nombre,
        "inmobiliaria": p.inmobiliaria, "comuna": p.comuna, "region": p.region,
        "direccion": p.direccion, "gps_lat": p.gps_lat, "gps_lon": p.gps_lon,
        "fase": p.fase, "modalidad": p.modalidad, "activo": p.activo, "disponible": p.disponible,
        "fecha_entrega": p.fecha_entrega, "ano_entrega": p.ano_entrega,
        "foto_principal_url": p.foto_principal_url, "external_url": p.external_url,
        "notas": p.notas, "extra": p.extra,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "stock_updated_at": p.stock_updated_at.isoformat() if p.stock_updated_at else None,
        "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
        "unidades": [_serializar_unidad(u) for u in p.unidades],
        "imagenes": [_serializar_imagen(im) for im in p.imagenes],
        "documentos": [_serializar_documento(d) for d in p.documentos],
    }


def _limpiar_viejos():
    if not BACKUP_DIR.exists():
        return
    limite = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    borrados = 0
    for f in BACKUP_DIR.glob("*.json.gz"):
        try:
            fecha_str = f.stem.replace(".json", "")[:19]  # "YYYY-MM-DD_HHMMSS"
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue
        if fecha < limite:
            f.unlink()
            borrados += 1
    if borrados:
        print(f"🧹 Borrados {borrados} backups con más de {RETENTION_DAYS} días.")


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        proyectos = db.query(Proyecto).all()
        payload = {
            "generado_at": datetime.utcnow().isoformat() + "Z",
            "total_proyectos": len(proyectos),
            "total_unidades": sum(len(p.unidades) for p in proyectos),
            "proyectos": [_serializar_proyecto(p) for p in proyectos],
        }
    finally:
        db.close()

    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    destino = BACKUP_DIR / f"{ts}.json.gz"
    with gzip.open(destino, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    tam_kb = destino.stat().st_size / 1024
    print(f"✓ Backup OK: {destino} ({tam_kb:.0f} KB, {payload['total_proyectos']} proyectos, "
          f"{payload['total_unidades']} unidades)")

    _limpiar_viejos()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ BACKUP FALLÓ: {e}", file=sys.stderr)
        sys.exit(1)
