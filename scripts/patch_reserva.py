"""patch_reserva.py — Override manual de extra.comercial.valor_reserva_clp.

No toca nada más (unidades, notas, fotos). El sync diario de marketplace
workview corre con --stock-only y NO re-scrapea Condiciones Comerciales, así
que este override sobrevive las corridas normales -- pero un refresh manual
completo (workflow_dispatch sin --stock-only) SÍ volvería a traer el valor
real de JB y lo pisaría.

Uso: PID=jb-iquforoo VALOR_CLP=100000 python3 scripts/patch_reserva.py
"""
import json
import os

import httpx

BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ["PID"]
VALOR_CLP = int(os.environ["VALOR_CLP"])
jwt = os.environ["BC_API_JWT"]

cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

r = cli.get(f"/proyectos/{PID}")
r.raise_for_status()
current = r.json()

extra = dict(current.get("extra") or {})
comercial = dict(extra.get("comercial") or {})
antes = comercial.get("valor_reserva_clp")
comercial["valor_reserva_clp"] = VALOR_CLP
extra["comercial"] = comercial

body = {
    "nombre": current["nombre"],
    "inmobiliaria": current.get("inmobiliaria"),
    "comuna": current.get("comuna"),
    "region": current.get("region"),
    "direccion": current.get("direccion"),
    "gps_lat": current.get("gps_lat"),
    "gps_lon": current.get("gps_lon"),
    "fase": current.get("fase"),
    "modalidad": current.get("modalidad"),
    "activo": current.get("activo", True),
    "disponible": current.get("disponible", True),
    "fecha_entrega": current.get("fecha_entrega"),
    "ano_entrega": current.get("ano_entrega"),
    "foto_principal_url": current.get("foto_principal_url"),
    "external_url": current.get("external_url"),
    "notas": current.get("notas"),
    "extra": extra,
}
r2 = cli.put(f"/proyectos/{PID}", json=body)
print(f"PUT /proyectos/{PID} -> HTTP {r2.status_code}")
if not r2.is_success:
    print(r2.text[:500])
    raise SystemExit(1)

updated = r2.json()
nuevo = (updated.get("extra") or {}).get("comercial", {}).get("valor_reserva_clp")
print(f"valor_reserva_clp: {antes!r} -> {nuevo!r}")
