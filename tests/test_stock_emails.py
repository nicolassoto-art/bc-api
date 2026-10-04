"""Correos "Stock interno" (proyectos sin revisar · fallas en fichas) — 2026-10-05."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import _registrar_jobs, app
from app.models import Proyecto, Unidad
from app.services import stock_emails as se
from app.settings import settings

AHORA = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)  # lunes 09:00 Chile

# Voseo y anglicismos prohibidos en textos para el equipo (CLAUDE.md global).
PROHIBIDAS = re.compile(
    r"\b(tenés|sos|querés|podés|revisá|subí|marcá|hacé|poné|mirá|fijate|dashboard|lead|leads|stage|"
    r"score|pipeline|follow-up|breach|deal|scraper|FAIL|Canario)\b", re.IGNORECASE)


def _pid():
    return "test-se-" + uuid.uuid4().hex[:8]


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _proyecto(db, pid, publicado=True, activo=True, ok_hace=None, **extra):
    ok = _naive(AHORA - timedelta(days=ok_hace)) if ok_hace is not None else None
    db.add(Proyecto(id=pid, nombre=f"Proyecto {pid}", inmobiliaria="Iroyal", comuna="Ñuñoa", activo=activo,
                    stock_ok_at=ok, stock_updated_at=ok,
                    extra={"publicar_en_catalogo": publicado, "timeline": [], **extra}))
    db.commit()


def _fila(data, pid):
    for sec in data["secciones"]:
        for g in sec.get("grupos", []):
            for f in g["filas"]:
                if f["id"] == pid:
                    return sec["clave"], f
    return None, None


def test_sin_revisar_solo_publicados_atrasados(db):
    a, b, c = _pid(), _pid(), _pid()
    _proyecto(db, a, ok_hace=5)
    _proyecto(db, b, ok_hace=5, publicado=False)
    _proyecto(db, c, ok_hace=1)
    data = se.build_sin_revisar(db, AHORA)
    sec, f = _fila(data, a)
    assert sec == "sin_revisar" and f["dias"] == 5
    assert _fila(data, b) == (None, None) and _fila(data, c) == (None, None)
    html = se.html_sin_revisar(data)
    assert f"proyecto.html?id={a}#tab=stock" in html
    assert not PROHIBIDAS.search(re.sub(r"<[^>]+>", " ", html))
    assert re.search(r"\d\d/\d\d/\d{4}", html)
    assert se.asunto_sin_revisar(data).startswith("Stock interno · ")


def test_send_sin_revisar_silencio_destinatarios_y_apagado(monkeypatch):
    enviados = []
    monkeypatch.setattr(se, "enviar_html", lambda *a, **k: enviados.append(a) or "enviado")
    monkeypatch.setattr(settings, "stock_sin_revisar_enabled", False)
    assert se.send_sin_revisar() == "deshabilitado" and not enviados
    monkeypatch.setattr(settings, "stock_sin_revisar_enabled", True)
    monkeypatch.setattr(se, "build_sin_revisar", lambda db, now=None: {
        "n": 0, "cuenta": {}, "secciones": [], "fecha_cl": "x", "n_urgentes": 0})
    assert se.send_sin_revisar() == "sin_novedad" and not enviados
    monkeypatch.setattr(se, "build_sin_revisar", lambda db, now=None: {
        "n": 1, "cuenta": {"sin_revisar": 1}, "secciones": [], "fecha_cl": "x", "n_urgentes": 0})
    assert se.send_sin_revisar() == "enviado"
    asunto, _html, _txt, para = enviados[0][:4]
    assert para == ["beatriz.vinet@bigcapital.cl", "alvaro.meneses@bigcapital.cl",
                    "pamela.scheel@bigcapital.cl", "nicolas.soto@bigcapital.cl"]
    assert asunto == "Stock interno · 1 proyecto sin revisar (1 a mano)"


def _claves(data, pid):
    out = {}
    for sec in data["secciones"]:
        for x in sec["proyectos"]:
            if x["id"] == pid:
                for f in x["filas"]:
                    out[f["codigo"]] = f
    return out


def test_fallas_siembra_nuevas_y_resueltas(db):
    pid = _pid()
    _proyecto(db, pid, ok_hace=1)
    d1 = se.build_fallas(db, AHORA, estado={})
    c1 = _claves(d1, pid)
    assert d1["sembrando"] and c1 and not any(f["nueva"] for f in c1.values())
    html1 = se.html_fallas(d1)
    assert "abierta desde antes del 05/10/2026" in html1 and ">NUEVA</span>" not in html1
    # Día siguiente: aparece una falla nueva (sin comuna) y otra se resuelve.
    p = db.get(Proyecto, pid)
    p.comuna = None
    p.foto_principal_url = "f.jpg"
    db.commit()
    d2 = se.build_fallas(db, AHORA + timedelta(days=1), estado=d1["estado_nuevo"])
    c2 = _claves(d2, pid)
    assert c2["ficha.sin_comuna"]["nueva"] is True
    assert not c2.get("material.sin_fachada")
    assert any(r["texto"] == "Sin foto de fachada" for r in d2["resueltas"])
    assert not d2["sembrando"]


def test_falla_que_vuelve_antes_de_7_dias_no_es_nueva(db):
    pid = _pid()
    _proyecto(db, pid, ok_hace=1)
    clave = f"{pid}::ficha.sin_direccion"
    for dias_ausente, nueva in ((3, False), (10, True)):
        visto = (AHORA - timedelta(days=dias_ausente)).date().isoformat()
        estado = {"fallas_sembrada": "2026-09-01",
                  "fallas": {clave: {"first_seen": "2026-09-01", "last_seen": visto, "sembrada": False}}}
        d = se.build_fallas(db, AHORA, estado=estado)
        assert _claves(d, pid)["ficha.sin_direccion"]["nueva"] is nueva


def test_estado_danado_se_aparta(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    (tmp_path / se.ARCHIVO_ESTADO).write_text("{no es json", "utf-8")
    assert se.cargar_estado() == {}
    assert any(p.name.startswith(se.ARCHIVO_ESTADO + ".corrupto-") for p in tmp_path.iterdir())


def test_estado_vive_fuera_de_uploads():
    assert settings.state_path.resolve() != settings.upload_path.resolve()
    assert settings.upload_path.resolve() not in settings.state_path.resolve().parents


def test_correo_de_fallas_acotado_y_pdf():
    filas = [{"codigo": f"x.{i}", "texto": "Plan de pago incompleto: falta pie %, valor de reserva " * 2,
              "severidad": "critica", "tab": "general", "clave": f"p{i}::x", "nueva": False,
              "sembrada": False, "dias": 3} for i in range(40)]
    data = {"fecha_cl": "05/10/2026 · 09:04", "n_fichas": 60, "n_criticas": 2400, "n_nuevas": 0,
            "sembrando": False, "fecha_siembra": "2026-10-01", "resueltas": [],
            "resumen_textos": {"textos.sin_info_relevante": 3, "textos.sin_porque_si": 4},
            "secciones": [{"clave": "publicados", "titulo": "Publicadas", "n_fallas": 2400,
                           "proyectos": [{"id": f"p{j}", "nombre": f"P{j}", "inmobiliaria": "Ecasa",
                                          "filas": filas, "n_crit": 40} for j in range(60)]}],
            "pdf_items": [{"id": "p1", "proyecto": "P1", "inmobiliaria": "Ecasa", "texto": "Sin comuna",
                           "tab": "general"}]}
    html = se.html_fallas_acotado(data)
    assert len(html.encode("utf-8")) < se.MAX_BYTES and "PDF adjunto" in html
    assert not PROHIBIDAS.search(re.sub(r"<[^>]+>", " ", html))
    assert se.pdf_fallas(data)[:4] == b"%PDF"
    assert se.asunto_fallas(data) == "Stock interno · fallas en 60 fichas (2400 críticas)"


def test_send_fallas_no_envia_sin_fallas_y_guarda_estado_al_enviar(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    monkeypatch.setattr(settings, "fallas_fichas_enabled", True)
    enviados = []
    monkeypatch.setattr(se, "enviar_html", lambda *a, **k: enviados.append(a) or "enviado")
    vacio = {"n_fichas": 0, "estado_nuevo": {"fallas": {}, "fallas_sembrada": "2026-10-05"}}
    monkeypatch.setattr(se, "build_fallas", lambda db, now=None, estado=None: vacio)
    assert se.send_fallas() == "sin_novedad" and not enviados
    assert json.loads((tmp_path / se.ARCHIVO_ESTADO).read_text())["jobs"]["fallas"]["resultado"] == "sin novedad"


def test_vistas_previas_no_escriben_estado(client, admin, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", str(tmp_path))
    _, h = admin
    for url in ("/admin/fallas-fichas/preview", "/admin/stock-sin-revisar/preview", "/admin/stock-interno/conteo"):
        r = client.get(url, headers=h)
        assert r.status_code == 200, (url, r.text[:300])
    assert not (tmp_path / se.ARCHIVO_ESTADO).exists()
    r = client.get("/admin/fallas-fichas/pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert client.get("/admin/fallas-fichas/preview").status_code in (401, 403)


class _Prog:
    def __init__(self):
        self.jobs = {}

    def add_job(self, func, trigger, id, **kw):
        self.jobs[id] = trigger


def test_registrar_jobs_respeta_los_interruptores(monkeypatch):
    prog = _Prog()
    _registrar_jobs(prog)
    assert "daily_stock_report" in prog.jobs and "stock_sin_revisar" not in prog.jobs
    monkeypatch.setattr(settings, "stock_sin_revisar_enabled", True)
    monkeypatch.setattr(settings, "fallas_fichas_enabled", True)
    prog = _Prog()
    _registrar_jobs(prog)
    assert {"daily_stock_report", "stock_sin_revisar", "fallas_fichas", "inbox_processor"} <= set(prog.jobs)
    assert "minute='2'" in str(prog.jobs["stock_sin_revisar"]) and "minute='4'" in str(prog.jobs["fallas_fichas"])


def test_arranque_real_de_la_api():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
