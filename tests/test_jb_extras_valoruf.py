"""Estacionamientos y bodegas con «ValorUF» / «Sup Total» (Excel de Ingevec) — 2026-11-06.

El Excel de Ingevec nombra el precio de estacionamientos y bodegas «ValorUF» y la superficie
«Sup Total» (los nombres de la hoja UNIDAD de la propia plantilla), mientras los demás robots
usan «PrecioUF» y «Superficie». `_build_jb_extras` solo leía estos últimos, así que en 22
proyectos de Ingevec extra.estacionamientos / extra.bodegas quedaban con precio_uf=None: el
asesor veía «—» y la cotización sumaba 0 UF (Tocornal: 43 estac a 364,57 UF, 9 bodegas a
99,13 UF). Regla: «PrecioUF»/«Superficie» mandan; los otros nombres solo se usan si faltan.
"""
import copy
import uuid

from app.models import Proyecto
from app.routes.unidades import _build_jb_extras

from tests.test_precio_sin_iva import _excel, _subir, _proyecto

NOMBRE = "Prueba Interna"


def test_ingevec_valoruf_y_sup_total_llegan_al_precio_y_superficie():
    estac = [{"Número": "2", "ValorUF": 364.57, "Nivel": "-1", "Tipo": None, "Disponible": True}]
    bod = [{"Número": "8", "ValorUF": 99.13, "Sup Total": 4.71, "Disponible": True}]
    out = _build_jb_extras(copy.deepcopy(estac), copy.deepcopy(bod))
    assert out["estacionamientos"][0]["precio_uf"] == 364.57
    assert out["bodegas"][0]["precio_uf"] == 99.13
    assert out["bodegas"][0]["superficie"] == 4.71
    # lo crudo queda intacto (diagnóstico)
    assert out["_estacionamientos_dom"] == estac and out["_bodegas_dom"] == bod


def test_precio_uf_y_superficie_mandan_si_vienen_los_dos_nombres():
    estac = [{"Número": "E-1A", "PrecioUF": 300, "ValorUF": 999}]
    bod = [{"Número": "B-1A", "PrecioUF": 80, "ValorUF": 999, "Superficie": 3.5, "Sup Total": 99}]
    out = _build_jb_extras(estac, bod)
    assert out["estacionamientos"][0]["precio_uf"] == 300.0
    assert out["bodegas"][0]["precio_uf"] == 80.0 and out["bodegas"][0]["superficie"] == 3.5


def test_precio_uf_vacio_usa_valoruf_y_sin_ninguno_queda_none():
    estac = [{"Número": "1", "PrecioUF": None, "ValorUF": 210}, {"Número": "2", "PrecioUF": ""},
             {"Número": "3"}]
    out = _build_jb_extras(estac, [])
    assert [e["precio_uf"] for e in out["estacionamientos"]] == [210.0, None, None]


def test_pack_suma_con_valoruf():
    estac = [{"Número": "36", "ValorUF": 300, "Pack Número": "G1"}]
    bod = [{"Número": "30", "ValorUF": 100, "Pack Número": "G1"}]
    out = _build_jb_extras(estac, bod)
    assert out["packs"][0]["precio_uf"] == 400.0


def test_subida_de_excel_estilo_ingevec_deja_precio_para_el_asesor(client, admin, db):
    _, h = admin
    pid = f"test-valoruf-{uuid.uuid4().hex[:8]}"
    db.add(Proyecto(id=pid, nombre=f"{NOMBRE} {pid}", inmobiliaria="Ingevec", extra={}))
    db.commit()
    xlsx = _excel([["101", "A1", 3000]], estac=[["2", 364.57]], bodegas=[["8", 99.13, 4.71]],
                  cols_sec=("Número", "ValorUF", "Sup Total"))
    _subir(client, h, pid, xlsx)
    p = _proyecto(db, pid)
    assert p.extra["estacionamientos"][0]["precio_uf"] == 364.57
    assert p.extra["bodegas"][0]["precio_uf"] == 99.13
    assert p.extra["bodegas"][0]["superficie"] == 4.71
