"""CRUD de proyectos."""
from typing import List, Optional
import re
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func, Integer
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps.auth import service_token, stock_access, current_user
from ..models import Proyecto, Unidad, Usuario
from ..schemas import ProyectoIn, ProyectoOut, ProyectoSummary
from ..services import email_service

router = APIRouter(prefix="/proyectos", tags=["proyectos"])


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s or "proyecto-" + uuid.uuid4().hex[:6]


# ── Catálogo público (Cloudflare Worker) ────────────────────────────────────
# Estos endpoints los consume SOLO el worker con el token de servicio. Devuelven
# proyectos con publicar_en_catalogo=true (flag guardado en extra por el editor).
# El extra se "aplana" al top-level para que el worker lea estacionamientos/
# bodegas/modelos/comercial directamente. Se enmascaran campos sensibles.

# Claves de `extra` SEGURAS para el catálogo público. Allow-list (fail-closed):
# si el importador agrega una clave nueva, NO se filtra hasta listarla acá.
# Reemplaza la vieja deny-list que apuntaba a nombres inexistentes (rut/numero/
# rut_spa) y dejaba pasar titular_rut, numero_cuenta, link_pago, spa_proyecto.rut,
# notas internas y el path del Excel de stock.
_PUBLIC_EXTRA_KEYS = {
    "external_id", "publicar_en_catalogo",
    "modelos", "estacionamientos", "bodegas",
    "etiquetas", "equipamiento", "areas_comunes", "entorno",
    "descripcion", "constructora", "modalidad", "fisicos",
    # Notas comerciales del proyecto. Salen al worker (server-side, autenticado
    # con service token); el worker decide si reenviarlas al navegador solo en
    # bcStockToCatalogoDetalle (broker logueado), NO en bcStockToCatalogoPublic.
    "notas_html", "notas_text",
}
# Subcampos de `comercial` que el catálogo necesita; el resto (promo_broker,
# márgenes, etc.) NO sale.
_PUBLIC_COMERCIAL_KEYS = {
    "pie_pct", "cuoton_inicial_pct", "cuoton_final_pct",
    "cuotas_pre_entrega", "cuotas_post_entrega", "valor_reserva_clp",
    # Unidad de los cuotones (% o UF) — el catálogo respeta cómo se cargó.
    "cuoton_inicial_unit", "cuoton_final_unit",
    # Tipo de descuento / bono pie (ej. "Todo" / "Solo Unidad" / "No"). Benignos:
    # el corredor los necesita en el recuadro "Plan de pago" del catálogo (piloto
    # Vistamar 2026-06-11). NO son márgenes ni comisiones.
    "tipo_descuento", "tipo_bono_pie",
    # Esquema "Maestra": el bono pie infla la tasacion que ve el banco y el cliente
    # paga el pie sobre el precio lista. El catalogo lo usa para prender Maestra solo
    # en el simulador al cotizar este proyecto.
    "bono_infla_tasacion",
    # Modo de precio activo (lista|dcto|bono). El Worker lo expone en precioCotizacion
    # para que el catálogo muestre y cotice con el precio correcto por proyecto.
    "precio_cotizacion",
}
# Claves de `comercial` visibles para CUALQUIER corredor logueado (no solo
# stock_access) vía GET /{id}/comercial. Es el "Plan de pago" COMPLETO del
# catálogo. Superset de _PUBLIC_COMERCIAL_KEYS — todas benignas (condiciones
# comerciales del proyecto). NO incluye promo_broker / comisiones / márgenes (van
# a nivel top de extra, no en `comercial`) ni la cuenta de reserva (nested aparte).
_BROKER_COMERCIAL_KEYS = _PUBLIC_COMERCIAL_KEYS | {
    "tipo_reserva", "destino_reserva", "tipo_pie", "precio_cotizacion",
    "cuoton_inicial_uf", "cuoton_final_uf",
    "pago_cuoton_inicial", "pago_pre_entrega", "pago_post_entrega",
    "valor_cuota_clp", "nota_pago_pie", "cuota_pre_entrega_uf",
}


def _public_extra(extra: dict) -> dict:
    """Allow-list: SOLO las claves seguras de extra van al catálogo público."""
    src = extra or {}
    e = {k: src[k] for k in _PUBLIC_EXTRA_KEYS if k in src}
    com = src.get("comercial")
    if isinstance(com, dict):
        e["comercial"] = {k: v for k, v in com.items() if k in _PUBLIC_COMERCIAL_KEYS}
    return e


