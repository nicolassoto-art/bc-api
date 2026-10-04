"""Informe de las 09:00 al equipo y fin del de las 13:00 — 2026-10-05."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.main import _registrar_jobs
from app.models import Proyecto
from app.services import daily_report as dr
from app.settings import settings


class _SMTP:
    enviados = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        _SMTP.enviados.append(msg)


@pytest.fixture
def smtp(monkeypatch, tmp_path):
    _SMTP.enviados = []
    monkeypatch.setattr(dr.smtplib, "SMTP", _SMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_user", "sistema@bigcapital.cl")
    monkeypatch.setattr(settings, "smtp_pass", "x")
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    return _SMTP


def test_ya_no_existen_los_destinatarios_viejos():
    for campo in ("daily_report_to", "daily_report_cc", "daily_report_operator_name",
                  "operador_report_enabled", "operador_report_to"):
        assert not hasattr(settings, campo), campo
    assert not hasattr(dr, "send_operador_today_report")


def test_agenda_sin_informe_de_las_13():
    class P:
        jobs = {}

        def add_job(self, func, trigger, id, **kw):
            self.jobs[id] = trigger
    prog = P()
    _registrar_jobs(prog)
    assert "operador_today_report" not in prog.jobs
    assert "minute='0'" in str(prog.jobs["daily_stock_report"]) and "hour='9'" in str(prog.jobs["daily_stock_report"])


def test_informe_va_a_los_cuatro_en_para(smtp):
    assert dr.send_daily_report() == "enviado"
    msg = smtp.enviados[-1]
    assert msg["To"] == ("beatriz.vinet@bigcapital.cl, alvaro.meneses@bigcapital.cl, "
                         "pamela.scheel@bigcapital.cl, nicolas.soto@bigcapital.cl")
    assert msg["Cc"] is None


def test_prueba_manual_va_solo_a_quien_la_pide(client, admin, smtp):
    _, h = admin
    r = client.post("/admin/daily-report/test", headers=h)
    assert r.status_code == 200 and r.json()["sent_to"] == ["admin@test.local"]
    assert smtp.enviados[-1]["To"] == "admin@test.local"


def test_mejoras_cuentan_a_cualquier_persona_y_nunca_a_robots(db):
    pid = "test-inf-" + uuid.uuid4().hex[:8]
    ayer = datetime.now(timezone.utc) - timedelta(days=1)
    f = ayer.replace(hour=15, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    tl = [
        {"id": "tl-1", "tipo": "Edición", "fecha": f, "usuario": "pamela.scheel@bigcapital.cl", "detalles": "Ficha"},
        {"id": "tl-2", "tipo": "Excel Stock", "fecha": f, "usuario": "beatriz.vinet@bigcapital.cl", "detalles": "Excel"},
        {"id": "tl-3", "tipo": "Excel Stock", "fecha": f, "usuario": "aj-urbana-sync@bigcapital.cl",
         "origen_auto": None, "detalles": "sync"},
        {"id": "tl-4", "tipo": "Alerta", "fecha": f, "usuario": "mnk-scraper@bigcapital.cl", "detalles": "x"},
    ]
    db.add(Proyecto(id=pid, nombre=pid, extra={"timeline": tl}))
    db.commit()
    p = db.get(Proyecto, pid)
    desde = datetime.now(timezone.utc) - timedelta(days=3)
    grupos, n, _ = dr._operador_actividad([p], desde)
    usuarios = {ev["usuario"] for g in grupos for ev in g["eventos"]}
    assert usuarios == {"pamela.scheel@bigcapital.cl", "beatriz.vinet@bigcapital.cl"} and n == 2
    html = dr._operador_section_html("el equipo", grupos, n, 1, "el día anterior", titulo="📋 Mejoras")
    assert "Pamela Scheel" in html and "Beatriz Vinet" in html


def test_informe_se_arma_en_lunes_con_resumen_semanal(db):
    data = dr.build_daily_report(db, forzar_semana=True)
    html = dr._build_html(data)
    assert "Resumen de la semana anterior" in html and data["operador_nombre"] == "el equipo"
