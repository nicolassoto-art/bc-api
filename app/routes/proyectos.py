"""CRUD de proyectos."""
from typing import List, Optional
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func, Integer, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps.auth import service_token, stock_access, current_user
from ..models import Proyecto, Unidad, Usuario
from ..schemas import ProyectoIn, ProyectoOut, ProyectoSummary
from ..services import email_service
from ..services.timeline import fusionar_timeline
from ..services.estado_stock import estado_stock

router = APIRouter(prefix="/proyectos", tags=["proyectos"])
log = logging.getLogger(__name__)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s or "proyecto-" + uuid.uuid4().hex[:6]


def _next_codigo_corto(db: Session) -> str:
    """Próximo código corto secuencial ("A1", "A2", ...). El id (slug) sigue
    siendo el identificador real — esto es solo una referencia humana corta."""
    existentes = db.query(Proyecto.codigo_corto).filter(Proyecto.codigo_corto.isnot(None)).all()
    max_n = 0
    for (c,) in existentes:
        if c and c[:1] == "A" and c[1:].isdigit():
            max_n = max(max_n, int(c[1:]))
    return f"A{max_n + 1}"


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
    # (23-sep-2026) Listas que se cargan A MANO en la ficha del proyecto (editor de stock
    # propio). puntos_interes: máximo 10 líneas, se muestran en el catálogo junto al mapa.
    # porque_si: argumentos del proyecto para el "Análisis de Factores" del simulador; es
    # material interno, así que el worker lo reenvía SOLO en bcStockToCatalogoDetalle
    # (broker logueado), igual que las notas.
    "puntos_interes", "porque_si",
    # (19-oct-2026) Video del edificio (HLS). Lo escribe SOLO routes/video_proyecto.py. Como porque_si, el
    # worker lo reenvía solo en bcStockToCatalogoDetalle (corredor con sesión).
    "video_ubicacion",
}
# Subcampos de `comercial` que el catálogo necesita; el resto (promo_broker,
# márgenes, etc.) NO sale.
_PUBLIC_COMERCIAL_KEYS = {
    "pie_pct", "bono_pie_pct", "cuoton_inicial_pct", "cuoton_final_pct",
    # % de la etapa construcción (nuevo, 2026-07-22): pie_pct = cuoton_inicial_pct +
    # pago_construccion_pct + cuoton_final_pct + bono_pie_pct. Antes era un vacío
    # implícito entre pie y cuotón — ahora explícito y validable por proyecto.
    "pago_construccion_pct",
    "cuotas_pre_entrega", "cuotas_post_entrega", "valor_reserva_clp",
    # Descuenta 1 cuota automáticamente cada mes desde cuotas_inicio_mes — antes
    # excluidas de ambas allowlists, se perdían siempre en "cotizar desde catálogo"
    # (bug preexistente, corregido al agregar el campo nuevo de arriba).
    "cuotas_auto_decremento", "cuotas_inicio_mes",
    # (2026-08-03) Mismo mecanismo, para el tramo Cuotón Final (cuotas_post_entrega) —
    # par de campos separado a propósito, no comparte dato con el par de arriba.
    "cuotas_post_auto_decremento", "cuotas_post_inicio_mes",
    # (2026-08-12) UF mínima por cuota del tramo construcción. Estaba solo en
    # _BROKER_COMERCIAL_KEYS, así que por el camino worker / link-directo llegaba
    # vacía y la regla "si la cuota daría menos que el mínimo, baja el N° de
    # cuotas" no podía activarse. Mismo bug de allow-list que ya mordió con
    # es_maestra y cuotas_auto_decremento. Hoy la usan 8 proyectos (7 Maestra
    # + Aviador Acevedo).
    "cuota_pre_entrega_uf",
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
    # (2026-08-01) es_maestra: campo INDEPENDIENTE de bono_infla_tasacion (separados
    # 2026-07-24) — decide la fórmula del pie que paga el cliente (esquema Maestra
    # real), no la tasación. Faltaba acá desde que se creó: el checkbox se guardaba y
    # se leía bien en la ficha (GET/PUT /proyectos/{id}, sin filtro), pero catálogo,
    # worker y simulador usan /comercial, /public y /public/{id} — los 3 filtrados por
    # esta lista — así que nunca lo veían. Bug confirmado con plata real: un proyecto
    # Maestra (vistamar) cotizado por link directo calculaba el pie con la fórmula
    # equivocada, cobrando ~943.000 CLP de más al cliente en una unidad de prueba.
    "es_maestra",
    # Modo de precio activo (lista|dcto|bono). El Worker lo expone en precioCotizacion
    # para que el catálogo muestre y cotice con el precio correcto por proyecto.
    "precio_cotizacion",
    # Descuentos a nivel-proyecto (lista {nombre,pct} del editor, card "Descuentos").
    # Igual de benigno que tipo_descuento — el catálogo/cotización lo necesita como
    # respaldo cuando el % aún no se aplicó a cada unidad (botón "Aplicar a todas").
    "descuentos", "descuentos_adicionales",
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
    # (2026-10-29, MNK sin IVA) Precio normal: se adjunta SOLO si existe, así la unidad
    # de cualquier otro proyecto sale idéntica a antes.
    if u.precio_con_iva_uf is not None:
        out["precio_con_iva_uf"] = u.precio_con_iva_uf
    # Arriendo garantizado: columna real en Unidad desde la migración 006
    # (2026-06-16) — la fuente de verdad actual, la que llena el editor y expone
    # el endpoint /unidades. Antes esta función solo miraba extra.arriendos[numero]
    # (mecanismo legado pre-columna, JSON a mano) y JAMÁS la columna → bug real
    # confirmado en vivo (santa-elena-1670-mbi): catálogo mostraba arriendo
    # garantizado en 20/87 unidades (las únicas con entrada legada) mientras la
    # columna real ya lo tenía en 85/87. Se adjunta SOLO si existe → viaja con la
    # unidad y solo llega al transform de broker del worker (el transform público
    # NO manda unidades → no se filtra a anónimos). Sensible: solo lo ve el
    # corredor logueado en el catálogo. Fallback al dict legado por si algún
    # proyecto viejo solo tiene el dato ahí (no debería, tras la migración).
    if u.arriendo_garantizado:
        out["arriendo_garantizado"] = u.arriendo_garantizado
        out["arriendo_moneda"] = u.arriendo_moneda
    elif arriendos:
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
        "codigo_corto": p.codigo_corto,
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
        # (2026-07-27) `notas` es columna real del modelo (Text), la que la pestaña
        # "Notas comerciales" del editor SÍ actualiza — nunca salía acá, solo
        # extra.notas_html/notas_text (legado, congelado desde la importación JB)
        # vía _public_extra. Sin esto, el worker/catálogo/cotizador mostraban para
        # siempre la nota vieja aunque el editor ya tuviera una actual (bug real:
        # edificio-teatinos-750, notas="Up 2%..." nunca llegaba al worker).
        "notas": p.notas,
        # (2026-07-31) Fecha real de stock — antes solo la exponía /comercial (endpoint
        # aparte, autenticado). El catálogo (worker → bcStockToCatalogoDetalle) necesita
        # este mismo /public/{id} para no depender de un segundo fetch async que causaba
        # una carrera visual con la hora de carga de la página (bug crónico reportado,
        # bulnes-138). Con el dato acá, llega junto al resto — sin carrera posible.
        "stock_updated_at": p.stock_updated_at,
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
    # (31-oct-2026) Código estable para el link del video que el asesor manda al cliente: solo si ya hay video listo.
    # Lo entrega este endpoint de servicio (Worker); el navegador del asesor lo recibe por el detalle con sesión.
    try:
        from .video_compartido import codigo_compartir, video_listo
        if video_listo(p):
            d["video_compartir"] = codigo_compartir(p.id)
    except Exception:   # nunca romper el catálogo por esto
        pass
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
        extra = p.extra or {}
        # (2026-09-10) Se acepta también extra.jb_id. La ficha del catálogo se abre
        # con el id de JetBrokers (paginas/catalogo-proyecto.html?id=<jbid>), y una
        # auditoría de los 140 encontró 92 proyectos publicados con jb_id pero
        # external_id vacío: esa URL les devolvía 404 y el catálogo caía a los datos
        # de JB. La alternativa era escribir external_id en los 92, pero eso cambia
        # el id de la tarjeta y borra los proyectos fijados (📌) de cada corredor
        # (catalogo.html usa pinned.includes(p.id)). Resolverlo acá los arregla
        # todos de una, sin tocar un solo dato ni cambiar ninguna URL existente.
        ext = extra.get("external_id")
        jb = extra.get("jb_id")
        if external_id in (ext, jb, p.id):
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
    # (2026-10-18) El listado tardaba ~8 s: cargaba `extra` completo (unidades_dom, etc.)
    # de los 142 proyectos para usar 4 claves. Ahora se piden solo las columnas del
    # resumen y esas claves, extraídas en la base con operadores JSONB.
    stmt = select(
        *(getattr(Proyecto, c) for c in _COLS_LISTADO),
        Proyecto.extra["comercial"]["pie_pct"].label("x_pie_pct"),
        Proyecto.extra["publicar_en_catalogo"].label("x_publicar"),
        Proyecto.extra["gps_verificado"].label("x_gps"),
        Proyecto.extra["timeline"].label("x_timeline"),
    ).where(Proyecto.deleted_at.is_(None))  # la papelera va aparte (#papelera)
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
    proys = db.execute(stmt).all()

    # Conteos de unidades por proyecto en 1 query (no N+1)
    rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.count(Unidad.id),
            func.sum(func.cast(Unidad.disponible, Integer)),
        ).group_by(Unidad.proyecto_id)
    ).all()
    counts = {pid: (total or 0, disp or 0) for pid, total, disp in rows}

    # Precio mínimo de unidades disponibles por proyecto (1 query, no N+1).
    # SIEMPRE precio_lista_uf (nunca precio_final_uf) — el "desde" de catálogo/listados
    # no debe reflejar descuento_pct de ninguna unidad, ese descuento solo se aplica
    # y se muestra dentro de la cotización. (2026-07-20, decisión Nicolás)
    precio_rows = db.execute(
        select(
            Unidad.proyecto_id,
            func.min(Unidad.precio_lista_uf),
        )
        .where(Unidad.disponible == True)
        .where(Unidad.precio_lista_uf > 0)
        .group_by(Unidad.proyecto_id)
    ).all()
    precios_min = {pid: precio for pid, precio in precio_rows if precio}

    # (2026-10-29, MNK sin IVA) Precio normal de la unidad que da el «desde». Solo se
    # consulta para los proyectos con algún precio normal cargado; para el resto queda
    # null y la respuesta trae el mismo «desde» de siempre.
    con_iva_rows = db.execute(
        select(Unidad.proyecto_id, Unidad.precio_lista_uf, Unidad.precio_con_iva_uf)
        .where(Unidad.disponible == True)  # noqa: E712
        .where(Unidad.precio_lista_uf > 0)
        .where(Unidad.proyecto_id.in_(
            select(Unidad.proyecto_id).where(Unidad.precio_con_iva_uf.is_not(None)).distinct()
        ))
    ).all()
    precios_min_con_iva: dict[str, float] = {}
    _mejor: dict[str, float] = {}
    for pid, lista, con_iva in con_iva_rows:
        # Empate en el «desde» (dos unidades con el mismo sin IVA): se queda la que trae
        # precio normal y, entre ellas, la de menor precio normal. Así el resultado no
        # depende del orden en que la base devuelva las filas.
        if (pid not in _mejor or lista < _mejor[pid]
                or (lista == _mejor[pid] and con_iva is not None
                    and (precios_min_con_iva.get(pid) is None or con_iva < precios_min_con_iva[pid]))):
            _mejor[pid] = lista
            precios_min_con_iva[pid] = con_iva  # None si esa unidad no lo trae
    precios_min_con_iva = {pid: v for pid, v in precios_min_con_iva.items() if v}

    # Foto fallback: si Proyecto.foto_principal_url está vacío (importados JB),
    # priorizar FACHADA real ('jb-foto', '', 'fachada', 'exterior') sobre plantas
    # ('jb-planta-*') y otros assets. min(id) alfabético elegía a veces
    # 'jb-planta-3d1b' antes que 'jb-foto' (problema reportado en Alto Buzeta).
    # Solo se consulta para los proyectos sin foto principal, y la base devuelve
    # 1 fila por proyecto (DISTINCT ON) en vez de todas las imágenes.
    sin_foto = [p.id for p in proys if not p.foto_principal_url]
    img_url_by_pid: dict[str, str] = {}
    if sin_foto:
        from ..models import Imagen
        cat = func.lower(func.coalesce(Imagen.categoria, ""))
        es_fachada = or_(cat.in_(["jb-foto", "foto", "fachada", "exterior", ""]), cat.like("%foto%"))

        def _primera_por_proyecto(*condiciones):
            return db.execute(
                select(Imagen.proyecto_id, Imagen.url)
                .where(Imagen.proyecto_id.in_(sin_foto), *condiciones)
                .distinct(Imagen.proyecto_id)
                .order_by(Imagen.proyecto_id, Imagen.id)
            ).all()

        # Primera de cualquier tipo; la fachada (la primera por id) gana si existe.
        img_url_by_pid = {pid: url for pid, url in _primera_por_proyecto()}
        img_url_by_pid.update({pid: url for pid, url in _primera_por_proyecto(es_fachada)})

    out = []
    _ahora = datetime.now(timezone.utc)
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
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
                    "pie_pct": p.x_pie_pct,
                    "precio_desde_uf": precios_min.get(p.id),
                    "precio_desde_con_iva_uf": precios_min_con_iva.get(p.id),
                    "publicar_en_catalogo": bool(p.x_publicar),
                    "gps_verificado": bool(p.x_gps),
                    "foto_principal_url": foto,
                    "estado_stock": _estado_stock_seguro(_ProyectoLigero(p), _ahora),
                }
            )
        )
    return out


