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
    assert filas[0]["detenciones_n"] == 1 and "detenciones" not in filas[0]
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


def test_vista_previa_admin(client, db, dia, admin):
    _, h = admin
    assert client.get("/mis-llamadas/gestion?fecha=2026-10-22&anexo=102", headers=h).json()["anexo"] == "102"
    otra = _token_para(db, "setter.qa@test.local")
    # una setter no puede mirar otro anexo con ?anexo=
    assert client.get("/mis-llamadas/gestion?fecha=2026-10-22&anexo=103", headers=otra).json()["anexo"] == "102"


def test_reuniones_desde_la_tarea(db, dia, monkeypatch, tmp_path):
    import json as _json
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    (tmp_path / "reuniones_setters.json").write_text(_json.dumps({"generado": "2026-10-22T18:00:00+00:00", "por_dia": {
        "2026-10-22": {"102": {"agendadas": 3, "reuniones_del_dia": 2, "asistidas": 1, "inasistencias": 1}}}}))
    r = {x["anexo"]: x for x in gs.gestion_dia(db, DIA)}
    assert r["102"]["reuniones"]["agendadas"] == 3 and r["102"]["reuniones"]["tasa_asistencia"] == 50
    assert r["103"]["reuniones"]["agendadas"] == 0
    (tmp_path / "reuniones_setters.json").unlink()
    assert gs.gestion_dia(db, DIA)[0]["reuniones"] is None


def test_extractor_reuniones():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("ext", pathlib.Path(__file__).parents[1] / "scripts/extraer_reuniones_setters.py")
    ext = importlib.util.module_from_spec(spec); spec.loader.exec_module(ext)
    foto = {"calendar_events": [
        {"contactId": "K0", "createdBy": {"userId": "U102"}, "dateAdded": "2026-10-21T15:00:00-03:00", "startTime": "2026-10-22T10:00:00-03:00", "appointmentStatus": "showed"},
        {"contactId": "K1", "createdBy": {"userId": "U102"}, "dateAdded": "2026-10-21T16:00:00-03:00", "startTime": "2026-10-22T11:00:00-03:00", "appointmentStatus": "noshow"},
        {"contactId": "K2", "createdBy": {"userId": "OTRO"}, "calendarId": "CAL103", "dateAdded": "2026-10-22T02:30:00Z", "startTime": "2030-01-01T10:00:00Z", "appointmentStatus": "confirmed"},
        {"contactId": "K3", "createdBy": {"userId": "U102"}, "title": "Prueba interna", "dateAdded": "2026-10-21T15:00:00-03:00"},
        {"contactId": "K4", "createdBy": {"userId": "NADIE"}, "dateAdded": "2026-10-21T15:00:00-03:00"},
    ]}
    d = ext.extraer(foto, {"U102": "102"}, {"CAL103": "103"})["por_dia"]
    assert d["2026-10-21"]["102"]["agendadas"] == 2
    assert d["2026-10-22"]["102"]["asistidas"] == 1 and d["2026-10-22"]["102"]["inasistencias"] == 1
    assert "agendadas" not in d["2026-10-21"].get("103", {})   # la creó otro en su calendario: no es agendada por ella
    assert d["2026-10-22"]["102"].get("agendadas", 0) == 0
    assert d["2030-01-01"]["103"]["pendientes"] == 1


def _extractor():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("ext", pathlib.Path(__file__).parents[1] / "scripts/extraer_reuniones_setters.py")
    ext = importlib.util.module_from_spec(spec); spec.loader.exec_module(ext)
    return ext


