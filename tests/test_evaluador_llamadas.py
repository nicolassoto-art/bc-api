"""Evaluador de llamadas: puntaje, omisiones, reintentos y job con modelo simulado."""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.llamada import Llamada
from app.services import evaluador_llamadas as ev
from app.settings import settings

EVAL_OK = {
    "resultado_llamada": "agendo",
    "pasos": [
        {"paso": "apertura", "cumple": "si", "puntaje": 100, "evidencia": "Hablas con Prueba", "comentario": "Bien"},
        {"paso": "dolor", "cumple": "parcial", "puntaje": 50, "evidencia": "¿Primera vez?", "comentario": "Faltó profundizar"},
        {"paso": "propuesta_valor", "cumple": "si", "puntaje": 80, "evidencia": "Sin costo", "comentario": "Ok"},
        {"paso": "calificacion", "cumple": "no", "puntaje": 0, "evidencia": "", "comentario": "No calificó"},
        {"paso": "cierre", "cumple": "si", "puntaje": 90, "evidencia": "Mañana a las 11 o a las 5", "comentario": "Bien"},
    ],
    "reglas": {"nombro_proyecto_en_apertura": False, "rut_antes_de_agendar": False,
               "ofrecio_dos_horarios": "si", "aviso_recordatorio_whatsapp": "no"},
    "objeciones": [], "lo_que_hizo_bien": ["Cierre con dos horarios"],
    "consejo": "Haz las preguntas de calificación.", "resumen": "Agendó sin calificar.",
}


class ModeloFalso:
    def __init__(self, salida=EVAL_OK, falla=False):
        self.salida, self.falla, self.llamadas = salida, falla, 0
        self.messages = self

    def create(self, **kw):
        self.llamadas += 1
        assert kw["tool_choice"]["name"] == "registrar_evaluacion"
        if self.falla:
            raise RuntimeError("caída simulada")
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="registrar_evaluacion", input=self.salida)])


@pytest.fixture
def llamada(db):
    pid = f"ev_test_{uuid.uuid4().hex[:12]}"
    ll = Llamada(pbx_call_id=pid, setter="Prueba Interna", anexo="102", resultado="answered", duracion_s=180,
                 transcripcion_texto="Canal 1: Alo\nCanal 2: Sí", estado="pendiente", intentos=0,
                 created_at=datetime.utcnow(), updated_at=datetime.utcnow() - timedelta(minutes=10))
    db.add(ll)
    db.commit()
    yield ll
    db.query(Llamada).filter(Llamada.pbx_call_id == pid).delete()
    db.commit()


def test_puntaje_ponderado():
    # (15*100 + 20*50 + 20*80 + 20*0 + 25*90) / 100 = 63.5
    assert ev.puntaje_total(EVAL_OK) == 63.5


def test_puntaje_ignora_no_aplica_y_castiga_reglas():
    e = {"pasos": [{"paso": "apertura", "cumple": "si", "puntaje": 80},
                   {"paso": "cierre", "cumple": "no_aplica", "puntaje": 0}],
         "reglas": {"nombro_proyecto_en_apertura": True, "rut_antes_de_agendar": True}}
    assert ev.puntaje_total(e) == 65.0   # 80 - 10 - 5
    assert ev.puntaje_total({"pasos": []}) is None


def test_omite_no_contestada_y_corta():
    assert ev.motivo_para_omitir(Llamada(resultado="no answer", transcripcion_texto="x")) == "no contestada"
    assert ev.motivo_para_omitir(Llamada(resultado="answered", duracion_s=30, transcripcion_texto="x")) == "dura menos de 60 s"
    assert ev.motivo_para_omitir(Llamada(resultado="answered", duracion_s=90, transcripcion_texto="")) == "sin transcripción"
    assert ev.motivo_para_omitir(Llamada(resultado="answered", duracion_s=90, transcripcion_texto="hola")) is None


def test_job_evalua_pendiente(db, llamada):
    modelo = ModeloFalso()
    assert ev.evaluar_pendientes(limite=50, cliente=modelo) >= 1
    db.expire_all()
    ll = db.get(Llamada, llamada.id)
    assert ll.estado == "ok" and ll.puntaje == 63.5 and ll.version_pauta == ev.VERSION_PAUTA
    assert ll.evaluacion["resultado_llamada"] == "agendo" and ll.evaluada_en is not None


def test_job_reintenta_y_luego_error(db, llamada):
    modelo = ModeloFalso(falla=True)
    for intento in range(1, ev.MAX_INTENTOS + 1):
        db.query(Llamada).filter(Llamada.id == llamada.id).update(
            {"updated_at": datetime.utcnow() - timedelta(minutes=10)})
        db.commit()
        ev.evaluar_pendientes(limite=50, cliente=modelo)
        db.expire_all()
        ll = db.get(Llamada, llamada.id)
        assert ll.intentos == intento
    assert ll.estado == "error"


def test_job_no_toma_las_recien_llegadas(db, llamada):
    db.query(Llamada).filter(Llamada.id == llamada.id).update({"updated_at": datetime.utcnow()})
    db.commit()
    ev.evaluar_pendientes(limite=50, cliente=ModeloFalso())
    db.expire_all()
    assert db.get(Llamada, llamada.id).estado == "pendiente"


def test_sin_clave_no_hace_nada(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ev.evaluar_pendientes() == 0


def test_job_registrado_en_el_programador(monkeypatch):
    from app.main import _registrar_jobs
    monkeypatch.setattr(settings, "evaluador_llamadas_enabled", True)
    agregados = []
    falso = SimpleNamespace(add_job=lambda *a, **k: agregados.append(k["id"]))
    assert "evaluador_llamadas" in _registrar_jobs(falso)