def _unidad_dict(u: Unidad, arriendos: dict | None = None) -> dict:
    out = {
        "id": u.id, "numero": u.numero, "modelo": u.modelo, "tipologia": u.tipologia,
        "tipo": u.tipo, "orientacion": u.orientacion,
        "sup_total": u.sup_total, "sup_interior": u.sup_interior, "sup_terraza": u.sup_terraza,
        "sup_logia": u.sup_logia, "sup_jardin": u.sup_jardin,
        "precio_lista_uf": u.precio_lista_uf, "precio_final_uf": u.precio_final_uf,
        "descuento_pct": u.descuento_pct, "bono_pie_pct": u.bono_pie_pct,
        "disponible": u.disponible,
    }
    # Arriendo garantizado (Euro): vive en extra.arriendos[numero] = {valor, moneda}.
    # Se adjunta a la unidad SOLO si existe → viaja con la unidad y solo llega al
    # transform de broker del worker (el transform público NO manda unidades → no
    # se filtra a anónimos). Sensible: solo lo ve el corredor logueado en el catálogo.
    if arriendos:
        ag = arriendos.get(str(u.numero)) or arriendos.get(u.numero)
        if isinstance(ag, dict) and ag.get("valor"):
            out["arriendo_garantizado"] = ag.get("valor")
            out["arriendo_moneda"] = ag.get("moneda")
    return out


def _foto_principal_fallback(p: Proyecto) -> str | None:
    """foto_principal_url con fallback a las imágenes del proyecto.

    Si el campo plano está vacío (típico en importados JB donde el importador
    sube imágenes pero no setea la portada), deriva: 1º la marcada es_principal,
    2º la fachada (categoría jb-foto/fachada/exterior/vacía — nunca plantas
    jb-planta-*), 3º la primera por id. Misma lógica que el detalle (~L289) y
    el listado admin — centralizada para que el catálogo público (worker)
    nunca quede sin cover. Causa raíz de '57 proyectos sin foto' (2026-06-08).
    """
    # data: URIs (portadas base64 del editor pre-2026-07-02, hasta 836KB) se
    # ignoran: inflaban el catalogo publico a 5MB. Cae al fallback de imagenes.
    if p.foto_principal_url and not p.foto_principal_url.startswith("data:"):
        return p.foto_principal_url
    if not p.imagenes:
        return None
    ordered = sorted(p.imagenes, key=lambda im: im.id)
    principal = next((im for im in ordered if im.es_principal), None)
    if principal:
        return principal.url

    def _is_facade(im):
        c = (im.categoria or "").lower()
        if c.startswith("jb-planta"):
            return False
        return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c

    facade = next((im for im in ordered if _is_facade(im)), None)
    if facade:
        return facade.url
    no_planta = next((im for im in ordered if not (im.categoria or "").lower().startswith("jb-planta")), None)
    return (no_planta or ordered[0]).url


# Tipos de documento que SÍ se exponen en el catálogo público (resto = privado).
_DOCS_PUBLICOS = {"brochure", "plano", "folleto", "ficha", "ficha técnica", "ficha tecnica"}


def _proyecto_public_dict(p: Proyecto) -> dict:
    """Forma que el worker espera: extra aplanado + unidades + relaciones, enmascarado."""
    extra = p.extra or {}
    d = {
        "id": p.id,
        "external_id": extra.get("external_id") or p.id,
        "publicar_en_catalogo": bool(extra.get("publicar_en_catalogo")),
        "nombre": p.nombre,
        "inmobiliaria": p.inmobiliaria,
        "comuna": p.comuna,
        "region": p.region,
        "direccion": p.direccion,
        "gps_lat": p.gps_lat,
        "gps_lon": p.gps_lon,
        "fase": p.fase,
        "modalidad": p.modalidad,
        "fecha_entrega": p.fecha_entrega,
        "ano_entrega": p.ano_entrega,
        "foto_principal_url": _foto_principal_fallback(p),
        "unidades": [
            _unidad_dict(u, extra.get("arriendos") if isinstance(extra.get("arriendos"), dict) else None)
            for u in (p.unidades or [])
        ],
        "imagenes": [
            {"id": im.id, "url": im.url, "categoria": im.categoria, "es_principal": im.es_principal}
            for im in (p.imagenes or [])
        ],
        # Documentos: SOLO tipos públicos (2026-06-10). Antes se exponían TODOS
        # — incluyendo SPA, escrituras, pólizas y reglamentos con URL directa en
        # el endpoint público del catálogo (fuga de documentos privados a
        # cualquiera). Allow-list de tipos comerciales que sí se muestran al
        # cliente final. El editor (privado) sigue viendo todos.
        "documentos": [
            {"id": dc.id, "tipo": dc.tipo, "detalles": dc.nombre, "url": dc.url}
            for dc in (p.documentos or [])
            if str(dc.tipo or "").strip().lower() in _DOCS_PUBLICOS
        ],
    }
    # Aplanar SOLO las claves seguras de extra (allow-list, fail-closed):
    # estacionamientos, bodegas, modelos, comercial[sanitizado], etiquetas,
    # equipamiento, areas_comunes, entorno, descripcion, constructora, fisicos.
    for k, v in _public_extra(extra).items():
        if k not in d:
            d[k] = v
    return d


