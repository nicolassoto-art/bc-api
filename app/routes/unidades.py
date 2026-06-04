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
from ..deps.auth import stock_access
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


def _normalize_label(s: str) -> str:
    """Normaliza header: sin tildes, lowercase, sin puntos, espacios normalizados.
    Sup./Sup./Superficie/SUP. → 'sup'; Logía/Logia → 'logia'; Jardín/Jardin → 'jardin'.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace(".", "").replace("º", "").replace("°", "")
    s = " ".join(s.split())  # colapsa espacios
    # equivalencias de prefijo "superficie" → "sup"
    if s.startswith("superficie "):
        s = "sup " + s[len("superficie "):]
    return s


def _build_idx_map(labels: list[str]) -> dict[int, str]:
    """Mapea índice de columna → bc-api key, con matching robusto (case+tildes+sinónimos)."""
    norm_to_key = {_normalize_label(k): v for k, v in JB_UNIDAD_MAP.items()}
    # Sinónimos extra (defensivo, por si JB cambia headers)
    extra = {
        "sup logia": "sup_logia", "sup logía": "sup_logia",
        "superficie logia": "sup_logia", "superficie logía": "sup_logia",
        "sup jardin": "sup_jardin", "sup jardín": "sup_jardin",
        "superficie jardin": "sup_jardin", "superficie jardín": "sup_jardin",
        "sup interior": "sup_interior", "superficie interior": "sup_interior",
        "sup terraza": "sup_terraza", "superfice terraza": "sup_terraza",  # typo JB conocido
        "superficie terraza": "sup_terraza",
        "sup total": "sup_total", "superficie total": "sup_total",
    }
    for k, v in extra.items():
        norm_to_key[_normalize_label(k)] = v
    idx_map: dict[int, str] = {}
    for i, label in enumerate(labels):
        norm = _normalize_label(label)
        if norm in norm_to_key:
            idx_map[i] = norm_to_key[norm]
    return idx_map


def _parse_jb_excel(wb) -> tuple[list[dict], list[str]]:
    """Parsea sheet UNIDAD del Excel JB → lista de dicts compatibles con bc-api.

    Retorna (rows_data, errors). Cada row ya tiene los nombres normalizados a bc-api.
    """
    import logging
    log = logging.getLogger(__name__)
    ws = wb["UNIDAD"]
    all_rows = list(ws.iter_rows(values_only=True))
    if len(all_rows) < 3:
        return [], ["Sheet UNIDAD vacío"]
    # Fila 2 (index 1) tiene los labels reales
    labels = [str(c or "").strip() for c in all_rows[1]]
    idx_map = _build_idx_map(labels)
    # Loggear qué columnas se mapearon (debug) y cuáles quedaron sin mapear
    mapped_keys = sorted(set(idx_map.values()))
    unmapped = [labels[i] for i in range(len(labels)) if i not in idx_map and labels[i]]
    log.info(f"   📋 Excel UNIDAD mapeado: {mapped_keys}")
    if unmapped:
        log.info(f"   📋 Headers sin mapear: {unmapped}")
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
def listar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    _ensure_project(db, proyecto_id)
    return db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).order_by(Unidad.numero).all()


@router.post("", response_model=UnidadOut, status_code=status.HTTP_201_CREATED)
def crear(
    proyecto_id: str,
    body: UnidadIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
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
    _: Usuario = Depends(stock_access),
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
    _: Usuario = Depends(stock_access),
):
    u = db.get(Unidad, unidad_id)
    if not u or u.proyecto_id != proyecto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada")
    db.delete(u)
    db.commit()


# ── Excel formato JetBrokers v2.4 (4 sheets) ────────────────────────────────
# Estructura JB:
#   INSTRUCCIONES: descripción + guía
#   UNIDAD:        row1=marcadores REQ/OPC, row2=labels español, row3+=data deptos
#   ESTACIONAMIENTOS / BODEGAS: row1=labels español, row2+=data
# Generamos compatible con JB para que el archivo pueda subirse tanto a bc-api
# como al editor JetBrokers original.

# Labels JB para sheet UNIDAD (orden = columnas). bc-api key + label visible + REQ.
JB_UNIDAD_COLS = [
    ("numero_depto",    "Unidad Número",          "REQ"),
    ("_dormitorios",    "Dormitorios",            "REQ"),
    ("_banos",          "Baños",                  "REQ"),
    ("modelo",          "Modelo",                 "OPC"),
    ("orientacion",     "Orientacion",            "OPC"),
    ("sup_interior",    "Sup Interior",           "OPC"),
    ("sup_terraza",     "Sup Terraza",            "OPC"),
    ("sup_logia",       "Sup Logia",              "OPC"),
    ("sup_jardin",      "Sup Jardin",             "OPC"),
    ("sup_total",       "Sup Total",              "REQ"),
    ("precio_lista_uf", "ValorUF",                "REQ"),
    ("descuento_pct",   "Descuento",              "OPC"),
    ("bono_pie_pct",    "Bonopie",                "OPC"),
    ("estac_flag",      "Cotiza Estacionamiento", "OPC"),
    ("bodega_flag",     "Cotiza Bodega",          "OPC"),
    ("pack_flag",       "Cotiza Pack",            "OPC"),
    ("disponible",      "Disponible",             "OPC"),
]

JB_FLAG_TO_LABEL = {"required": "Obligatorio", "optional": "Opcional", "never": "Nunca"}

JB_BODEGAS_COLS = [("numero", "Número"), ("precio_uf", "ValorUF"), ("superficie", "Sup Total"), ("disponible", "Disponible")]
JB_ESTAC_COLS = [("numero", "Número"), ("precio_uf", "ValorUF"), ("nivel", "Nivel"), ("tipo", "Tipo"), ("disponible", "Disponible")]


def _is_depto(u: Unidad) -> bool:
    t = (u.tipo or "").lower()
    return t in ("depto", "departamento", "apartment", "")


def _parse_dorm_banos(tipologia: str) -> tuple[int | None, int | None]:
    """'3D - 2B' / '3D2B' → (3, 2)."""
    import re as _re
    if not tipologia: return (None, None)
    m = _re.search(r"(\d+)\s*D[^\d]*(\d+)\s*B", tipologia.upper())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


@router.get("/excel/template")
def descargar_plantilla(
    proyecto_id: str,
    con_datos: bool = False,
    formato: str = "jb",  # "jb" (4 sheets compat JetBrokers) | "legacy" (1 sheet vieja)
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Excel en formato JetBrokers (4 sheets: INSTRUCCIONES / UNIDAD / ESTACIONAMIENTOS / BODEGAS).

    Compatible con el editor JetBrokers — se puede descargar de bc-api,
    editar offline, y re-subir a JB o a bc-api.

    Parámetros:
      - con_datos: True → exporta unidades/bodegas/estac existentes
                   False → plantilla vacía con 1 fila de ejemplo
      - formato:   "jb" (default, 4 sheets) | "legacy" (1 sheet técnica)
    """
    proy = _ensure_project(db, proyecto_id)

    if formato == "legacy":
        return _excel_legacy(proy, proyecto_id, con_datos, db)

    wb = Workbook()
    wb.remove(wb.active)  # quitar Sheet default

    # ── 1. INSTRUCCIONES ──────────────────────────────────────────────
    ws = wb.create_sheet("INSTRUCCIONES")
    ws.append(["Stock — formato compatible JetBrokers"])
    ws.append([])
    ws.append([f"Proyecto: {proy.nombre or '?'}"])
    ws.append([f"Inmobiliaria: {proy.inmobiliaria or '?'}"])
    ws.append([f"Comuna: {proy.comuna or '?'}"])
    ws.append([])
    ws.append(["Pestañas:"])
    ws.append(["  UNIDAD            → departamentos (1 fila por depto)"])
    ws.append(["  ESTACIONAMIENTOS  → estacionamientos"])
    ws.append(["  BODEGAS           → bodegas"])
    ws.append([])
    ws.append(["Convenciones:"])
    ws.append(["  REQ = obligatorio · OPC = opcional (marcado en fila 1 de UNIDAD)"])
    ws.append(["  Cotiza Estac/Bodega/Pack: Obligatorio · Opcional · Nunca"])
    ws.append(["  Disponible: TRUE = a la venta · FALSE = reservada/vendida"])
    ws.append([])
    ws.append(["Generado por BigCapital · bc-api"])

    # ── 2. UNIDAD ─────────────────────────────────────────────────────
    ws = wb.create_sheet("UNIDAD")
    # Row 1: marcadores REQ/OPC (como JB)
    ws.append([req for (_, _, req) in JB_UNIDAD_COLS])
    # Row 2: labels en español (como JB)
    ws.append([label for (_, label, _) in JB_UNIDAD_COLS])

    if con_datos:
        unidades = db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).order_by(Unidad.numero).all()
        for u in unidades:
            if not _is_depto(u):
                continue
            dorm, banos = _parse_dorm_banos(u.tipologia or "")
            row = []
            for key, _label, _req in JB_UNIDAD_COLS:
                if key == "_dormitorios": row.append(dorm)
                elif key == "_banos": row.append(banos)
                elif key == "numero_depto": row.append(u.numero)
                elif key in ("estac_flag", "bodega_flag", "pack_flag"):
                    row.append(JB_FLAG_TO_LABEL.get(getattr(u, key) or "optional", "Opcional"))
                elif key == "disponible":
                    row.append("TRUE" if u.disponible else "FALSE")
                else:
                    row.append(getattr(u, key, None))
            ws.append(row)
    else:
        # Fila de ejemplo
        ws.append(["101", 3, 2, "A1", "N", 60.0, 2.5, 0, 0, 62.5, 3200, 0, 20,
                   "Opcional", "Obligatorio", "Nunca", "TRUE"])

    # ── 3. ESTACIONAMIENTOS ───────────────────────────────────────────
    ws = wb.create_sheet("ESTACIONAMIENTOS")
    # JB tiene row 1 vacío opcional. Usamos solo row 2 con labels.
    ws.append([])  # row 1: vacía (compat JB)
    ws.append([label for (_, label) in JB_ESTAC_COLS])
    if con_datos:
        extra = proy.extra or {}
        for source in (extra.get("estacionamientos_dom"), extra.get("_estacionamientos_dom")):
            if not source: continue
            for e in source:
                cells = e.get("cells") if isinstance(e, dict) else None
                if cells:
                    # Cells JB típicas: [_, numero, precio, nivel, tipo, ...]
                    ws.append([cells[1] if len(cells)>1 else "",
                               cells[2] if len(cells)>2 else "",
                               cells[3] if len(cells)>3 else "",
                               cells[4] if len(cells)>4 else "",
                               "TRUE" if e.get("disponible", True) else "FALSE"])
            break
        # También unidades con tipo="Estacionamiento"
        for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).all():
            t = (u.tipo or "").lower()
            if "estac" in t or "parking" in t:
                ws.append([u.numero, u.precio_lista_uf, u.orientacion or "", u.modelo or "",
                           "TRUE" if u.disponible else "FALSE"])
    else:
        ws.append(["E-101", 250, "S1", "Doble", "TRUE"])

    # ── 4. BODEGAS ────────────────────────────────────────────────────
    ws = wb.create_sheet("BODEGAS")
    ws.append([])  # row 1: vacía
    ws.append([label for (_, label) in JB_BODEGAS_COLS])
    if con_datos:
        extra = proy.extra or {}
        for source in (extra.get("bodegas_dom"), extra.get("_bodegas_dom")):
            if not source: continue
            for b in source:
                cells = b.get("cells") if isinstance(b, dict) else None
                if cells:
                    ws.append([cells[1] if len(cells)>1 else "",
                               cells[2] if len(cells)>2 else "",
                               cells[3] if len(cells)>3 else "",
                               "TRUE" if b.get("disponible", True) else "FALSE"])
            break
        for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).all():
            t = (u.tipo or "").lower()
            if "bodega" in t or t == "storage":
                ws.append([u.numero, u.precio_lista_uf, u.sup_total or "",
                           "TRUE" if u.disponible else "FALSE"])
    else:
        ws.append(["B-15", 80, 3.5, "TRUE"])

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


