"""Gestión diaria de las setters, sincronización con Zadarma y accesos."""
import uuid
from datetime import date, datetime

import pytest

from app.models import Usuario
from app.models.llamada import Llamada
from app.services import gestion_setters as gs
from app.services import zadarma
from app.services.auth import create_token, hash_password
from app.settings import settings

DIA = date(2026, 10, 22)


def _ll(pref, n, hora, minuto, dur, resultado="answered", anexo="102", **kw):
    return Llamada(pbx_call_id=f"{pref}_{n}", anexo=anexo, setter="Prueba Interna", sentido="saliente",
                   inicio=datetime(2026, 10, 22, hora, minuto), duracion_s=dur, resultado=resultado,
                   estado=kw.pop("estado", "nuevo"), intentos=0,
                   created_at=datetime.utcnow(), updated_at=datetime.utcnow(), **kw)


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(settings, "zadarma_anexos", "102:Prueba Interna,103:Prueba Dos")
    monkeypatch.setattr(settings, "zadarma_correos", "102:setter.qa@test.local")
    monkeypatch.setattr(settings, "detencion_min", 10)


@pytest.fixture
def dia(db, config):
    pref = f"gs_{uuid.uuid4().hex[:8]}"
    filas = [
        _ll(pref, 1, 9, 0, 120),                       # 09:00-09:02
        _ll(pref, 2, 9, 5, 15),                        # hueco 3 min, corta
        _ll(pref, 3, 9, 30, 300, estado="ok", puntaje=70.0,
            evaluacion={"resultado_llamada": "agendo"}),  # hueco ~25 min → detención
        _ll(pref, 4, 9, 40, 0, resultado="no answer"),  # hueco 5 min
        _ll(pref, 5, 9, 0, 60, anexo="101"),             # Carolina: no cuenta
    ]
    db.add_all(filas)
    db.commit()
    yield pref
    db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
    db.commit()


def test_gestion_del_dia(db, dia):
    r = {x["anexo"]: x for x in gs.gestion_dia(db, DIA)}
    m = r["102"]
    assert m["llamadas"] == 4 and m["contestadas"] == 3 and m["cortas"] == 1
    assert m["primera"] == "09:00" and m["ultima"] == "09:40"
    assert m["minutos_hablados"] == round((120 + 15 + 300) / 60, 1)
    assert [d["desde"] for d in m["detenciones"]] == ["09:05"]
    assert m["detenciones"][0]["hasta"] == "09:30" and m["detencion_mayor_min"] == 25
    assert m["puntaje_promedio"] == 70.0 and m["agendadas_en_llamada"] == 1
    assert m["tasa_contacto"] == 75
    assert r["103"]["llamadas"] == 0 and r["103"]["primera"] is None
    assert "101" not in r


def test_rango_y_horarios(db, dia):
    filas = [x for x in gs.gestion_rango(db, DIA, DIA) if x["anexo"] == "102"]
    assert filas[0]["fecha"] == "2026-10-22" and "linea_tiempo" not in filas[0]
    h = {x["hora"]: x for x in gs.mejor_horario(db, DIA, DIA)}
    assert h["09:00"]["llamadas"] == 4 and h["09:00"]["contestadas"] == 3


def test_estadistica_saliente_y_entrante(config):
    s = zadarma.fila_estadistica_a_campos({"sip": "383974-102", "clid": "+56973054251", "destination": "+56911112222",
                                           "callstart": "2026-10-22 10:00:00", "seconds": 90,
                                           "disposition": "answered", "is_recorded": True, "call_id": "1.2"})
    assert s["sentido"] == "saliente" and s["anexo"] == "102" and s["numero_cliente"] == "+56911112222"
    assert s["call_id_con_grabacion"] == "1.2" and s["setter"] == "Prueba Interna"
    e = zadarma.fila_estadistica_a_campos({"sip": "+56933334444", "clid": "+56933334444", "destination": "103",
                                           "callstart": "2026-10-22 11:00:00", "seconds": 0, "disposition": "no answer"})
    assert e["sentido"] == "entrante" and e["anexo"] == "103" and e["numero_cliente"] == "+56933334444"


def test_sincronizar_idempotente(db, config, monkeypatch):
    pbx = f"sync_{uuid.uuid4().hex[:8]}"
    filas = [{"pbx_call_id": pbx, "sip": "102", "destination": "+56900000000", "callstart": "2026-10-22 12:00:00",
              "seconds": 10, "disposition": "answered"},
             {"pbx_call_id": pbx, "sip": "102", "destination": "+56900000000", "callstart": "2026-10-22 12:00:00",
              "seconds": 95, "disposition": "answered"}]
    monkeypatch.setattr(zadarma, "llamar_api", lambda *a, **k: {"stats": filas})
    try:
        assert zadarma.sincronizar_estadisticas(db, datetime(2026, 10, 22), datetime(2026, 10, 23)) == 1
        zadarma.sincronizar_estadisticas(db, datetime(2026, 10, 22), datetime(2026, 10, 23))
        db.expire_all()
        ll = db.query(Llamada).filter(Llamada.pbx_call_id == pbx).all()
        assert len(ll) == 1 and ll[0].duracion_s == 95
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id == pbx).delete()
        db.commit()


def _token_para(db, email, admin=False):
    u = db.query(Usuario).filter(Usuario.email == email).first()
    if not u:
        db.add(Usuario(email=email, nombre="Prueba Interna", password_hash=hash_password("x1234567"), is_admin=admin, activo=True))
        db.commit()
    return {"Authorization": f"Bearer {create_token(sub=email)[0]}"}


def test_acceso_informes(client, db, dia, monkeypatch):
    monkeypatch.setattr(settings, "informes_lectores", "lector.qa@test.local")
    assert client.get("/llamadas/gestion?fecha=2026-10-22", headers=_token_para(db, "lector.qa@test.local")).status_code == 200
    assert client.get("/llamadas/gestion?fecha=2026-10-22", headers=_token_para(db, "otro.qa@test.local")).status_code == 403


def test_setter_ve_solo_lo_suyo(client, db, dia):
    h = _token_para(db, "setter.qa@test.local")
    g = client.get("/mis-llamadas/gestion?fecha=2026-10-22", headers=h).json()
    assert g["anexo"] == "102" and g["llamadas"] == 4
    propias = client.get("/mis-llamadas?desde=2026-10-22&hasta=2026-10-22", headers=h).json()
    assert {x["anexo"] for x in propias} == {"102"}
    ajena = db.query(Llamada).filter(Llamada.pbx_call_id == f"{dia}_5").one()
    assert client.get(f"/mis-llamadas/{ajena.id}", headers=h).status_code == 404
    assert client.get("/mis-llamadas/gestion", headers=_token_para(db, "otro.qa@test.local")).status_code == 403


def test_eco_4444_no_cuenta(config):
    c = zadarma.fila_estadistica_a_campos({"sip": "102", "destination": "4444", "callstart": "2026-10-22 10:00:00",
                                           "seconds": 20, "disposition": "answered"})
    assert c["anexo"] == "102" and c["numero_cliente"] == "4444"
    r = gs.resumen_setter("Prueba Interna", "102", [_ll("eco", 1, 10, 0, 20, numero_cliente="4444")], 10)
    assert r["llamadas"] == 0
