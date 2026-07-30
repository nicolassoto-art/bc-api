"""
audit_aj_urbana_freshness.py — Dead-man-switch de frescura para los 7 proyectos AJ Urbana.

AJ Urbana no usa el importador JetBrokers (confirmado 2026-07-26): su stock/precio/
descuento se actualiza 100% manual, vía carga de Excel (evento tipo "Excel Stock" en
extra.timeline), aparentemente alimentado por un sync externo (Drive -> bc-api,
sync_aj_to_bcapi.py) que no vive en este repo.

Este script NO valida que los datos sean correctos (para eso hace falta cruzar contra
la planilla real de AJ Urbana, que solo es legible por navegador autenticado hoy — no
hay credencial de servicio compartida). Lo que SÍ valida: que cada uno de los 7
proyectos haya tenido un evento "Excel Stock" reciente. Si el sync se cayó por completo,
esto lo detecta. Si el sync sigue corriendo pero deja datos parciales/incorrectos
(el caso real ya confirmado: unidad 1603 de Teatinos 750 quedó disponible=true en
bc-api mientras la fuente la marca no-disponible), este chequeo NO lo detecta — para
eso hace falta acceso de lectura a la planilla real.

Exit code 0 = todo fresco. Exit code 1 = al menos un proyecto lleva más de
UMBRAL_DIAS sin un evento "Excel Stock" nuevo (falla el workflow a propósito para que
GitHub Actions lo marque en rojo y notifique).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import httpx

PROYECTOS_AJ = [
    "edificio-teatinos-750",
    "monjitas-690",
    "edificio-vista-morand",
    "edificio-vista-amunategui",
    "edificio-downtown-san-mart-n",
    "santa-ana",
    "vista-san-martin",
]

UMBRAL_DIAS = int(os.environ.get("AJ_FRESHNESS_UMBRAL_DIAS", "3"))


def _parse_fecha(fecha_str: str) -> datetime:
    # bc-api guarda timestamps naive UTC o con sufijo Z — normalizar a aware UTC.
    s = fecha_str.rstrip("Z")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ.get("BC_API_JWT") or os.environ.get("STOCK_INTERNO_API_KEY")
    if not jwt:
        print("Falta BC_API_JWT o STOCK_INTERNO_API_KEY en el entorno")
        return 2

    cli = httpx.Client(
        base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0
    )
    ahora = datetime.now(timezone.utc)

    stale = []
    ok = []
    errores = []

    for pid in PROYECTOS_AJ:
        try:
            r = cli.get(f"/proyectos/{pid}")
            if r.status_code != 200:
                errores.append((pid, f"HTTP {r.status_code}"))
                continue
            data = r.json()
        except Exception as e:
            errores.append((pid, str(e)))
            continue

        extra = data.get("extra") or {}
        timeline = extra.get("timeline") or []
        eventos_excel = [e for e in timeline if e.get("tipo") == "Excel Stock" and e.get("fecha")]

        if not eventos_excel:
            stale.append((pid, None, "nunca tuvo un evento 'Excel Stock'"))
            continue

        ultimo = max(eventos_excel, key=lambda e: e["fecha"])
        fecha_ultimo = _parse_fecha(ultimo["fecha"])
        antiguedad = ahora - fecha_ultimo

        if antiguedad > timedelta(days=UMBRAL_DIAS):
            stale.append((pid, fecha_ultimo, f"{antiguedad.days} días sin sync"))
        else:
            ok.append((pid, fecha_ultimo, antiguedad))

    print(f"Umbral de frescura: {UMBRAL_DIAS} días\n")
    print(f"OK ({len(ok)}/{len(PROYECTOS_AJ)}):")
    for pid, fecha, antiguedad in ok:
        horas = antiguedad.total_seconds() / 3600
        print(f"  ✓ {pid}: último Excel Stock hace {horas:.1f}h ({fecha.isoformat()})")

    if errores:
        print(f"\nERRORES DE CONSULTA ({len(errores)}):")
        for pid, msg in errores:
            print(f"  ✗ {pid}: {msg}")

    if stale:
        print(f"\n⚠️  DESACTUALIZADOS ({len(stale)}/{len(PROYECTOS_AJ)}):")
        for pid, fecha, motivo in stale:
            fecha_str = fecha.isoformat() if fecha else "N/A"
            print(f"  ⚠️  {pid}: {motivo} (último: {fecha_str})")
        print(
            "\nSi el sync realmente sigue corriendo pero un proyecto puntual quedó "
            "desactualizado (ej. precios/stock parcial), este chequeo de FRESCURA no lo "
            "detecta — solo detecta que el sync se detuvo por completo. Para validar "
            "campo por campo hace falta cruzar contra la planilla real de AJ Urbana."
        )
        return 1

    if errores:
        return 1

    print("\nTodos los proyectos AJ Urbana tienen sync reciente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