def _is_publicable(p: Proyecto) -> bool:
    extra = p.extra or {}
    return bool(extra.get("publicar_en_catalogo")) and p.activo


@router.get("/public")
def listar_publicos(db: Session = Depends(get_db), _: bool = Depends(service_token)):
    """Lista proyectos con publicar_en_catalogo=true (consume el worker)."""
    proys = db.execute(
        select(Proyecto)
        .options(selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos))
        .where(Proyecto.activo == True)  # noqa: E712
        .where(Proyecto.deleted_at.is_(None))  # excluir papelera
        .order_by(Proyecto.updated_at.desc())
    ).scalars().all()
    return [_proyecto_public_dict(p) for p in proys if _is_publicable(p)]


@router.get("/public/{external_id}")
def detalle_publico(external_id: str, db: Session = Depends(get_db), _: bool = Depends(service_token)):
    """Detalle de UN proyecto publicado, por external_id (o id propio como fallback)."""
    proys = db.execute(
        select(Proyecto)
        .options(selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos))
        .where(Proyecto.activo == True)  # noqa: E712
        .where(Proyecto.deleted_at.is_(None))  # excluir papelera
    ).scalars().all()
    for p in proys:
        if not _is_publicable(p):
            continue
        ext = (p.extra or {}).get("external_id")
        if external_id in (ext, p.id):
            return _proyecto_public_dict(p)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no publicado")