def test_extractor_cohorte_meet_y_pruebas():
    from datetime import datetime
    ext = _extractor()
    ahora = datetime.fromisoformat("2026-11-03T09:00:00-03:00")
    base = {"createdBy": {"userId": "U102"}, "dateAdded": "2026-10-21T15:00:00-03:00"}
    foto = {
        "users": [{"id": "U102", "name": "Ana Setter"}, {"id": "UN", "name": "Nicolás Soto"}],
        "conversations": [{"contactId": "CINT", "fullName": "Nicolas Soto", "email": "otro@gmail.com"},
                          {"contactId": "CMAIL", "fullName": "Alguien", "email": "x@BigCapital.cl"},
                          {"contactId": "CAV", "fullName": "Aviso Y."}],
        "calendar_events": [
            {**base, "id": "A1", "contactId": "C1", "startTime": "2026-10-22T10:00:00-03:00", "appointmentStatus": "showed"},
            {**base, "id": "A2", "contactId": "C2", "startTime": "2026-10-23T10:00:00-03:00", "appointmentStatus": "noshow"},
            {**base, "id": "A3", "contactId": "C3", "startTime": "2026-10-24T10:00:00-03:00", "appointmentStatus": "cancelled"},
            {**base, "id": "A4", "contactId": "C4", "startTime": "2026-11-10T10:00:00-03:00", "appointmentStatus": "confirmed"},
            {**base, "id": "A5", "contactId": "C5", "startTime": "2026-10-25T10:00:00-03:00", "appointmentStatus": "confirmed"},
            # pruebas e internas: ninguna cuenta
            {**base, "id": "P1", "contactId": "C6", "title": "Cita de PRUÉBA", "startTime": "2026-10-22T10:00:00-03:00"},
            {**base, "id": "P2", "contactId": "CINT", "title": "Nicolas Soto → atiende Pamela", "startTime": "2026-10-22T10:00:00-03:00", "appointmentStatus": "noshow"},
            {**base, "id": "P3", "contactId": "CMAIL", "startTime": "2026-10-22T10:00:00-03:00"},
            {**base, "id": "P4", "contactId": "CAV", "title": "Ana Setter | Propuestas", "startTime": "2026-10-22T10:00:00-03:00", "appointmentStatus": "cancelled"},
            {**base, "id": "P5", "contactId": "C7", "title": "NO AGENDAR", "startTime": "2026-10-22T10:00:00-03:00"},
            {**base, "id": "P6", "title": "Bloqueo sin contacto", "startTime": "2026-10-22T10:00:00-03:00"},
        ]}
    # con Meet: A1 entraron los dos, A2 solo el asesor, A5 sin material
    d = ext.extraer(foto, {"U102": "102"}, {}, {"A1": "ambos", "A2": "solo_asesor"}, ahora)
    c = d["por_dia"]["2026-10-21"]["102"]
    assert d["asistencia_fuente"] == "meet"
    assert c["agendadas"] == 5
    assert (c["ag_asistidas"], c["ag_inasistencias"], c["ag_canceladas"], c["ag_futuras"], c["ag_sin_resultado"]) == (1, 1, 1, 1, 1)
    assert c["agendadas"] == sum(c[k] for k in ext.AG.values())
    assert (c["meet_asistio"], c["meet_no_asistio"], c["meet_sin_prueba"]) == (1, 1, 1)
    assert d["por_dia"]["2026-10-22"]["102"] == {"reuniones_del_dia": 1, "asistidas": 1}
    # sin Meet: cae al estado de Nova sin romper
    d = ext.extraer(foto, {"U102": "102"}, {}, None, ahora)
    c = d["por_dia"]["2026-10-21"]["102"]
    assert d["asistencia_fuente"] == "nova"
    assert (c["meet_asistio"], c["meet_no_asistio"], c["meet_sin_prueba"]) == (1, 1, 1)
    # si el subproceso de Meet no existe, devuelve None (no lanza)
    assert ext.asistencia_meet(["A1"], "/no/existe") is None
    assert ext.asistencia_meet([], "/no/existe") == {}


