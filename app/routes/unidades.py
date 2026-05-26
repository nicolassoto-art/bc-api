"""Unidades de un proyecto: CRUD + upload/download Excel."""
from typing import List
import io
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps.auth import super_admin
from ..models import Proyecto, Unidad, Usuario
from ..schemas import UnidadIn, UnidadOut

router = APIRouter(prefix="/proyectos/{proyecto_id}/unidades", tags=["unidades"])

HEADERS = [
    "numero_depto", "modelo", "tipologia", "tipo", "orientacion",
    "sup_total", "sup_interior", "sup_terraza", "sup_logia", "sup_jardin",
    "precio_lista_uf", "descuento_pct", "bono_pie_pct", "precio_final_uf",
    "estac_flag", "bodega_flag", "pack_flag", "disponible",
]

# ── JetBrokers Excel format support ──────────────────────────────────────────
# JB Excel v2.4 tiene 4 sheets: INSTRUCCIONES, UNIDAD, ESTACIONAMIENTOS, BODEGAS
# En sheet UNIDAD: fila 1 = "REQ" markers, fila 2 = labels reales, fila 3+ = data
JB_SHEETS = {"INSTRUCCIONES", "UNIDAD", "ESTACIONAMIENTOS", "BODEGAS"}

# Mapeo de label JB (en sheet UNIDAD fila 2) → key interna bc-api
JB_UNIDAD_MAP = {
    "Unidad Número":            "numero_depto",
    "Dormitorios":              "_dormitorios",
    "Baños":                    "_banos",
    "Modelo":                   "modelo",
    "Orientacion":              "orientacion",
    "Sup Interior":             "sup_interior",
    "Sup Terraza":              "sup_terraza",
    "Sup Logia":                "sup_logia",
    "Sup Jardin":               "sup_jardin",
    "Sup Total":                "sup_total",
    "ValorUF":                  "precio_lista_uf",
    "Descuento":                "descuento_pct",
    "Bonopie":                  "bono_pie_pct",
    "Cotiza Estacionamiento":   "estac_flag",
    "Cotiza Bodega":            "bodega_flag",
    "Cotiza Pack":              "pack_flag",
    "Estacionamiento Número":   "_estac_num",
    "Bodega Número":            "_bodega_num",
    "Pack Número":              "_pack_num",
    "Id Externo":               "_jb_id",
}

# Mapeo de valores "Cotiza X" JB → flag bc-api
JB_COTIZA_MAP = {
    "obligatorio": "required",
    "opcional":    "optional",
    "nunca":       "never",
    "required":    "required",
    "optional":    "optional",
    "never":       "never",
}


def _is_jb_excel(wb) -> bool:
    """Detecta si el .xlsx es formato JB (tiene los 4 sheets típicos)."""
    return JB_SHEETS.issubset(set(wb.sheetnames))


def _parse_jb_excel(wb) -> tuple[list[dict], list[str]]:
    """Parsea sheet UNIDAD del Excel JB → lista de dicts compatibles con bc-api.

    Retorna (rows_data, errors). Cada row ya tiene los nombres normalizados a bc-api.
    """
    ws = wb["UNIDAD"]
    all_rows = list(ws.iter_rows(values_only=True))
    if len(all_rows) < 3:
        return [], ["Sheet UNIDAD vacío"]
    # Fila 2 (index 1) tiene los labels reales
    labels = [str(c or "").strip() for c in all_rows[1]]
    # Mapeo column_index → bc-api key
    idx_map: dict[int, str] = {}
    for i, label in enumerate(labels):
        if label in JB_UNIDAD_MAP:
            idx_map[i] = JB_UNIDAD_MAP[label]
    out_rows = []
    errors = []
    for row_idx, row in enumerate(all_rows[2:], start=3):
        if not row or all(c is None or c == "" for c in row):
            continue
        d: dict = {}
        for i, val in enumerate(row):
            key = idx_map.get(i)
            if not key:
                continue
            d[key] = val
        num = str(d.get("numero_depto") or "").strip()
        if not num:
            errors.append(f"Fila {row_idx}: falta 'Unidad Número'")
            continue
        # Traducir cotiza_X a flags
        for k in ("estac_flag", "bodega_flag", "pack_flag"):
            v = d.get(k)
            if v is not None:
                d[k] = JB_COTIZA_MAP.get(str(v).strip().lower(), "optional")
        # Componer tipologia desde Dormitorios + Baños si bc-api la usa
        if d.get("_dormitorios") is not None and d.get("_banos") is not None:
            try:
                d["tipologia"] = f"{int(d['_dormitorios'])}D - {int(d['_banos'])}B"
            except Exception:
                pass
        # Disponible: JB no lo trae explícito → asumir True
        d.setdefault("disponible", True)
        # tipo: deducir
        d.setdefault("tipo", "Depto")
        out_rows.append(d)
    return out_rows, errors


