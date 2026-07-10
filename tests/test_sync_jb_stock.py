"""Tests de la guardia anti-baja-masiva de scripts/sync_jb_stock.py (pura, sin red/DB).

Replica el incidente real documentado en el CLAUDE.md de MNK ("Guarda anti-baja-masiva
en sync_jetbroker", 2026-06-10): un Excel con Torre 2 vacía por throttle habría marcado
58 deptos reales como vendidos. /excel/upload de bc-api no chequea esto server-side
(confirmado leyendo app/routes/unidades.py) — la guardia vive acá, cliente-side.
"""
import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "sync_jb_stock", Path(__file__).resolve().parent.parent / "scripts" / "sync_jb_stock.py"
)
sync_jb_stock = importlib.util.module_from_spec(_SPEC)
sys.modules["sync_jb_stock"] = sync_jb_stock
_SPEC.loader.exec_module(sync_jb_stock)

check_baja_masiva = sync_jb_stock.check_baja_masiva


def _unidad(numero, tipo="Depto", disponible=True):
    return {"numero": numero, "tipo": tipo, "disponible": disponible}


def test_sin_deptos_previos_no_aborta():
    abortar, motivo = check_baja_masiva(set(), [])
    assert not abortar
    assert "nada que resguardar" in motivo


def test_delta_chico_no_aborta():
    actuales = [_unidad(str(i)) for i in range(1, 11)]  # 10 deptos disponibles
    excel = {str(i) for i in range(1, 10)}  # falta 1 → 10% baja
    abortar, _ = check_baja_masiva(excel, actuales)
    assert not abortar


def test_baja_masiva_aborta():
    # Estilo Cordillera Oriente: 86 disponibles, Excel solo trae 28 (Torre 2 vacía)
    actuales = [_unidad(str(i)) for i in range(1, 87)]
    excel = {str(i) for i in range(1, 29)}
    abortar, motivo = check_baja_masiva(excel, actuales)
    assert abortar
    assert "BAJA MASIVA" in motivo


def test_baja_bajo_piso_absoluto_no_aborta():
    # Proyecto chico (estilo Pinar I): 9 deptos, baja de 5 = 56% pero 5 < piso absoluto (8)
    actuales = [_unidad(str(i)) for i in range(1, 10)]
    excel = {str(i) for i in range(1, 5)}
    abortar, _ = check_baja_masiva(excel, actuales)
    assert not abortar


def test_baja_bajo_piso_porcentual_no_aborta():
    # Proyecto grande: baja de 10 (>= piso absoluto) pero solo 10% del total
    actuales = [_unidad(str(i)) for i in range(1, 101)]
    excel = {str(i) for i in range(1, 91)}
    abortar, _ = check_baja_masiva(excel, actuales)
    assert not abortar


def test_ignora_no_disponibles_y_no_deptos():
    actuales = [
        _unidad("1", disponible=True),
        _unidad("2", disponible=False),  # ya vendido, no cuenta para el delta
        {"numero": "E-1", "tipo": "Estacionamiento", "disponible": True},  # no es depto
    ]
    excel = set()  # excel sin deptos
    abortar, _ = check_baja_masiva(excel, actuales)
    # solo 1 depto disponible real cuenta; baja de 1 < piso absoluto de 8
    assert not abortar


def test_baja_total_pequena_aborta_si_supera_ambos_pisos():
    actuales = [_unidad(str(i)) for i in range(1, 21)]  # 20 disponibles
    excel = {str(i) for i in range(1, 11)}  # baja de 10 (50%, >= piso abs 8)
    abortar, motivo = check_baja_masiva(excel, actuales)
    assert abortar
    assert "10/20" in motivo