def test_lista_de_agendadas_cuadra_con_la_cifra():
    from datetime import datetime
    ext = _extractor()
    ahora = datetime.fromisoformat("2026-11-03T09:00:00-03:00")
    base = {"createdBy": {"userId": "U102"}, "dateAdded": "2026-10-21T15:00:00-03:00", "assignedUserId": "UA"}
    foto = {
        "users": [{"id": "U102", "name": "Ana Setter"}, {"id": "UA", "name": "Asesor Uno"}],
        "opportunities": [{"contactId": "C1", "contact": {"id": "C1", "name": "Cliente  Uno", "phone": "+56900000000", "email": "c1@x.cl"}}],
        "calendar_events": [
            {**base, "id": "A1", "contactId": "C1", "startTime": "2026-10-22T10:00:00-03:00", "appointmentStatus": "showed"},
            {**base, "id": "A2", "contactId": "C2", "title": "Cliente Dos | Propuestas", "startTime": "2026-10-23T10:00:00-03:00",
             "appointmentStatus": "noshow", "assignedUserId": None},
            {**base, "id": "A3", "contactId": "C3", "startTime": "2026-11-10T10:00:00-03:00", "appointmentStatus": "confirmed",
             "dateAdded": "2026-10-22T02:30:00Z"},   # 21-oct 23:30 en Chile: cuenta el 21
            {**base, "id": "P1", "contactId": "C6", "title": "Prueba", "startTime": "2026-10-22T10:00:00-03:00"},
        ]}
    d = ext.extraer(foto, {"U102": "102"}, {}, {"A1": "ambos"}, ahora)
    c, filas = d["por_dia"]["2026-10-21"]["102"], d["agendadas_detalle"]["2026-10-21"]["102"]
    assert c["agendadas"] == len(filas) == 3
    assert c["ag_asistidas"] == sum(f["resultado"] == "asistidas" for f in filas) == 1
    a1 = next(f for f in filas if f["resultado"] == "asistidas")
    assert a1 == {"cliente": "Cliente Uno", "creada": "2026-10-21T15:00-03:00", "inicio": "2026-10-22T10:00-03:00",
                  "asesor": "Asesor Uno", "resultado": "asistidas", "meet": "ambos"}
    a2 = next(f for f in filas if f["resultado"] == "inasistencias")
    assert a2["cliente"] == "Cliente Dos" and a2["asesor"] == "Sin asignar"
    assert all("+569" not in str(f) and "@" not in str(f) for f in filas)   # sin teléfono ni correo


def test_endpoint_reuniones_mismo_filtro(client, db, config, monkeypatch, tmp_path, admin):
    import json as _json
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    fila = {"cliente": "Cliente Uno", "creada": "2026-10-22T10:00-03:00", "inicio": "2026-10-23T10:00-03:00",
            "asesor": "Asesor Uno", "resultado": "asistidas", "meet": "ambos"}
    (tmp_path / "reuniones_setters.json").write_text(_json.dumps({"generado": "x", "por_dia": {
        "2026-10-22": {"102": {"agendadas": 2, "ag_asistidas": 1}, "103": {"agendadas": 1, "ag_asistidas": 1}},
        "2026-10-25": {"102": {"agendadas": 1}}},
        "agendadas_detalle": {
            "2026-10-22": {"102": [fila, {**fila, "resultado": "pendientes", "meet": None}], "103": [fila], "101": [fila]},
            "2026-10-25": {"102": [fila]}}}))
    _, h = admin
    lista = client.get("/llamadas/reuniones?desde=2026-10-22&hasta=2026-10-24", headers=h).json()
    rango = client.get("/llamadas/gestion/rango?desde=2026-10-22&hasta=2026-10-24", headers=h).json()
    for r in rango:   # la cifra de cada setter y día es el largo de su lista
        propias = [x for x in lista if x["fecha"] == r["fecha"] and x["setter"] == r["setter"]]
        assert len(propias) == r["reuniones"]["agendadas"]
        assert sum(x["resultado"] == "asistidas" for x in propias) == r["reuniones"]["ag_asistidas"]
    assert {x["anexo"] for x in lista} == {"102", "103"}           # el 101 no es setter configurada
    assert set(lista[0]) == {"fecha", "setter", "anexo", "cliente", "creada", "inicio", "asesor", "resultado", "meet"}
    h2 = _token_para(db, "setter.qa@test.local")
    mias = client.get("/mis-llamadas/reuniones?desde=2026-10-22&hasta=2026-10-31", headers=h2).json()
    assert {x["anexo"] for x in mias} == {"102"} and len(mias) == 3
    assert client.get("/llamadas/reuniones?desde=2026-10-22&hasta=2026-10-24", headers=h2).status_code == 403
    assert client.get("/llamadas/reuniones?desde=2026-01-01&hasta=2026-10-24", headers=h).status_code == 422


def test_dias_del_rango_igual_que_antes():
    assert len(gs.dias_del_rango(date(2026, 10, 1), date(2026, 12, 31), 2)) == 31   # 62 filas con 2 setters
    assert len(gs.dias_del_rango(date(2026, 10, 1), date(2026, 10, 3), 2)) == 3
    assert len(gs.dias_del_rango(date(2026, 10, 1), date(2026, 10, 3), 0)) == 3