def _parse_jb_estacionamientos(wb) -> list[dict]:
    """Parsea sheet ESTACIONAMIENTOS del Excel JB."""
    if "ESTACIONAMIENTOS" not in wb.sheetnames:
        return []
    ws = wb["ESTACIONAMIENTOS"]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return []
    labels = [str(c or "").strip() for c in rows[1]]
    out = []
    for r in rows[2:]:
        if not r or all(c is None or c == "" for c in r):
            continue
        item = {labels[i]: r[i] for i in range(min(len(labels), len(r))) if labels[i]}
        if item.get("Número"):
            out.append(item)
    return out


def _parse_jb_bodegas(wb) -> list[dict]:
    """Parsea sheet BODEGAS del Excel JB."""
    if "BODEGAS" not in wb.sheetnames:
        return []
    ws = wb["BODEGAS"]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return []
    labels = [str(c or "").strip() for c in rows[1]]
    out = []
    for r in rows[2:]:
        if not r or all(c is None or c == "" for c in r):
            continue
        item = {labels[i]: r[i] for i in range(min(len(labels), len(r))) if labels[i]}
        if item.get("Número"):
            out.append(item)
    return out


def _ensure_project(db: Session, proyecto_id: str) -> Proyecto:
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return p


def _num_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@router.get("", response_model=List[UnidadOut])
def listar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(super_admin)):
    _ensure_project(db, proyecto_id)
    return db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).order_by(Unidad.numero).all()


@router.post("", response_model=UnidadOut, status_code=status.HTTP_201_CREATED)
def crear(
    proyecto_id: str,
    body: UnidadIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    _ensure_project(db, proyecto_id)
    if db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id, Unidad.numero == body.numero).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya existe la unidad {body.numero}")
    u = Unidad(id="u-" + uuid.uuid4().hex[:10], proyecto_id=proyecto_id, **body.model_dump())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.put("/{unidad_id}", response_model=UnidadOut)
