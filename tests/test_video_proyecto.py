"""Video del edificio: subida en pedazos retomable, conversión a HLS y estado en extra.video_ubicacion."""
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from app.models import Proyecto
from app.routes import video_proyecto as vp
from app.settings import settings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="falta ffmpeg")


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "DIR", tmp_path / "trabajos")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(vp, "PEDAZO", 16 * 1024)            # pedazos chicos: el video de prueba pesa poco
    monkeypatch.setattr(vp, "_lanzar", lambda jid: None)     # el proceso se llama a mano, sin hilos
    return tmp_path


@pytest.fixture
def proyecto(db):
    pid = "prueba-video-" + uuid.uuid4().hex[:6]
    db.add(Proyecto(id=pid, nombre="Edificio Prueba Interna"))
    db.commit()
    yield pid
    p = db.get(Proyecto, pid)
    if p:
        db.delete(p)
        db.commit()


def _video(ruta: Path, alto=720, seg=3, audio=True):
    ancho = alto * 16 // 9 // 2 * 2
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={ancho}x{alto}:rate=25:duration={seg}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seg}", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(ruta)]
    subprocess.run(cmd, check=True)
    return ruta.read_bytes()


def _subir(client, h, pid, datos: bytes, nombre="edificio.mp4"):
    r = client.post(f"/proyectos/{pid}/video/iniciar", headers=h, json={"nombre": nombre, "tamano": len(datos), "mime": "video/mp4"})
    assert r.status_code == 200, r.text
    jid = r.json()["trabajo_id"]
    pedazo = r.json()["pedazo_bytes"]
    desde = 0
    while desde < len(datos):
        r = client.post(f"/proyectos/{pid}/video/pedazo-crudo", headers=h, params={"trabajo_id": jid, "desde": desde},
                        content=datos[desde:desde + pedazo])
        assert r.status_code == 200 and r.json()["ok"], r.text
        desde = r.json()["recibido"]
    return jid


def test_elegir_calidades():
    assert vp.elegir_calidades(2160) == [2160, 1080]
    assert vp.elegir_calidades(1440) == [1080, 720]
    assert vp.elegir_calidades(1080) == [1080, 720]
    assert vp.elegir_calidades(1088) == [1080, 720]
    assert vp.elegir_calidades(720) == [720, 480]
    assert vp.elegir_calidades(480) == [480]
    assert vp.elegir_calidades(360) == [360]


def test_sin_sesion_y_no_video(client, admin, proyecto, entorno):
    assert client.post(f"/proyectos/{proyecto}/video/iniciar", json={"nombre": "a.mp4", "tamano": 10}).status_code in (401, 403)
    _, h = admin
    r = client.post(f"/proyectos/{proyecto}/video/iniciar", headers=h, json={"nombre": "foto.pdf", "tamano": 10})
    assert r.status_code == 400
    r = client.post(f"/proyectos/{proyecto}/video/iniciar", headers=h, json={"nombre": "a.mp4", "tamano": 3 * 1024 ** 3})
    assert r.status_code == 413


def test_subida_retomable_y_hls(client, admin, db, proyecto, entorno):
    _, h = admin
    datos = _video(entorno / "origen.mp4", alto=720)
    # Subida partida con un pedazo repetido y uno adelantado: nunca daña el archivo.
    r = client.post(f"/proyectos/{proyecto}/video/iniciar", headers=h, json={"nombre": "edificio.mp4", "tamano": len(datos), "mime": "video/mp4"})
    jid, pedazo = r.json()["trabajo_id"], r.json()["pedazo_bytes"]
    p1 = client.post(f"/proyectos/{proyecto}/video/pedazo-crudo", headers=h, params={"trabajo_id": jid, "desde": 0}, content=datos[:pedazo])
    assert p1.json()["recibido"] == pedazo
    # adelantado (salta un pedazo): no se guarda, dice cuánto llegó
    adel = client.post(f"/proyectos/{proyecto}/video/pedazo-crudo", headers=h, params={"trabajo_id": jid, "desde": pedazo * 2}, content=datos[pedazo * 2:pedazo * 3])
    assert adel.json()["ok"] is False and adel.json()["recibido"] == pedazo
    # "se cayó": el cliente consulta cuánto llegó y sigue desde ahí
    est = client.get(f"/proyectos/{proyecto}/video/estado-subida/{jid}", headers=h).json()
    assert est["recibido"] == pedazo and est["tamano"] == len(datos)
    desde = est["recibido"]
    while desde < len(datos):
        r = client.post(f"/proyectos/{proyecto}/video/pedazo-crudo", headers=h, params={"trabajo_id": jid, "desde": desde}, content=datos[desde:desde + pedazo])
        desde = r.json()["recibido"]
    # terminar antes de tiempo no aplica; ahora sí
    assert client.post(f"/proyectos/{proyecto}/video/terminar", headers=h, json={"trabajo_id": jid}).json()["estado"] == "procesando"
    v = client.get(f"/proyectos/{proyecto}/video", headers=h).json()["video"]
    assert v["estado"] == "procesando"
    vp._procesar(jid)
    v = client.get(f"/proyectos/{proyecto}/video", headers=h).json()["video"]
    assert v["estado"] == "listo", v
    assert v["calidades"] == [720, 480]
    raiz = Path(settings.upload_dir) / proyecto / "video" / v["token"]
    master = (raiz / "master.m3u8").read_text()
    assert "720p/index.m3u8" in master and "480p/index.m3u8" in master and "RESOLUTION" in master
    assert list((raiz / "720p").glob("seg*.ts")) and (raiz / "poster.jpg").exists()
    assert v["hls"] == f"/uploads/{proyecto}/video/{v['token']}/master.m3u8"
    # el original y la carpeta de trabajo se borran
    assert not (entorno / "trabajos" / jid).exists()
    # El PUT del navegador (copia vieja, sin video) NO borra ni pisa el video
    db.expire_all()
    p = db.get(Proyecto, proyecto)
    body = client.get(f"/proyectos/{proyecto}", headers=h).json()
    body["extra"] = {"puntos_interes": ["x"]}
    body.pop("id", None)
    assert client.put(f"/proyectos/{proyecto}", headers=h, json=body).status_code == 200
    assert client.get(f"/proyectos/{proyecto}/video", headers=h).json()["video"]["estado"] == "listo"
    # Quitar borra los archivos y la clave
    assert client.delete(f"/proyectos/{proyecto}/video", headers=h).status_code == 200
    assert client.get(f"/proyectos/{proyecto}/video", headers=h).json()["video"] is None
    assert not raiz.exists()


def test_video_no_leible_da_error_claro(client, admin, proyecto, entorno):
    _, h = admin
    jid = _subir(client, h, proyecto, b"esto no es un video" * 50)
    client.post(f"/proyectos/{proyecto}/video/terminar", headers=h, json={"trabajo_id": jid})
    vp._procesar(jid)
    v = client.get(f"/proyectos/{proyecto}/video", headers=h).json()["video"]
    assert v["estado"] == "error" and v["mensaje"]


def test_cancelar_subida_borra_lo_recibido(client, admin, proyecto, entorno):
    _, h = admin
    r = client.post(f"/proyectos/{proyecto}/video/iniciar", headers=h, json={"nombre": "a.mp4", "tamano": 1000})
    jid = r.json()["trabajo_id"]
    assert client.post(f"/proyectos/{proyecto}/video/cancelar", headers=h, json={"trabajo_id": jid}).status_code == 200
    assert client.get(f"/proyectos/{proyecto}/video/estado-subida/{jid}", headers=h).status_code == 404
