"""Variaciones de video: acceso por código, subida por pedazos, combinaciones y ZIP."""
import json
import re
import shutil
import subprocess
import time
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import capacitaciones as cap
from app.routes import videos_variaciones as vv
from app.services import email_service

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado")

CORREO = "francisco.ceballos@bigcapital.cl"


def _clip(ruta, color, seg, tam="320x240", audio=True, fps=25):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={tam}:r={fps}:d={seg}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seg}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else ["-an"]) + [str(ruta)]
    subprocess.run(cmd, check=True)
    return ruta


def _dur(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout)


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(vv, "DIR", tmp_path / "videos")
    monkeypatch.setattr(cap, "DIR_TRABAJOS", tmp_path / "taller")
    monkeypatch.setattr(vv, "MARGEN_DISCO", 0)
    enviados = []
    monkeypatch.setattr(email_service, "enviar_html", lambda asunto, html, texto, para, adjuntos=(): enviados.append((para, texto)) or "enviado")
    app = FastAPI()
    app.include_router(vv.router)
    with TestClient(app) as c:
        c.enviados = enviados
        yield c


def _entrar(c):
    assert c.post("/videos/auth/solicitar", json={"email": CORREO}).status_code == 200
    codigo = re.search(r"\d{6}", c.enviados[-1][1]).group(0)
    r = c.post("/videos/auth/verificar", json={"email": CORREO, "codigo": codigo})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _subir(c, h, lote, clip, parte, ruta, nombre, trozo=20000):
    datos = ruta.read_bytes()
    desde = 0
    while desde < len(datos):
        r = c.post("/videos/subir", params=dict(lote=lote, clip=clip, parte=parte, desde=desde, nombre=nombre,
                                                archivo=ruta.name), content=datos[desde:desde + trozo], headers=h)
        assert r.status_code == 200, r.text
        desde = r.json()["recibido"]
    r = c.post("/videos/subir/terminar", json={"lote": lote, "clip": clip}, headers=h)
    assert r.status_code == 200, r.text


def test_correo_no_autorizado_no_recibe_codigo(cliente):
    r = cliente.post("/videos/auth/solicitar", json={"email": "otra@persona.cl"})
    assert r.status_code == 200 and cliente.enviados == []
    assert cliente.post("/videos/auth/verificar", json={"email": "otra@persona.cl", "codigo": "123456"}).status_code == 400


def test_codigo_malo_y_sin_sesion(cliente):
    cliente.post("/videos/auth/solicitar", json={"email": CORREO})
    assert cliente.post("/videos/auth/verificar", json={"email": CORREO, "codigo": "000000"}).status_code == 400
    assert cliente.post("/videos/lote").status_code == 401


def test_codigo_vale_una_sola_vez(cliente):
    _entrar(cliente)
    codigo = re.search(r"\d{6}", cliente.enviados[-1][1]).group(0)
    assert cliente.post("/videos/auth/verificar", json={"email": CORREO, "codigo": codigo}).status_code == 400


