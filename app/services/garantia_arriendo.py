"""Arriendo Garantizado por la inmobiliaria — bc-api · 2026-11-03

Caso que lo origina: Larraín Prieto garantiza el arriendo de los deptos de Exequiel
Fernández 2000 hasta septiembre 2029, con un canon mensual en UF por depto (su tabla
oficial, adjunta al proyecto). El dato vive a nivel PROYECTO en
`extra["garantia_arriendo"]`:

    {"hasta": "2029-09", "condiciones": "...", "documento_url": "/uploads/<id>/...pdf",
     "moneda": "UF", "canon": {"201": 11.1, ...}}

Reglas:
- La escribe SOLO `PATCH /proyectos/{id}/garantia-arriendo`. El PUT del editor nunca la
  pisa ni la borra (mismo patrón que `video_ubicacion`): una pestaña vieja del editor
  reenvía `extra` completo y la perdería.
- La tabla `canon` es la fuente para las unidades NUEVAS: cada alta (Excel, POST) o PUT
  con el arriendo vacío toma su monto de acá. Nunca pisa un monto ya cargado.
- Al catálogo (Worker) sale SIN la tabla: solo vigencia, condiciones, documento y moneda
  (ver `publica`). El monto de cada depto ya viaja en su unidad.
- Es opt-in por proyecto: sin la clave, todo queda exactamente igual que antes (Euro).
"""
from __future__ import annotations

import re
from typing import Any, Optional

CLAVE = "garantia_arriendo"
MONEDAS = {"UF"}
APLICAR = {"vacios", "sobrescribir"}
MAX_CONDICIONES = 600
MAX_CANON = 1000.0
MAX_CLAVES_CANON = 2000  # muy por encima de cualquier edificio; evita cuerpos gigantes
_HASTA_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CAMPOS = {"hasta", "condiciones", "documento_url", "moneda", "canon"}
# Lo único que sale al catálogo. La tabla de canon queda solo en la ficha privada.
CAMPOS_PUBLICOS = ("hasta", "condiciones", "documento_url", "moneda")


class GarantiaInvalida(ValueError):
    """Dato de la garantía que no se puede guardar (el endpoint lo devuelve como 422)."""


def _es_numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validar(proyecto_id: str, body: Any) -> dict:
    """Valida y normaliza el cuerpo del PATCH. Devuelve el dict que se guarda."""
    if not isinstance(body, dict):
        raise GarantiaInvalida("El cuerpo debe ser un objeto con la garantía, o null para quitarla")
    extra_keys = set(body) - _CAMPOS
    if extra_keys:
        raise GarantiaInvalida(f"Campos no reconocidos: {', '.join(sorted(map(str, extra_keys)))}")

    hasta = body.get("hasta")
    if not isinstance(hasta, str) or not _HASTA_RE.match(hasta.strip()):
        raise GarantiaInvalida("«hasta» debe ser el mes de término en formato AAAA-MM (ej. 2029-09)")
    hasta = hasta.strip()

    condiciones = body.get("condiciones")
    if condiciones is None:
        condiciones = ""
    if not isinstance(condiciones, str):
        raise GarantiaInvalida("«condiciones» debe ser texto")
    condiciones = condiciones.strip()
    if len(condiciones) > MAX_CONDICIONES:
        raise GarantiaInvalida(f"«condiciones» admite hasta {MAX_CONDICIONES} caracteres")

    doc = body.get("documento_url")
    if doc is None or (isinstance(doc, str) and not doc.strip()):
        doc = None
    else:
        if not isinstance(doc, str):
            raise GarantiaInvalida("«documento_url» debe ser texto")
        doc = doc.strip()
        prefijo = f"/uploads/{proyecto_id}/"
        # Solo documentos subidos a ESTE proyecto (nada de URLs externas ni de otro proyecto).
        if not doc.startswith(prefijo) or ".." in doc or len(doc) <= len(prefijo):
            raise GarantiaInvalida(f"«documento_url» debe ser un documento del proyecto ({prefijo}…)")

    moneda = body.get("moneda")
    if moneda is None or moneda == "":
        moneda = "UF"
    if not isinstance(moneda, str) or moneda.strip().upper() not in MONEDAS:
        raise GarantiaInvalida("«moneda» admite solo UF")
    moneda = moneda.strip().upper()

    canon_in = body.get("canon")
    if canon_in is None:
        canon_in = {}
    if not isinstance(canon_in, dict):
        raise GarantiaInvalida("«canon» debe ser un objeto {número de depto: monto}")
    if len(canon_in) > MAX_CLAVES_CANON:
        raise GarantiaInvalida(f"«canon» admite hasta {MAX_CLAVES_CANON} deptos")
    canon: dict = {}
    for k, v in canon_in.items():
        num = k.strip() if isinstance(k, str) else ""
        if not num:
            raise GarantiaInvalida("«canon»: cada número de depto debe ser texto no vacío")
        if not _es_numero(v) or not (0 < float(v) <= MAX_CANON):
            raise GarantiaInvalida(f"«canon»: el monto del depto {num} debe ser un número mayor que 0 y hasta "
                                   f"{MAX_CANON:g}")
        if num in canon:
            raise GarantiaInvalida(f"«canon»: el depto {num} viene repetido")
        canon[num] = float(v)

    return {"hasta": hasta, "condiciones": condiciones, "documento_url": doc, "moneda": moneda,
            "canon": canon}


def garantia_de(proy: Any) -> Optional[dict]:
    """La garantía guardada del proyecto, o None si no tiene (o el dato está roto)."""
    g = (getattr(proy, "extra", None) or {}).get(CLAVE)
    return g if isinstance(g, dict) else None


def canon_de(proy: Any, numero: Any) -> Optional[tuple]:
    """(valor, moneda) del canon de ese depto según la tabla del proyecto, o None."""
    g = garantia_de(proy)
    if not g:
        return None
    canon = g.get("canon")
    if not isinstance(canon, dict):
        return None
    v = canon.get(str(numero or "").strip())
    if not _es_numero(v) or v <= 0:
        return None
    return float(v), (g.get("moneda") or "UF")


def publica(g: Any) -> Optional[dict]:
    """Versión para el catálogo: sin la tabla de canon."""
    if not isinstance(g, dict):
        return None
    return {k: g.get(k) for k in CAMPOS_PUBLICOS}