def _excel_legacy(proy, proyecto_id, con_datos, db):
    """Formato viejo de 1 sheet — fallback opcional."""
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
    fname = f"{safe_name}_stock_legacy{suffix}.xlsx"
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
    usuario: Usuario = Depends(stock_access),
):
    """Upsert por numero_depto. Devuelve resumen {inserted, updated, errors}.

    - Preserva campos manuales (orientación) cuando el Excel viene vacío.
    - Da de baja (disponible=False) los deptos que ya no vienen en el Excel.
    - Registra un evento en extra.timeline ("Excel Stock") con qué cambió.
    """
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
            # Upsert parcial: campos manuales que el origen (PlanOk/MNK) NO provee
            # se preservan si vienen vacíos, para no pisar datos cargados a mano.
            # Ej: orientación — PlanOk no la expone, es manual en BC.
            PRESERVAR_SI_VACIO = {"orientacion"}
            for k, v in data.items():
                if k in PRESERVAR_SI_VACIO and (v is None or v == ""):
                    continue
                setattr(u, k, v)
            updated.append(num)
        else:
            u = Unidad(id="u-" + uuid.uuid4().hex[:10], proyecto_id=proyecto_id, **data)
            db.add(u)
            inserted.append(num)

    # ── Baja de stock: deptos que YA NO vienen en el Excel → disponible=False ──
    # El scraper sube el stock disponible completo; lo que falta = vendido/reservado.
    # NO se borra (preserva registro + datos manuales). Si reaparece → se reactiva.
    seen_nums = {str(d.get("numero_depto") or "").strip() for _i, d in rows_iter}
    dados_de_baja = []
    for u in db.query(Unidad).filter(Unidad.proyecto_id == proyecto_id).all():
        if _is_depto(u) and u.numero not in seen_nums and u.disponible:
            u.disponible = False
            dados_de_baja.append(u.numero)

    proy.stock_last_upload = {
        "filename": file.filename,
        "at": datetime.utcnow().isoformat() + "Z",
        "inserted": len(inserted),
        "updated": len(updated),
        "errors": len(errors),
        "dados_de_baja": len(dados_de_baja),
        "format": "jb_v2.4" if is_jb else "bc_api",
    }

    # ── Timeline: registrar el evento de actualización con comentario corto ──
    _es_scraper = (getattr(usuario, "email", "") or "").lower().startswith("mnk-scraper")
    _origen = "Actualización automática (scraper MNK · PlanOk)" if _es_scraper else "Carga de Excel de stock"
    _partes = [f"{len(updated)} actualizadas"]
    if inserted:
        _partes.append(f"{len(inserted)} nuevas")
    if dados_de_baja:
        _muestra = ", ".join(dados_de_baja[:8]) + ("…" if len(dados_de_baja) > 8 else "")
        _partes.append(f"{len(dados_de_baja)} dadas de baja ({_muestra})")
    _evento = {
        "id": "tl-" + uuid.uuid4().hex[:10],
        "fecha": datetime.utcnow().isoformat() + "Z",
        "tipo": "Excel Stock",
        "detalles": f"{_origen} — {', '.join(_partes)}",
        "usuario": getattr(usuario, "email", None) or "sistema",
        "archivo_url": None,
    }

    # Componer extra: jb_extras (si JB) + timeline actualizado
    _extra = {**(proy.extra or {})}
    if is_jb and jb_extras:
        _extra.update(jb_extras)
    _tl = list(_extra.get("timeline") or [])
    _tl.insert(0, _evento)
    _extra["timeline"] = _tl
    proy.extra = _extra

    db.commit()

    return {
        "format": "jb_v2.4" if is_jb else "bc_api",
        "inserted": len(inserted),
        "updated": len(updated),
        "dados_de_baja": dados_de_baja,
        "errors": errors,
        "estacionamientos_count": len(jb_extras.get("_estacionamientos_dom", [])),
        "bodegas_count": len(jb_extras.get("_bodegas_dom", [])),
        "stock_last_upload": proy.stock_last_upload,
    }