def test_reuniones_claves_nuevas(db, monkeypatch, tmp_path):
    import json as _json
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    (tmp_path / "reuniones_setters.json").write_text(_json.dumps({"generado": "x", "asistencia_fuente": "meet", "por_dia": {
        "2026-10-22": {"102": {"agendadas": 2, "ag_asistidas": 1, "ag_futuras": 1, "meet_asistio": 1}}}}))
    r = gs.gestion_dia(db, DIA)[0]
    assert r["reuniones"]["ag_asistidas"] == 1 and r["reuniones"]["ag_futuras"] == 1
    assert r["reuniones"]["meet_asistio"] == 1 and r["reuniones"]["meet_no_asistio"] == 0
    assert r["reuniones_fuente_asistencia"] == "meet"


# ── Alertas, calidad y metas ────────────────────────────────────────────────
def test_metas_editables(db, tmp_path, monkeypatch, client, admin):
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    assert gs.metas() == {"llamadas": settings.meta_llamadas_dia, "agendadas": settings.meta_agendadas_dia,
                          "detencion_min": settings.detencion_min}
    _, h = admin
    r = client.put("/llamadas/metas", json={"llamadas": 50, "agendadas": 3, "detencion_min": 15}, headers=h)
    assert r.status_code == 200 and r.json()["llamadas"] == 50
    assert gs.metas()["detencion_min"] == 15
    assert client.put("/llamadas/metas", json={"llamadas": 0}, headers=h).status_code == 422
    assert client.put("/llamadas/metas", json={"llamadas": "mucho"}, headers=h).status_code == 422
    assert client.put("/llamadas/metas", json={"llamadas": True}, headers=h).status_code == 422
    assert client.get("/llamadas/metas", headers=h).json()["llamadas"] == 50
    # un lector de Informes ve las metas pero no las cambia
    lector = _token_para(db, "lector.metas@test.local")
    monkeypatch.setattr(settings, "informes_lectores", "lector.metas@test.local")
    assert client.get("/llamadas/metas", headers=lector).status_code == 200
    assert client.put("/llamadas/metas", json={"llamadas": 10}, headers=lector).status_code == 403


def test_metas_corruptas_usan_las_de_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    (tmp_path / "metas_llamadas.json").write_text("{no es json")
    assert gs.metas()["llamadas"] == settings.meta_llamadas_dia
    (tmp_path / "metas_llamadas.json").write_text('{"llamadas": 99999, "agendadas": -4}')
    assert gs.metas()["llamadas"] == settings.meta_llamadas_dia and gs.metas()["agendadas"] == settings.meta_agendadas_dia


def test_alertas(db, config, dia):
    # el día de la fixture es jueves 22-oct-2026
    sin = {a["tipo"] for a in gs.alertas(db, datetime(2026, 10, 22, 9, 30))}
    assert sin == set()                                                   # antes de las 10 y última llamada a las 09:40 (hace 0)
    a10 = [a for a in gs.alertas(db, datetime(2026, 10, 22, 10, 30)) if a["setter"] == "Prueba Dos"]
    assert [a["tipo"] for a in a10] == ["sin_llamadas"]                    # 103 no llamó
    det = [a for a in gs.alertas(db, datetime(2026, 10, 22, 11, 0)) if a["setter"] == "Prueba Interna"]
    assert [a["tipo"] for a in det] == ["detenida"]                        # última a las 09:40, ya 80 min
    tarde = {a["tipo"] for a in gs.alertas(db, datetime(2026, 10, 22, 18, 30)) if a["setter"] == "Prueba Interna"}
    assert "sin_agendadas" not in tarde                                    # agendó 1 en la llamada de las 09:30
    assert gs.alertas(db, datetime(2026, 10, 24, 11, 0)) == []             # sábado


