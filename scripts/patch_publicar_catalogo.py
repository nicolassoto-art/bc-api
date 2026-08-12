"""patch_publicar_catalogo.py — Activa/desactiva extra.publicar_en_catalogo de un proyecto.

Sin ese flag, /proyectos/public no lo devuelve (ver _is_publicable en
app/routes/proyectos.py:255) y el worker del catálogo NO lo toma como SBC: un
proyecto importado desde el marketplace de JB sigue mostrándose como SJB con
datos de JetBrokers en vez de los de bc-api.

Sigue el patrón obligatorio de PUT completo (GET completo -> modificar -> PUT
completo): un payload mínimo BORRA campos top-level del proyecto existente.

Uso: PID=jb-1zvx7adn VALOR=true python3 scripts/patch_publicar_catalogo.py
"""
import json
import os

import httpx

BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ["PID"]
VALOR = os.environ.get("VALOR", "true").strip().lower() in ("1", "true", "si", "sí", "yes")
jwt = os.environ["BC_API_JWT"]

cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

r = cli.get(f"/proyectos/{PID}")
r.raise_for_status()
current = r.json()

extra = dict(current.get("extra") or {})
antes = extra.get("publicar_en_catalogo")
extra["publicar_en_catalogo"] = VALOR

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
nuevo = (updated.get("extra") or {}).get("publicar_en_catalogo")
print(f"publicar_en_catalogo: {antes!r} -> {nuevo!r}")
print(f"activo: {updated.get('activo')} | unidades: {len(updated.get('unidades') or [])}")
