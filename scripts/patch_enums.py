"""
patch_enums.py — Corrige NO-DESTRUCTIVAMENTE los enums crudos (inglés) de un proyecto ya
importado, SIN wipe. Solo cambia valores que están en inglés crudo; preserva ediciones
manuales, unidades, imágenes y documentos (el PUT /proyectos no toca esas tablas).

Env: BC_API_JWT, PID_BC (csv, default 'vistamar,etapa-2-portal-del-pinar')
"""
from __future__ import annotations
import os, sys
import httpx

BC = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
PIDS = [p.strip() for p in os.environ.get("PID_BC", "vistamar,etapa-2-portal-del-pinar").split(",") if p.strip()]

PIE_T = {"voluntary": "Opcional", "optional": "Opcional", "required": "Obligatorio", "mandatory": "Obligatorio"}
DESC_T = {"all": "Todo", "onlyapartment": "Solo Unidad", "none": "No"}
BONO_T = {"all": "Todo", "onlyapartment": "Solo Unidad", "none": "No"}
RES_T = {"downpayment": "Pie", "operationalexpenses": "Gastos operacionales", "expense": "Gastos operacionales",
         "expenses": "Gastos operacionales", "torefund": "A devolver", "refundable": "A devolver", "refund": "A devolver"}
DEST_T = {"projectdeveloper": "Inmobiliaria", "developer": "Inmobiliaria", "broker": "Broker"}
CESION_T = {"yesauthorized": "Si, con autorización de la inmobiliaria",
            "yesemergency": "Si, sólo en casos de emergencia", "yesopen": "Si, abierta"}
CUENTA_T = {"cta corriente": "Cuenta Corriente", "corriente": "Cuenta Corriente", "checking": "Cuenta Corriente",
            "cta vista": "Cuenta Vista", "vista": "Cuenta Vista", "ahorro": "Cuenta de Ahorro",
            "savings": "Cuenta de Ahorro", "rut": "CuentaRUT", "cuentarut": "CuentaRUT"}
PERMISO_T = {"yes": "1", "no": "0", "inprocess": "tramite", "processing": "tramite", "intramite": "tramite"}
PREAP_T = {"atpromise": "Aprobación a la promesa", "atreservation": "Aprobación a la reserva",
           "yespromise": "Si, a la promesa", "yesreservation": "Si, a la reserva"}
STOCK_T = {"shared": "Compartido", "exclusive": "Exclusivo", "own": "Propio", "private": "Propio"}

FIELDS = [
    (("extra", "stock_type"), STOCK_T),
    (("extra", "comercial", "tipo_pie"), PIE_T),
    (("extra", "comercial", "tipo_descuento"), DESC_T),
    (("extra", "comercial", "tipo_bono_pie"), BONO_T),
    (("extra", "comercial", "tipo_reserva"), RES_T),
    (("extra", "comercial", "destino_reserva"), DEST_T),
    (("extra", "fisicos", "acepta_cesion"), CESION_T),
    (("extra", "fisicos", "permiso_construccion"), PERMISO_T),
    (("extra", "cuenta_reserva", "tipo_cuenta"), CUENTA_T),
    (("extra", "solicita_preaprobacion"), PREAP_T),
]


def get_path(o, path):
    for k in path:
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


def set_path(o, path, val):
    for k in path[:-1]:
        o = o.setdefault(k, {})
    o[path[-1]] = val


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    for pid in PIDS:
        r = cli.get(f"/proyectos/{pid}")
        if r.status_code != 200:
            print(f"{pid}: GET {r.status_code} — skip", flush=True)
            continue
        p = r.json()
        changes = []
        for path, m in FIELDS:
            cur = get_path(p, path)
            if cur in (None, ""):
                continue
            mapped = m.get(str(cur).strip().lower())
            if mapped and mapped != cur:
                set_path(p, path, mapped)
                changes.append(f"{'.'.join(path)}: {cur!r}→{mapped!r}")
        if not changes:
            print(f"{pid}: sin cambios (todo en español ya) ✓", flush=True)
            continue
        # PUT solo campos escribibles del proyecto (NO unidades/imagenes/documentos)
        body = {k: p[k] for k in p
                if k not in ("id", "unidades", "imagenes", "documentos", "created_at", "updated_at")}
        pr = cli.put(f"/proyectos/{pid}", json=body)
        print(f"{pid}: PUT {pr.status_code} · cambios: {changes}", flush=True)
    print("\n✓ patch no-destructivo completo (unidades/imágenes/ediciones manuales intactas)", flush=True)


if __name__ == "__main__":
    main()
