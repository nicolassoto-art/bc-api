"""Tests de JBImporter._parse_marketplace_unidades (pura, sin red/Playwright/DB).

Datos de entrada calcados del DOM real de /marketplace/workview/{id} para
"Laguna Centro Torre H" (depto 1402), confirmado leyendo el HTML crudo
descargado en la sesión de reconocimiento (scripts/inspect_marketplace_workview.py).
"""
import tempfile
from pathlib import Path

from app.services.jb_importer import JBImporter


def _imp() -> JBImporter:
    return JBImporter(
        jb_email="x@example.com",
        jb_password="pw",
        bc_api_base="http://example.invalid",
        bc_jwt="dummy",
        imports_dir=Path(tempfile.mkdtemp()),
    )


def _card(numero="1402", tipo="1D - 1B", modelo="B", orientacion="SO",
          sup_total="39,56", sup_interior="32,92", sup_terraza="6,64",
          sup_logia="0", sup_jardin="0", precio="3.034 UF",
          descuento="10 %", bono_pie="10 %", precio_final="3.034 UF",
          estac="Opcional", bodega="Opcional", pack="Nunca") -> dict:
    return {
        "numero": numero,
        "fields": {
            "Tipo:": tipo, "Modelo:": modelo,
            "Orientación:": orientacion, "Sup. Total:": sup_total,
            "Sup. Interior:": sup_interior, "Sup. Terraza:": sup_terraza,
            "Sup. Logia:": sup_logia, "Sup. Jardin:": sup_jardin,
        },
        "precio": precio,
        "precioFinal": precio_final,
        "descBono": {"Descuento:": descuento, "Bono Pie:": bono_pie},
        "estac": estac,
        "bodega": bodega,
        "pack": pack,
    }


def test_parsea_card_real_depto_1402():
    imp = _imp()
    out = imp._parse_marketplace_unidades([_card()])
    assert len(out) == 1
    u = out[0]
    assert u["numero"] == "1402"
    assert u["modelo"] == "B"
    assert u["tipologia"] == "1D - 1B"
    assert u["tipo"] == "Depto"
    assert u["orientacion"] == "SO"
    assert u["sup_total"] == 39.56
    assert u["sup_interior"] == 32.92
    assert u["sup_terraza"] == 6.64
    assert u["sup_logia"] == 0
    assert u["sup_jardin"] == 0
    assert u["precio_lista_uf"] == 3034
    assert u["precio_final_uf"] == 3034
    assert u["descuento_pct"] == 10
    assert u["bono_pie_pct"] == 10
    assert u["estac_flag"] == "optional"
    assert u["bodega_flag"] == "optional"
    assert u["pack_flag"] == "never"
    assert u["disponible"] is True


def test_precio_grande_sin_decimales():
    imp = _imp()
    out = imp._parse_marketplace_unidades([_card(precio="12.500 UF", precio_final="11.250 UF")])
    assert out[0]["precio_lista_uf"] == 12500
    assert out[0]["precio_final_uf"] == 11250


def test_flags_obligatorio_y_nunca():
    imp = _imp()
    out = imp._parse_marketplace_unidades([_card(estac="Obligatorio", bodega="Nunca", pack="Opcional")])
    assert out[0]["estac_flag"] == "required"
    assert out[0]["bodega_flag"] == "never"
    assert out[0]["pack_flag"] == "optional"


def test_descarta_cards_sin_numero():
    imp = _imp()
    out = imp._parse_marketplace_unidades([_card(numero="")])
    assert out == []


def test_modelo_faltante_usa_sm():
    imp = _imp()
    card = _card()
    del card["fields"]["Modelo:"]
    out = imp._parse_marketplace_unidades([card])
    assert out[0]["modelo"] == "S/M"


def test_multiples_cards():
    imp = _imp()
    cards = [_card(numero="1402"), _card(numero="2111", modelo="K"), _card(numero="2512", modelo="L")]
    out = imp._parse_marketplace_unidades(cards)
    assert [u["numero"] for u in out] == ["1402", "2111", "2512"]
    assert out[1]["modelo"] == "K"
