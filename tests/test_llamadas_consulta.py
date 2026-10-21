"""Panel de llamadas: listado, resumen, detalle y grabación (solo super admin)."""
import uuid
from datetime import datetime

import pytest

from app.models.llamada import Llamada
from app.services import zadarma
from app.settings import settings

SETTER = "Prueba Interna QA"


@pytest.fixture
def llamadas(db):
    pref = f"cq_{uuid.uuid4().hex[:8]}"
    filas = [
        Llamada(pbx_call_id=f"{pref}_1", setter=SETTER, anexo="102", resultado="answered", duracion_s=200,
                inicio=datetime(2026, 10, 20, 10, 0), estado="ok", puntaje=80.0, call_id_con_grabacion="rec-a",
                evaluacion={"resultado_llamada": "agendo"}, transcripcion_frases=[{"canal": 1, "texto": "Hola"}],
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(), intentos=1),
        Llamada(pbx_call_id=f"{pref}_2", setter=SETTER, anexo="102", resultado="no answer", duracion_s=0,
                inicio=datetime(2026, 10, 21, 11, 0), estado="omitida",
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(), intentos=0),
    ]
    db.add_all(filas)
    db.commit()
    yield filas
    db.query(Llamada).filter(Llamada.pbx_call_id.like(f"{pref}_%")).delete(synchronize_session=False)
    db.commit()


def test_requiere_admin(client):
    assert client.get("/llamadas").status_code in (401, 403)


def test_listado_y_filtros(client, admin, llamadas):
    _, h = admin
    r = client.get(f"/llamadas?setter={SETTER}", headers=h)
    assert r.status_code == 200 and len(r.json()) == 2
    r = client.get(f"/llamadas?setter={SETTER}&desde=2026-10-21&hasta=2026-10-21", headers=h)
    assert [x["resultado"] for x in r.json()] == ["no answer"]


def test_resumen(client, admin, llamadas):
    _, h = admin
    fila = next(s for s in client.get("/llamadas/resumen", headers=h).json() if s["setter"] == SETTER)
    assert fila["llamadas"] == 2 and fila["contestadas"] == 1 and fila["evaluadas"] == 1
    assert fila["agendadas"] == 1 and fila["puntaje_promedio"] == 80.0


def test_detalle(client, admin, llamadas):
    _, h = admin
    r = client.get(f"/llamadas/{llamadas[0].id}", headers=h)
    assert r.status_code == 200
    assert r.json()["transcripcion_frases"] == [{"canal": 1, "texto": "Hola"}]
    assert client.get("/llamadas/999999999", headers=h).status_code == 404


def test_grabacion(client, admin, llamadas, monkeypatch):
    _, h = admin
    monkeypatch.setattr(settings, "zadarma_api_key", "k")
    monkeypatch.setattr(settings, "zadarma_api_secret", "s")
    monkeypatch.setattr(zadarma, "enlace_grabacion", lambda call_id, pbx, segundos=600: f"https://ejemplo/{call_id}")
    r = client.get(f"/llamadas/{llamadas[0].id}/grabacion", headers=h)
    assert r.status_code == 200 and r.json()["link"] == "https://ejemplo/rec-a"


def test_grabacion_sin_configurar(client, admin, llamadas, monkeypatch):
    _, h = admin
    monkeypatch.setattr(settings, "zadarma_api_key", "")
    assert client.get(f"/llamadas/{llamadas[0].id}/grabacion", headers=h).status_code == 503
