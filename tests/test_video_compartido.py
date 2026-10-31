"""Link del video para el cliente (31-oct-2026): el código es estable aunque cambie el video, es anónimo y no filtra nada."""
import re
import pytest

from app.db import SessionLocal
from app.models import Proyecto
from app.routes import video_compartido as vc
from app.routes.video_compartido import codigo_compartir

TOKEN1, TOKEN2 = "a" * 24, "b" * 24
PID = "proyecto-prueba-video-compartido"


def _poner(db, extra):
    p = db.get(Proyecto, PID)
    if not p:
        p = Proyecto(id=PID, nombre="Edificio Prueba Interna", extra=extra)
        db.add(p)
    else:
        p.extra = extra
    db.commit()


def _video(token, estado="listo", poster=True):
    return {"estado": estado, "token": token, "nombre": "x.mp4", "poster": f"/uploads/{PID}/video/{token}/poster.jpg" if poster else "",
            "hls": f"/uploads/{PID}/video/{token}/master.m3u8", "duracion": 40, "calidades": [720, 480]}


@pytest.fixture(autouse=True)
def limpio(db):
    vc._mapa.clear(); vc._mapa_ts = 0.0
    yield
    p = db.get(Proyecto, PID)
    if p:
        db.delete(p); db.commit()


def test_codigo_estable_y_distinto_por_proyecto():
    a = codigo_compartir("proyecto-a")
    assert a == codigo_compartir("proyecto-a") and re.fullmatch(r"[0-9a-f]{16}", a)
    assert a != codigo_compartir("proyecto-b")


def test_codigo_depende_de_la_clave(monkeypatch):
    antes = codigo_compartir(PID)
    monkeypatch.setattr(vc.settings, "video_compartir_secret", "otra-clave", raising=False)
    assert codigo_compartir(PID) != antes     # cambiar la clave invalida todos los links


def test_el_link_no_cambia_al_reemplazar_el_video(client, db):
    cod = codigo_compartir(PID)
    _poner(db, {"video_ubicacion": _video(TOKEN1)})
    r1 = client.get(f"/video-compartido/{cod}")
    assert r1.status_code == 200 and r1.json()["estado"] == "listo" and r1.json()["token"] == TOKEN1
    _poner(db, {"video_ubicacion": _video(TOKEN2)})        # el asesor reemplaza el video: otro token
    r2 = client.get(f"/video-compartido/{cod}")
    assert r2.status_code == 200 and r2.json()["token"] == TOKEN2          # mismo link, video nuevo


def test_sin_video_o_procesando_dice_sin_video(client, db):
    cod = codigo_compartir(PID)
    _poner(db, {})
    assert client.get(f"/video-compartido/{cod}").json()["estado"] == "sin_video"
    _poner(db, {"video_ubicacion": _video(TOKEN1, estado="procesando")})
    assert client.get(f"/video-compartido/{cod}").json()["estado"] == "sin_video"


def test_codigo_desconocido_o_malo_da_el_mismo_404_sin_pistas(client, db):
    _poner(db, {"video_ubicacion": _video(TOKEN1)})
    for malo in ("0" * 16, "zzzz", "A" * 16, "a" * 40, "ab-cd-ef-gh-12-34"):
        r = client.get(f"/video-compartido/{malo}")
        assert r.status_code == 404 and r.json() == {"detail": "No encontrado"}


def test_no_filtra_otros_campos_ni_sesion(client, db):
    _poner(db, {"video_ubicacion": _video(TOKEN1), "notas_html": "SECRETO", "comercial": {"x": 1}})
    j = client.get(f"/video-compartido/{codigo_compartir(PID)}").json()
    assert set(j) == {"proyecto", "proyecto_id", "estado", "token", "poster", "duracion", "calidades"}
    assert "SECRETO" not in str(j)


def test_cache_corta_para_cloudflare(client, db):
    _poner(db, {"video_ubicacion": _video(TOKEN1)})
    r = client.get(f"/video-compartido/{codigo_compartir(PID)}")
    assert r.headers["cache-control"] == "public, max-age=30"


def test_proyecto_nuevo_se_encuentra_sin_reiniciar(client, db, monkeypatch):
    cod = codigo_compartir(PID)
    assert client.get(f"/video-compartido/{cod}").status_code == 404     # aún no existe (y arma el mapa)
    monkeypatch.setattr(vc, "_mapa_ts", vc._mapa_ts - 60)                 # pasó el mínimo de reintento
    _poner(db, {"video_ubicacion": _video(TOKEN1)})
    assert client.get(f"/video-compartido/{cod}").status_code == 200


def test_el_detalle_publico_trae_el_codigo_solo_con_video_listo(db):
    from app.routes.proyectos import _proyecto_public_dict
    _poner(db, {"video_ubicacion": _video(TOKEN1)})
    assert _proyecto_public_dict(db.get(Proyecto, PID))["video_compartir"] == codigo_compartir(PID)
    _poner(db, {"video_ubicacion": _video(TOKEN1, estado="error")})
    assert "video_compartir" not in _proyecto_public_dict(db.get(Proyecto, PID))
