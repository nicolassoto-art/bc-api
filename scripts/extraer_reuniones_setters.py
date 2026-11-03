"""Extrae las reuniones de las setters desde la foto de GHL (latest.json) para bc-api.

Corre como tarea programada del servidor (systemd, cada 10 min, como root porque la
foto es solo del administrador). Deja en /opt/bc-api/estado/reuniones_setters.json
SOLO conteos por anexo y día (sin nombres, teléfonos ni ids de contactos), legible
por bc-api. Solo usa la biblioteca estándar de Python (Meet se consulta con el
entorno propio de ghl-ia, en un subproceso).

Atribución: la cita es de la setter si la creó ella (createdBy.userId) o si está en
su calendario. Dos lecturas por día:
  · por día de la REUNIÓN → reuniones_del_dia, asistidas, inasistencias, canceladas,
    pendientes (futuras) y sin_resultado (pasadas sin estado), según el estado de Nova;
  · por día de CREACIÓN (solo las que creó ella) → agendadas y su resultado, para que
    las columnas sumen: agendadas = ag_asistidas + ag_inasistencias + ag_canceladas +
    ag_futuras + ag_sin_resultado. Y la asistencia según Google Meet (regla del
    negocio: asistió = entraron los dos; no asistió = solo el asesor), para cada cita
    pasada no cancelada: meet_asistio + meet_no_asistio + meet_sin_prueba. Si Meet no
    responde, esas tres claves salen del estado de Nova y `asistencia_fuente` = "nova".

Citas de prueba e internas fuera: título o contacto que contenga «prueba» o «test»
(sin importar mayúsculas ni acentos), contactos «Aviso», contactos del equipo (nombre
igual al de un usuario de GHL o correo @bigcapital.cl) y los eventos internos que
excluyen los Informes (no agendar, feriado, bloqueo, vacaciones, recordatorio,
reunión de equipo…).

Uso:
  python3 extraer_reuniones_setters.py --setter 102=<ghl_user_id> --setter 103=<ghl_user_id> \
      [--calendario 103=<calendar_id>] [--foto ...] [--salida ...] [--dueno bcapi] [--sin-meet]
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CHILE = ZoneInfo("America/Santiago")
ASISTIO = {"showed", "completed", "attended"}
NO_ASISTIO = {"noshow", "no_show"}
CANCELADA = {"cancelled", "canceled", "invalid"}

# Mismo criterio que los Informes (Herramientas BC, scripts/gerencia_datos.py) + pruebas.
RX_INTERNO = re.compile(r"(prueba|\btest\b|\baviso\b|\bno agendar\b|\bferiado\b|\bbloqueo\b|"
                        r"\bbloqueado\b|\bvacaciones\b|\benviar\b|\brecordar\b|\brecordatorio\b|"
                        r"\breunion (de |del )?equipo\b)")
CONTACTO_COMODIN = "PoWRAtiY4eoOKX4N0xHz"
DOMINIO_PROPIO = "@bigcapital.cl"


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


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


def _contactos(foto: dict) -> dict[str, tuple[str, str]]:
    """contactId → (nombre, correo) normalizados, desde oportunidades y conversaciones."""
    out: dict[str, tuple[str, str]] = {}
    for op in foto.get("opportunities") or []:
        c = op.get("contact") or {}
        cid = op.get("contactId") or c.get("id")
        if cid:
            out[cid] = (_norm(c.get("name") or op.get("name")), _norm(c.get("email")))
    for cv in foto.get("conversations") or []:
        cid = cv.get("contactId")
        if cid and (cid not in out or not all(out[cid])):
            nombre, correo = out.get(cid, ("", ""))
            out[cid] = (nombre or _norm(cv.get("fullName") or cv.get("contactName")), correo or _norm(cv.get("email")))
    return out


def es_interna(e: dict, contactos: dict, equipo: set[str]) -> bool:
    """Cita de prueba, de alguien del equipo o evento interno (no es una reunión con un cliente)."""
    cid = e.get("contactId")
    if not cid or cid == CONTACTO_COMODIN:
        return True
    nombre, correo = contactos.get(cid, ("", ""))
    if RX_INTERNO.search(_norm(e.get("title"))) or RX_INTERNO.search(nombre):
        return True
    return correo.endswith(DOMINIO_PROPIO) or (bool(nombre) and nombre in equipo)


def citas(foto: dict, setters: dict[str, str], calendarios: dict[str, str]):
    """(evento, anexo, la creó ella, estado Nova, creada, inicio) de cada cita válida de las setters."""
    contactos = _contactos(foto)
    equipo = {_norm(u.get("name")) for u in foto.get("users") or [] if _norm(u.get("name"))}
    for e in foto.get("calendar_events") or []:
        if e.get("deleted"):
            continue
        creador = e.get("createdBy") or {}
        uid = creador.get("userId") if isinstance(creador, dict) else creador
        propia = setters.get(uid)          # la creó ella
        anexo = propia or calendarios.get(e.get("calendarId"))
        if not anexo or es_interna(e, contactos, equipo):
            continue
        estado = str(e.get("appointmentStatus") or e.get("appoinmentStatus") or "").lower()
        yield e, anexo, bool(propia), estado, _fecha(e.get("dateAdded")), _fecha(e.get("startTime"))


SNIPPET_MEET = r'''
import asyncio, json, sys
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.meeting_artifact import MeetingArtifact
from app.recovery.corregir_asistencia import clasificar_prueba

async def main():
    ids = json.load(sys.stdin)
    out = {}
    async with AsyncSessionLocal() as db:
        q = select(MeetingArtifact).where(MeetingArtifact.appointment_id.in_(ids))
        for a in (await db.execute(q)).scalars().all():
            v = clasificar_prueba(a.duration_seconds, a.transcript_text, a.client_talk_ratio, a.broker_talk_ratio)
            clase = "ambos" if v.startswith("fuerte") else "solo_asesor" if "solo el asesor" in v else "sin_prueba"
            if out.get(a.appointment_id) != "ambos":
                out[a.appointment_id] = clase
    print(json.dumps(out))

asyncio.run(main())
'''


def asistencia_meet(ids: list[str], carpeta: str = "/opt/ghl-ia") -> dict[str, str] | None:
    """id de cita → "ambos" | "solo_asesor" | "sin_prueba" según meeting_artifacts de ghl-ia.

    La evaluación es `clasificar_prueba` de ghl-ia (la regla del negocio vive allá, igual
    que en kpi_rentabilizacion.asistencia_verificada). None si Meet no está disponible."""
    if not ids:
        return {}
    try:
        r = subprocess.run([os.path.join(carpeta, ".venv/bin/python3"), "-c", SNIPPET_MEET], cwd=carpeta,
                           input=json.dumps(ids), capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"Meet no disponible: {r.stderr.strip()[-200:]}")
            return None
        datos = json.loads(r.stdout.strip().splitlines()[-1])
        return datos if isinstance(datos, dict) else None
    except Exception as ex:  # noqa: BLE001 — sin Meet se cae al estado de Nova, nunca se rompe
        print(f"Meet no disponible: {ex}")
        return None


def _resultado(estado: str, inicio: datetime | None, ahora: datetime) -> str:
    if estado in ASISTIO:
        return "asistidas"
    if estado in NO_ASISTIO:
        return "inasistencias"
    if estado in CANCELADA:
        return "canceladas"
    if inicio and inicio > ahora:
        return "pendientes"
    return "sin_resultado"


AG = {"asistidas": "ag_asistidas", "inasistencias": "ag_inasistencias", "canceladas": "ag_canceladas",
      "pendientes": "ag_futuras", "sin_resultado": "ag_sin_resultado"}
MEET = {"ambos": "meet_asistio", "solo_asesor": "meet_no_asistio", "sin_prueba": "meet_sin_prueba"}


def extraer(foto: dict, setters: dict[str, str], calendarios: dict[str, str],
            meet: dict[str, str] | None = None, ahora: datetime | None = None) -> dict:
    """`meet`: id de cita → clase de Meet (ver asistencia_meet); None = Meet no disponible."""
    ahora = ahora or datetime.now(CHILE)
    dias: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for e, anexo, propia, estado, creada, inicio in citas(foto, setters, calendarios):
        res = _resultado(estado, inicio, ahora)
        if creada and propia:              # una cita que otro creó en su calendario (formulario, tercero) no es agendada por ella
            c = dias[creada.date().isoformat()][anexo]
            c["agendadas"] += 1
            c[AG[res]] += 1
            if res != "canceladas" and inicio and inicio <= ahora:
                if meet is None:           # sin Meet: el estado de Nova
                    clase = {"asistidas": "ambos", "inasistencias": "solo_asesor"}.get(res, "sin_prueba")
                else:
                    clase = meet.get(e.get("id"), "sin_prueba")
                c[MEET[clase]] += 1
        if inicio:
            d = dias[inicio.date().isoformat()][anexo]
            d["reuniones_del_dia"] += 1
            d[res] += 1
    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "foto_modificada": (foto.get("metadata") or {}).get("generated_at"),
        "asistencia_fuente": "nova" if meet is None else "meet",
        "por_dia": {dia: {a: dict(c) for a, c in por_anexo.items()} for dia, por_anexo in dias.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--foto", default="/opt/bigcapital-dashboard/data/latest.json")
    ap.add_argument("--salida", default="/opt/bc-api/estado/reuniones_setters.json")
    ap.add_argument("--setter", action="append", default=[], help="anexo=ghl_user_id")
    ap.add_argument("--calendario", action="append", default=[], help="anexo=calendar_id")
    ap.add_argument("--dueno", default="bcapi")
    ap.add_argument("--ghl-ia", default="/opt/ghl-ia", help="carpeta de ghl-ia (Meet)")
    ap.add_argument("--sin-meet", action="store_true", help="no consultar Meet (usa el estado de Nova)")
    a = ap.parse_args()

    with open(a.foto, encoding="utf-8") as f:
        foto = json.load(f)
    setters, calendarios = _pares(a.setter), _pares(a.calendario)
    ahora = datetime.now(CHILE)
    pasadas = sorted({e["id"] for e, _a, propia, _s, _c, inicio in citas(foto, setters, calendarios)
                      if propia and e.get("id") and inicio and inicio <= ahora})
    meet = None if a.sin_meet else asistencia_meet(pasadas, a.ghl_ia)
    datos = extraer(foto, setters, calendarios, meet, ahora)

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
    print(f"reuniones de setters: {len(datos['por_dia'])} días, {total} agendadas, "
          f"asistencia por {datos['asistencia_fuente']} → {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
