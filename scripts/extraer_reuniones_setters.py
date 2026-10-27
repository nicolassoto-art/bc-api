"""Extrae las reuniones de las setters desde la foto de GHL (latest.json) para bc-api.

Corre como tarea programada del servidor (systemd, cada 10 min, como root porque la
foto es solo del administrador). Deja en /opt/bc-api/estado/reuniones_setters.json
SOLO conteos por anexo y día (sin nombres, teléfonos ni ids de contactos), legible
por bc-api. Solo usa la biblioteca estándar de Python.

Atribución: «agendadas» solo cuenta las que creó ella (createdBy.userId); las que otro creó en
su calendario (formulario web, terceros) cuentan en sus reuniones del día pero no como agendadas.
Por día de creación → agendadas; por día de la reunión → asistidas,
inasistencias, canceladas, pendientes (futuras) y sin resultado (pasadas sin estado).

Uso:
  python3 extraer_reuniones_setters.py --setter 102=<ghl_user_id> --setter 103=<ghl_user_id> \
      [--calendario 103=<calendar_id>] [--foto ...] [--salida ...] [--dueno bcapi]
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CHILE = ZoneInfo("America/Santiago")
ASISTIO = {"showed", "completed", "attended"}
NO_ASISTIO = {"noshow", "no_show"}
CANCELADA = {"cancelled", "canceled", "invalid"}


def _fecha(valor) -> datetime | None:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=CHILE)
    return d.astimezone(CHILE)


def _pares(valores: list[str]) -> dict[str, str]:
    out = {}
    for v in valores or []:
        anexo, _, ident = v.partition("=")
        if anexo and ident:
            out[ident.strip()] = anexo.strip()
    return out


def extraer(foto: dict, setters: dict[str, str], calendarios: dict[str, str]) -> dict:
    ahora = datetime.now(CHILE)
    dias: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for e in foto.get("calendar_events") or []:
        if e.get("deleted") or str(e.get("title") or "").strip().lower().startswith("prueba"):
            continue
        creador = e.get("createdBy") or {}
        uid = creador.get("userId") if isinstance(creador, dict) else creador
        propia = setters.get(uid)          # la creó ella
        anexo = propia or calendarios.get(e.get("calendarId"))
        if not anexo:
            continue
        estado = str(e.get("appointmentStatus") or e.get("appoinmentStatus") or "").lower()
        creada, inicio = _fecha(e.get("dateAdded")), _fecha(e.get("startTime"))
        if creada and propia:              # una cita que otro creó en su calendario (formulario, tercero) no es agendada por ella
            dias[creada.date().isoformat()][anexo]["agendadas"] += 1
        if inicio:
            d = dias[inicio.date().isoformat()][anexo]
            d["reuniones_del_dia"] += 1
            if estado in ASISTIO:
                d["asistidas"] += 1
            elif estado in NO_ASISTIO:
                d["inasistencias"] += 1
            elif estado in CANCELADA:
                d["canceladas"] += 1
            elif inicio > ahora:
                d["pendientes"] += 1
            else:
                d["sin_resultado"] += 1
    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "foto_modificada": (foto.get("metadata") or {}).get("generated_at"),
        "por_dia": {dia: {a: dict(c) for a, c in por_anexo.items()} for dia, por_anexo in dias.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--foto", default="/opt/bigcapital-dashboard/data/latest.json")
    ap.add_argument("--salida", default="/opt/bc-api/estado/reuniones_setters.json")
    ap.add_argument("--setter", action="append", default=[], help="anexo=ghl_user_id")
    ap.add_argument("--calendario", action="append", default=[], help="anexo=calendar_id")
    ap.add_argument("--dueno", default="bcapi")
    a = ap.parse_args()

    with open(a.foto, encoding="utf-8") as f:
        foto = json.load(f)
    datos = extraer(foto, _pares(a.setter), _pares(a.calendario))

    carpeta = os.path.dirname(a.salida)
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=".reuniones_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    try:
        u = pwd.getpwnam(a.dueno)
        os.chown(tmp, u.pw_uid, u.pw_gid)
    except KeyError:
        pass
    os.chmod(tmp, 0o640)
    os.replace(tmp, a.salida)
    total = sum(c.get("agendadas", 0) for d in datos["por_dia"].values() for c in d.values())
    print(f"reuniones de setters: {len(datos['por_dia'])} días, {total} agendadas → {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