@router.get("/papelera", response_model=List[ProyectoSummary])
def listar_papelera(db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    """Proyectos en la papelera (soft-deleted). Purga-al-leer: borra de verdad los
    que ya pasaron 30 días desde el borrado. El frontend calcula los días restantes
    a partir de deleted_at. Declarada ANTES de /{proyecto_id} para que no la capture."""
    limite = datetime.utcnow() - timedelta(days=30)
    expirados = db.execute(
        select(Proyecto).where(Proyecto.deleted_at.is_not(None), Proyecto.deleted_at < limite)
    ).scalars().all()
    for p in expirados:
        db.delete(p)
    if expirados:
        db.commit()
    return db.execute(
        select(Proyecto).where(Proyecto.deleted_at.is_not(None)).order_by(Proyecto.deleted_at.desc())
    ).scalars().all()


@router.get("", response_model=List[ProyectoSummary])
def listar(
    q: Optional[str] = Query(None, description="Búsqueda en nombre/inmobiliaria/comuna"),
    activo: Optional[bool] = None,
    fase: Optional[str] = None,
    comuna: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    stmt = select(Proyecto).where(Proyecto.deleted_at.is_(None))  # la papelera va aparte (#papelera)
    if activo is not None:
        stmt = stmt.where(Proyecto.activo == activo)
    if fase:
        stmt = stmt.where(Proyecto.fase == fase)
    if comuna:
        stmt = stmt.where(Proyecto.comuna == comuna)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Proyecto.nombre).like(like)
            | func.lower(Proyecto.inmobiliaria).like(like)
            | func.lower(Proyecto.comuna).like(like)
        )
    stmt = stmt.order_by(Proyecto.updated_at.desc())
    proys = db.execute(stmt).scalars().all()

    # Conteos de unidades por proyecto en 1 query (no N+1)
    rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.count(Unidad.id),
            func.sum(func.cast(Unidad.disponible, Integer)),
        ).group_by(Unidad.proyecto_id)
    ).all()
    counts = {pid: (total or 0, disp or 0) for pid, total, disp in rows}

    # Precio mínimo de unidades disponibles por proyecto (1 query, no N+1)
    precio_rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.min(
                func.coalesce(Unidad.precio_final_uf, Unidad.precio_lista_uf)
            ),
        )
        .where(Unidad.disponible == True)
        .where(func.coalesce(Unidad.precio_final_uf, Unidad.precio_lista_uf) > 0)
        .group_by(Unidad.proyecto_id)
    ).all()
    precios_min = {pid: precio for pid, precio in precio_rows if precio}

    # Foto fallback: si Proyecto.foto_principal_url está vacío (importados JB),
    # priorizar FACHADA real ('jb-foto', '', 'fachada', 'exterior') sobre plantas
    # ('jb-planta-*') y otros assets. min(id) alfabético elegía a veces
    # 'jb-planta-3d1b' antes que 'jb-foto' (problema reportado en Alto Buzeta).
    from ..models import Imagen
    all_imgs = db.execute(
        select(Imagen.id, Imagen.proyecto_id, Imagen.url, Imagen.categoria).order_by(Imagen.id)
    ).all()

    def _is_facade(cat: str) -> bool:
        c = (cat or "").lower()
        return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c

    # Por proyecto: si hay alguna con categoría de fachada, esa gana (la primera
    # por id). Si no, usar la primera imagen sin discriminar.
    img_url_by_pid: dict[str, str] = {}
    img_facade_by_pid: dict[str, str] = {}
    for r in all_imgs:
        if r.proyecto_id not in img_url_by_pid:
            img_url_by_pid[r.proyecto_id] = r.url  # primera de cualquier tipo
        if _is_facade(r.categoria) and r.proyecto_id not in img_facade_by_pid:
            img_facade_by_pid[r.proyecto_id] = r.url
    # Merge: la fachada gana si existe; si no, la primera cualquiera.
    img_url_by_pid = {**img_url_by_pid, **img_facade_by_pid}

    out = []
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
        extra = p.extra or {}
        comercial = extra.get("comercial") or {}
        # NOTA: NO inflar unidades_total con extra.fisicos.unidades_totales.
        # Ese campo es el total del EDIFICIO, no stock disponible a la venta.
        # Proyectos sin detalle publicado en JB deben mostrar "sin stock" (0),
        # no el tamaño del edificio (que confunde). El total del edificio queda
        # disponible en la ficha (tab General) como dato informativo.
        # Foto principal: si no hay foto_principal_url, fallback a la primera imagen.
        foto = p.foto_principal_url or img_url_by_pid.get(p.id) or None
        out.append(
            ProyectoSummary.model_validate(p).model_copy(
                update={
                    "unidades_total": int(total),
                    "unidades_disponibles": int(disp),
                    "pie_pct": comercial.get("pie_pct"),
                    "precio_desde_uf": precios_min.get(p.id),
                    "publicar_en_catalogo": bool(extra.get("publicar_en_catalogo")),
                    "gps_verificado": bool(extra.get("gps_verificado")),
                    "foto_principal_url": foto,
                }
            )
        )
    return out


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def detalle(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = db.get(
        Proyecto,
        proyecto_id,
        options=[selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes), selectinload(Proyecto.documentos)],
    )
    if not p or p.deleted_at is not None:
        # En la papelera = no accesible por el detalle normal (restaurar usa /restaurar).
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    # Fallback de foto: si foto_principal_url está vacía pero hay imágenes,
    # priorizar la FACHADA REAL (categoria='jb-foto' / 'fachada' / vacía) por
    # encima de plantas ('jb-planta-*'). Si no hay fachada categorizada, usar
    # la primera por id como último recurso. Mutar el objeto SQLAlchemy es
    # seguro acá porque no llamamos commit().
    if not p.foto_principal_url and p.imagenes:
        def _is_facade(im):
            c = (im.categoria or "").lower()
            return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c
        ordered = sorted(p.imagenes, key=lambda im: im.id)
        facade = next((im for im in ordered if _is_facade(im)), None)
        p.foto_principal_url = (facade.url if facade else ordered[0].url)
    return p


@router.get("/{proyecto_id}/comercial")
def comercial_broker(
    proyecto_id: str,
    db: Session = Depends(get_db),
    _: Usuario = Depends(current_user),
):
    """Plan de pago (condiciones comerciales) del proyecto para CUALQUIER corredor
    logueado — no solo stock_access. El catálogo lo usa para pintar el recuadro
    "Plan de pago" COMPLETO a todos los brokers (el feed público del worker recorta
    varios de estos campos). Solo expone claves benignas del plan de pago vía
    _BROKER_COMERCIAL_KEYS; NO sale promo_broker / comisiones / márgenes / cuenta
    de reserva. Misma fuente para admin y corredor → vista idéntica en el catálogo.
    """
    p = db.get(Proyecto, proyecto_id)
    if not p or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    com = (p.extra or {}).get("comercial")
    com = com if isinstance(com, dict) else {}
    out = {k: v for k, v in com.items() if k in _BROKER_COMERCIAL_KEYS}
    # (2026-06-17) NO exponer arriendo garantizado por unidad acá: el usuario lo
    # marcó como información SENSIBLE → no debe verse en el catálogo (ningún broker).
    # Se quitó el mapa `arriendos`. El dato sigue en el editor de stock (privado).
    # (2026-06-22) Fecha real de actualización del stock (benigna): el catálogo la
    # usa para "Última actualización" en vez de la hora de carga. Naive UTC, igual
    # que en stock-interno → el frontend fuerza UTC y muestra en hora Chile.
    return {
        "id": p.id,
        "comercial": out,
        "stock_updated_at": p.stock_updated_at,
        "updated_at": p.updated_at,
    }