# Columnas que usa el resumen del listado (ProyectoSummary) + las que lee estado_stock.
_COLS_LISTADO = (
    "id", "codigo_corto", "nombre", "inmobiliaria", "comuna", "fase", "activo", "disponible",
    "fecha_entrega", "ano_entrega", "foto_principal_url", "external_url", "updated_at",
    "stock_updated_at", "ultima_revision_at", "stock_ok_at", "deleted_at",
)


class _ProyectoLigero:
    """Lo mínimo de un Proyecto que lee estado_stock, armado desde la fila del listado
    (extra trae solo las claves usadas, no el JSON completo)."""

    def __init__(self, row):
        self.inmobiliaria = row.inmobiliaria
        self.activo = row.activo
        self.deleted_at = row.deleted_at
        self.stock_ok_at = row.stock_ok_at
        self.stock_updated_at = row.stock_updated_at
        self.ultima_revision_at = row.ultima_revision_at
        self.extra = {"publicar_en_catalogo": row.x_publicar, "timeline": row.x_timeline}


def _estado_stock_seguro(p, ahora):
    """estado_stock sin tumbar el listado: si un proyecto trae datos raros, el listado
    del editor cae a su lógica de siempre (estado_stock = None)."""
    try:
        return estado_stock(p, ahora)
    except Exception:  # noqa: BLE001
        log.warning("estado_stock falló para %s", getattr(p, "id", "?"), exc_info=True)
        return None


