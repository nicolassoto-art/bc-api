"""Webhook de Zadarma: firmas, barreras e idempotencia de las llamadas."""
import json
import uuid

import pytest

from app.models.llamada import Llamada, ZadarmaEvento
from app.services import zadarma
from app.settings import settings

SECRETO = "secreto-de-prueba"
TOKEN = "token-de-prueba"
IP_OK = {"X-Real-IP": "185.45.152.41"}


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(settings, "zadarma_api_secret", SECRETO)
    monkeypatch.setattr(settings, "zadarma_webhook_token", TOKEN)
    monkeypatch.setattr(settings, "zadarma_ip_mode", "enforce")
    monkeypatch.setattr(settings, "zadarma_anexos", "102:Prueba Interna")


@pytest.fixture
def pbx(db):
    pid = f"in_test_{uuid.uuid4().hex[:12]}"
    yield pid
    db.query(ZadarmaEvento).filter(ZadarmaEvento.pbx_call_id == pid).delete()
    db.query(Llamada).filter(Llamada.pbx_call_id == pid).delete()
    db.commit()


def _enviar(client, datos, firmar=True, token=TOKEN, cab=None):
    cabeceras = dict(IP_OK if cab is None else cab)
    if firmar:
        f = zadarma.firma_evento(datos["event"], datos, SECRETO)
        if f:
            cabeceras["Signature"] = f
    return client.post(f"/webhooks/zadarma?k={token}", data=datos, headers=cabeceras)


# ── Firmas ───────────────────────────────────────────────────────────────────
def test_firma_formato_php():
    # base64 del HEX del HMAC-SHA1, como base64_encode(hash_hmac('sha1', …)) en PHP
    d = {"caller_id": "+56911111111", "called_did": "56973054251", "call_start": "2026-10-21 10:00:00"}
    import base64, hashlib, hmac
    esperado = base64.b64encode(hmac.new(SECRETO.encode(), "".join(d.values()).encode(), hashlib.sha1).hexdigest().encode()).decode()
    assert zadarma.firma_evento("NOTIFY_START", d, SECRETO) == esperado
    assert zadarma.verificar_firma("NOTIFY_START", d, esperado, SECRETO) is True
    assert zadarma.verificar_firma("NOTIFY_START", d, "otra", SECRETO) is False
    assert zadarma.verificar_firma("SPEECH_RECOGNITION", d, "", SECRETO) is None


def test_ip_de_zadarma():
    assert zadarma.ip_es_de_zadarma("185.45.152.40")
    assert zadarma.ip_es_de_zadarma("185.45.152.43")
    assert not zadarma.ip_es_de_zadarma("185.45.152.44")
    assert not zadarma.ip_es_de_zadarma("no-es-ip")


# ── Barreras ─────────────────────────────────────────────────────────────────
def test_zd_echo(client):
    r = client.get("/webhooks/zadarma?zd_echo=abc123")
    assert r.status_code == 200 and r.text == "abc123"


def test_sin_configurar_503(client, monkeypatch):
    monkeypatch.setattr(settings, "zadarma_webhook_token", "")
    assert client.post("/webhooks/zadarma?k=x", data={"event": "NOTIFY_START"}).status_code == 503


def test_token_incorrecto(client, config):
    assert _enviar(client, {"event": "NOTIFY_START"}, token="malo").status_code == 403


def test_ip_fuera_de_rango(client, config, pbx):
    datos = {"event": "NOTIFY_START", "pbx_call_id": pbx, "caller_id": "1", "called_did": "2", "call_start": "2026-10-21 10:00:00"}
    assert _enviar(client, datos, cab={"X-Real-IP": "8.8.8.8"}).status_code == 403


def test_firma_invalida(client, config, pbx):
    datos = {"event": "NOTIFY_START", "pbx_call_id": pbx, "caller_id": "1", "called_did": "2", "call_start": "2026-10-21 10:00:00"}
    r = client.post(f"/webhooks/zadarma?k={TOKEN}", data=datos, headers={**IP_OK, "Signature": "falsa"})
    assert r.status_code == 403