@router.post("", response_model=ProyectoOut, status_code=status.HTTP_201_CREATED)
def crear(body: ProyectoIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    pid = body.id or slugify(body.nombre)
    if db.get(Proyecto, pid):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya existe un proyecto con id '{pid}'")
    data = body.model_dump(exclude={"id"})
    p = Proyecto(id=pid, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    background_tasks.add_task(
        email_service.notify_change, "Nuevo proyecto en stock", p.nombre or pid,
        f"Se creó el proyecto ({p.inmobiliaria or 'sin inmobiliaria'} · {p.comuna or 's/comuna'}).", p.id,
    )
    return p


@router.put("/{proyecto_id}", response_model=ProyectoOut)
def actualizar(
    proyecto_id: str,
    body: ProyectoIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    for k, v in body.model_dump(exclude={"id"}).items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    """Soft-delete: mueve el proyecto a la PAPELERA (recuperable 30 días). Se oculta
    de listados y catálogo (activo=False + publicar=False). La purga final (borrado
    real) ocurre al listar la papelera una vez pasados los 30 días."""
    from sqlalchemy.orm.attributes import flag_modified
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    p.deleted_at = datetime.utcnow()
    p.activo = False
    extra = dict(p.extra or {})
    if extra.get("publicar_en_catalogo"):
        extra["publicar_en_catalogo"] = False
        p.extra = extra
        flag_modified(p, "extra")
    db.commit()


@router.post("/{proyecto_id}/restaurar", response_model=ProyectoOut)
def restaurar(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    """Restaura un proyecto desde la papelera: lo reactiva (deleted_at=None, activo=True).
    NO lo re-publica en el catálogo (eso queda como acción manual del usuario)."""
    p = db.get(Proyecto, proyecto_id)
    if not p or p.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El proyecto no está en la papelera")
    p.deleted_at = None
    p.activo = True
    db.commit()
    db.refresh(p)
    return p


class _EstadoBody(BaseModel):
    activo: bool


@router.patch("/{proyecto_id}/estado", response_model=ProyectoSummary)
def set_estado(
    proyecto_id: str,
    body: _EstadoBody,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Activa (activo=true) o desactiva (activo=false) un proyecto. Usado por el validador."""
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    p.activo = body.activo
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    total, disp = db.execute(
        select(func.count(Unidad.id), func.sum(func.cast(Unidad.disponible, Integer)))
        .where(Unidad.proyecto_id == proyecto_id)
    ).one()
    extra = p.extra or {}
    comercial = extra.get("comercial") or {}
    return ProyectoSummary.model_validate(p).model_copy(
        update={
            "unidades_total": int(total or 0),
            "unidades_disponibles": int(disp or 0),
            "pie_pct": comercial.get("pie_pct"),
            "publicar_en_catalogo": bool((p.extra or {}).get("publicar_en_catalogo")),
        }
    )


class _PublicarBody(BaseModel):
    publicar: bool


@router.patch("/{proyecto_id}/publicar")
def set_publicar(
    proyecto_id: str,
    body: _PublicarBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: Usuario = Depends(stock_access),
):
    """Marca/desmarca un proyecto para el catálogo público (extra.publicar_en_catalogo).
    Toggle liviano desde la lista de stock — toca SOLO el flag, no unidades ni nada más."""
    from sqlalchemy.orm.attributes import flag_modified
    p = db.get(Proyecto, proyecto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    extra = dict(p.extra or {})
    extra["publicar_en_catalogo"] = bool(body.publicar)
    p.extra = extra
    flag_modified(p, "extra")
    p.updated_at = datetime.utcnow()
    db.commit()
    background_tasks.add_task(
        email_service.notify_change,
        "Publicado en catálogo" if body.publicar else "Quitado del catálogo",
        p.nombre or p.id,
        "Ahora es visible en el catálogo público." if body.publicar else "Ya no aparece en el catálogo público.",
        p.id,
    )
    return {"ok": True, "id": p.id, "publicar_en_catalogo": bool(body.publicar)}
