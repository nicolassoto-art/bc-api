"""Diagnóstico (solo lectura) de las reuniones de las setters en la foto de GHL.

Corre en el VPS como root (la foto es solo del administrador). Imprime SOLO conteos:
antigüedad de la foto, rango de fechas, estados que existen, y cómo se atribuye cada cita
(creada por la setter, en su calendario, o ambas). Sin nombres, teléfonos ni ids de contactos.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraer_reuniones_setters import CHILE, _fecha, extraer  # noqa: E402

FOTO = "/opt/bigcapital-dashboard/data/latest.json"
SETTERS = {"j2vjPJ78gO7maOxUEh4W": "102", "SZpegYySvjtgTpJZVqDE": "103"}
CALS = {"nDdlsuYhUL1e9MfbTVZZ": "102", "NfBiNDyswEeL4KXJyXN4": "103"}


def main() -> int:
    foto = json.load(open(FOTO, encoding="utf-8"))
    ev = foto.get("calendar_events") or []
    print("Foto generada:", (foto.get("metadata") or {}).get("generated_at"), "· ahora UTC:", datetime.now(timezone.utc).isoformat()[:19])
    print("Citas en la foto:", len(ev), "· borradas:", sum(1 for e in ev if e.get("deleted")))
    ini = [d for d in (_fecha(e.get("startTime")) for e in ev) if d]
    add = [d for d in (_fecha(e.get("dateAdded")) for e in ev) if d]
    if ini:
        print("startTime de", min(ini).date(), "a", max(ini).date(), "· dateAdded de", min(add).date() if add else "?", "a", max(add).date() if add else "?")
    print("Estados (todas las citas):", dict(Counter(str(e.get("appointmentStatus") or e.get("appoinmentStatus") or "").lower() for e in ev)))
    atr = Counter()
    estados = {"102": Counter(), "103": Counter()}
    for e in ev:
        c = e.get("createdBy") or {}
        uid = c.get("userId") if isinstance(c, dict) else c
        por_creador, por_cal = SETTERS.get(uid), CALS.get(e.get("calendarId"))
        if por_creador and por_cal and por_creador == por_cal:
            k = "creada por ella y en su calendario"
        elif por_creador and por_cal:
            k = "creada por una y en el calendario de la otra"
        elif por_creador:
            k = "creada por ella, en otro calendario"
        elif por_cal:
            k = "en su calendario, creada por otro usuario"
        else:
            continue
        a = por_creador or por_cal
        atr[(a, k)] += 1
        estados[a][str(e.get("appointmentStatus") or "").lower()] += 1
    for (a, k), n in sorted(atr.items()):
        print(f"  anexo {a}: {n} {k}")
    print("Estados atribuidos:", {a: dict(c) for a, c in estados.items()})
    r = extraer(foto, SETTERS, CALS)
    print("Por día (conteos que usa el panel):")
    for dia in sorted(r["por_dia"])[-8:]:
        print(" ", dia, r["por_dia"][dia])
    print("Hora Chile ahora:", datetime.now(CHILE).strftime("%Y-%m-%d %H:%M"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