# ── Armado de la llamada ────────────────────────────────────────────────────
def test_llamada_saliente_completa(client, config, pbx, db):
    base = {"pbx_call_id": pbx, "internal": "102", "destination": "+56922222222", "call_start": "2026-10-21 10:00:00"}
    assert _enviar(client, {"event": "NOTIFY_OUT_START", **base}).status_code == 200
    # repetido: no debe duplicar
    assert _enviar(client, {"event": "NOTIFY_OUT_START", **base}).status_code == 200
    fin = {"event": "NOTIFY_OUT_END", **base, "caller_id": "56973054251", "duration": "185",
           "disposition": "answered", "status_code": "16", "is_recorded": "1", "call_id_with_rec": "rec-1"}
    assert _enviar(client, fin).status_code == 200

    transcripcion = {"event": "SPEECH_RECOGNITION", "pbx_call_id": pbx, "call_id": "rec-1", "lang": "es-MX",
                     "result": json.dumps({"phrases": [{"result": "Alo, ¿hablo con Prueba?", "channel": 1},
                                                        {"result": "Sí, con ella.", "channel": 2}]})}
    assert _enviar(client, transcripcion).status_code == 200

    db.expire_all()
    filas = db.query(Llamada).filter(Llamada.pbx_call_id == pbx).all()
    assert len(filas) == 1
    ll = filas[0]
    assert ll.sentido == "saliente" and ll.anexo == "102" and ll.setter == "Prueba Interna"
    assert ll.numero_cliente == "+56922222222" and ll.numero_linea == "56973054251"
    assert ll.duracion_s == 185 and ll.resultado == "answered" and ll.call_id_con_grabacion == "rec-1"
    assert ll.estado == "pendiente"
    assert ll.transcripcion_frases[0] == {"canal": 1, "texto": "Alo, ¿hablo con Prueba?"}
    assert "Canal 2: Sí, con ella." in ll.transcripcion_texto
    assert db.query(ZadarmaEvento).filter(ZadarmaEvento.pbx_call_id == pbx).count() == 4


def test_transcripcion_antes_que_el_fin(client, config, pbx, db):
    transcripcion = {"event": "SPEECH_RECOGNITION", "pbx_call_id": pbx, "call_id": "rec-2",
                     "result": json.dumps({"phrases": [{"result": "Hola", "channel": 1}]})}
    assert _enviar(client, transcripcion).status_code == 200
    fin = {"event": "NOTIFY_END", "pbx_call_id": pbx, "caller_id": "+56933333333", "called_did": "56966126547",
           "call_start": "2026-10-21 11:00:00", "internal": "102", "duration": "70", "disposition": "answered",
           "call_id_with_rec": "rec-2"}
    assert _enviar(client, fin).status_code == 200
    db.expire_all()
    ll = db.query(Llamada).filter(Llamada.pbx_call_id == pbx).one()
    assert ll.estado == "pendiente" and ll.sentido == "entrante" and ll.duracion_s == 70
    assert ll.transcripcion_frases == [{"canal": 1, "texto": "Hola"}]


def test_transcripcion_repetida_no_reabre_evaluada(client, config, pbx, db):
    transcripcion = {"event": "SPEECH_RECOGNITION", "pbx_call_id": pbx,
                     "result": json.dumps({"phrases": [{"result": "Hola", "channel": 1}]})}
    _enviar(client, transcripcion)
    db.query(Llamada).filter(Llamada.pbx_call_id == pbx).update({"estado": "ok"})
    db.commit()
    _enviar(client, transcripcion)
    db.expire_all()
    assert db.query(Llamada).filter(Llamada.pbx_call_id == pbx).one().estado == "ok"


def test_webhook_ignora_eventos_desconocidos_y_token_no_ascii(client, config, pbx, db):
    r = client.post("/webhooks/zadarma?k=tóken", data={"event": "NOTIFY_START"}, headers=IP_OK)
    assert r.status_code == 403
    r = _enviar(client, {"event": "ALGO_RARO", "pbx_call_id": pbx, "caller_id": "+56900000000"})
    assert r.status_code == 200
    assert db.query(ZadarmaEvento).filter(ZadarmaEvento.pbx_call_id == pbx).count() == 0