def actualizar(
    proyecto_id: str,
    unidad_id: str,
    body: UnidadIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    u = db.get(Unidad, unidad_id)
    if not u or u.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada")
    for k, v in body.model_dump().items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return u


@router.delete("/{unidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    proyecto_id: str,
    unidad_id: str,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    u = db.get(Unidad, unidad_id)
    if not u or u.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada")
    db.delete(u)
    db.commit()


@router.get("/excel/template")
def descargar_plantilla(
    proyecto_id: str,
    con_datos: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    """Devuelve un .xlsx — vacío (solo headers + ejemplo) o con datos actuales."""
    proy = _ensure_project(db, proyecto_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"
    ws.append(HEADERS)

    if con_datos:
        for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).order_by(Unidad.numero).all():
            ws.append([
                u.numero, u.modelo, u.tipologia, u.tipo, u.orientacion,
                u.sup_total, u.sup_interior, u.sup_terraza, u.sup_logia, u.sup_jardin,
                u.precio_lista_uf, u.descuento_pct, u.bono_pie_pct, u.precio_final_uf,
                u.estac_flag, u.bodega_flag, u.pack_flag,
                "TRUE" if u.disponible else "FALSE",
            ])
    else:
        ws.append(["101", "A1", "3D - 2B", "Depto", "N", 62.5, 60.0, 2.5, 0, 0,
                   3200, 0, 20, 3200, "optional", "never", "never", "TRUE"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    suffix = "_con_datos" if con_datos else ""
    safe_name = "".join(c if c.isalnum() else "_" for c in (proy.nombre or "proyecto"))
    fname = f"{safe_name}_stock{suffix}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/excel/upload")
async def subir_excel(
    proyecto_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Usuario = Depends(super_admin),
):
    """Upsert por numero_depto. Devuelve resumen {inserted, updated, errors}."""
    proy = _ensure_project(db, proyecto_id)
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser .xlsx o .xls")

    body = await file.read()
    try:
        wb = load_workbook(io.BytesIO(body), data_only=True, read_only=False)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Excel inválido: {e}")

    # ── Detectar formato: JB (4 sheets) o bc-api (1 sheet con headers en row 1) ──
    is_jb = _is_jb_excel(wb)
    inserted, updated, errors = [], [], []
    by_num = {u.numero: u for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).all()}
    jb_extras: dict = {}

    if is_jb:
        # Parser JB
        unidad_rows, parse_errors = _parse_jb_excel(wb)
        errors.extend(parse_errors)
        if not unidad_rows:
            # Diagnóstico: capturar sheet names + labels detectadas + sample row para debug
            try:
                ws_dbg = wb["UNIDAD"]
                rows_dbg = list(ws_dbg.iter_rows(values_only=True))
                sheets = list(wb.sheetnames)
                nrows = len(rows_dbg)
                row0 = [str(c)[:30] if c is not None else "" for c in (rows_dbg[0] if rows_dbg else [])][:20]
                row1 = [str(c)[:30] if c is not None else "" for c in (rows_dbg[1] if len(rows_dbg) > 1 else [])][:20]
                row2 = [str(c)[:30] if c is not None else "" for c in (rows_dbg[2] if len(rows_dbg) > 2 else [])][:20]
                row3 = [str(c)[:30] if c is not None else "" for c in (rows_dbg[3] if len(rows_dbg) > 3 else [])][:20]
                detail = (f"Sheet UNIDAD vacío o sin filas válidas. "
                          f"sheets={sheets} nrows={nrows} row0={row0} row1={row1} row2={row2} row3={row3} "
                          f"parse_errors={parse_errors[:3]}")
            except Exception as _e:
                detail = f"Sheet UNIDAD vacío o sin filas válidas (err diag: {_e})"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail)
        # Estacionamientos + Bodegas → extra (todavía no entidades separadas)
        jb_estac = _parse_jb_estacionamientos(wb)
        jb_bodegas = _parse_jb_bodegas(wb)
        jb_extras = {
            "_excel_format": "jb_v2.4",
            "_estacionamientos_dom": jb_estac,
            "_bodegas_dom": jb_bodegas,
        }
        rows_iter = [(i + 3, r) for i, r in enumerate(unidad_rows)]
    else:
        # Parser legado bc-api
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Excel vacío")
        header = [str(c or "").strip() for c in rows[0]]
        if "numero_depto" not in header:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Falta columna 'numero_depto'. Descarga la plantilla para ver el formato esperado.",
            )
        idx = {h: i for i, h in enumerate(header)}
        legacy_rows = []
        for i, r in enumerate(rows[1:], start=2):
            num = str(r[idx["numero_depto"]] or "").strip()
            if not num:
                errors.append(f"Fila {i}: falta número")
                continue

            def col(name, transform=lambda v: v):
                j = idx.get(name)
                return transform(r[j]) if j is not None and j < len(r) else None

            disp_raw = col("disponible")
            disp = (
                str(disp_raw).strip().lower() in ("true", "1", "sí", "si", "yes", "x")
                if disp_raw is not None
                else True
            )
            d = dict(
                numero_depto=num,
                modelo=col("modelo") or "",
                tipologia=col("tipologia") or "",
                tipo=col("tipo") or "Depto",
                orientacion=col("orientacion") or "",
                sup_total=col("sup_total"),
                sup_interior=col("sup_interior"),
                sup_terraza=col("sup_terraza"),
                sup_logia=col("sup_logia"),
                sup_jardin=col("sup_jardin"),
                precio_lista_uf=col("precio_lista_uf"),
                descuento_pct=col("descuento_pct"),
                bono_pie_pct=col("bono_pie_pct"),
                precio_final_uf=col("precio_final_uf"),
                estac_flag=col("estac_flag") or "optional",
                bodega_flag=col("bodega_flag") or "optional",
                pack_flag=col("pack_flag") or "optional",
                disponible=disp,
            )
            legacy_rows.append((i, d))
        rows_iter = legacy_rows

    # ── Procesar filas (mismo loop para JB o legacy) ──
    for i, d in rows_iter:
        num = str(d.get("numero_depto") or "").strip()
        if not num:
            errors.append(f"Fila {i}: falta 'Unidad Número'")
            continue
        data = dict(
            numero=num,
            modelo=d.get("modelo") or "",
            tipologia=d.get("tipologia") or "",
            tipo=d.get("tipo") or "Depto",
            orientacion=d.get("orientacion") or "",
            sup_total=_num_or_none(d.get("sup_total")),
            sup_interior=_num_or_none(d.get("sup_interior")),
            sup_terraza=_num_or_none(d.get("sup_terraza")),
            sup_logia=_num_or_none(d.get("sup_logia")),
            sup_jardin=_num_or_none(d.get("sup_jardin")),
            precio_lista_uf=_num_or_none(d.get("precio_lista_uf")),
            descuento_pct=_num_or_none(d.get("descuento_pct")) or 0,
            bono_pie_pct=_num_or_none(d.get("bono_pie_pct")) or 0,
            precio_final_uf=_num_or_none(d.get("precio_final_uf")),
            estac_flag=d.get("estac_flag") or "optional",
            bodega_flag=d.get("bodega_flag") or "optional",
            pack_flag=d.get("pack_flag") or "optional",
            disponible=bool(d.get("disponible", True)),
        )

        if num in by_num:
            u = by_num[num]
            for k, v in data.items():
                setattr(u, k, v)
            updated.append(num)
        else:
            u = Unidad(id="u-" + uuid.uuid4().hex[:10], proyecto_id=proyecto_id, **data)
            db.add(u)
            inserted.append(num)

    proy.stock_last_upload = {
        "filename": file.filename,
        "at": datetime.utcnow().isoformat() + "Z",
        "inserted": len(inserted),
        "updated": len(updated),
        "errors": len(errors),
        "format": "jb_v2.4" if is_jb else "bc_api",
    }

    # Si es JB, guardar extras (estac + bodegas individuales) en extra.X
    if is_jb and jb_extras:
        proy.extra = {**(proy.extra or {}), **jb_extras}

    db.commit()

    return {
        "format": "jb_v2.4" if is_jb else "bc_api",
        "inserted": len(inserted),
        "updated": len(updated),
        "errors": errors,
        "estacionamientos_count": len(jb_extras.get("_estacionamientos_dom", [])),
        "bodegas_count": len(jb_extras.get("_bodegas_dom", [])),
        "stock_last_upload": proy.stock_last_upload,
    }
