"""Unidades de un proyecto: CRUD + upload/download Excel."""
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


@router.get("", response_model=list[UnidadOut])
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
        wb = load_workbook(io.BytesIO(body), data_only=True, read_only=True)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Excel inválido: {e}")
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
    by_num = {u.numero: u for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).all()}
    inserted, updated, errors = [], [], []

    for i, r in enumerate(rows[1:], start=2):
        num = str(r[idx["numero_depto"]] or "").strip()
        if not num:
            errors.append(f"Fila {i}: falta número")
            continue

        def col(name, transform=lambda v: v):
            j = idx.get(name)
            return transform(r[j]) if j is not None and j < len(r) else None

        disp_raw = col("disponible")
        disp = str(disp_raw).strip().lower() in ("true", "1", "sí", "si", "yes", "x") if disp_raw is not None else True

        data = dict(
            numero=num,
            modelo=col("modelo") or "",
            tipologia=col("tipologia") or "",
            tipo=col("tipo") or "Depto",
            orientacion=col("orientacion") or "",
            sup_total=_num_or_none(col("sup_total")),
            sup_interior=_num_or_none(col("sup_interior")),
            sup_terraza=_num_or_none(col("sup_terraza")),
            sup_logia=_num_or_none(col("sup_logia")),
            sup_jardin=_num_or_none(col("sup_jardin")),
            precio_lista_uf=_num_or_none(col("precio_lista_uf")),
            descuento_pct=_num_or_none(col("descuento_pct")) or 0,
            bono_pie_pct=_num_or_none(col("bono_pie_pct")) or 0,
            precio_final_uf=_num_or_none(col("precio_final_uf")),
            estac_flag=col("estac_flag") or "optional",
            bodega_flag=col("bodega_flag") or "optional",
            pack_flag=col("pack_flag") or "optional",
            disponible=disp,
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
    }
    db.commit()

    return {
        "inserted": len(inserted),
        "updated": len(updated),
        "errors": errors,
        "stock_last_upload": proy.stock_last_upload,
    }
