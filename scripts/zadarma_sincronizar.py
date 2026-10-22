"""Trae a bc-api las llamadas de Zadarma de un período (respaldo del webhook).

Uso en el VPS:  .venv/bin/python scripts/zadarma_sincronizar.py --desde 2026-10-20 [--hasta 2026-10-22]
Muestra cuántas llamadas trajo por anexo. No imprime teléfonos.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.llamada import Llamada  # noqa: E402
from app.services import zadarma  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", default="")
    a = ap.parse_args()
    desde = datetime.strptime(a.desde, "%Y-%m-%d")
    hasta = datetime.strptime(a.hasta, "%Y-%m-%d") + timedelta(days=1) if a.hasta else datetime.now()
    db = SessionLocal()
    try:
        n = zadarma.sincronizar_estadisticas(db, desde, hasta)
        t = zadarma.traer_transcripciones_faltantes(db, limite=80)
        print(f"Llamadas sincronizadas: {n} · transcripciones nuevas: {t}")
        for anexo, setter, total, primera, ultima in (
            db.query(Llamada.anexo, Llamada.setter, func.count(), func.min(Llamada.inicio), func.max(Llamada.inicio))
            .filter(Llamada.inicio >= desde, Llamada.inicio < hasta)
            .group_by(Llamada.anexo, Llamada.setter).order_by(Llamada.anexo).all()
        ):
            print(f"  anexo {anexo} ({setter or 'no es setter'}): {total} llamadas, de {primera} a {ultima}")
        from app.models.llamada import ZadarmaEvento
        eventos = (db.query(ZadarmaEvento.evento, func.count(), func.max(ZadarmaEvento.recibido_en))
                   .group_by(ZadarmaEvento.evento).all())
        print("Avisos recibidos por el webhook:", eventos or "ninguno")
        estados = db.query(Llamada.estado, func.count()).group_by(Llamada.estado).all()
        print("Estados de las llamadas:", estados)
        con_grab = db.query(func.count()).select_from(Llamada).filter(Llamada.call_id_con_grabacion.isnot(None)).scalar()
        print("Llamadas con grabación:", con_grab)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
