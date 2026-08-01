"""Smoke test del CRUD de proyectos."""
import json
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


def test_public_dict_no_filtra_datos_sensibles():
    """El catálogo público (allow-list) NUNCA debe exponer RUT, cuenta bancaria,
    comisiones, promos de broker ni el path del Excel de stock. Las NOTAS del proyecto
    SÍ van al worker (que las gatea: brokers logueados, no público anónimo · #61).

    Regresión de C1/C2: el importador JB escribe cuenta_reserva.titular_rut /
    numero_cuenta / link_pago y spa_proyecto.rut — nombres que el mask viejo
    (rut/numero/rut_spa) NO borraba. Y el aplanado volcaba TODO el extra.
    """
    from types import SimpleNamespace
    from app.routes.proyectos import _proyecto_public_dict

    p = SimpleNamespace(
        id="test-leak", codigo_corto="X1", nombre="Edificio X", inmobiliaria="Inmobiliaria Real",
        comuna="Ñuñoa", region="RM", direccion="Calle 1", gps_lat=None, gps_lon=None,
        fase="Verde", modalidad="Nuevo", fecha_entrega=None, ano_entrega=None,
        foto_principal_url=None, unidades=[], imagenes=[], documentos=[],
        stock_updated_at=None, notas=None,
        extra={
            # --- seguros (deben salir) ---
            "external_id": "Sfp8j2Sq",
            "publicar_en_catalogo": True,
            "descripcion": "descripcion publica ok",
            "modelos": [{"nombre": "2D2B"}],
            "estacionamientos": [{"numero": "E-1"}],
            "bodegas": [{"numero": "B-1"}],
            "etiquetas": ["destacado"],
            # notas del proyecto: van al worker, que las gatea (brokers logueados · #61)
            "notas_html": "<p>nota del proyecto</p>",
            "notas_text": "nota del proyecto",
            "comercial": {"pie_pct": 20, "valor_reserva_clp": 500000,
                          "promo_broker": "SECRETO 5% extra"},
            # --- sensibles que el importador SÍ escribe (NO deben salir) ---
            "cuenta_reserva": {"titular_rut": "77.389.903-7",
                               "numero_cuenta": "92311635", "link_pago": "http://pay"},
            "spa_proyecto": {"rut": "76.000.000-0", "nombre": "SPA X"},
            "comision_admin": {"pct": 3},
            "_jb_stock_excel": {"path": "/srv/import/stock.xlsx"},
            "promocion_broker": "margen oculto",
        },
    )
    d = _proyecto_public_dict(p)
    blob = json.dumps(d, ensure_ascii=False)

    fugas = [
        "77.389.903-7", "92311635", "titular_rut", "numero_cuenta", "link_pago",
        "cuenta_reserva", "spa_proyecto", "76.000.000-0",
        "comision_admin", "_jb_stock_excel", "stock.xlsx",
        "promo_broker", "SECRETO", "promocion_broker", "margen oculto",
    ]
    for needle in fugas:
        assert needle not in blob, f"FUGA en catálogo público: '{needle}'"

    # Los campos seguros SÍ deben estar presentes
    assert d["descripcion"] == "descripcion publica ok"
    assert d["external_id"] == "Sfp8j2Sq"
    # Las notas del proyecto SÍ van al feed (el worker las gatea por audiencia · #61)
    assert d.get("notas_html") and d.get("notas_text")
    assert d["estacionamientos"] == [{"numero": "E-1"}]
    assert d["comercial"]["pie_pct"] == 20
    assert d["comercial"]["valor_reserva_clp"] == 500000
    assert "promo_broker" not in d["comercial"]  # comercial sanitizado
