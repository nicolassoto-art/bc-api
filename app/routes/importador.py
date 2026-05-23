"""Importación masiva desde JetBroker al staging (activo=False).

Endpoint principal:
  POST /importador/batch  →  acepta el JSON generado por jb_export_snippet.js
                              crea proyectos + unidades con activo=False
                              devuelve resumen

El validador en herramientas.bigcapital.cl/src/importador/ usa luego
  GET  /proyectos?activo=false           para listar los pendientes
  PATCH /proyectos/{id}/estado           para aprobar (activo=true) o rechazar (delete)
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import super_admin
from ..models import Proyecto, Unidad
from ..models.usuario import Usuario

router = APIRouter(prefix="/importador", tags=["importador"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class BatchImportRequest(BaseModel):
    projects: List[Dict[str, Any]]
    overwrite: bool = False


class ImportDetail(BaseModel):
    name: str
    status: str
    project_id: Optional[str] = None
    units: Optional[int] = None
    reason: Optional[str] = None


class BatchImportResult(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    errors: int
    details: List[ImportDetail]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-") or "proy"


def _to_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _to_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _build_notas(jb: dict) -> Optional[str]:
    """Combina campos descriptivos de JetBrokers en un texto rico para notas."""
    parts = []
    if jb.get("description"):
        parts.append(str(jb["description"]).strip())
    if jb.get("termDetails"):
        parts.append("📋 Detalles comerciales:\n" + str(jb["termDetails"]).strip())
    if jb.get("notes"):
        parts.append(str(jb["notes"]).strip())
    # Datos del developer
    dev_info = []
    if jb.get("developerName"): dev_info.append(f"Constructora: {jb['developerName']}")
    if jb.get("developerWeb"):  dev_info.append(f"Sitio: {jb['developerWeb']}")
    if jb.get("developerAddress"): dev_info.append(f"Dirección: {jb['developerAddress']}")
    if dev_info:
        parts.append("🏗 Desarrolladora:\n" + " · ".join(dev_info))
    # Permiso de edificación
    if jb.get("buildingPermit") or jb.get("buildingPermitNumber"):
        perm = []
        if jb.get("buildingPermitNumber"): perm.append(f"N° {jb['buildingPermitNumber']}")
        if jb.get("buildingPermit"): perm.append(str(jb["buildingPermit"]))
        parts.append("📄 Permiso edificación: " + " · ".join(perm))
    return "\n\n".join(parts) if parts else None


def _normalize_jb_photo_url(url: Optional[str]) -> Optional[str]:
    """Convierte jetgallery.jetbrokers.io a api.jetbrokers.io (más rápido)."""
    if not url:
        return None
    if "jetgallery.jetbrokers.io" in url:
        return url.replace("jetgallery.jetbrokers.io", "api.jetbrokers.io")
    return url


def _typology(u: dict) -> Optional[str]:
    m = u.get("apartmentModel")
    if isinstance(m, dict):
        r, b = m.get("rooms"), m.get("bathrooms")
        if r and b:
            return f"{r}D - {b}B"
    return u.get("typology")


def _make_proyecto(jb: dict) -> dict:
    pid = jb.get("id")
    name = (jb.get("name") or "Sin nombre").strip()
    org = jb.get("organization") or {}
    org_name = org.get("name") if isinstance(org, dict) else str(org or "")
    # La "inmobiliaria" real es el developer del proyecto, NO la organización del broker.
    inmobiliaria = (jb.get("developer") or jb.get("developerName")
                    or jb.get("buildingCompany") or org_name)
    slug = (_slugify(name) + ("-" + str(pid) if pid else ""))[:64]

    extra: dict = {}
    for k in ("locality", "address", "rooms", "bathrooms", "amenities",
              "deliveryDate", "modality", "stage", "phase", "totalUnits",
              "description", "downpaymentPercentage", "reservationValue",
              "discountType", "bonoPieTipo", "pieTipo", "constructionPermit",
              "developer", "buildingCompany", "developerWeb", "developerAddress"):
        if jb.get(k) is not None:
            extra[k] = jb[k]
    extra["jb_id"] = pid
    extra["jb_broker_org"] = org_name
    if isinstance(org, dict):
        extra["jb_org"] = org

    # Condiciones comerciales (formato esperado por proyecto-vista.js)
    comercial = {}
    if jb.get("pie") is not None:
        comercial["pie_pct"] = _to_float(jb.get("pie"))
        comercial["pie_tipo"] = jb.get("pieTipo")
    if jb.get("reservaCLP") is not None:
        comercial["valor_reserva_clp"] = _to_float(jb.get("reservaCLP"))
        comercial["tipo_reserva"] = jb.get("reservaTipo")
    if jb.get("bonoPieTipo"):
        comercial["bono_pie_tipo"] = jb.get("bonoPieTipo")
    if jb.get("discountType"):
        comercial["tipo_descuento"] = jb.get("discountType")
    if jb.get("promoBroker") is not None:
        comercial["promo_broker"] = _to_float(jb.get("promoBroker"))
    if jb.get("promoCustomer") is not None:
        comercial["promo_customer"] = _to_float(jb.get("promoCustomer"))
    if jb.get("cuotonInicial") is not None:
        comercial["cuoton_inicial_pct"] = _to_float(jb.get("cuotonInicial"))
    if jb.get("cuotonFinal") is not None:
        comercial["cuoton_final_pct"] = _to_float(jb.get("cuotonFinal"))
    if comercial:
        extra["comercial"] = comercial

    # Plan de pago / Formas de pago del pie
    formas_pago = {}
    if jb.get("cuotasPreEntrega") is not None:
        formas_pago["cuotas_pre_entrega"] = jb.get("cuotasPreEntrega")
    if jb.get("cuotasPostEntrega") is not None:
        formas_pago["cuotas_post_entrega"] = jb.get("cuotasPostEntrega")
    if jb.get("payMethodPreEntrega"):
        formas_pago["pago_pre_entrega"] = jb.get("payMethodPreEntrega")
    if jb.get("payMethodPostEntrega"):
        formas_pago["pago_post_entrega"] = jb.get("payMethodPostEntrega")
    if jb.get("payMethodCuotas"):
        formas_pago["pago_cuoton_inicial"] = jb.get("payMethodCuotas")
    if jb.get("valorCuotaCLP") is not None:
        formas_pago["valor_cuota_clp"] = _to_float(jb.get("valorCuotaCLP"))
    if jb.get("reservaDestino"):
        formas_pago["destino_reserva"] = jb.get("reservaDestino")
    if formas_pago:
        extra["formas_pago_pie"] = formas_pago

    # Equipamiento
    if jb.get("perks"): extra["equipamiento"] = jb.get("perks")
    if jb.get("perksCommonAreas"): extra["areas_comunes"] = jb.get("perksCommonAreas")
    if jb.get("perksNearby"): extra["entorno"] = jb.get("perksNearby")

    return {
        "id": slug,
        "nombre": name,
        "inmobiliaria": inmobiliaria,
        "comuna": jb.get("locality") or jb.get("commune"),
        "region": jb.get("region"),
        "direccion": jb.get("address"),
        "gps_lat": _to_float(jb.get("lat") or jb.get("latitude") or (jb.get("location") or {}).get("lat")),
        "gps_lon": _to_float(jb.get("lng") or jb.get("longitude") or (jb.get("location") or {}).get("lng")),
        "fase": jb.get("stage") or jb.get("phase"),
        "modalidad": jb.get("modality"),
        "activo": False,
        "disponible": bool(jb.get("available", True)),
        "fecha_entrega": str(jb.get("deliveryDate") or "") or None,
        "ano_entrega": _to_int(jb.get("deliveryYear")),
        "foto_principal_url": _normalize_jb_photo_url(
            (jb.get("cover") or {}).get("url") if isinstance(jb.get("cover"), dict) else jb.get("cover")
        ),
        "external_url": f"https://app.jetbrokers.io/projects/{pid}" if pid else None,
        "extra": extra,
        # Notas: combinar description + termDetails (condiciones especiales) + buildingPermit
        "notas": _build_notas(jb),
    }


def _make_unidades(jb_units: list, proyecto_id: str) -> list:
    units = []
    seen = set()
    for u in (jb_units or []):
        numero = str(u.get("number") or u.get("numero") or "").strip()
        if not numero:
            continue
        # Dedup por ID de JB cuando está disponible (proyectos multibloque
        # tienen el mismo número en distintas torres pero ID único por unidad)
        jb_id = str(u.get("id") or "").strip()
        dedup_key = jb_id if jb_id else numero
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        uid = f"u-{uuid.uuid4().hex[:10]}"
        m = u.get("apartmentModel")
        units.append(Unidad(
            id=uid,
            proyecto_id=proyecto_id,
            numero=numero,
            modelo=m.get("name") if isinstance(m, dict) else u.get("model"),
            tipologia=_typology(u),
            tipo=u.get("type", "Depto"),
            orientacion=u.get("facing") or u.get("orientacion"),
            sup_total=_to_float(u.get("surfaceTotal")),
            sup_interior=_to_float(u.get("surfaceInterior")),
            sup_terraza=_to_float(u.get("surfaceTerrace")),
            sup_logia=_to_float(u.get("surfaceLogia")),
            sup_jardin=_to_float(u.get("surfaceGarden")),
            precio_lista_uf=_to_float(u.get("price")),
            descuento_pct=_to_float(u.get("discountRate")) or 0.0,
            bono_pie_pct=_to_float(u.get("bonoPie")) or 0.0,
            precio_final_uf=_to_float(u.get("finalPrice")),
            disponible=bool(u.get("available", True)),
        ))
    return units


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/batch", response_model=BatchImportResult)
def batch_import(
    body: BatchImportRequest,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    """Importa proyectos de JetBroker al staging (activo=False).

    Acepta el JSON generado por scripts/jb_export_snippet.js.
    Los proyectos quedan con activo=False hasta que el validador los apruebe.
    """
    if not body.projects:
        raise HTTPException(400, "Lista de proyectos vacía")

    created = updated = skipped = errors = 0
    details: list[ImportDetail] = []

    for jb in body.projects:
        name = (jb.get("name") or "?").strip()
        try:
            data = _make_proyecto(jb)
            pid = data["id"]
            existing = db.get(Proyecto, pid)

            if existing and not body.overwrite:
                skipped += 1
                details.append(ImportDetail(name=name, status="skipped", project_id=pid, reason="ya existe"))
                continue

            if existing:
                # No sobrescribir activo (preserva aprobaciones del validador)
                for k, v in data.items():
                    if k not in ("id", "activo"):
                        setattr(existing, k, v)
                proyecto = existing
                updated += 1
            else:
                proyecto = Proyecto(**data)
                db.add(proyecto)
                created += 1

            db.flush()

            # Unidades: limpiar las existentes si overwrite, sino agregar solo nuevas
            if existing and body.overwrite:
                db.query(Unidad).filter(Unidad.proyecto_id == pid).delete()
                db.flush()

            existing_nums = {u.numero for u in db.query(Unidad).filter(Unidad.proyecto_id == pid).all()}
            new_units = [u for u in _make_unidades(jb.get("units") or [], pid)
                         if u.numero not in existing_nums]
            for u in new_units:
                db.add(u)

            details.append(ImportDetail(
                name=name, status="ok", project_id=pid,
                units=len(new_units),
            ))

        except Exception as e:
            db.rollback()
            errors += 1
            details.append(ImportDetail(name=name, status="error", reason=str(e)))

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error al guardar en DB: {e}")

    return BatchImportResult(
        total=len(body.projects),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        details=details,
    )


@router.get("/staging/count")
def staging_count(db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
    """Cuántos proyectos hay en staging (activo=False)."""
    count = db.query(Proyecto).filter(Proyecto.activo == False).count()
    return {"staging": count}
