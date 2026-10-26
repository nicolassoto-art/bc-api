"""Valida (solo lectura) lo que muestra el panel de Llamadas contra Zadarma y contra los avisos del webhook.

Uso en el VPS:  .venv/bin/python scripts/validar_llamadas.py --desde 2026-10-20 [--hasta 2026-10-26]
Compara por anexo y día: llamadas, contestadas y segundos hablados (Zadarma vs base), y revisa la zona
horaria de Zadarma contra la hora real de recepción de los avisos. No imprime teléfonos.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.models.llamada import Llamada, ZadarmaEvento  # noqa: E402
from app.services import zadarma  # noqa: E402
from app.settings import settings  # noqa: E402


def traer(desde: datetime, hasta: datetime) -> dict[str, dict]:
    mejores, skip = {}, 0
    while True:
        r = zadarma.llamar_api("GET", "/v1/statistics/pbx/", {
            "start": desde.strftime("%Y-%m-%d %H:%M:%S"), "end": hasta.strftime("%Y-%m-%d %H:%M:%S"),
            "version": 2, "skip": skip, "limit": 1000})
        filas = r.get("stats") or []
        for f in filas:
            p = str(f.get("pbx_call_id") or "").strip()
            if p:
                k = lambda x: (x.get("disposition") == "answered", int(x.get("seconds") or 0))  # noqa: E731
                if p not in mejores or k(f) > k(mejores[p]):
                    mejores[p] = f
        if len(filas) < 1000:
            return mejores
        skip += 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", default="")
    a = ap.parse_args()
    desde = datetime.strptime(a.desde, "%Y-%m-%d")
    hasta = (datetime.strptime(a.hasta, "%Y-%m-%d") if a.hasta else datetime.now()) + timedelta(days=1)
    z = traer(desde, hasta)
    zz: dict = defaultdict(lambda: [0, 0, 0])
    for f in z.values():
        c = zadarma.fila_estadistica_a_campos(f)
        if c["anexo"] not in settings.zadarma_anexos_map or c["sentido"] == "interna" or c["numero_cliente"] == "4444" or not c["inicio"]:
            continue
        k = (c["anexo"], c["inicio"].date().isoformat())
        zz[k][0] += 1
        if c["resultado"] == "answered":
            zz[k][1] += 1
            zz[k][2] += c["duracion_s"] or 0
    db = SessionLocal()
    dd: dict = defaultdict(lambda: [0, 0, 0])
    for x in db.query(Llamada).filter(Llamada.inicio >= desde, Llamada.inicio < hasta, Llamada.anexo.in_(list(settings.zadarma_anexos_map))).all():
        if x.sentido == "interna" or x.numero_cliente == "4444" or not x.inicio:
            continue
        k = (x.anexo, x.inicio.date().isoformat())
        dd[k][0] += 1
        if x.resultado == "answered":
            dd[k][1] += 1
            dd[k][2] += x.duracion_s or 0
    print("anexo · día · [llamadas, contestadas, seg hablados]  Zadarma  vs  base  → coincide")
    mal = 0
    for k in sorted(set(zz) | set(dd)):
        ok = list(zz[k]) == list(dd[k])
        mal += not ok
        print(f"  {k[0]} {k[1]}  {list(zz[k])}  vs  {list(dd[k])}  → {'OK' if ok else 'DIFIERE'}")
    print(f"Filas que difieren: {mal}")
    try:
        print("Zona horaria de la cuenta Zadarma:", zadarma.llamar_api("GET", "/v1/info/timezone/", {}))
    except Exception as e:  # noqa: BLE001
        print("No se pudo leer la zona horaria:", str(e)[:120])
    print("Hora UTC ahora:", datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "· Chile aprox:", (datetime.utcnow() - timedelta(hours=3)).strftime("%H:%M"))
    ev = (db.query(ZadarmaEvento).filter(ZadarmaEvento.evento.in_(["NOTIFY_START", "NOTIFY_OUT_START"]))
          .order_by(ZadarmaEvento.recibido_en.desc()).limit(5).all())
    for e in ev:
        d = e.payload or {}
        print(f"  aviso {e.evento}: call_start={d.get('call_start')} · recibido_en(UTC)={e.recibido_en}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
