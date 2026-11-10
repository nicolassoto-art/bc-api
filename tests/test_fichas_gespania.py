import httpx

from scripts.fichas_gespania import (
    PROYECTOS,
    categoria_foto,
    fotos_y_documentos,
    ficha_desde_catalogo,
    subir_documento,
)

CATALOGO = {
    "name": "Ciudad del Rosal 2",
    "developerName": "Gespania",
    "locality": "Maipú",
    "address": "Calle Prueba 123",
    "gpsLat": "-33.5",
    "gpsLon": "-70.7",
    "stage": "deliveryReady",
    "dateOfDelivery": "Primer Semestre",
    "yearOfDelivery": 2026,
    "description": "Texto",
    "perks": ["Piso"],
    "perksCommonAreas": ["Quincho"],
    "perksNearby": ["Metro"],
    "buildingCompany": "Constructora Prueba",
    "floors": 4,
    "elevatorsCount": 0,
    "apartmentCount": 96,
    "parkingCount": 96,
    "storeCount": 58,
    "buildingPermit": "yes",
    "installmentsPreEntrega": 1,
    "installmentsPostEntrega": 60,
    "payMethodPreEntrega": "Transferencia",
    "payMethodPostEntrega": "Banca",
    "reserveName": "Titular Prueba",
    "reserveTaxId": "1-9",
    "reserveBank": "Banco Prueba",
    "reserveAccountType": "Corriente",
    "reserveAccountNumber": "123",
    "models": [
        {
            "name": "D2",
            "rooms": "2",
            "bathrooms": "1",
            "blueprintId": "Su7gHFj0",
            "surfaceTotal": ["56.37"],
            "priceBase": 3206.2,
        }
    ],
}


def test_ficha_sale_sin_publicar_y_conserva_alias():
    f = ficha_desde_catalogo(CATALOGO, "RsQcvZc9", ["Credito Interno"])
    assert f["id"] == "jb-rsqcvzc9"
    assert f["nombre"] == "Ciudad del Rosal 2"
    assert f["inmobiliaria"] == "Gespania"
    assert f["fase"] == "Entrega inmediata"
    assert f["gps_lat"] == -33.5
    assert f["extra"]["jb_id"] == "RsQcvZc9"
    assert f["extra"]["external_id"] == "RsQcvZc9"
    assert f["extra"]["etiquetas"] == ["Credito Interno"]
    assert f["extra"]["areas_comunes"] == ["Quincho"]
    assert f["extra"]["fisicos"]["unidades_totales"] == 96
    assert f["extra"]["cuenta_reserva"]["banco"] == "Banco Prueba"
    assert "publicar_en_catalogo" not in f["extra"]


def test_modelo_no_arrastra_referencias_a_jetbroker():
    m = ficha_desde_catalogo(CATALOGO, "RsQcvZc9", [])["extra"]["modelos"][0]
    assert m["nombre"] == "D2"
    assert m["dormitorios"] == 2
    assert m["superficie"] == 56.37
    assert m["precio_base"] == 3206.2
    assert "blueprintId" not in m


def test_clasifica_fotos_por_nombre():
    assert categoria_foto("banner-distrito-bustamante-2-scaled.png") == "Fachada"
    assert categoria_foto("R1_piscina-1.jpg") == "Áreas comunes"
    assert categoria_foto("05-living.webp") == "Interior"
    assert categoria_foto("12-entorno-metro-parque-bustamante.webp") == "Entorno"
    assert categoria_foto("R1_metro-monte-tabor.jpg") == "Entorno"
    assert categoria_foto("5I7A1345-scaled.webp") == "Otro"


def test_toma_originales_y_descarta_imagenes_del_sitio():
    base = "https://gespania.cl/wp-content/uploads/2026/06"
    html = f"""
      <img src="{base}/R1_piscina-1.jpg"><img src="{base}/R1_piscina-1-300x142.jpg">
      <img src="{base}/LOGO2.png"><img src="{base}/Pop-up-Gespania.webp">
      <img src="{base}/ciudad-del-rosal_mobile.png">
      <img src="https://otro.cl/wp-content/uploads/foto.jpg">
      <a href="{base}/Brochure-Rosal-2-.pdf">x</a>
    """
    fotos, documentos = fotos_y_documentos(html)
    assert fotos == [f"{base}/R1_piscina-1.jpg"]
    assert documentos == [f"{base}/Brochure-Rosal-2-.pdf"]


def test_los_cuatro_proyectos_estan_definidos():
    assert set(PROYECTOS) == {"RsQcvZc9", "xMqukaTC", "aj3VE334", "JFLW8myr"}
    assert PROYECTOS["aj3VE334"]["pagina"] is None
    assert httpx.URL("https://gespania.cl").host == "gespania.cl"


def test_documento_pesado_queda_como_enlace_a_gespania():
    llamadas = []

    def api(req):
        llamadas.append((req.method, req.url.path))
        if req.url.path.endswith("/documentos"):
            return httpx.Response(413)
        return httpx.Response(201, json={"id": "doc-1"})

    cli = httpx.Client(transport=httpx.MockTransport(api), base_url="http://bc")
    web = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"%PDF-1.7")))
    url = "https://gespania.cl/wp-content/uploads/2025/12/Folleto.pdf"
    fallas = []
    subir_documento(cli, web, "p", url, fallas)
    assert fallas == []
    assert llamadas == [("POST", "/proyectos/p/documentos"), ("POST", "/proyectos/p/documentos/url")]


def test_toma_brochure_de_subdominio_de_gespania():
    url = "https://sic.gespania.cl/sic/storage/brochure-distrito-parque.pdf"
    _, documentos = fotos_y_documentos(f'<a href="{url}">x</a><a href="https://otro.cl/a.pdf">y</a>')
    assert documentos == [url]
