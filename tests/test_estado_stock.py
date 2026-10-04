"""Estado del stock (correo "proyectos sin revisar") — 2026-10-05.

Regla de Nicolás: "actualizado" = revisado, con o sin cambios, por un robot o una
persona. Más de 3 días corridos (8 en Vellatrix y Las Palmas) = sin revisar.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import Proyecto, Unidad
from app.services.estado_stock import estado_stock

# Lunes 05/10/2026 09:00 en Chile (UTC-3 en octubre) = 12:00 UTC.
AHORA = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _p(ok=None, rev=None, upd=None, timeline=None, inmob="Iroyal", pub=True, activo=True):
    return SimpleNamespace(
        inmobiliaria=inmob, activo=activo, deleted_at=None,
        extra={"publicar_en_catalogo": pub, "timeline": timeline or []},
        stock_ok_at=_naive(ok) if ok else None,
        ultima_revision_at=_naive(rev) if rev else None,
        stock_updated_at=_naive(upd) if upd else None,
    )


def _ev(tipo, fecha, usuario="beatriz.vinet@bigcapital.cl", **kw):
    return {"id": "tl-" + uuid.uuid4().hex[:6], "tipo": tipo, "fecha": _iso(fecha),
            "usuario": usuario, "detalles": kw.pop("detalles", ""), **kw}


def _auto(fecha, inmob_txt="Ingevec"):
    return _ev("Excel Stock", fecha, usuario="mnk-scraper@bigcapital.cl", origen_auto=True,
               detalles=f"Actualización automática (scraper {inmob_txt}) — 2 deptos nuevos")


def test_al_dia_y_sin_revisar_a_los_4_dias():
    assert estado_stock(_p(ok=AHORA - timedelta(days=2)), AHORA)["estado"] == "al_dia"
    e = estado_stock(_p(ok=AHORA - timedelta(days=4)), AHORA)
    assert e["estado"] == "sin_revisar" and e["dias"] == 4 and not e["urgente"]
    assert estado_stock(_p(ok=AHORA - timedelta(days=7)), AHORA)["urgente"]


def test_dias_corridos_jueves_tarde_a_lunes_son_4():
    jueves_18 = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)  # 18:00 Chile
    e = estado_stock(_p(ok=jueves_18), AHORA)
    assert e["dias"] == 4 and e["estado"] == "sin_revisar"


def test_borde_de_fecha_se_cuenta_en_hora_de_chile():
    # 02/10 02:00 UTC = 01/10 23:00 Chile → al lunes 05/10 son 4 días, no 3.
    e = estado_stock(_p(ok=datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)), AHORA)
    assert e["dias"] == 4


def test_nunca_revisado():
    e = estado_stock(_p(), AHORA)
    assert e["dias"] is None and e["estado"] == "sin_revisar" and e["urgente"]
    assert e["por"] == "sin registro"


def test_semanales_esperan_8_dias():
    hace5 = AHORA - timedelta(days=5)
    tl = [_auto(AHORA - timedelta(days=20), "Vellatrix")]
    assert estado_stock(_p(ok=hace5, inmob="Vellatrix", timeline=tl), AHORA)["estado"] == "al_dia"
    e = estado_stock(_p(ok=AHORA - timedelta(days=9), inmob="Vellatrix", timeline=tl), AHORA)
    assert e["estado"] == "robot_sin_actualizar" and e["umbral"] == 8
    assert "No ha llegado archivo nuevo" in e["motivo"]


def test_robot_detenido_por_alertas_de_bloqueo():
    ok = AHORA - timedelta(days=5)
    tl = [_auto(ok, "Larrain Prieto")]
    for h in range(1, 60, 6):
        tl.append(_ev("Alerta", AHORA - timedelta(hours=h), usuario="mnk-scraper@bigcapital.cl",
                      titulo="Safety FAIL: Los Alerces — stock NO actualizado", severity="WARNING"))
    e = estado_stock(_p(ok=ok, rev=AHORA - timedelta(hours=1), inmob="Inmobiliaria Larrain Prieto",
                        timeline=tl), AHORA)
    assert e["estado"] == "robot_detenido"
    assert "frenó la subida" in e["motivo"] and "FAIL" not in e["motivo"]


def test_aviso_de_la_misma_corrida_no_bloquea():
    ok = AHORA - timedelta(days=1)
    tl = [_ev("Alerta", ok + timedelta(minutes=10), usuario="mnk-scraper@bigcapital.cl",
              titulo="Modelos no registrados detectados: 1")]
    e = estado_stock(_p(ok=ok, rev=ok + timedelta(minutes=10), timeline=tl), AHORA)
    assert e["estado"] == "al_dia" and e["robot_detenido_nota"] is None


def test_alerta_stock_actualizado_de_ingevec_cuenta_como_revision():
    tl = [_ev("Alerta", AHORA - timedelta(days=1), usuario="mnk-scraper@bigcapital.cl",
              titulo="Stock actualizado (proyecto sin deptos disponibles)")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=10), timeline=tl, inmob="Ingevec"), AHORA)
    assert e["estado"] == "al_dia"


def test_revision_de_persona_no_la_anula_una_alerta():
    tl = [_ev("Stock revisado", AHORA - timedelta(days=2)),
          _ev("Alerta", AHORA - timedelta(hours=2), usuario="mnk-scraper@bigcapital.cl",
              titulo="Canario MNK: X", detalles="stock NO actualizado esta corrida")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=9), timeline=tl, inmob="MNK"), AHORA)
    assert e["estado"] == "al_dia" and e["por"] == "Beatriz Vinet"
    assert e["robot_detenido_nota"]  # el aviso queda como nota para el listado


def test_revision_de_persona_vieja_y_robot_bloqueado():
    tl = [_ev("Stock revisado", AHORA - timedelta(days=4)),
          _ev("Alerta", AHORA - timedelta(hours=2), usuario="mnk-scraper@bigcapital.cl",
              titulo="Canario MNK: X", detalles="stock NO actualizado esta corrida")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=9), timeline=tl, inmob="MNK"), AHORA)
    assert e["estado"] == "robot_detenido"


def test_caso_aj_fecha_de_revision_directa_cuenta():
    # El sync de AJ actualiza la fecha directo en la base, sin alerta.
    e = estado_stock(_p(ok=AHORA - timedelta(days=10), rev=AHORA - timedelta(days=1),
                        inmob="AJ URBANA"), AHORA)
    assert e["estado"] == "al_dia"


def test_fecha_de_revision_movida_por_una_alerta_no_cuenta():
    t_alerta = AHORA - timedelta(hours=3)
    tl = [_auto(AHORA - timedelta(days=30)),
          _ev("Alerta", t_alerta, usuario="mnk-scraper@bigcapital.cl",
              titulo="Canario MNK: X", detalles="subida con problema (upload_failed)")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=10), rev=t_alerta, timeline=tl, inmob="MNK"), AHORA)
    assert e["estado"] == "robot_detenido" and "no pudo subir" in e["motivo"]


def test_robot_sin_actualizar_solo_con_rastro_del_robot_en_el_proyecto():
    # Inmobiliaria con robot, pero este proyecto nunca lo tocó un robot → a mano.
    e = estado_stock(_p(ok=AHORA - timedelta(days=6), inmob="Ecasa"), AHORA)
    assert e["estado"] == "sin_revisar"
    tl = [_auto(AHORA - timedelta(days=40), "Ecasa")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=6), inmob="Ecasa", timeline=tl), AHORA)
    assert e["estado"] == "robot_sin_actualizar" and e["fuente"] == "robot Ecasa"


def test_rastro_de_jetbrokers_no_cuenta_como_robot():
    tl = [_ev("Excel Stock", AHORA - timedelta(days=40), usuario="nicolas.soto@bigcapital.cl",
              origen_auto=True, detalles="Actualización automática (JetBrokers · scraper) — Sin cambios")]
    e = estado_stock(_p(ok=AHORA - timedelta(days=6), timeline=tl), AHORA)
    assert e["estado"] == "sin_revisar"


def test_por_quien_robot_y_nunca_una_edicion():
    ok = AHORA - timedelta(days=1)
    tl = [_ev("Edición", ok, usuario="pamela.scheel@bigcapital.cl", detalles="cambió el nombre"),
          _auto(ok + timedelta(seconds=5))]
    e = estado_stock(_p(ok=ok + timedelta(seconds=5), timeline=tl, inmob="Ingevec"), AHORA)
    assert e["por"] == "robot Ingevec"


def test_grupos_y_aplica():
    assert estado_stock(_p(ok=AHORA), AHORA)["aplica"] is True
    e = estado_stock(_p(ok=AHORA, pub=False), AHORA)
    assert e["grupo"] == "en_preparacion" and e["aplica"] is False
    assert estado_stock(_p(ok=AHORA, activo=False), AHORA)["grupo"] == "desactivados"


# ── Endpoints ────────────────────────────────────────────────────────────────

def _pid():
    return "test-est-" + uuid.uuid4().hex[:8]


def _proyecto(db, pid, **kw):
    db.add(Proyecto(id=pid, nombre=pid, extra={"timeline": []}, **kw))
    db.commit()


def _leer(db, pid):
    db.expire_all()
    return db.get(Proyecto, pid)


def test_verificado_sin_cuerpo_igual_que_siempre(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto(db, pid)
    r = client.post(f"/proyectos/{pid}/unidades/verificado", headers=h)
    assert r.status_code == 204 and r.content == b""
    p = _leer(db, pid)
    assert p.stock_updated_at and p.stock_ok_at and p.ultima_revision_at


def test_verificado_con_cuerpo_es_revision_de_persona(client, admin, db):
    _, h = admin
    pid = _pid()
    viejo = datetime(2026, 9, 1, 12, 0)
    _proyecto(db, pid, stock_updated_at=viejo)
    r = client.post(f"/proyectos/{pid}/unidades/verificado", headers=h, json={"registrar_evento": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evento"]["tipo"] == "Stock revisado" and body["evento"]["origen_auto"] is False
    p = _leer(db, pid)
    assert p.stock_updated_at == viejo           # la fecha del catálogo no se mueve
    assert p.stock_ok_at > viejo and p.ultima_revision_at > viejo
    assert p.extra["timeline"][0]["tipo"] == "Stock revisado"
    assert estado_stock(p)["estado"] == "al_dia"


def test_verificado_con_archivo_no_anota_evento(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto(db, pid)
    r = client.post(f"/proyectos/{pid}/unidades/verificado", headers=h,
                    json={"archivo": "lista.xlsx", "registrar_evento": False})
    assert r.status_code == 200 and r.json()["evento"] is None
    p = _leer(db, pid)
    assert p.stock_ok_at is not None and p.extra["timeline"] == []


def test_verificado_en_papelera_y_sin_sesion(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto(db, pid, deleted_at=datetime(2026, 10, 1))
    r = client.post(f"/proyectos/{pid}/unidades/verificado", headers=h, json={"registrar_evento": True})
    assert r.status_code == 404
    r = client.post(f"/proyectos/{pid}/unidades/verificado", json={"registrar_evento": True})
    assert r.status_code in (401, 403)


def test_reserva_de_la_intranet_no_cuenta_como_revision(client, admin, db):
    _, h = admin
    pid = _pid()
    _proyecto(db, pid, stock_ok_at=datetime(2026, 9, 1, 12, 0))
    db.add(Unidad(id=f"{pid}-101", proyecto_id=pid, numero="101", tipo="Depto", modelo="2D1B", disponible=True))
    db.commit()
    r = client.put(f"/proyectos/{pid}/unidades/{pid}-101/reserva-bc", headers=h, json={"reserva_bc": "RES-1"})
    assert r.status_code == 200, r.text
    p = _leer(db, pid)
    assert p.stock_ok_at == datetime(2026, 9, 1, 12, 0)
    assert p.stock_updated_at is not None  # el catálogo sigue viendo el cambio, como hoy
