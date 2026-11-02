"""Reemplazar el archivo de una foto (02-nov-2026): trae a nuestro disco las fotos que eran enlaces externos."""
import uuid
from app.models import Proyecto, Imagen
from app.settings import settings

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a3a80000000049454e44ae426082")


def _proyecto_con_externa(db, principal=True):
    pid = "prueba-interna-" + uuid.uuid4().hex[:8]
    db.add(Proyecto(id=pid, nombre="Prueba Interna", foto_principal_url="https://externo.test/a.jpg" if principal else None))
    db.add(Imagen(id="img-" + uuid.uuid4().hex[:10], proyecto_id=pid, url="https://externo.test/a.jpg",
                  categoria="Fachada", es_principal=principal, orden=3, bytes=0, mime="image/external"))
    db.commit()
    img = db.query(Imagen).filter(Imagen.proyecto_id == pid).first()
    return pid, img.id


def test_trae_externa_y_conserva_datos(client, db, admin):
    _, h = admin
    pid, iid = _proyecto_con_externa(db)
    r = client.post(f"/proyectos/{pid}/imagenes/{iid}/archivo", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] == iid and d["url"] == f"/uploads/{pid}/{iid}.png"
    assert d["categoria"] == "Fachada" and d["orden"] == 3 and d["es_principal"] is True
    assert (settings.upload_path / pid / f"{iid}.png").read_bytes() == PNG
    db.expire_all()
    assert db.get(Proyecto, pid).foto_principal_url == f"/uploads/{pid}/{iid}.png"


def test_rechaza_pdf_vacio_y_ajena(client, db, admin):
    _, h = admin
    pid, iid = _proyecto_con_externa(db, principal=False)
    assert client.post(f"/proyectos/{pid}/imagenes/{iid}/archivo", headers=h, files={"file": ("a.pdf", b"%PDF", "application/pdf")}).status_code == 415
    assert client.post(f"/proyectos/{pid}/imagenes/{iid}/archivo", headers=h, files={"file": ("a.png", b"", "image/png")}).status_code == 400
    otro, _ = _proyecto_con_externa(db, principal=False)
    assert client.post(f"/proyectos/{otro}/imagenes/{iid}/archivo", headers=h, files={"file": ("a.png", PNG, "image/png")}).status_code == 404


def test_sin_sesion_401(client, db):
    pid, iid = _proyecto_con_externa(db, principal=False)
    assert client.post(f"/proyectos/{pid}/imagenes/{iid}/archivo", files={"file": ("a.png", PNG, "image/png")}).status_code in (401, 403)


def test_traer_externas_baja_y_reporta(client, db, admin, monkeypatch):
    import app.routes.imagenes as mod
    _, h = admin
    pid, iid = _proyecto_con_externa(db)
    db.add(Imagen(id="img-" + uuid.uuid4().hex[:10], proyecto_id=pid, url="https://bloqueado.test/b.jpg", categoria="Interior", es_principal=False, orden=4, bytes=0, mime="image/external"))
    db.add(Imagen(id="img-" + uuid.uuid4().hex[:10], proyecto_id=pid, url=f"/uploads/{pid}/propia.jpg", categoria="Interior", es_principal=False, orden=5, bytes=10, mime="image/jpeg"))
    db.commit()
    monkeypatch.setattr(mod, "_host_publico", lambda u: True)

    class Resp:
        def __init__(self, code, content): self.status_code, self.content = code, content

    class Cli:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return Resp(200, PNG) if "externo" in url else Resp(480, b'{"ipBanned"}')
    monkeypatch.setattr(mod.httpx, "Client", Cli)
    r = client.post(f"/proyectos/{pid}/imagenes/traer-externas", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 2 and d["traidas"] == 1, d
    malo = [x for x in d["resultados"] if not x["ok"]][0]
    assert "480" in malo["motivo"]
    db.expire_all()
    assert db.get(Imagen, iid).url == f"/uploads/{pid}/{iid}.png"
    assert db.get(Proyecto, pid).foto_principal_url == f"/uploads/{pid}/{iid}.png"


def test_host_publico_bloquea_red_interna():
    import app.routes.imagenes as mod
    assert mod._host_publico("https://127.0.0.1/a.jpg") is False
    assert mod._host_publico("http://ejemplo.com/a.jpg") is False
    assert mod._host_publico("https://localhost/a.jpg") is False
