"""Fallas de las fichas (correo "fallas en fichas" y panel Pendientes) — 2026-10-05."""
import copy
from datetime import datetime
from types import SimpleNamespace

from app.services.daily_report import _alertas_de_proyecto
from app.services.fallas import CRITICA, AVISO, fallas_de_proyecto, rut_valido

HOY = datetime(2026, 10, 5, 12, 0)


def _u(numero, **kw):
    base = dict(numero=numero, tipo="Depto", tipologia="2D - 1B", modelo="2D1B", disponible=True,
                precio_lista_uf=3000.0, precio_final_uf=2940.0, sup_total=50.0, descuento_pct=None,
                bono_pie_pct=None, arriendo_garantizado=None, arriendo_moneda=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _img(cat, principal=False):
    return SimpleNamespace(categoria=cat, es_principal=principal)


def _doc(tipo):
    return SimpleNamespace(tipo=tipo)


def _ficha(**over):
    """Ficha completa y publicada: no debe tener fallas (salvo lo que se cambie)."""
    extra = {
        "publicar_en_catalogo": True, "gps_verificado": True,
        "comercial": {"pie_pct": 20, "valor_reserva_clp": 100000, "cuotas_pre_entrega": 36,
                      "pago_pre_entrega": "Transferencia", "tipo_pie": "Obligatorio",
                      "tipo_bono_pie": "Todo", "bono_pie_pct": 10, "pago_construccion_pct": 10,
                      "cuoton_inicial_pct": 0, "cuoton_final_pct": 0},
        "pisos": 10, "unidades_totales": 100, "unidades_por_piso": 10, "estac_totales": 50,
        "bodegas_totales": 50, "ascensores": 2,
        "modelos": [{"nombre": "2D1B", "planta_url": "x.png"}],
        "cuenta_reserva": {"titular_nombre": "Inmobiliaria X SpA", "titular_rut": "76.086.428-5",
                           "tipo_cuenta": "Corriente", "numero_cuenta": "123", "banco": "Banco Chile"},
        "spa_proyecto": {"nombre": "X SpA", "rut": "77.389.903-7", "direccion": "Calle 1"},
        "puntos_interes": ["Metro a 2 cuadras"], "porque_si": ["Buena conectividad"],
        "etiquetas": [],
    }
    extra.update(over.pop("extra", {}))
    p = dict(id="p1", nombre="Proyecto Uno", inmobiliaria="Iroyal", comuna="Ñuñoa", direccion="Calle 1",
             region="Metropolitana", fase="Verde", fecha_entrega="Mar 2027", ano_entrega=2027, activo=True,
             foto_principal_url="f.jpg", extra=extra,
             unidades=[_u("101"), _u("102"), _u("103"), _u("104"), _u("105")],
             imagenes=[_img("fachada", True), _img("Interior")], documentos=[_doc("Brochure")])
    p.update(over)
    return SimpleNamespace(**p)


def _codigos(p):
    return {it["codigo"]: it for it in fallas_de_proyecto(p, HOY)}


def test_ficha_completa_sin_fallas():
    assert _codigos(_ficha()) == {}


def test_rut():
    assert rut_valido("77.389.903-7") and not rut_valido("77.389.903-8")
    assert rut_valido("10.000.013-K") and rut_valido("10000013k")
    assert not rut_valido("1-9") and not rut_valido("")


def test_pie_no_cuadra_y_casos_que_no_aplican():
    p = _ficha()
    p.extra["comercial"]["pago_construccion_pct"] = 5   # 20 ≠ 0+5+0+10
    it = _codigos(p)["plan.pie_no_cuadra"]
    assert it["severidad"] == CRITICA and "falta 5%" in it["texto"]
    # Sin "construcción" guardada (fichas importadas o viejas): no se evalúa.
    p = _ficha()
    p.extra["comercial"].pop("pago_construccion_pct")
    assert "plan.pie_no_cuadra" not in _codigos(p)
    # Cuotón en UF no entra a la suma.
    p = _ficha()
    p.extra["comercial"].update({"pago_construccion_pct": 5, "cuoton_inicial_uf": 100, "cuoton_inicial_pct": 5})
    assert "plan.pie_no_cuadra" in _codigos(p)
    p.extra["comercial"].update({"cuoton_inicial_uf": None, "cuoton_inicial_pct": 5})
    assert "plan.pie_no_cuadra" not in _codigos(p)          # 20 = 5+5+0+10


def test_plan_lee_formas_pago_pie_del_importador():
    p = _ficha()
    com = p.extra.pop("comercial")
    p.extra["formas_pago_pie"] = {k: com[k] for k in ("cuotas_pre_entrega", "pago_pre_entrega")}
    p.extra["comercial"] = {k: v for k, v in com.items() if k not in ("cuotas_pre_entrega", "pago_pre_entrega")}
    assert "plan.incompleto" not in _codigos(p) and "plan.forma_pago" not in _codigos(p)
    # Las reglas de siempre (informe de las 09:00) no se tocaron: ellas sí lo marcan.
    legado = _alertas_de_proyecto(SimpleNamespace(
        nombre="x", inmobiliaria="y", comuna="z", direccion="d", region="r", fase="Verde",
        fecha_entrega="2027", ano_entrega=2027, foto_principal_url="f", extra=p.extra,
        unidades=p.unidades, imagenes=p.imagenes))
    assert any(c.startswith("Plan de pago incompleto") for c in legado["criticos"])


def test_fisicos_aceptan_extra_fisicos():
    p = _ficha()
    for k in ("pisos", "estac_totales"):
        p.extra.pop(k)
    p.extra["fisicos"] = {"pisos": 9, "estacionamientos_totales": 40}
    assert "ficha.fisicos" not in _codigos(p)


def test_bono_cero_solo_si_la_ficha_ofrece_bono():
    p = _ficha(unidades=[_u("101", bono_pie_pct=0), _u("102"), _u("103"), _u("104"), _u("105")])
    it = _codigos(p)["precios.bono_unidad_cero"]
    assert it["severidad"] == AVISO and "101" in it["texto"]
    for tipo in ("No", "Distinto por depto"):
        q = copy.deepcopy(p)
        q.extra["comercial"]["tipo_bono_pie"] = tipo
        assert "precios.bono_unidad_cero" not in _codigos(q)
    q = copy.deepcopy(p)
    q.extra["comercial"]["tipo_bono_pie"] = "Solo Unidad"  # alcance, no "todos tienen"
    assert "precios.bono_unidad_cero" in _codigos(q)
    q = copy.deepcopy(p)
    q.inmobiliaria = "EuroInmobiliaria"
    assert "reparación de Euro" in _codigos(q)["precios.bono_unidad_cero"]["texto"]


def test_precios():
    p = _ficha(unidades=[_u("101", precio_final_uf=3100.0), _u("102", precio_lista_uf=None),
                         _u("103", sup_total=None), _u("104", precio_lista_uf=None, precio_final_uf=None),
                         _u("105", bono_pie_pct=25), _u("106", descuento_pct=120),
                         _u("E-1", tipo="Estacionamiento", precio_lista_uf=None, precio_final_uf=None)])
    c = _codigos(p)
    assert "101" in c["precios.final_mayor_lista"]["texto"]
    assert "102" in c["precios.sin_precio_lista"]["texto"]
    assert "103" in c["precios.sin_superficie"]["texto"]
    assert "104" in c["precios.sin_precio"]["texto"] and "E-1" not in c["precios.sin_precio"]["texto"]
    assert "105" in c["precios.bono_mayor_pie"]["texto"]
    assert "106" in c["precios.pct_fuera_rango"]["texto"]


def test_uf_m2_atipico():
    us = [_u(str(100 + i)) for i in range(6)] + [_u("999", precio_lista_uf=300.0)]
    assert "999" in _codigos(_ficha(unidades=us))["precios.uf_m2_atipico"]["texto"]


def test_inmobiliaria_placeholder_y_vacia():
    assert _codigos(_ficha(inmobiliaria="Sin asignar."))["ficha.inmobiliaria"]["texto"].startswith("Inmobiliaria sin asignar")
    assert _codigos(_ficha(inmobiliaria="Big Capital"))["ficha.inmobiliaria"]["severidad"] == CRITICA
    assert _codigos(_ficha(inmobiliaria=""))["ficha.inmobiliaria"]["texto"] == "Sin inmobiliaria"


def test_etapa_vs_entrega():
    assert "ficha.etapa_vs_entrega" in _codigos(_ficha(fase="Entrega Inmediata", ano_entrega=2028))
    assert "ficha.etapa_vs_entrega" in _codigos(_ficha(fase="En Verde", ano_entrega=2024, fecha_entrega="2024"))
    assert "ficha.etapa_vs_entrega" in _codigos(_ficha(fase="Verde", ano_entrega=None, fecha_entrega="Inmediata"))
    assert "ficha.etapa_vs_entrega" not in _codigos(_ficha(fase="Obra Gruesa", ano_entrega=2027))
    assert "ficha.etapa_vs_entrega" not in _codigos(_ficha(fase="Venta privada", ano_entrega=2020))
    assert "ficha.etapa_vs_entrega" not in _codigos(_ficha(fase="Terminado", ano_entrega=None, fecha_entrega="Mar 2026"))


def test_documentos_y_galeria():
    c = _codigos(_ficha(documentos=[_doc("Planos")]))
    assert "cambia el tipo" in c["material.sin_documento_publico"]["texto"]
    c = _codigos(_ficha(documentos=[], imagenes=[_img("fachada", True), _img("jb-doc-1")]))
    assert "quedó como imagen" in c["material.sin_documento_publico"]["texto"]
    assert "material.sin_galeria" in c
    c = _codigos(_ficha(foto_principal_url=None, imagenes=[_img("jb-planta-x")]))
    assert "material.sin_fachada" in c and "material.sin_galeria" not in c


def test_reserva_y_spa():
    p = _ficha()
    p.extra["cuenta_reserva"] = {"nombre": "X", "rut": "76.086.428-5", "tipo_cuenta": "Corriente",
                                 "numero": "1", "banco": "B"}            # claves antiguas
    assert "reserva.cuenta_incompleta" not in _codigos(p)
    p.extra["cuenta_reserva"] = {"banco": "B"}
    assert "reserva.cuenta_incompleta" in _codigos(p)
    p.extra["cuenta_reserva"] = {"banco": "B", "link_pago": "https://pago"}
    assert "reserva.cuenta_incompleta" not in _codigos(p)                 # con link de pago basta
    p = _ficha()
    p.extra["cuenta_reserva"]["titular_rut"] = "76.086.428-6"
    assert "reserva.rut_invalido" in _codigos(p)
    p = _ficha()
    p.extra["cuenta_reserva"]["titular_rut"] = "11.111.111-1"             # relleno = incompleta
    assert "reserva.cuenta_incompleta" in _codigos(p)
    p = _ficha()
    p.extra["spa_proyecto"] = {"nombre_spa": "X", "rut_spa": "77.389.903-7"}
    assert "dirección" in _codigos(p)["reserva.spa_incompleta"]["texto"]


def test_arriendo():
    p = _ficha()
    p.extra["etiquetas"] = ["Arriendo garantizado"]
    assert "arriendo.etiqueta_sin_valores" in _codigos(p)
    p.unidades[0].arriendo_garantizado = 12.5
    c = _codigos(p)
    assert "arriendo.etiqueta_sin_valores" not in c and "101" in c["arriendo.sin_moneda"]["texto"]
    p.unidades[0].arriendo_garantizado = 350000                           # pesos sin moneda: no se duda
    assert "arriendo.sin_moneda" not in _codigos(p)


def test_textos_de_venta_son_solo_resumen():
    p = _ficha()
    p.extra["puntos_interes"] = []
    it = _codigos(p)["textos.sin_info_relevante"]
    assert it["resumen"] is True and it["severidad"] == AVISO


def test_ficha_sin_publicar_baja_a_aviso_lo_que_falta_completar():
    p = _ficha()
    p.extra["publicar_en_catalogo"] = False
    p.extra["comercial"]["tipo_pie"] = ""
    p.extra["comercial"]["pago_construccion_pct"] = 5
    c = _codigos(p)
    assert c["plan.incompleto"]["severidad"] == AVISO and c["plan.incompleto"]["texto"].endswith("ficha sin publicar")
    assert c["plan.pie_no_cuadra"]["severidad"] == CRITICA  # cuadrar el pie no es "falta completar"


def test_pestanas_validas():
    tabs = {"general", "documentos", "modelos", "unidades", "bodegas", "estac", "packs", "local", "arr",
            "notas", "timeline", "stock", "fotos"}
    p = _ficha(inmobiliaria="", comuna="", foto_principal_url=None, imagenes=[], documentos=[],
               unidades=[_u("101", precio_lista_uf=None, precio_final_uf=None, sup_total=None, modelo="X")])
    p.extra.update({"gps_verificado": False, "cuenta_reserva": {}, "spa_proyecto": {}, "puntos_interes": []})
    for it in fallas_de_proyecto(p, HOY):
        assert it["tab"] in tabs, it
