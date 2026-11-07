"""«PlanOk manda»: marca de reserva provisoria — 2026-11-06.

Los 10 escenarios del plan (Task 5b, majestic-crafting-pine.md) más las marcas puestas
antes del cambio (44C, 54D, 18D). La lectura horaria de PlanOk es el Excel que sube el
scraper: «viene en el Excel» = PlanOk la ofrece; «no viene» = PlanOk ya no la ofrece.
"""
from datetime import datetime, timedelta

from app.models import Proyecto, Unidad

from tests.test_reserva_bc import XLSX, _excel, _marcar, _pid, _proyecto_con, _subir, _unidad


def _envejecer(db, pid, numero, horas=0.0, vista_min=None):
    """Mueve hacia atrás la hora de la marca y, si se pide, la de la 1ª vista disponible."""
    u = _unidad(db, pid, numero)
    ahora = datetime.utcnow()
    if horas:
        u.reserva_bc_at = ahora - timedelta(hours=horas)
    if vista_min is not None:
        u.reserva_bc_vista_disponible_at = ahora - timedelta(minutes=vista_min)
    db.commit()


def _eventos(db, pid, tipo="Reserva PlanOk"):
    db.expire_all()
    proy = db.query(Proyecto).filter(Proyecto.id == pid).one()
    return [e["detalles"] for e in (proy.extra or {}).get("timeline", []) if e.get("tipo") == tipo]


def _reservar(client, h, pid, numero="101", res="RES-1"):
    r = _marcar(client, h, pid, f"{pid}-{numero}", reserva_bc=res)
    assert r.status_code == 200, r.text
    return r.json()["unidad"]


# ── Poner la marca ────────────────────────────────────────────────────────────