def test_calidad_por_paso(db, config):
    pref = f"cal_{uuid.uuid4().hex[:8]}"
    ev = {"pasos": [{"paso": "apertura", "cumple": "si", "puntaje": 80}, {"paso": "cierre", "cumple": "no_aplica", "puntaje": 0},
                    {"paso": "dolor", "cumple": "no", "puntaje": 20}],
          "reglas": {"nombro_proyecto_en_apertura": True, "rut_antes_de_agendar": False,
                     "ofrecio_dos_horarios": "no", "aviso_recordatorio_whatsapp": "si"}}
    db.add_all([_ll(pref, 1, 10, 0, 120, estado="ok", puntaje=50.0, evaluacion=ev),
                _ll(pref, 2, 11, 0, 120, estado="ok", puntaje=70.0, evaluacion=ev)])
    db.commit()
    try:
        c = {x["anexo"]: x for x in gs.calidad(db, DIA, DIA)}["102"]
        assert c["evaluadas"] == 2 and c["puntaje_promedio"] == 60.0
        pasos = {p["paso"]: p for p in c["pasos"]}
        assert pasos["apertura"]["promedio"] == 80 and pasos["cierre"]["promedio"] is None and pasos["dolor"]["n"] == 2
        reglas = {r["regla"]: r["veces"] for r in c["reglas"]}
        assert reglas["nombro_proyecto_en_apertura"] == 2 and reglas["ofrecio_dos_horarios"] == 2
        assert reglas["rut_antes_de_agendar"] == 0 and reglas["aviso_recordatorio_whatsapp"] == 0
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
        db.commit()


# ── Arreglos de la revisión adversarial ─────────────────────────────────────
def test_puntaje_total_tolera_basura():
    from app.services.evaluador_llamadas import puntaje_total
    ev = {"pasos": [{"paso": "cierre", "cumple": "si", "puntaje": None}, {"paso": "apertura", "cumple": "si", "puntaje": "85.5"},
                    "texto suelto", {"paso": "dolor", "cumple": "si", "puntaje": "mucho"}], "reglas": "no es dict"}
    assert puntaje_total(ev) == 85.0
    assert puntaje_total({"pasos": [{"paso": "cierre", "puntaje": None}]}) is None


def test_enmascarar_rut_y_telefonos():
    from app.services.evaluador_llamadas import enmascarar
    t = "mi rut es 12.345.678-5 y el otro 9876543-K, llámame al +56 9 7305 4251 o al 977909854"
    m = enmascarar(t)
    assert "12.345.678" not in m and "7305" not in m and "977909854" not in m and "[RUT]" in m and "[NÚMERO]" in m
    assert enmascarar("agendamos para las 11 o las 17 horas, son 25 minutos") == "agendamos para las 11 o las 17 horas, son 25 minutos"


def test_evaluacion_cortada_por_largo_se_rechaza():
    from types import SimpleNamespace
    from app.services import evaluador_llamadas as ev
    class M:
        messages = None
        def __init__(self): self.messages = self
        def create(self, **kw):
            return SimpleNamespace(stop_reason="max_tokens", content=[])
    with pytest.raises(ValueError):
        ev.evaluar_transcripcion("Canal 1: hola", "Prueba", M())

    class M2(M):
        def create(self, **kw):
            return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", name="registrar_evaluacion", input={"pasos": []})])
    with pytest.raises(ValueError):
        ev.evaluar_transcripcion("Canal 1: hola", "Prueba", M2())


def test_job_una_llamada_rara_no_frena_el_lote(db, config):
    from types import SimpleNamespace
    from app.services import evaluador_llamadas as ev
    pref = f"lote_{uuid.uuid4().hex[:8]}"
    malo = {"pasos": [{"paso": "cierre", "cumple": "si", "puntaje": None}]}   # sin las claves requeridas
    db.add_all([_ll(pref, 1, 9, 0, 120, estado="pendiente", transcripcion_texto="Canal 1: hola"),
                _ll(pref, 2, 9, 5, 120, estado="pendiente", transcripcion_texto="Canal 1: hola")])
    for x in db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).all():
        pass
    db.commit()
    db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).update({"updated_at": datetime(2026, 1, 1)}, synchronize_session=False)
    db.commit()
    class M:
        def __init__(self): self.messages = self
        def create(self, **kw):
            return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", name="registrar_evaluacion", input=malo)])
    try:
        ev.evaluar_pendientes(limite=50, cliente=M())
        db.expire_all()
        estados = {x.estado for x in db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).all()}
        assert estados <= {"pendiente", "error"} and "evaluando" not in estados
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
        db.commit()


