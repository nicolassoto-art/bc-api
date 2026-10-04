"""Fallas de las fichas — bc-api · 2026-10-05

Base del correo "Stock interno · fallas en fichas" y del panel "Pendientes" del
editor (GET /proyectos/{id}/alertas → `items`). Pedido de Nicolás (30/09/2026):
"un email que alerte fallas, por ejemplo que un plan de pago no está, que falta
información… piensa en todo".

Cada falla es un dict con un CÓDIGO estable (sirve para saber desde cuándo está
abierta y marcar las nuevas), un texto para personas, su gravedad y la pestaña del
editor donde se arregla:
    {codigo, texto, severidad: "critica"|"aviso", tab, grupo, resumen?}

Las reglas de siempre (_alertas_de_proyecto en daily_report.py) siguen ahí, sin
tocar: el informe de las 09:00 las usa tal cual. Acá se recalculan con dos arreglos
que el listado del editor ya tenía: el plan de pago se lee juntando
`formas_pago_pie` (lo escribe el importador) y `comercial` (lo escribe el editor),
y los datos del edificio aceptan `extra.fisicos` además de las claves sueltas.

En fichas que no están publicadas, lo que es "falta completar" baja a aviso (igual
que el editor): es trabajo pendiente, no algo que hoy vea un corredor.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from datetime import datetime
from typing import Any, Optional

CRITICA = "critica"
AVISO = "aviso"

GRUPO_PLAN = "Plan de pago y precios"
GRUPO_FICHA = "Ficha y material"
GRUPO_RESERVA = "Reserva y operación"
GRUPO_TEXTOS = "Textos de venta"
GRUPO_STOCK = "Stock y modelos"

# Mismo criterio que el catálogo público (routes/proyectos.py:_DOCS_PUBLICOS).
DOCS_PUBLICOS = {"brochure", "plano", "folleto", "ficha", "ficha técnica", "ficha tecnica"}

_PLACEHOLDERS_INMOB = {"sin asignar", "bigcapital", "big capital"}


def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _pos(v: Any) -> bool:
    n = _num(v)
    return n is not None and n > 0


def _fmt_pct(v: float) -> str:
    return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",") + "%"


def es_depto(u: Any) -> bool:
    """¿La unidad es un departamento (no estacionamiento/bodega/pack)? Misma regla que
    daily_report._is_depto."""
    t = ((getattr(u, "tipo", None) or getattr(u, "tipologia", None)) or "").lower()
    n = (getattr(u, "numero", None) or "")
    if n.startswith("E-") or "estac" in t or "parking" in t:
        return False
    if n.startswith("B-") or "bodeg" in t or t == "storage":
        return False
    if "pack" in t:
        return False
    return True


def comercial_normalizado(extra: dict) -> dict:
    """formas_pago_pie (importador) + comercial (editor). Gana comercial, salvo vacío."""
    out = dict(extra.get("formas_pago_pie") or {})
    for k, v in (extra.get("comercial") or {}).items():
        if not _vacio(v) or k not in out:
            out[k] = v
    return out


_FISICOS_ALIAS = {"estac_totales": ("estac_totales", "estacionamientos_totales")}


def _fisico(extra: dict, clave: str) -> Any:
    for k in _FISICOS_ALIAS.get(clave, (clave,)):
        v = extra.get(k)
        if not _vacio(v):
            return v
        v = (extra.get("fisicos") or {}).get(k)
        if not _vacio(v):
            return v
    return None


def rut_valido(rut: Any) -> bool:
    """RUT chileno con dígito verificador correcto (módulo 11). Acepta puntos, guion, k."""
    s = re.sub(r"[^0-9kK]", "", str(rut or ""))
    if len(s) < 8 or len(s) > 9:
        return False
    cuerpo, dv = s[:-1], s[-1].upper()
    if not cuerpo.isdigit():
        return False
    total, factor = 0, 2
    for d in reversed(cuerpo):
        total += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    r = 11 - (total % 11)
    esperado = "0" if r == 11 else "K" if r == 10 else str(r)
    return dv == esperado


def _rut_relleno(rut: Any) -> bool:
    s = re.sub(r"[^0-9kK]", "", str(rut or ""))
    cuerpo = s[:-1]
    return not cuerpo or len(set(cuerpo)) == 1


_ETAPA = {
    "blanco": "blanco", "en blanco": "blanco", "etapa blanca": "blanco", "white": "blanco", "inwhite": "blanco",
    "verde": "verde", "en verde": "verde", "green": "verde", "ingreen": "verde",
    "en construccion": "construccion", "construccion": "construccion", "underconstruction": "construccion",
    "obra gruesa": "construccion",
    "entrega inmediata": "inmediata", "deliveryready": "inmediata", "terminado": "inmediata",
}
_ETAPA_TXT = {"blanco": "En blanco", "verde": "En verde", "construccion": "En construcción",
              "inmediata": "Entrega inmediata"}


def _ejemplos(numeros: list, n: int = 5) -> str:
    lst = [str(x or "?") for x in numeros]
    return ", ".join(lst[:n]) + ("…" if len(lst) > n else "")


def _it(codigo: str, texto: str, severidad: str, tab: str, grupo: str, *,
        baja_sin_publicar: bool = False, resumen: bool = False) -> dict:
    return {"codigo": codigo, "texto": texto, "severidad": severidad, "tab": tab,
            "grupo": grupo, "baja_sin_publicar": baja_sin_publicar, "resumen": resumen}


def fallas_de_proyecto(p: Any, hoy: Optional[datetime] = None) -> list:
    """Todas las fallas de la ficha `p` (Proyecto o un objeto con los mismos campos)."""
    hoy = hoy or datetime.utcnow()
    extra = getattr(p, "extra", None) or {}
    publicado = bool(extra.get("publicar_en_catalogo")) and bool(getattr(p, "activo", True))
    unidades = list(getattr(p, "unidades", None) or [])
    imagenes = list(getattr(p, "imagenes", None) or [])
    documentos = list(getattr(p, "documentos", None) or [])
    deptos = [u for u in unidades if es_depto(u)]
    disp = [u for u in deptos if getattr(u, "disponible", False)]
    com = comercial_normalizado(extra)
    items: list = []
    add = items.append

    # ── Datos básicos
    if _vacio(getattr(p, "nombre", None)):
        add(_it("ficha.sin_nombre", "Sin nombre", CRITICA, "general", GRUPO_FICHA))
    inmob = (getattr(p, "inmobiliaria", None) or "").strip()
    if not inmob:
        add(_it("ficha.inmobiliaria", "Sin inmobiliaria", CRITICA, "general", GRUPO_FICHA))
    elif _norm(inmob).rstrip(".") in _PLACEHOLDERS_INMOB:
        add(_it("ficha.inmobiliaria", f"Inmobiliaria sin asignar (dice «{inmob}»)", CRITICA, "general",
                GRUPO_FICHA))
    if _vacio(getattr(p, "comuna", None)):
        add(_it("ficha.sin_comuna", "Sin comuna", CRITICA, "general", GRUPO_FICHA))
    if _vacio(getattr(p, "direccion", None)):
        add(_it("ficha.sin_direccion", "Sin dirección", AVISO, "general", GRUPO_FICHA))
    if _vacio(getattr(p, "region", None)):
        add(_it("ficha.sin_region", "Sin región", AVISO, "general", GRUPO_FICHA))
    if extra.get("gps_verificado") is not True:
        if publicado:
            add(_it("ficha.sin_gps", "Sin ubicación verificada (publicado)", CRITICA, "local", GRUPO_FICHA))
        else:
            add(_it("ficha.sin_gps", "Sin ubicación verificada", AVISO, "local", GRUPO_FICHA))
    if _vacio(getattr(p, "fase", None)):
        add(_it("ficha.sin_fase", "Sin fase definida", AVISO, "general", GRUPO_FICHA))
    if _vacio(getattr(p, "fecha_entrega", None)) and not getattr(p, "ano_entrega", None):
        add(_it("ficha.sin_entrega", "Sin fecha de entrega", AVISO, "general", GRUPO_FICHA))

    # Etapa vs fecha de entrega
    etapa = _ETAPA.get(_norm(getattr(p, "fase", None)))
    fecha_txt = str(getattr(p, "fecha_entrega", None) or "")
    anio = getattr(p, "ano_entrega", None)
    if not anio:
        m = re.search(r"\b(20\d\d)\b", fecha_txt)
        anio = int(m.group(1)) if m else None
    if etapa and (anio or "inmediata" in _norm(fecha_txt)):
        if etapa == "inmediata" and anio and anio > hoy.year:
            add(_it("ficha.etapa_vs_entrega", f"La etapa dice «Entrega inmediata» pero la entrega es en {anio}",
                    AVISO, "general", GRUPO_FICHA))
        elif etapa in ("blanco", "verde", "construccion") and anio and anio < hoy.year:
            add(_it("ficha.etapa_vs_entrega", f"La etapa dice «{_ETAPA_TXT[etapa]}» pero la entrega fue en {anio}",
                    AVISO, "general", GRUPO_FICHA))
        elif etapa in ("blanco", "verde") and "inmediata" in _norm(fecha_txt):
            add(_it("ficha.etapa_vs_entrega", f"La etapa dice «{_ETAPA_TXT[etapa]}» pero la entrega dice «inmediata»",
                    AVISO, "general", GRUPO_FICHA))

    # ── Material
    def _img_fachada(im):
        c = (getattr(im, "categoria", None) or "").strip().lower()
        if c.startswith("jb-planta"):
            return False
        return bool(getattr(im, "es_principal", False)) or c in {"jb-foto", "foto", "fachada", "exterior", "cover", ""} \
            or "foto" in c
    tiene_fachada = bool(getattr(p, "foto_principal_url", None)) or any(_img_fachada(im) for im in imagenes)
    if not tiene_fachada:
        add(_it("material.sin_fachada", "Sin foto de fachada", CRITICA, "fotos", GRUPO_FICHA))
    else:
        galeria = [im for im in imagenes
                   if not (getattr(im, "categoria", None) or "").lower().startswith(("jb-planta", "jb-doc"))]
        if len(galeria) <= 1:
            add(_it("material.sin_galeria", "Falta foto de galería (solo hay portada)", AVISO, "fotos", GRUPO_FICHA,
                    baja_sin_publicar=True))
    tipos_doc = [_norm(getattr(d, "tipo", None)) for d in documentos]
    if not any(t in DOCS_PUBLICOS for t in tipos_doc):
        brochure_img = any((getattr(im, "categoria", None) or "").lower().startswith("jb-doc") for im in imagenes)
        if documentos:
            texto = ("Falta documento que vea el corredor: los que hay son de un tipo que el catálogo no "
                     "muestra; cambia el tipo a Brochure, Folleto, Plano o Ficha")
        elif brochure_img:
            texto = "Falta documento que vea el corredor: el brochure quedó como imagen; súbelo como documento"
        else:
            texto = "Falta documento que vea el corredor (brochure, folleto, plano o ficha)"
        add(_it("material.sin_documento_publico", texto, AVISO, "documentos", GRUPO_FICHA, baja_sin_publicar=True))

    # ── Stock
    if not unidades:
        add(_it("stock.sin_stock", "Sin stock cargado", CRITICA, "unidades", GRUPO_STOCK))
    elif publicado and not disp:
        add(_it("stock.publicado_sin_disponible", "Publicado sin stock disponible", CRITICA, "unidades", GRUPO_STOCK))

    # ── Plan de pago
    falta_pp = []
    if _vacio(com.get("pie_pct")):
        falta_pp.append("pie %")
    if _vacio(com.get("valor_reserva_clp")):
        falta_pp.append("valor de reserva")
    if not any(_pos(com.get(k)) for k in ("cuotas_pre_entrega", "cuotas_post_entrega", "cuoton_inicial_pct",
                                          "cuoton_final_pct", "cuoton_inicial_uf", "cuoton_final_uf")):
        falta_pp.append("cuotas del pie (pre/post o cuotones)")
    if _vacio(com.get("tipo_pie")):
        falta_pp.append("tipo de pie")
    descuentos = com.get("descuentos")
    if isinstance(descuentos, list) and descuentos and _vacio(com.get("tipo_descuento")):
        falta_pp.append("tipo de descuento")
    if _vacio(com.get("tipo_bono_pie")):
        falta_pp.append("tipo de bono pie")
    if falta_pp:
        add(_it("plan.incompleto", "Plan de pago incompleto: falta " + ", ".join(falta_pp), CRITICA, "general",
                GRUPO_PLAN, baja_sin_publicar=True))
    falta_fp = []
    if (_pos(com.get("cuoton_inicial_pct")) or _pos(com.get("cuoton_inicial_uf"))) and _vacio(com.get("pago_cuoton_inicial")):
        falta_fp.append("pago del cuotón inicial")
    if _pos(com.get("cuotas_pre_entrega")) and _vacio(com.get("pago_pre_entrega")):
        falta_fp.append("pago pre-entrega")
    if _pos(com.get("cuotas_post_entrega")) and _vacio(com.get("pago_post_entrega")):
        falta_fp.append("pago post-entrega")
    if falta_fp:
        add(_it("plan.forma_pago", "Forma de pago del pie incompleta: falta " + ", ".join(falta_fp), CRITICA,
                "general", GRUPO_PLAN, baja_sin_publicar=True))

    # El pie no cuadra (misma cuenta que el editor, proyecto.js actualizarCuadraturaPie):
    # pie = cuotón inicial + construcción + cuotón final + bono. Cuotones en UF no entran.
    # Solo fichas con "construcción" guardada (campo de 2026-07-22): en las anteriores
    # la suma no se puede hacer y marcaría falsas fallas.
    pie = _num(com.get("pie_pct")) or 0
    if pie > 0 and not _vacio(com.get("pago_construccion_pct")):
        def _cuoton(k):
            uf = _num(com.get(f"cuoton_{k}_uf"))
            if (uf is not None and uf > 0) or str(com.get(f"cuoton_{k}_unit") or "").upper() == "UF":
                return 0.0
            return _num(com.get(f"cuoton_{k}_pct")) or 0.0
        ini, fin = _cuoton("inicial"), _cuoton("final")
        con = _num(com.get("pago_construccion_pct")) or 0.0
        bono = _num(com.get("bono_pie_pct")) or 0.0
        suma = round(ini + con + fin + bono, 2)
        delta = round(pie - suma, 2)
        if abs(delta) >= 0.01:
            cuenta = (f"{_fmt_pct(pie)} (pie) ≠ {_fmt_pct(ini)} + {_fmt_pct(con)} + {_fmt_pct(fin)} + "
                      f"{_fmt_pct(bono)} (bono) = {_fmt_pct(suma)}")
            texto = (f"El pie no cuadra: falta {_fmt_pct(delta)} — {cuenta}" if delta > 0
                     else f"El pie no cuadra: se pasa por {_fmt_pct(-delta)} — {cuenta}")
            add(_it("plan.pie_no_cuadra", texto, CRITICA, "general", GRUPO_PLAN))

    # ── Precios (deptos disponibles)
    sin_precio = [u.numero for u in disp if not (_pos(u.precio_final_uf) or _pos(u.precio_lista_uf))]
    if sin_precio:
        add(_it("precios.sin_precio", f"{len(sin_precio)} depto(s) sin precio: {_ejemplos(sin_precio)}", CRITICA,
                "unidades", GRUPO_PLAN, baja_sin_publicar=True))
    solo_final = [u.numero for u in disp if _pos(u.precio_final_uf) and not _pos(u.precio_lista_uf)]
    if solo_final:
        add(_it("precios.sin_precio_lista",
                f"{len(solo_final)} depto(s) con precio final pero sin precio de lista: {_ejemplos(solo_final)}",
                CRITICA, "unidades", GRUPO_PLAN, baja_sin_publicar=True))
    sin_m2 = [u.numero for u in disp if not _pos(getattr(u, "sup_total", None))]
    if sin_m2:
        add(_it("precios.sin_superficie", f"{len(sin_m2)} depto(s) sin m²: {_ejemplos(sin_m2)}", CRITICA,
                "unidades", GRUPO_PLAN, baja_sin_publicar=True))
    final_mayor = [u.numero for u in disp if _pos(u.precio_final_uf) and _pos(u.precio_lista_uf)
                   and float(u.precio_final_uf) > float(u.precio_lista_uf) + 0.01]
    if final_mayor:
        add(_it("precios.final_mayor_lista",
                f"{len(final_mayor)} depto(s) con precio final mayor que el de lista: {_ejemplos(final_mayor)}",
                CRITICA, "unidades", GRUPO_PLAN))
    bono_ficha = _num(com.get("bono_pie_pct"))
    fuera_rango, bono_mayor = [], []
    for u in disp:
        d = _num(getattr(u, "descuento_pct", None))
        b = _num(getattr(u, "bono_pie_pct", None))
        b_ef = b if b is not None else bono_ficha
        if (d is not None and not (0 <= d <= 100)) or (b is not None and not (0 <= b <= 100)):
            fuera_rango.append(u.numero)
        elif pie > 0 and b_ef is not None and b_ef > pie + 0.001:
            bono_mayor.append(u.numero)
    if fuera_rango:
        add(_it("precios.pct_fuera_rango",
                f"{len(fuera_rango)} depto(s) con descuento o bono fuera de 0–100%: {_ejemplos(fuera_rango)}",
                CRITICA, "unidades", GRUPO_PLAN))
    if bono_mayor:
        add(_it("precios.bono_mayor_pie",
                f"{len(bono_mayor)} depto(s) con bono pie mayor que el pie ({_fmt_pct(pie)}): {_ejemplos(bono_mayor)}",
                CRITICA, "unidades", GRUPO_PLAN))
    # Bono pie 0% en la unidad cuando la ficha ofrece bono. None = la unidad hereda la
    # ficha (correcto); 0 = cero real que tapa la ficha en el editor y en su Cotizar.
    tipo_bono = _norm(com.get("tipo_bono_pie"))
    if bono_ficha and bono_ficha > 0 and tipo_bono not in ("no", "distinto por depto"):
        cero = [u.numero for u in disp if _num(getattr(u, "bono_pie_pct", None)) == 0]
        if cero:
            texto = (f"{len(cero)} depto(s) disponibles cotizan bono pie 0% y la ficha dice {_fmt_pct(bono_ficha)}: "
                     f"en el editor y su botón Cotizar salen sin bono (el catálogo usa el de la ficha). "
                     f"Ej.: {_ejemplos(cero)}")
            if _norm(inmob) in ("euroinmobiliaria", "euro inmobiliaria", "euro"):
                texto += " (se corrige en la reparación de Euro ya programada)"
            add(_it("precios.bono_unidad_cero", texto, AVISO, "unidades", GRUPO_PLAN))
    # UF/m² muy distinto al resto (posible error de tipeo), con 5 o más deptos.
    ufm2 = [(u.numero, float(u.precio_lista_uf) / float(u.sup_total)) for u in disp
            if _pos(u.precio_lista_uf) and _pos(getattr(u, "sup_total", None))]
    if len(ufm2) >= 5:
        med = statistics.median(v for _, v in ufm2)
        raros = [n for n, v in ufm2 if med > 0 and (v < 0.5 * med or v > 1.8 * med)]
        if raros:
            add(_it("precios.uf_m2_atipico",
                    f"{len(raros)} depto(s) con UF/m² muy distinto al resto del proyecto (posible error de tipeo): "
                    f"{_ejemplos(raros)}", AVISO, "unidades", GRUPO_PLAN))

    # ── Datos del edificio
    fis_labels = [("pisos", "pisos"), ("unidades_totales", "unidades totales"),
                  ("unidades_por_piso", "unidades por piso"), ("estac_totales", "estacionamientos totales"),
                  ("bodegas_totales", "bodegas totales"), ("ascensores", "ascensores")]
    falta_fis = [lbl for k, lbl in fis_labels if _fisico(extra, k) is None]
    if falta_fis:
        add(_it("ficha.fisicos", "Datos físicos incompletos: falta " + ", ".join(falta_fis), CRITICA, "general",
                GRUPO_FICHA, baja_sin_publicar=True))

    # ── Modelos
    modelos = extra.get("modelos") or []
    norm = lambda s: (s or "").strip().lower()
    plantas_ids, plantas_norm = set(), set()
    for im in imagenes:
        cat = (getattr(im, "categoria", None) or "").strip()
        if cat.lower().startswith("jb-planta-"):
            bid = cat[len("jb-planta-"):]
            plantas_ids.add(bid)
            plantas_norm.add(bid.lower())

    def _bid(m):
        b = m.get("_blueprint")
        if isinstance(b, str):
            return b
        if isinstance(b, dict):
            return b.get("id") or b.get("blueprintId")
        return m.get("blueprintId")
    en_uso = {norm(u.modelo) for u in disp if getattr(u, "modelo", None)}
    sin_planta = []
    for m in modelos:
        if not isinstance(m, dict):
            continue
        nombre = m.get("nombre") or m.get("name")
        if not norm(nombre) or m.get("planta_no_disponible"):
            continue
        b = _bid(m)
        if not ((b is not None and b in plantas_ids) or norm(nombre) in plantas_norm
                or m.get("planta_thumb_src") or m.get("plano_url") or m.get("planta_url")):
            sin_planta.append(nombre)
    uso = [n for n in sin_planta if norm(n) in en_uso]
    if uso:
        add(_it("modelos.sin_planta_en_uso", f"{len(uso)} modelo(s) sin planta en uso: {_ejemplos(uso)}", CRITICA,
                "modelos", GRUPO_STOCK))
    fuera = [n for n in sin_planta if norm(n) not in en_uso]
    if fuera:
        add(_it("modelos.sin_planta", f"{len(fuera)} modelo(s) sin planta (no en uso): {_ejemplos(fuera)}", AVISO,
                "modelos", GRUPO_STOCK))
    por_nombre = {norm(m.get("nombre") or m.get("name")) for m in modelos
                  if isinstance(m, dict) and (m.get("nombre") or m.get("name"))}
    huerfanos = [f'{u.numero or "?"} (modelo "{u.modelo}")' for u in deptos
                 if norm(getattr(u, "modelo", None)) and norm(u.modelo) not in por_nombre]
    if huerfanos:
        add(_it("modelos.huerfanos", f"{len(huerfanos)} unidad(es) con modelo que no existe: {_ejemplos(huerfanos)}",
                CRITICA, "modelos", GRUPO_STOCK))
    sin_tipo = [u.numero for u in disp if _vacio(getattr(u, "tipologia", None))]
    if sin_tipo:
        add(_it("unidades.sin_tipologia", f"{len(sin_tipo)} depto(s) sin tipología: {_ejemplos(sin_tipo, 8)}", AVISO,
                "unidades", GRUPO_STOCK))
    dw = extra.get("_deptos_con_warning") or []
    if isinstance(dw, list) and dw and not huerfanos:
        vig = sorted({d.get("modelo") for d in dw if isinstance(d, dict) and d.get("modelo")
                      and norm(d.get("modelo")) not in por_nombre})
        if vig:
            add(_it("modelos.no_registrados", f"{len(vig)} modelo(s) no registrado(s) (robot): {_ejemplos(vig)}",
                    CRITICA, "modelos", GRUPO_STOCK))

    # ── Reserva y operación
    cr = extra.get("cuenta_reserva") or {}
    if isinstance(cr, dict):
        def _cr(*claves):
            for k in claves:
                if not _vacio(cr.get(k)):
                    return cr.get(k)
            return None
        campos = {"titular": _cr("titular_nombre", "nombre"), "RUT del titular": _cr("titular_rut", "rut"),
                  "tipo de cuenta": _cr("tipo_cuenta"), "número de cuenta": _cr("numero_cuenta", "numero"),
                  "banco": _cr("banco")}
        link = _cr("link_pago", "link_pago_online")
        rut_t = campos["RUT del titular"]
        if rut_t is not None and _rut_relleno(rut_t):
            campos["RUT del titular"] = None
        faltan = [k for k, v in campos.items() if v is None]
        if faltan and not link:
            add(_it("reserva.cuenta_incompleta", "Cuenta para la reserva incompleta: falta " + ", ".join(faltan),
                    CRITICA, "general", GRUPO_RESERVA, baja_sin_publicar=True))
        if campos["RUT del titular"] is not None and not rut_valido(campos["RUT del titular"]):
            add(_it("reserva.rut_invalido", f"RUT del titular de la cuenta de reserva inválido ({campos['RUT del titular']})",
                    CRITICA, "general", GRUPO_RESERVA))
    spa = extra.get("spa_proyecto") or {}
    if isinstance(spa, dict):
        def _sp(*claves):
            for k in claves:
                if not _vacio(spa.get(k)):
                    return spa.get(k)
            return None
        s_campos = {"razón social": _sp("nombre", "nombre_spa"), "RUT": _sp("rut", "rut_spa"),
                    "dirección": _sp("direccion", "direccion_spa")}
        if s_campos["RUT"] is not None and _rut_relleno(s_campos["RUT"]):
            s_campos["RUT"] = None
        s_faltan = [k for k, v in s_campos.items() if v is None]
        if s_faltan:
            add(_it("reserva.spa_incompleta", "Datos de la sociedad (SPA) incompletos: falta " + ", ".join(s_faltan),
                    AVISO, "general", GRUPO_RESERVA, baja_sin_publicar=True))
        if s_campos["RUT"] is not None and not rut_valido(s_campos["RUT"]):
            add(_it("reserva.rut_invalido_spa", f"RUT de la sociedad (SPA) inválido ({s_campos['RUT']})", CRITICA,
                    "general", GRUPO_RESERVA))

    # Arriendo garantizado: el valor puede estar en la unidad (arriendo_garantizado +
    # arriendo_moneda), en extra.arriendos[numero] (legado) o por modelo.
    etiquetas = [_norm(e) for e in (extra.get("etiquetas") or []) if isinstance(e, str)]
    con_arriendo = [u for u in deptos if _pos(getattr(u, "arriendo_garantizado", None))]
    arr = extra.get("arriendos") or {}
    legado = bool(isinstance(arr, dict) and any(isinstance(v, dict) and _pos(v.get("valor")) for v in arr.values()))
    por_modelo = bool(isinstance(arr, dict) and any(isinstance(m, dict) and any(_pos(v) for v in m.values())
                                                    for m in (arr.get("modelos") or [])))
    if "arriendo garantizado" in etiquetas and not con_arriendo and not legado and not por_modelo:
        add(_it("arriendo.etiqueta_sin_valores",
                "Dice «Arriendo garantizado» pero ninguna unidad ni modelo tiene el monto", AVISO, "arr",
                GRUPO_RESERVA))
    sin_moneda = [u.numero for u in con_arriendo if _vacio(getattr(u, "arriendo_moneda", None))
                  and 0 < float(u.arriendo_garantizado) < 1000]
    if sin_moneda:
        add(_it("arriendo.sin_moneda",
                f"{len(sin_moneda)} depto(s) con arriendo garantizado sin moneda (¿UF o pesos?): {_ejemplos(sin_moneda)}",
                AVISO, "arr", GRUPO_RESERVA))

    # ── Textos de venta (solo como línea de resumen en el correo)
    if not [x for x in (extra.get("puntos_interes") or []) if isinstance(x, str) and x.strip()]:
        add(_it("textos.sin_info_relevante", "Sin «Información relevante»", AVISO, "general", GRUPO_TEXTOS,
                baja_sin_publicar=True, resumen=True))
    if not [x for x in (extra.get("porque_si") or []) if isinstance(x, str) and x.strip()]:
        add(_it("textos.sin_porque_si", "Sin «Por qué Sí»", AVISO, "general", GRUPO_TEXTOS,
                baja_sin_publicar=True, resumen=True))

    # ── Fichas sin publicar: lo que es "falta completar" baja a aviso
    if not publicado:
        for it in items:
            if it["baja_sin_publicar"] and it["severidad"] == CRITICA:
                it["severidad"] = AVISO
                it["texto"] += " · ficha sin publicar"
    return items


def fallas_seguras(p: Any, hoy: Optional[datetime] = None) -> list:
    """fallas_de_proyecto sin tumbar el correo ni el panel por una ficha con datos raros."""
    try:
        return fallas_de_proyecto(p, hoy)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("fallas_de_proyecto falló para %s", getattr(p, "id", "?"), exc_info=True)
        return [_it("ficha.no_revisable", "No se pudo revisar esta ficha (datos con formato inesperado)", AVISO,
                    "general", GRUPO_FICHA)]
