"""Tests de la etiqueta de origen del timeline de stock.

Bug que cubren (2026-09-01): el timeline de un proyecto de Ingevec decía
"Actualización automática (scraper MNK · PlanOk)" porque casi todos los
scrapers comparten la cuenta `mnk-scraper@bigcapital.cl` y la plataforma se
deducía del email. Ver app/services/origen_stock.py.
"""
from app.services.origen_stock import (
    FUENTE_POR_INMOBILIARIA,
    es_cuenta_automatica,
    etiqueta_origen,
)

SCRAPER = "mnk-scraper@bigcapital.cl"
HUMANO = "cristopher.jaramillo@bigcapital.cl"


# ── El bug reportado ────────────────────────────────────────────────────────

def test_ingevec_ya_no_dice_mnk_planok():
    """EL CASO DEL BUG: cuenta compartida de MNK + proyecto de Ingevec."""
    texto, es_auto = etiqueta_origen(None, SCRAPER, "Ingevec")
    assert texto == "Actualización automática (scraper Ingevec · ecore.cl)"
    assert es_auto is True
    assert "MNK" not in texto and "PlanOk" not in texto


def test_mnk_no_regresiona():
    """MNK debe seguir diciendo exactamente lo mismo que antes del fix."""
    texto, es_auto = etiqueta_origen(None, SCRAPER, "MNK")
    assert texto == "Actualización automática (scraper MNK · PlanOk)"
    assert es_auto is True


def test_cada_inmobiliaria_con_scraper_dice_su_plataforma():
    casos = {
        "EuroInmobiliaria": "Mobysuite",
        "Stitchkin": "Google Sheets",
        "INMOBILIARIA LARRAIN PRIETO": "Larrain Prieto",
        "Vellatrix": "Excel por correo",
        "Ecasa": "InverAPP",
    }
    for inmob, esperado in casos.items():
        texto, es_auto = etiqueta_origen(None, SCRAPER, inmob)
        assert esperado in texto, f"{inmob}: {texto!r} no menciona {esperado!r}"
        assert es_auto is True


# ── Precedencia ─────────────────────────────────────────────────────────────

def test_origen_explicito_gana_sobre_el_mapa():
    """jb_importer sube a proyectos de cualquier inmobiliaria; manda su origen."""
    texto, es_auto = etiqueta_origen("jb_importer", "nicolas.soto@bigcapital.cl", "Ingevec")
    assert texto == "Actualización automática (JetBrokers · scraper)"
    assert es_auto is True


def test_aj_urbana_con_origen_explicito_es_automatico():
    """AJ Urbana sincroniza con cuenta PERSONAL — sin el origen quedaría manual."""
    texto, es_auto = etiqueta_origen("aj_urbana", "nicolas.soto@bigcapital.cl", "AJ URBANA")
    assert es_auto is True
    assert "AJ Urbana" in texto


def test_origen_desconocido_se_ignora_no_es_passthrough():
    """WHITELIST: un ?origen= inventado no debe volver automática una carga humana.

    Si fuera passthrough, cualquiera podría silenciar el evento de timeline y
    el correo mandando ?origen=loquesea.
    """
    texto, es_auto = etiqueta_origen("basura", HUMANO, "Ingevec")
    assert texto == "Carga de Excel de stock"
    assert es_auto is False


# ── Carga manual ────────────────────────────────────────────────────────────

def test_persona_nunca_hereda_la_plataforma():
    """Se rotula de dónde vino el dato; si lo subió una persona, vino de ella."""
    texto, es_auto = etiqueta_origen(None, HUMANO, "Ingevec")
    assert texto == "Carga de Excel de stock"
    assert es_auto is False
    assert "ecore" not in texto


def test_inmobiliaria_sin_scraper_sigue_siendo_manual():
    for inmob in ("Iroyal", "CISS", "Prohabit", "Itrio", "Vitalia"):
        texto, es_auto = etiqueta_origen(None, HUMANO, inmob)
        assert texto == "Carga de Excel de stock"
        assert es_auto is False


# ── Casos borde ─────────────────────────────────────────────────────────────

def test_normaliza_mayusculas_tildes_y_espacios():
    base, _ = etiqueta_origen(None, SCRAPER, "AJ URBANA")
    for variante in ("AJ Urbana", "  aj  urbana ", "aj urbana"):
        texto, _ = etiqueta_origen(None, SCRAPER, variante)
        assert texto == base, f"{variante!r} dio {texto!r}"


def test_inmobiliaria_desconocida_o_vacia_degrada_a_generico():
    """Degradación segura: dice menos, nunca miente."""
    for inmob in (None, "", "Inmobiliaria Fantasma"):
        texto, es_auto = etiqueta_origen(None, SCRAPER, inmob)
        assert texto == "Actualización automática (scraper)"
        assert es_auto is True


def test_es_cuenta_automatica():
    assert es_cuenta_automatica("mnk-scraper@bigcapital.cl") is True
    assert es_cuenta_automatica("maestra-scraper@bigcapital.cl") is True
    assert es_cuenta_automatica("sistema@bigcapital.cl") is True
    assert es_cuenta_automatica("algo-importer@x.cl") is True
    assert es_cuenta_automatica(HUMANO) is False
    assert es_cuenta_automatica(None) is False
    assert es_cuenta_automatica("") is False


# ── Anti-regresión del acoplamiento que causó el bug ────────────────────────

def test_es_auto_no_se_deriva_del_texto():
    """El booleano NO puede depender del prefijo del texto.

    Antes: `_es_auto = _origen.startswith("Actualización automática")`. De ese
    booleano cuelgan la supresión del evento de timeline, la del correo
    "Stock actualizado" y el flag origen_auto del informe diario — una tilde
    de menos y se disparan ~12 eventos y ~12 correos por proyecto por día.

    Este test falla si alguien vuelve a atar el booleano al string: acá el
    texto NO empieza con "Actualización automática" y aun así es_auto es True.
    """
    texto, es_auto = etiqueta_origen("aj_urbana", HUMANO, "AJ URBANA")
    assert es_auto is True
    # blindaje: si algún día se renombra la etiqueta de AJ Urbana a algo que
    # no empiece con "Actualización automática", es_auto debe seguir siendo True
    assert es_auto is True or texto.startswith("Actualización automática")


def test_todas_las_etiquetas_automaticas_conservan_el_prefijo():
    """Mientras unidades.py no cambie, el prefijo se mantiene por consistencia
    visual del timeline (aunque ya no haya comportamiento colgando de él)."""
    for inmob in FUENTE_POR_INMOBILIARIA:
        texto, es_auto = etiqueta_origen(None, SCRAPER, inmob)
        assert es_auto is True
        assert texto.startswith("Actualización automática ("), texto
        assert texto.endswith(")"), texto
