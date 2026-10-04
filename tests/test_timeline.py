"""Historia del proyecto: fusión en el PUT y tope de alertas — 2026-10-05.

El autoguardado del editor reemplazaba `extra` entero con la copia del navegador y se
llevaba las alertas que un robot había publicado mientras la ficha estaba abierta.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Proyecto
from app.services.timeline import (
    MAX_ALERTAS, fusionar_timeline, parse_fecha, recortar_timeline,
)


def _pid():
    return "test-tl-" + uuid.uuid4().hex[:8]


def _ev(i, tipo="Edición", titulo=None, minutos=0):
    f = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutos)
    ev = {"id": f"tl-{i}", "fecha": f.isoformat().replace("+00:00", "Z"), "tipo": tipo,
          "detalles": f"evento {i}", "usuario": "x@bigcapital.cl"}
    if titulo:
        ev["titulo"] = titulo
    return ev


def test_parse_fecha_formatos():
    assert parse_fecha("2026-10-05T12:00:00Z") == datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    assert parse_fecha("2026-10-05T12:00:00.123Z").microsecond == 123000
    assert parse_fecha("2026-10-05T12:00:00").tzinfo is not None  # sin zona = UTC
    assert parse_fecha("2026-10-05T09:00:00-03:00") == datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    assert parse_fecha("") is None and parse_fecha(None) is None and parse_fecha("ayer") is None


def test_fusion_sin_timeline_en_el_cuerpo_queda_la_del_servidor():
    srv = [_ev(1), _ev(2)]
    assert fusionar_timeline(None, srv) == srv


def test_fusion_conserva_eventos_del_servidor_que_el_cuerpo_no_trae():
    vieja = [_ev(1, minutos=0)]
    alerta = _ev(2, tipo="Alerta", titulo="Safety FAIL", minutos=30)
    srv = [alerta] + vieja
    out = fusionar_timeline(vieja, srv)
    assert [e["id"] for e in out] == ["tl-2", "tl-1"]


def test_fusion_sin_faltantes_respeta_el_orden_del_cuerpo():
    ent = [_ev(1, minutos=0), _ev(2, minutos=10)]  # orden "raro" a propósito
    assert fusionar_timeline(ent, [_ev(1)]) == ent


def test_fusion_eventos_sin_id_vienen_del_cuerpo_tal_cual():
    sin_id = {"fecha": "2026-10-01T10:00:00Z", "tipo": "Nota", "detalles": "vieja sin id"}
    out = fusionar_timeline([sin_id], [_ev(9, minutos=60)])
    assert sin_id in out and any(e.get("id") == "tl-9" for e in out)


def test_tope_conserva_no_alertas_y_ultima_de_cada_titulo():
    eventos = [_ev(f"n{i}", tipo="Excel Stock", minutos=i) for i in range(5)]
    eventos += [_ev(f"a{i}", tipo="Alerta", titulo="Safety FAIL", minutos=100 + i) for i in range(150)]
    eventos += [_ev("viejo", tipo="Alerta", titulo="Stock actualizado (Ingevec)", minutos=-500)]
    out = recortar_timeline(eventos)
    alertas = [e for e in out if e["tipo"] == "Alerta"]
    assert len([e for e in out if e["tipo"] != "Alerta"]) == 5
    assert len(alertas) == MAX_ALERTAS + 1           # 100 más recientes + la única de su título
    assert any(e["id"] == "tl-viejo" for e in alertas)
    assert any(e["id"] == "tl-a149" for e in alertas)  # la más reciente queda
    assert not any(e["id"] == "tl-a0" for e in alertas)  # las más viejas salen


def test_tope_no_toca_listas_cortas():
    eventos = [_ev(i, tipo="Alerta", titulo="x", minutos=i) for i in range(10)]
    assert recortar_timeline(eventos) == eventos


def test_put_no_borra_la_alerta_publicada_mientras_la_ficha_estaba_abierta(client, admin, db):
    _, h = admin
    pid = _pid()
    db.add(Proyecto(id=pid, nombre=pid, extra={"timeline": [_ev(1)]}))
    db.commit()
    # El editor abre la ficha (copia con un solo evento)…
    copia_navegador = client.get(f"/proyectos/{pid}", headers=h).json()
    # …mientras tanto el robot publica una alerta…
    r = client.post(f"/proyectos/{pid}/unidades/timeline/alerta", headers=h,
                    json={"severity": "WARNING", "titulo": "Safety FAIL: x — stock NO actualizado",
                          "detalle": "bloqueado"})
    assert r.status_code in (200, 201), r.text
    # …y el autoguardado manda la copia vieja.
    cuerpo = {k: copia_navegador[k] for k in ("nombre", "extra")}
    r = client.put(f"/proyectos/{pid}", headers=h, json=cuerpo)
    assert r.status_code == 200, r.text
    tl = r.json()["extra"]["timeline"]
    assert any(e.get("tipo") == "Alerta" for e in tl)
    assert any(e.get("id") == "tl-1" for e in tl)


def test_put_sin_timeline_en_el_cuerpo_no_la_borra(client, admin, db):
    _, h = admin
    pid = _pid()
    db.add(Proyecto(id=pid, nombre=pid, extra={"timeline": [_ev(1)], "otra": 1}))
    db.commit()
    r = client.put(f"/proyectos/{pid}", headers=h, json={"nombre": pid, "extra": {"otra": 2}})
    assert r.status_code == 200, r.text
    extra = r.json()["extra"]
    assert extra["otra"] == 2
    assert [e["id"] for e in extra["timeline"]] == ["tl-1"]
