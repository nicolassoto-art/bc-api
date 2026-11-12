"""GET /proyectos/public/{id}: encuentra el proyecto por external_id, jb_id o id propio,
sin cargar todo el catálogo (12-nov-2026: tardaba ~1,5 s y con carga llegaba a 100 s)."""
import pytest
from sqlalchemy import event

from app.settings import settings
from app.db import engine
from app.models import Proyecto

TOKEN = "sk_test_detalle_publico"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def proyectos(db, monkeypatch):
    monkeypatch.setattr(settings, "bc_api_service_token", TOKEN)
    filas = [
        Proyecto(id="tdp-publicado", nombre="Prueba Interna Publicado", activo=True,
                 extra={"publicar_en_catalogo": True, "external_id": "tdp-ext-1", "jb_id": "tdpJb001"}),
        Proyecto(id="tdp-no-publicado", nombre="Prueba Interna Oculto", activo=True,
                 extra={"publicar_en_catalogo": False, "external_id": "tdp-ext-2"}),
        Proyecto(id="tdp-inactivo", nombre="Prueba Interna Inactivo", activo=False,
                 extra={"publicar_en_catalogo": True, "external_id": "tdp-ext-3"}),
    ]
    for p in filas:
        old = db.get(Proyecto, p.id)
        if old:
            db.delete(old)
    db.commit()
    db.add_all(filas)
    db.commit()
    yield
    for p in filas:
        db.delete(db.get(Proyecto, p.id))
    db.commit()


@pytest.mark.parametrize("clave", ["tdp-ext-1", "tdpJb001", "tdp-publicado"])
def test_encuentra_por_external_id_jb_id_o_id(client, proyectos, clave):
    r = client.get(f"/proyectos/public/{clave}", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Prueba Interna Publicado"


@pytest.mark.parametrize("clave", ["tdp-ext-2", "tdp-ext-3", "tdp-inactivo", "noExiste"])
def test_no_publicado_inactivo_o_inexistente_da_404(client, proyectos, clave):
    r = client.get(f"/proyectos/public/{clave}", headers=H)
    assert r.status_code == 404


def test_no_carga_relaciones_de_otros_proyectos(client, proyectos):
    """Solo se cargan unidades/imágenes/documentos del proyecto encontrado:
    las consultas no pueden traer 'tdp-no-publicado' ni 'tdp-inactivo'."""
    sql = []

    def anotar(conn, cursor, statement, params, context, executemany):
        sql.append(str(params))

    event.listen(engine, "before_cursor_execute", anotar)
    try:
        r = client.get("/proyectos/public/tdpJb001", headers=H)
    finally:
        event.remove(engine, "before_cursor_execute", anotar)
    assert r.status_code == 200
    todo = " ".join(sql)
    assert "tdp-no-publicado" not in todo and "tdp-inactivo" not in todo
