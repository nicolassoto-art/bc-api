"""Armado de Laguna Centro Torre H como stock propio desde datos ya guardados (sin red).

Regla de Nicolás (12-nov-2026): nada se pide directo a *.jetbrokers.io; las imágenes
solo por nuestro Worker (/api/img).
"""
import csv
import io
import json
from pathlib import Path

import openpyxl

from app.routes.unidades import HEADERS
from app.schemas.proyecto import PlanPago, ProyectoIn
from scripts.proyecto_propio.armar import (
    armar_excel_unidades, armar_proyecto, es_url_nuestra, lista_documentos,
    lista_imagenes, modelos, plan_pago, url_nuestra,
)

D = Path(__file__).resolve().parents[1] / "scripts/data/laguna_centro_torre_h"
FICHA = json.loads((D / "ficha.json").read_text(encoding="utf-8"))
FILAS = list(csv.DictReader((D / "unidades.csv").open(encoding="utf-8-sig"), delimiter=";"))


def test_proyecto_ids_y_datos():
    p = armar_proyecto(FICHA)
    ProyectoIn(**p)  # valida contra el esquema real
    assert p["id"] == "jb-iquforoo" and p["nombre"] == "Laguna Centro Torre H"
    assert p["inmobiliaria"] == "Vitalia" and p["comuna"] == "Macul"
    assert p["direccion"] == "Avenida Quilín 155" and p["fase"] == "Entrega inmediata"
    e = p["extra"]
    assert e["jb_id"] == "IquFoRoO" and not e.get("external_id")
    assert e["publicar_en_catalogo"] is True
    assert e["pisos"] == 25 and e["unidades_totales"] == 344 and e["ascensores"] == 4
    assert len(e["modelos"]) == 25
    c = e["comercial"]
    assert c["valor_reserva_clp"] == 250000 and c["tipo_reserva"] == "Gastos operacionales"
    assert c["valor_cuota_clp"] == 600000
    assert "planes_pago" not in c
    assert "378 UF" in e["notas_text"] and "70 UF" in e["notas_text"]


def test_plan_pago_cuadra_y_valida():
    pp = plan_pago()
    PlanPago(**pp)
    assert pp["pie_pct"] == pp["cuoton_inicial_pct"] + pp["pago_construccion_pct"] \
        + pp["cuoton_final_pct"] + pp["bono_pie_pct"] == 20
    assert pp["cuotas_pre_entrega"] == 1 and pp["cuotas_post_entrega"] == 12


def test_excel_unidades_formato_bc_api():
    ws = openpyxl.load_workbook(io.BytesIO(armar_excel_unidades(FILAS))).active
    assert [c.value for c in ws[1]] == HEADERS
    filas = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(filas) == 83
    r = dict(zip(HEADERS, next(f for f in filas if f[0] == "1512")))
    assert r["precio_lista_uf"] == 2955 and r["descuento_pct"] == 10 and r["bono_pie_pct"] == 10
    assert r["precio_final_uf"] in (None, "")  # bc-api lo calcula: lista × (1 − descuento)
    assert r["sup_total"] == 39.23 and r["tipologia"] == "1D - 1B"
    assert r["estac_flag"] == "optional" and r["bodega_flag"] == "optional"


def test_imagenes_y_documentos():
    imgs = lista_imagenes(FICHA)
    assert len(imgs) == 39  # portada + 38 fotos; los 2 PDF van como documentos
    assert [i["categoria"] for i in imgs if i["es_principal"]] == ["cover"]
    assert {i["categoria"] for i in imgs} == {
        "cover", "jb-foto", "jb-foto-areas-comunes", "jb-foto-entorno"}
    assert sorted(d["tipo"] for d in lista_documentos(FICHA)) == ["Brochure", "Plano"]


def test_solo_direcciones_de_nuestro_worker():
    u = url_nuestra("wPrMYtB8")
    assert es_url_nuestra(u)
    assert not es_url_nuestra("https://jetgallery.jetbrokers.io/api/gallery/download/uv13koru/wPrMYtB8")
    assert not es_url_nuestra("https://api.jetbrokers.io/x")
    assert not es_url_nuestra("http://bigcapital-worker.nsotofchile.workers.dev/api/img?url=x")
    for i in lista_imagenes(FICHA) + lista_documentos(FICHA):
        assert es_url_nuestra(url_nuestra(i["file_id"]))


def test_modelos():
    m = modelos(FICHA)
    assert len(m) == 25 and all(x["blueprint_id"] for x in m)
    assert sum(x["disponibles"] for x in m) == 83
    assert len({x["id"] for x in m}) == 25