def _resolver_proyecto(db: Session, ident: str, options=None):
    """Busca un proyecto por CUALQUIERA de sus ids: el nuestro (clave primaria),
    extra.external_id o extra.jb_id. Devuelve None si no existe.

    (2026-09-15) Por que existe: cada endpoint resolvia el id con reglas distintas.
    /proyectos/public/{id} aceptaba 3 formas y /proyectos/{id} + /{id}/comercial solo
    la clave primaria. Eso convirtio un cambio de datos en una regresion con plata en
    juego: al ponerle external_id a Cordillera Oriente y La Rioja, la ficha del catalogo
    empezo a abrirse con el id de JetBrokers, /{id}/comercial devolvia 404, y el
    catalogo perdia en SILENCIO los descuentos, el bono pie y las condiciones al
    cotizar (2 descuentos de 100 UF en Cordillera). El sintoma no era un error: era
    un formulario con campos vacios.

    La regla, ahora en un solo lugar: un proyecto responde por todos sus ids.

    Solo para LECTURA. Las mutaciones (PUT/DELETE/restaurar) siguen exigiendo la clave
    primaria a proposito: escribir por un id alternativo no tiene caso de uso aca y es
    justo la forma de terminar modificando el registro equivocado.
    """
    if not ident:
        return None
    p = db.get(Proyecto, ident, options=options) if options else db.get(Proyecto, ident)
    if p:
        return p
    stmt = select(Proyecto).where(or_(
        Proyecto.extra["external_id"].astext == ident,
        Proyecto.extra["jb_id"].astext == ident,
    ))
    if options:
        stmt = stmt.options(*options)
    return db.execute(stmt).scalars().first()


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def detalle(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    p = _resolver_proyecto(
        db, proyecto_id,
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


@router.get("/{proyecto_id}/alertas")
def alertas_proyecto(proyecto_id: str, db: Session = Depends(get_db), _: Usuario = Depends(stock_access)):
    """Pendientes/errores de ESTE proyecto, calculados en vivo (misma lógica que
    el informe diario). Permite verificar al toque si un fix se aplicó bien, sin
    esperar al email de mañana."""
    from ..services.daily_report import _alertas_de_proyecto
    from ..services.fallas import fallas_seguras
    p = _resolver_proyecto(
        db, proyecto_id,
        options=[selectinload(Proyecto.unidades), selectinload(Proyecto.imagenes),
                 selectinload(Proyecto.documentos)],
    )
    if not p or p.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    out = _alertas_de_proyecto(p)
    # (2026-10-05) `items`: las mismas fallas del correo "fallas en fichas", con código,
    # gravedad y pestaña. `criticos`/`warnings` quedan iguales que siempre.
    out["items"] = fallas_seguras(p)
    out["estado_stock"] = _estado_stock_seguro(p, datetime.now(timezone.utc))
    return out


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
    p = _resolver_proyecto(db, proyecto_id)
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
    p = Proyecto(id=pid, codigo_corto=_next_codigo_corto(db), **data)
    db.add(p)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "codigo_corto" not in str(e.orig):
            raise  # conflicto real (ej. id), no es el código corto — propagar tal cual
        # Colisión de codigo_corto por creación concurrente (raro) — reintenta 1 vez.
        p.codigo_corto = _next_codigo_corto(db)
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
    datos = body.model_dump(exclude={"id"})
    # (2026-10-05) La historia NO se reemplaza con la copia del navegador: se une por
    # id con la del servidor. Antes, una alerta de robot publicada mientras la ficha
    # estaba abierta se perdía en el siguiente autoguardado (ver services/timeline.py).
    extra_in = dict(datos.get("extra") or {})
    extra_srv = p.extra or {}
    if "timeline" in extra_in or extra_srv.get("timeline"):
        extra_in["timeline"] = fusionar_timeline(
            extra_in["timeline"] if "timeline" in extra_in else None,
            extra_srv.get("timeline"),
        )
        datos["extra"] = extra_in
    # (19-oct-2026) El video del edificio lo maneja solo routes/video_proyecto.py: la copia que manda
    # el navegador (que puede ser vieja: el video se procesa en segundo plano) nunca lo pisa.
    ex = dict(datos.get("extra") or {})
    if extra_srv.get("video_ubicacion") is not None:
        ex["video_ubicacion"] = extra_srv["video_ubicacion"]
    else:
        ex.pop("video_ubicacion", None)
    # (29-oct-2026) Las listas crudas de estacionamientos y bodegas que deja la subida de
    # Excel JB (con su precio normal `PrecioConIvaUF` en MNK sin IVA) solo las escribe esa
    # subida: la copia del navegador puede ser de antes de la última lectura horaria y
    # el autoguardado del editor las volvía atrás. Mismo patrón que video_ubicacion.
    # SOLO en proyectos que ya traen el precio normal en esas listas (MNK sin IVA
    # activado): en el resto el PUT queda como siempre, porque hay scripts que borran
    # esas claves a propósito (scripts/wipe_proyecto_jb.py, scripts/patch_stock.py).
    def _trae_precio_normal(lista) -> bool:
        return isinstance(lista, list) and any(
            isinstance(it, dict) and "PrecioConIvaUF" in it for it in lista)
    if extra_srv.get("_excel_format") == "jb_v2.4" and (
            _trae_precio_normal(extra_srv.get("_estacionamientos_dom"))
            or _trae_precio_normal(extra_srv.get("_bodegas_dom"))):
        for _k in ("_estacionamientos_dom", "_bodegas_dom", "_excel_format"):
            if _k in extra_srv:
                ex[_k] = extra_srv[_k]
            else:
                ex.pop(_k, None)
    datos["extra"] = ex
    for k, v in datos.items():
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
