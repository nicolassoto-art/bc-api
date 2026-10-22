"""Diagnóstico de solo lectura: ¿bc-api puede leer la foto de GHL (latest.json) y
trae las citas de las setters? No imprime nombres ni teléfonos, solo conteos y llaves."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

RUTAS = ["/opt/bigcapital-dashboard/data/latest.json", "/var/www/herramientas/data/latest.json"]
SETTERS = {"j2vjPJ78gO7maOxUEh4W": "Mafalda", "SZpegYySvjtgTpJZVqDE": "Maria"}
CAL_MARIA = "NfBiNDyswEeL4KXJyXN4"

for ruta in RUTAS:
    print("==", ruta, "existe:", os.path.exists(ruta), "legible:", os.access(ruta, os.R_OK))
    if not os.access(ruta, os.R_OK):
        continue
    print("tamaño:", os.path.getsize(ruta), "modificado:", os.path.getmtime(ruta))
    d = json.load(open(ruta))
    print("llaves:", list(d)[:40] if isinstance(d, dict) else type(d))
    ev = d.get("calendar_events") or d.get("calendarEvents") or []
    print("calendar_events:", len(ev))
    if ev:
        print("campos de un evento:", sorted(ev[0].keys()))
        cb = Counter()
        cal = Counter()
        for e in ev:
            c = e.get("createdBy") or {}
            uid = c.get("userId") if isinstance(c, dict) else c
            if uid in SETTERS:
                cb[(SETTERS[uid], e.get("appointmentStatus"))] += 1
            if e.get("calendarId") == CAL_MARIA:
                cal[e.get("appointmentStatus")] += 1
        print("creadas por setter (setter, estado):", dict(cb))
        print("en calendario de María (estado):", dict(cal))
        fechas = sorted(str(e.get("dateAdded") or e.get("createdAt") or "")[:10] for e in ev if e.get("dateAdded") or e.get("createdAt"))
        print("rango dateAdded:", fechas[:1], fechas[-1:])
    us = d.get("users") or []
    print("users:", len(us), "con ids de setters:", [SETTERS[u.get("id")] for u in us if isinstance(u, dict) and u.get("id") in SETTERS])
sys.exit(0)
