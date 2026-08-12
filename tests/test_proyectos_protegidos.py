"""Guard de proyectos protegidos del import JetBrokers.

Contexto (2026-08-12): la lista de protegidos existía SOLO en scripts/import_detail.py
(un script suelto). El servicio real -- app/services/jb_importer.py :: JBImporter.run(),
que es el que usan import-jb.yml, reimport-todos-84.yml y batch-import-jb.yml -- no la
consultaba, así que en la práctica no protegía nada: un reimport masivo habría hecho wipe
del stock de AJ Urbana (que viene del Excel de Drive) y de los proyectos de marketplace
migrados a SBC con mantención manual.
"""
import os

import pytest

from app.services.jb_importer import PROYECTOS_PROTEGIDOS, _es_protegido


@pytest.fixture(autouse=True)
def _sin_forzado(monkeypatch):
    """Ningún test debe depender de un FORCE_* heredado del entorno."""
    monkeypatch.delenv("FORCE_IMPORT", raising=False)
    monkeypatch.delenv("FORCE_AJ", raising=False)


def test_proyecto_normal_no_esta_protegido():
    assert _es_protegido("jb-iquforoo") is False
    assert _es_protegido("cordillera-oriente-etapa-1") is False


def test_aj_urbana_protegida():
    # Su stock viene del sync del Excel de Drive, no de JB.
    assert _es_protegido("monjitas-690") is True
    assert _es_protegido("edificio-teatinos-750") is True


def test_marketplace_migrado_a_sbc_protegido():
    # Aviador Acevedo pasó de SJB a SBC el 2026-08-12 y quedó desconectado de JB.
    assert _es_protegido("jb-1zvx7adn") is True


@pytest.mark.parametrize("valor", ["1", "true", "TRUE", "yes", "si", "sí"])
def test_force_import_permite_sobrescribir(monkeypatch, valor):
    monkeypatch.setenv("FORCE_IMPORT", valor)
    assert _es_protegido("monjitas-690") is False


def test_force_aj_historico_sigue_funcionando(monkeypatch):
    # Compat: el escape hatch viejo documentado en import_detail.py.
    monkeypatch.setenv("FORCE_AJ", "1")
    assert _es_protegido("monjitas-690") is False


@pytest.mark.parametrize("valor", ["", "0", "false", "no", "quizas"])
def test_valores_que_no_fuerzan(monkeypatch, valor):
    monkeypatch.setenv("FORCE_IMPORT", valor)
    assert _es_protegido("monjitas-690") is True


def test_lista_no_vacia_y_sin_none():
    assert PROYECTOS_PROTEGIDOS, "la lista de protegidos no puede quedar vacía"
    assert all(isinstance(p, str) and p.strip() for p in PROYECTOS_PROTEGIDOS)


def test_import_detail_usa_la_misma_lista():
    """El script suelto no debe re-declarar su propia lista (se desincronizaría)."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", "import_detail.py")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    assert "_es_protegido" in src, "import_detail.py debe usar el guard compartido"
    assert "AJ_PROTEGIDOS = {" not in src, "no debe re-declarar la lista localmente"
