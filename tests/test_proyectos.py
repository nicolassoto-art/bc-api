"""Smoke test del CRUD de proyectos."""
from app.settings import settings


def test_list_requires_auth(client):
    r = client.get("/proyectos")
    assert r.status_code in (401, 403)


# ── Catálogo público (endpoint del worker) ──────────────────────────────────

def test_public_sin_token_configurado_da_503(client, monkeypatch):
    """Si el server no tiene BC_API_SERVICE_TOKEN, el endpoint está deshabilitado."""
    monkeypatch.setattr(settings, "bc_api_service_token", "")
    r = client.get("/proyectos/public")
    assert r.status_code == 503


def test_public_token_invalido_da_401(client, monkeypatch):
    """Con token configurado, un Bearer incorrecto da 401 (antes de tocar la DB)."""
    monkeypatch.setattr(settings, "bc_api_service_token", "sk_test_correcto")
    r = client.get("/proyectos/public", headers={"Authorization": "Bearer sk_test_WRONG"})
    assert r.status_code == 401
    # Sin header tampoco
    r2 = client.get("/proyectos/public")
    assert r2.status_code == 401


def test_public_no_choca_con_detalle(client):
    """La ruta /public no debe ser capturada por /{proyecto_id}.
    Sin token → 503/401, NUNCA 404 'Proyecto no encontrado' ni 200."""
    r = client.get("/proyectos/public")
    assert r.status_code in (401, 503)


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