def test_calidad_promedio_ignora_sin_puntaje(db, config):
    pref = f"calp_{uuid.uuid4().hex[:8]}"
    db.add_all([_ll(pref, 1, 10, 0, 120, estado="ok", puntaje=80.0, evaluacion={"pasos": [], "reglas": {}}),
                _ll(pref, 2, 11, 0, 120, estado="ok", puntaje=80.0, evaluacion={"pasos": [], "reglas": {}}),
                _ll(pref, 3, 12, 0, 120, estado="ok", puntaje=None, evaluacion={"pasos": [], "reglas": {}})])
    db.commit()
    try:
        assert {x["anexo"]: x for x in gs.calidad(db, DIA, DIA)}["102"]["puntaje_promedio"] == 80.0
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
        db.commit()


def test_horarios_sin_eco(db, config):
    pref = f"hor_{uuid.uuid4().hex[:8]}"
    db.add_all([_ll(pref, 1, 15, 0, 20, numero_cliente="4444"), _ll(pref, 2, 15, 5, 60, numero_cliente="+56911112222")])
    db.commit()
    try:
        h = {x["hora"]: x for x in gs.mejor_horario(db, DIA, DIA)}
        assert h["15:00"]["llamadas"] == 1
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
        db.commit()


def test_sync_prefiere_contestada_e_interna(db, config, monkeypatch):
    pbx, pbx2 = f"sy_{uuid.uuid4().hex[:8]}", f"sy2_{uuid.uuid4().hex[:8]}"
    filas = [{"pbx_call_id": pbx, "sip": "+56911110000", "clid": "+56911110000", "destination": "102", "callstart": "2026-10-22 12:00:00",
              "seconds": 40, "disposition": "no answer"},
             {"pbx_call_id": pbx, "sip": "+56911110000", "clid": "+56911110000", "destination": "102", "callstart": "2026-10-22 12:00:00",
              "seconds": 8, "disposition": "answered"},
             {"pbx_call_id": pbx2, "sip": "102", "clid": "102", "destination": "103", "callstart": "2026-10-22 13:00:00",
              "seconds": 30, "disposition": "answered"}]
    monkeypatch.setattr(zadarma, "llamar_api", lambda *a, **k: {"stats": filas})
    try:
        zadarma.sincronizar_estadisticas(db, datetime(2026, 10, 22), datetime(2026, 10, 23))
        db.expire_all()
        a = db.query(Llamada).filter(Llamada.pbx_call_id == pbx).one()
        b = db.query(Llamada).filter(Llamada.pbx_call_id == pbx2).one()
        assert a.resultado == "answered" and a.sentido == "entrante"
        assert b.sentido == "interna"
        assert gs.resumen_setter("x", "102", [b], 10)["llamadas"] == 0
        from app.services.evaluador_llamadas import motivo_para_omitir
        assert motivo_para_omitir(b) == "llamada interna"
    finally:
        db.query(Llamada).filter(Llamada.pbx_call_id.in_([pbx, pbx2])).delete(synchronize_session=False)
        db.commit()


def test_numero_ausente_no_es_texto_none(config):
    c = zadarma.fila_estadistica_a_campos({"sip": "102", "callstart": "2026-10-22 10:00:00", "seconds": 5, "disposition": "no answer"})
    assert c["numero_cliente"] is None
    assert zadarma._ext("xx-xx-1234") is None and zadarma._ext("383974-102") == "102" and zadarma._ext("4444") is None


def test_rango_acotado(client, db, admin):
    _, h = admin
    assert client.get("/llamadas/gestion/rango?desde=2026-01-01&hasta=2026-12-31", headers=h).status_code == 422
    assert client.get("/llamadas/calidad?desde=2026-10-01&hasta=9999-12-31", headers=h).status_code == 422
    assert client.get("/llamadas/horarios?desde=2026-10-22&hasta=2026-10-01", headers=h).status_code == 422
    assert client.get("/llamadas/calidad?desde=2026-10-01&hasta=2026-10-22", headers=h).status_code == 200


def test_json_raro_en_estado(db, tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    for contenido in ("null", "[]", "5", '{"por_dia": null}', '{"por_dia": {"2026-10-22": null}}', '{"por_dia": {"2026-10-22": {"102": "x"}}}'):
        (tmp_path / "reuniones_setters.json").write_text(contenido)
        (tmp_path / "metas_llamadas.json").write_text(contenido)
        assert isinstance(gs.metas(), dict)
        gs.gestion_dia(db, DIA)     # no debe lanzar