def test_flujo_completo_tres_hooks_un_desarrollo_un_cta(cliente, tmp_path):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    f = tmp_path / "f"
    f.mkdir()
    # hook 2 en otro tamaño y sin audio: obliga a recodificar esa combinación
    clips = [("a1" * 4, "hook", _clip(f / "gancho uno.mp4", "red", 2), "Gancho uno"),
             ("b2" * 4, "hook", _clip(f / "g2.mp4", "blue", 2, tam="640x360", audio=False, fps=30), "Gancho dos"),
             ("c3" * 4, "hook", _clip(f / "g3.mp4", "green", 2), "Gancho tres"),
             ("d4" * 4, "desarrollo", _clip(f / "des.mp4", "white", 3), "Explicación"),
             ("e5" * 4, "cta", _clip(f / "cta.mp4", "black", 1), "Llamado")]
    for cid, parte, ruta, nombre in clips:
        _subir(cliente, h, lote, cid, parte, ruta, nombre)
    orden = {"hook": ["a1" * 4, "b2" * 4, "c3" * 4], "desarrollo": ["d4" * 4], "cta": ["e5" * 4]}
    r = cliente.post("/videos/generar", json={"lote": lote, "orden": orden, "proyecto": "Crédito Hipotecario"}, headers=h)
    assert r.status_code == 200, r.text
    assert [c["archivo"] for c in r.json()["combos"]] == ["Crédito_Hipotecario_111.mp4", "Crédito_Hipotecario_211.mp4", "Crédito_Hipotecario_311.mp4"]
    for _ in range(240):
        t = cliente.get(f"/videos/lote/{lote}", headers=h).json()
        if t["estado"] in ("listo", "error"):
            break
        time.sleep(0.5)
    assert t["estado"] == "listo", t
    assert [c["estado"] for c in t["combos"]] == ["listo"] * 3
    assert t["combos"][0]["partes"] == {"hook": "gancho uno.mp4", "desarrollo": "des.mp4", "cta": "cta.mp4"}
    assert "320×240" in t["combos"][0]["detalle"]
    assert "640×360" in t["combos"][1]["detalle"]
    assert cliente.get(f"/videos/descargar/{lote}/zip", headers=h).status_code == 401      # la sesión no sirve de entrada
    ent = cliente.post(f"/videos/descargar/{lote}/entrada", headers=h).json()["t"]
    assert cliente.get("/videos/lote/" + lote, headers={"Authorization": "Bearer " + ent}).status_code == 401
    z = cliente.get(f"/videos/descargar/{lote}/zip", params={"t": ent})
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    zp = tmp_path / "salida.zip"
    zp.write_bytes(z.content)
    with zipfile.ZipFile(zp) as zf:
        assert zf.namelist() == ["LEEME.txt"] + [c["archivo"] for c in t["combos"]]
        leeme = zf.read("LEEME.txt").decode()
        assert "Crédito_Hipotecario_111.mp4  =  gancho uno.mp4  +  des.mp4  +  cta.mp4" in leeme
        zf.extractall(tmp_path / "x")
    for c in t["combos"]:
        assert abs(_dur(tmp_path / "x" / c["archivo"]) - 6.0) < 0.6      # hook + desarrollo + cta = 2 + 3 + 1
    for c in t["combos"]:      # uniones sin cortes: imagen y sonido duran lo mismo y no falta ni sobra ningún cuadro
        r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                            "stream=codec_type,duration,nb_read_packets", "-of", "json", str(tmp_path / "x" / c["archivo"])],
                           capture_output=True, text=True, check=True)
        flujos = {x["codec_type"]: x for x in json.loads(r.stdout)["streams"]}
        assert abs(float(flujos["video"]["duration"]) - float(flujos["audio"]["duration"])) < 0.05
        assert c["id"] != "H2-D1-C1" or int(flujos["video"]["nb_read_packets"]) == 2 * 30 + 3 * 30 + 1 * 30   # a 30 fps del hook
        assert c["id"] == "H2-D1-C1" or int(flujos["video"]["nb_read_packets"]) == 6 * 25
    assert cliente.get(f"/videos/descargar/{lote}/video", params={"combo": "H2-D1-C1", "t": ent}).status_code == 200


def test_pedazo_fuera_de_lugar_devuelve_lo_recibido(cliente, tmp_path):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    r = cliente.post("/videos/subir", params=dict(lote=lote, clip="a1a1a1a1", parte="hook", desde=0, nombre="x"),
                     content=b"1234", headers=h)
    assert r.json() == {"recibido": 4}
    r = cliente.post("/videos/subir", params=dict(lote=lote, clip="a1a1a1a1", parte="hook", desde=0, nombre="x"),
                     content=b"1234", headers=h)
    assert r.status_code == 409 and r.json()["recibido"] == 4


def test_archivo_que_no_es_video_se_rechaza(cliente, tmp_path):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    cliente.post("/videos/subir", params=dict(lote=lote, clip="a1a1a1a1", parte="hook", desde=0, nombre="x"),
                 content=b"esto no es un video", headers=h)
    r = cliente.post("/videos/subir/terminar", json={"lote": lote, "clip": "a1a1a1a1"}, headers=h)
    assert r.status_code == 422


def test_otro_usuario_no_ve_el_lote(cliente, monkeypatch):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    otro = {"Authorization": "Bearer " + vv._crear_token("nicolas.soto@bigcapital.cl")}
    assert cliente.get(f"/videos/lote/{lote}", headers=otro).status_code == 404


def test_faltan_partes_y_tope_de_combinaciones(cliente, tmp_path):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    r = cliente.post("/videos/generar", json={"lote": lote, "orden": {"hook": [], "desarrollo": [], "cta": []}}, headers=h)
    assert r.status_code == 400


def test_barrido_borra_lotes_de_mas_de_tres_dias(cliente):
    h = _entrar(cliente)
    lote = cliente.post("/videos/lote", headers=h).json()["id"]
    ruta = vv._lote_dir(lote) / "lote.json"
    d = json.loads(ruta.read_text())
    d["actualizado"] = int(time.time()) - vv.VIDA_SEG - 10
    ruta.write_text(json.dumps(d))
    vv._barrer()
    assert not vv._lote_dir(lote).exists()


def test_codigo_hook_cta_desarrollo():
    assert vv._codigo(1, 2, 1) == "112"          # hook 1, desarrollo 2, CTA 1
    assert vv._codigo(2, 1, 3) == "231"
    assert vv._codigo(1, 1, 10) == "1-10-1"
