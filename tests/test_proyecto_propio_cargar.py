"""Carga de Laguna Centro Torre H a stock propio: ensayo sin escrituras, carga completa,
segunda vuelta sin duplicar y nunca una petición directa a JetBrokers."""
import json
from pathlib import Path

import pytest

from app.models import Proyecto
from app.settings import settings
from scripts.proyecto_propio.armar import JB_ID, PROYECTO_ID, es_url_nuestra, lista_documentos
from scripts.proyecto_propio.cargar import bajar_seguro, cargar

D = Path(__file__).resolve().parents[1] / "scripts/data/laguna_centro_torre_h"
FICHA = json.loads((D / "ficha.json").read_text(encoding="utf-8"))
DOCS = {d["file_id"] for d in lista_documentos(FICHA)}
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _limpio(tmp_path, monkeypatch, db):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "bc_api_service_token", "sk_test_laguna")
    p = db.get(Proyecto, PROYECTO_ID)
    if p:
        db.delete(p)
        db.commit()
    yield
    db.expire_all()
    p = db.get(Proyecto, PROYECTO_ID)
    if p:
        db.delete(p)
        db.commit()


def _bajar(pedidas):
    def f(url):
        assert es_url_nuestra(url), url
        pedidas.append(url)
        return PDF if any(i in url for i in DOCS) else JPG
    return f


def test_bajar_seguro_rechaza_jetbrokers():
    for u in ("https://jetgallery.jetbrokers.io/api/gallery/download/uv13koru/x",
              "https://api.jetbrokers.io/api/file-unauthenticated/download/x"):
        with pytest.raises(ValueError):
            bajar_seguro(u)


def test_ensayo_no_escribe(client, admin):
    _, h = admin
    pedidas = []
    r = cargar(client, D, aplicar=False, bajar=_bajar(pedidas), headers=h)
    assert r["proyecto"] == "ensayo" and r["estado_previo"] == "no existe"
    assert r["plan"] == {"unidades": 83, "imagenes": 39, "documentos": 2, "planos": 25}
    assert pedidas == []
    assert client.get(f"/proyectos/{PROYECTO_ID}", headers=h).status_code == 404


def test_aplicar_completo_e_idempotente(client, admin):
    _, h = admin
    pedidas = []
    r1 = cargar(client, D, aplicar=True, bajar=_bajar(pedidas), headers=h)
    assert r1["errores"] == [], r1["errores"]
    assert r1["proyecto"] == "creado"
    r2 = cargar(client, D, aplicar=True, bajar=_bajar(pedidas), headers=h)
    assert r2["errores"] == [], r2["errores"]
    assert r2["proyecto"] == "actualizado"
    assert pedidas and all(es_url_nuestra(u) for u in pedidas)

    p = client.get(f"/proyectos/{PROYECTO_ID}", headers=h).json()
    disp = [u for u in p["unidades"] if u["disponible"]]
    assert len(disp) == 83 and len(p["unidades"]) == 83
    u = next(x for x in p["unidades"] if x["numero"] == "1512")
    assert u["precio_lista_uf"] == 2955 and u["descuento_pct"] == 10 and u["bono_pie_pct"] == 10
    assert abs(u["precio_final_uf"] - 2659.5) < 0.01
    fotos = [i for i in p["imagenes"] if not i["categoria"].startswith("jb-planta-")]
    planos = [i for i in p["imagenes"] if i["categoria"].startswith("jb-planta-")]
    assert len(fotos) == 39 and len(planos) == 25  # sin duplicar en la segunda vuelta
    assert sum(i["es_principal"] for i in fotos) == 1
    assert p["foto_principal_url"].startswith(f"/uploads/{PROYECTO_ID}/")
    assert all(m["planta_url"].startswith(f"/uploads/{PROYECTO_ID}/") for m in p["extra"]["modelos"])
    assert sorted(d["tipo"] for d in p["documentos"]) == ["Brochure", "Plano"]
    assert p["extra"]["publicar_en_catalogo"] is True and p["extra"]["jb_id"] == JB_ID
    assert p["extra"]["comercial"]["planes_pago"][0]["pie_pct"] == 20
    assert "jetbrokers" not in json.dumps(p)

    pub = client.get(f"/proyectos/public/{JB_ID}", headers={"Authorization": "Bearer sk_test_laguna"})
    assert pub.status_code == 200 and pub.json()["id"] == PROYECTO_ID


def test_conserva_ediciones_manuales_y_limpia_urls_jetbrokers(client, admin, db):
    _, h = admin
    cargar(client, D, aplicar=True, bajar=_bajar([]), headers=h)
    p = db.get(Proyecto, PROYECTO_ID)
    p.notas = "Nota manual de Nicolás"
    p.extra = {**p.extra, "porque_si": ["Laguna navegable"]}
    db.commit()
    client.post(f"/proyectos/{PROYECTO_ID}/imagenes/url", headers=h,
                json={"url": "https://api.jetbrokers.io/api/file-unauthenticated/download/viejo",
                      "categoria": "Otro"})
    r = cargar(client, D, aplicar=True, bajar=_bajar([]), headers=h)
    assert r["errores"] == [] and r["urls_jetbrokers_previas"]
    q = client.get(f"/proyectos/{PROYECTO_ID}", headers=h).json()
    assert q["notas"] == "Nota manual de Nicolás"
    assert q["extra"]["porque_si"] == ["Laguna navegable"]
    assert "jetbrokers" not in json.dumps(q)


def test_restaura_desde_papelera(client, admin, db):
    _, h = admin
    cargar(client, D, aplicar=True, bajar=_bajar([]), headers=h)
    assert client.delete(f"/proyectos/{PROYECTO_ID}", headers=h).status_code in (200, 204)
    r = cargar(client, D, aplicar=True, bajar=_bajar([]), headers=h)
    assert r["estado_previo"] == "papelera" and r["errores"] == []
    assert client.get(f"/proyectos/{PROYECTO_ID}", headers=h).status_code == 200