def test_marcar_deja_la_reserva_provisoria_y_la_expone(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    fila = _reservar(client, h, pid)
    assert fila["reserva_bc_estado"] == "provisoria"
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "provisoria" and u.reserva_bc_at is not None
    r = client.get(f"/proyectos/{pid}/unidades", headers=h)
    assert next(x for x in r.json() if x["numero"] == "101")["reserva_bc_estado"] == "provisoria"


# ── Escenario 1: el robot la toma ─────────────────────────────────────────────

def test_1_excel_sin_la_unidad_la_confirma(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid)
    _subir(client, h, pid, ["102"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False
    assert u.reserva_bc == "RES-1"
    assert _eventos(db, pid) == ["101: reserva tomada en PlanOk (RES-1), sigue fuera del catálogo"]
    # Una 2ª subida igual no repite el evento.
    _subir(client, h, pid, ["102"])
    assert len(_eventos(db, pid)) == 1


# ── Escenario 2: el robot no puede, menos de 24 h ─────────────────────────────

def test_2_provisoria_menor_a_24h_sigue_oculta(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=23)
    _subir(client, h, pid, ["101"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "provisoria" and u.disponible is False
    assert _eventos(db, pid) == []


# ── Escenario 3: 24 h y nadie la tomó ─────────────────────────────────────────

def test_3_provisoria_mayor_a_24h_reaparece_como_no_tomada(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid, res="RES-3")
    _envejecer(db, pid, "101", horas=25)
    _subir(client, h, pid, ["101"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "no_tomada" and u.disponible is True
    assert u.reserva_bc == "RES-3"  # la marca nunca se borra sola
    assert _eventos(db, pid) == [
        "101: reserva no tomada en PlanOk en 24 h (RES-3), vuelve a estar disponible"]
    # Se mantiene así en las subidas siguientes, sin repetir el evento.
    _subir(client, h, pid, ["101"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "no_tomada" and u.disponible is True
    assert len(_eventos(db, pid)) == 1


# ── Escenario 4: estaba tomada y PlanOk la suelta ─────────────────────────────

def test_4_confirmada_que_vuelve_dos_subidas_seguidas_queda_caida(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid, res="RES-44")
    _subir(client, h, pid, ["102"])               # el robot la tomó
    assert _unidad(db, pid, "101").reserva_bc_estado == "confirmada"
    _subir(client, h, pid, ["101", "102"])         # 1ª vez que PlanOk la ofrece
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False
    assert u.reserva_bc_vista_disponible_at is not None
    _envejecer(db, pid, "101", vista_min=55)       # la pasada siguiente, ~1 h después
    _subir(client, h, pid, ["101", "102"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "caida" and u.disponible is True
    assert u.reserva_bc == "RES-44"
    assert _eventos(db, pid)[0] == "101: reserva caída en PlanOk (RES-44), vuelve a estar disponible"


def test_4_una_sola_bajada_rara_no_la_suelta(client, admin, db):
    """Ofrecida → no ofrecida → ofrecida: el conteo vuelve a empezar."""
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid)
    _subir(client, h, pid, ["102"])
    _subir(client, h, pid, ["101", "102"])
    _envejecer(db, pid, "101", vista_min=55)
    _subir(client, h, pid, ["102"])               # PlanOk la vuelve a tomar
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_vista_disponible_at is None and u.reserva_bc_estado == "confirmada"
    _subir(client, h, pid, ["101", "102"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False


def test_4_reintento_inmediato_de_la_misma_subida_no_cuenta_doble(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid)
    _subir(client, h, pid, ["102"])
    _subir(client, h, pid, ["101", "102"])
    _subir(client, h, pid, ["101", "102"])         # reenvío segundos después (502 → reintento)
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False


# ── Escenario 5: otra corredora la toma antes ─────────────────────────────────

def test_5_tomada_por_otro_sigue_oculta(client, admin, db):
    """PlanOk ya no la ofrece (aunque no sea nuestra): PlanOk manda, sigue oculta."""
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=30)
    _subir(client, h, pid, ["102"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False


# ── Escenario 6: pago por link sin reserva ────────────────────────────────────

def test_6_marca_de_pago_sigue_la_misma_regla_de_24h(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid, res="PAG-306")
    _subir(client, h, pid, ["101"])
    assert _unidad(db, pid, "101").disponible is False
    _envejecer(db, pid, "101", horas=25)
    _subir(client, h, pid, ["101"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "no_tomada" and u.disponible is True


# ── Escenario 7: se anula en Herramientas ─────────────────────────────────────

def test_7_anular_quita_la_marca_y_el_estado(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    r = _marcar(client, h, pid, f"{pid}-101", reserva_bc=None, esperado="RES-1", reabrir=False)
    assert r.status_code == 200
    u = _unidad(db, pid, "101")
    assert u.reserva_bc is None and u.reserva_bc_estado is None and u.disponible is False
    _subir(client, h, pid, ["101"])                # PlanOk la ofrece: reaparece
    assert _unidad(db, pid, "101").disponible is True


def test_7_anular_una_caida_y_volver_a_reservar_parte_provisoria(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=25)
    _subir(client, h, pid, ["101"])
    assert _unidad(db, pid, "101").reserva_bc_estado == "no_tomada"
    assert _marcar(client, h, pid, f"{pid}-101", reserva_bc=None, esperado="RES-1").status_code == 200
    fila = _reservar(client, h, pid, res="RES-2")
    assert fila["reserva_bc_estado"] == "provisoria" and fila["disponible"] is False


# ── Escenario 8: no se pudo leer PlanOk / Excel parcial ───────────────────────

def test_8_excel_parcial_no_cambia_nada(client, admin, db):
    """Una subida que bajaría ≥ 8 y ≥ 40 % de los disponibles es parcial: las marcas no
    se mueven (ni la que viene ofrecida ni la que no viene)."""
    _, h = admin
    pid = _pid()
    disponibles = {str(n): True for n in range(101, 111)}   # 10 disponibles
    _proyecto_con(db, pid, {**disponibles, "201": True, "202": True})
    _reservar(client, h, pid, "201", res="RES-A")           # vieja: ofrecida en el parcial
    _reservar(client, h, pid, "202", res="RES-B")           # nueva: falta en el parcial
    _envejecer(db, pid, "201", horas=30)
    _subir(client, h, pid, ["101", "201"])                  # 9 de 10 desaparecen
    a, b = _unidad(db, pid, "201"), _unidad(db, pid, "202")
    assert a.reserva_bc_estado == "provisoria" and a.disponible is False
    assert a.reserva_bc_vista_disponible_at is None
    assert b.reserva_bc_estado == "provisoria" and b.disponible is False
    assert _eventos(db, pid) == []


def test_8_excel_sin_deptos_no_cambia_nada(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    r = client.post(f"/proyectos/{pid}/unidades/excel/upload?permitir_sin_unidades=true",
                    headers=h, files={"file": ("x.xlsx", _excel([]), XLSX)})
    assert r.status_code == 200, r.text
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "provisoria" and u.disponible is False


def test_8_sin_subida_no_cambia_nada(client, admin, db):
    """Si la bajada de PlanOk falla, el scraper no sube (delta_abort): nada se mueve,
    aunque pasen las 24 h."""
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=48)
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "provisoria" and u.disponible is False


# ── Escenario 9: Operaciones reservó a mano en PlanOk sin reserva nuestra ─────

def test_9_sin_marca_y_tomada_en_planok_queda_oculta(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _subir(client, h, pid, ["102"])
    u = _unidad(db, pid, "101")
    assert u.disponible is False and u.reserva_bc is None and u.reserva_bc_estado is None


# ── Escenario 10: vendida / promesada ─────────────────────────────────────────

def test_10_liberada_que_desaparece_se_oculta_y_queda_confirmada(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True, "102": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=25)
    _subir(client, h, pid, ["101", "102"])
    assert _unidad(db, pid, "101").disponible is True        # no_tomada
    r = _subir(client, h, pid, ["102"])                       # PlanOk la vuelve a tomar
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False
    assert "101" in r["dados_de_baja"]
    assert _eventos(db, pid)[0] == "101: PlanOk volvió a tomar la unidad (RES-1), sale del catálogo"


# ── Marcas puestas antes de este cambio (44C, 54D, 18D) ───────────────────────

def _marca_antigua(db, pid, numero, horas):
    u = _unidad(db, pid, numero)
    u.reserva_bc = "RES-OLD"
    u.reserva_bc_at = datetime.utcnow() - timedelta(hours=horas)
    u.reserva_bc_estado = None
    u.disponible = False
    db.commit()


def test_marca_antigua_de_mas_de_24h_cae_en_la_segunda_subida(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"44C": True, "102": True})
    _marca_antigua(db, pid, "44C", horas=24 * 20)
    _subir(client, h, pid, ["44C", "102"])                   # 1ª subida tras el deploy
    u = _unidad(db, pid, "44C")
    assert u.reserva_bc_estado == "confirmada" and u.disponible is False
    _envejecer(db, pid, "44C", vista_min=60)
    _subir(client, h, pid, ["44C", "102"])                   # 2ª subida, ~1 h después
    u = _unidad(db, pid, "44C")
    assert u.reserva_bc_estado == "caida" and u.disponible is True
    assert u.reserva_bc == "RES-OLD"
    assert _eventos(db, pid) == ["44C: reserva caída en PlanOk (RES-OLD), vuelve a estar disponible"]


def test_marca_antigua_reciente_cuenta_como_provisoria(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _marca_antigua(db, pid, "101", horas=3)
    _subir(client, h, pid, ["101"])
    u = _unidad(db, pid, "101")
    assert u.reserva_bc_estado == "provisoria" and u.disponible is False


# ── Red final ─────────────────────────────────────────────────────────────────

def test_la_red_final_deja_disponible_una_marca_liberada(db):
    pid = _pid()
    _proyecto_con(db, pid, {"101": False})
    u = _unidad(db, pid, "101")
    u.reserva_bc = "RES-1"
    u.reserva_bc_estado = "caida"
    u.disponible = True
    db.commit()
    assert _unidad(db, pid, "101").disponible is True
    u = _unidad(db, pid, "101")
    u.reserva_bc_estado = "confirmada"
    u.disponible = True
    db.commit()
    assert _unidad(db, pid, "101").disponible is False


def test_repetir_la_misma_marca_no_oculta_una_reserva_liberada(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto_con(db, pid, {"101": True})
    _reservar(client, h, pid)
    _envejecer(db, pid, "101", horas=25)
    _subir(client, h, pid, ["101"])
    fila = _reservar(client, h, pid)               # reintento de la intranet
    assert fila["reserva_bc_estado"] == "no_tomada" and fila["disponible"] is True
