"""Smoke test del CRUD de proyectos."""


def test_list_requires_auth(client):
    r = client.get("/proyectos")
    assert r.status_code in (401, 403)


def test_crud_proyecto(client, admin):
    _, h = admin

    # Crear
    payload = {
        "id": "test-cicd",
        "nombre": "Proyecto Test CI",
        "comuna": "Las Condes",
        "fase": "Verde",
        "modalidad": "Nuevo",
    }
    r = client.post("/proyectos", json=payload, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "test-cicd"

    # Detalle
    r = client.get("/proyectos/test-cicd", headers=h)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Proyecto Test CI"

    # Update
    payload["nombre"] = "Renombrado"
    r = client.put("/proyectos/test-cicd", json=payload, headers=h)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Renombrado"

    # List incluye el nuevo
    r = client.get("/proyectos", headers=h)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert "test-cicd" in ids

    # Delete
    r = client.delete("/proyectos/test-cicd", headers=h)
    assert r.status_code == 204
    r = client.get("/proyectos/test-cicd", headers=h)
    assert r.status_code == 404
