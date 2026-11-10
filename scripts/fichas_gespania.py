"""Crea en Stock BigCapital las fichas Gespania SIN publicar y SIN consultar JetBrokers.

Fuentes: copia guardada del catálogo BigCapital (worker, X-Cache: HIT), sitio público
gespania.cl y bc-api. Si el catálogo no responde desde su copia, se detiene.

Uso: python3 scripts/fichas_gespania.py RsQcvZc9
"""
import argparse
import os
import re
import sys

import httpx

BC_API = "https://bc-api.178-105-91-29.nip.io"
CATALOGO = "https://bigcapital-worker.nsotofchile.workers.dev/api/proyecto"
SITIO = "https://gespania.cl"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 BigCapital"}

PROYECTOS = {
    "RsQcvZc9": {"pagina": "departamentos-en-maipu-5", "etiquetas": ["Credito Interno"]},
    "xMqukaTC": {"pagina": "departamentos-en-venta-concepcion", "etiquetas": ["Credito Interno", "Airbnb"]},
    "JFLW8myr": {"pagina": "departamentos-para-inversion", "etiquetas": ["Credito Interno", "Airbnb"]},
    "aj3VE334": {"pagina": None, "etiquetas": ["Credito Interno", "Airbnb"]},
}

FASES = {"green": "En verde", "deliveryReady": "Entrega inmediata", "white": "En blanco", "privateSale": "Venta privada"}
PATRON_ARCHIVO = r"https://gespania\.cl/wp-content/uploads/[^\"' )]+\."
DEL_SITIO = re.compile(r"LOGO|Pop-up|Black-Inmobiliario|sello-energetico|_mobile|Video-Aereo", re.I)
ENTORNO = re.compile(r"entorno|colegio|inacap|mall-|metro-|supermercado", re.I)
INTERIOR = re.compile(r"cocina|comedor|dormitorio|living|panoramica|depto", re.I)
COMUNES = re.compile(
    r"gimnasio|gym|piscina|quincho|sala|salon|co-?work|hall|lavanderia|peluqueria|pet-spa|zona|lockers|taller|jardin",
    re.I,
)
FACHADA = re.compile(r"banner|fachada|master", re.I)


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _entero(valor):
    numero = _numero(valor)
    return int(numero) if numero is not None else None


def _primero(valor):
    return valor[0] if isinstance(valor, list) and valor else None


def _modelo(m: dict) -> dict:
    return {
        "nombre": m.get("name") or "",
        "dormitorios": _entero(m.get("rooms")) or 0,
        "banos": _entero(m.get("bathrooms")) or 0,
        "superficie": _numero(_primero(m.get("surfaceTotal"))),
        "precio_base": m.get("priceBase"),
    }


def ficha_desde_catalogo(d: dict, jb_id: str, etiquetas: list[str]) -> dict:
    return {
        "id": f"jb-{jb_id.lower()}",
        "nombre": d["name"],
        "inmobiliaria": d.get("developerName") or "Gespania",
        "comuna": d.get("locality"),
        "direccion": d.get("address"),
        "gps_lat": _numero(d.get("gpsLat")),
        "gps_lon": _numero(d.get("gpsLon")),
        "fase": FASES.get(d.get("stage"), d.get("stage")),
        "modalidad": "Nuevo",
        "activo": True,
        "disponible": True,
        "fecha_entrega": (d.get("dateOfDelivery") or "").strip() or None,
        "ano_entrega": _entero(d.get("yearOfDelivery")),
        "extra": {
            "jb_id": jb_id,
            "external_id": jb_id,
            "etiquetas": etiquetas,
            "descripcion": d.get("description"),
            "constructora": d.get("buildingCompany"),
            "equipamiento": d.get("perks") or [],
            "areas_comunes": d.get("perksCommonAreas") or [],
            "entorno": d.get("perksNearby") or [],
            "modelos": [_modelo(m) for m in d.get("models") or []],
            "fisicos": {
                "pisos": d.get("floors"),
                "ascensores": d.get("elevatorsCount"),
                "unidades_totales": d.get("apartmentCount"),
                "estacionamientos_totales": d.get("parkingCount"),
                "bodegas_totales": d.get("storeCount"),
                "constructora": d.get("buildingCompany"),
                "permiso_construccion": d.get("buildingPermit"),
            },
            "formas_pago_pie": {
                "cuotas_pre_entrega": d.get("installmentsPreEntrega"),
                "pago_pre_entrega": d.get("payMethodPreEntrega"),
                "cuotas_post_entrega": d.get("installmentsPostEntrega"),
                "pago_post_entrega": d.get("payMethodPostEntrega"),
            },
            "cuenta_reserva": {
                "titular_nombre": d.get("reserveName"),
                "titular_rut": d.get("reserveTaxId"),
                "banco": d.get("reserveBank"),
                "tipo_cuenta": d.get("reserveAccountType"),
                "numero_cuenta": d.get("reserveAccountNumber"),
            },
        },
    }


def categoria_foto(nombre: str) -> str:
    if FACHADA.search(nombre):
        return "Fachada"
    if ENTORNO.search(nombre):
        return "Entorno"
    if INTERIOR.search(nombre):
        return "Interior"
    if COMUNES.search(nombre):
        return "Áreas comunes"
    return "Otro"


def fotos_y_documentos(html: str) -> tuple[list[str], list[str]]:
    imagenes = set(re.findall(PATRON_ARCHIVO + r"(?:jpe?g|png|webp)", html, re.I))
    fotos = sorted(u for u in imagenes if not re.search(r"-\d+x\d+\.", u) and not DEL_SITIO.search(u))
    documentos = sorted(set(re.findall(PATRON_ARCHIVO + r"pdf", html, re.I)))
    return fotos, documentos


def _tipo(contenido: bytes, url: str) -> str:
    if contenido[:5] == b"%PDF-":
        return "application/pdf"
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError(f"Tipo no reconocido: {url}")


def _subir(cli, web, ruta: str, url: str, datos: dict, fallas: list[str]) -> None:
    nombre = url.rsplit("/", 1)[1]
    try:
        resp = web.get(url)
        resp.raise_for_status()
        archivos = [("files", (nombre, resp.content, _tipo(resp.content, url)))]
        cli.post(ruta, files=archivos, data=datos).raise_for_status()
    except (httpx.HTTPError, ValueError) as e:
        fallas.append(f"{nombre}: {e}")


def subir_documento(cli, web, pid: str, url: str, fallas: list[str]) -> None:
    """Un PDF sobre el límite de bc-api queda como enlace al sitio público de Gespania."""
    nombre = url.rsplit("/", 1)[1]
    try:
        resp = web.get(url)
        resp.raise_for_status()
        archivos = [("files", (nombre, resp.content, _tipo(resp.content, url)))]
        subida = cli.post(f"/proyectos/{pid}/documentos", files=archivos, data={"tipo": "Brochure"})
        if subida.status_code == 413:
            enlace = {"url": url, "nombre": nombre, "tipo": "Brochure"}
            cli.post(f"/proyectos/{pid}/documentos/url", json=enlace).raise_for_status()
        else:
            subida.raise_for_status()
    except (httpx.HTTPError, ValueError) as e:
        fallas.append(f"{nombre}: {e}")


def main(jb_id: str) -> int:
    fuente = PROYECTOS[jb_id]
    pid = f"jb-{jb_id.lower()}"
    auth = {"Authorization": f"Bearer {os.environ['BC_API_JWT']}"}
    with httpx.Client(base_url=BC_API, headers=auth, timeout=120) as cli, httpx.Client(
        headers=NAVEGADOR, timeout=90, follow_redirects=True
    ) as web:
        catalogo = web.get(CATALOGO, params={"id": jb_id})
        catalogo.raise_for_status()
        if catalogo.headers.get("x-cache") != "HIT":
            print(f"{pid}: DETENIDO, el catálogo no respondió desde su copia")
            return 1

        existente = cli.get(f"/proyectos/{pid}")
        if existente.status_code == 200:
            if existente.json().get("deleted_at"):
                print(f"{pid}: DETENIDO, está en la papelera")
                return 1
            print(f"{pid}: ya existe, no se modifican sus datos")
        elif existente.status_code == 404:
            ficha = ficha_desde_catalogo(catalogo.json(), jb_id, fuente["etiquetas"])
            cli.post("/proyectos", json=ficha).raise_for_status()
            print(f"{pid}: ficha creada sin publicar")
        else:
            existente.raise_for_status()

        fallas: list[str] = []
        if fuente["pagina"]:
            pagina = web.get(f"{SITIO}/{fuente['pagina']}/")
            pagina.raise_for_status()
            fotos, documentos = fotos_y_documentos(pagina.text)
            if not cli.get(f"/proyectos/{pid}/imagenes").raise_for_status().json():
                portada = next((u for u in fotos if "banner" in u.lower()), None)
                for url in fotos:
                    datos = {
                        "categoria": categoria_foto(url.rsplit("/", 1)[1]),
                        "es_principal": str(url == portada).lower(),
                    }
                    _subir(cli, web, f"/proyectos/{pid}/imagenes", url, datos, fallas)
            ya_subidos = {d.get("nombre") for d in cli.get(f"/proyectos/{pid}/documentos").raise_for_status().json()}
            for url in documentos:
                if url.rsplit("/", 1)[1] not in ya_subidos:
                    subir_documento(cli, web, pid, url, fallas)
            print(f"{pid}: encontrados {len(fotos)} fotos y {len(documentos)} documentos en gespania.cl")
        else:
            print(f"{pid}: sin página en gespania.cl; fotos y documentos quedan pendientes")

        final = cli.get(f"/proyectos/{pid}").raise_for_status().json()
        print(
            f"{pid}: quedó con {len(final.get('imagenes') or [])} fotos y "
            f"{len(final.get('documentos') or [])} documentos; "
            f"publicado={bool((final.get('extra') or {}).get('publicar_en_catalogo'))}"
        )
        for falla in fallas:
            print(f"{pid}: NO SUBIÓ {falla}")
        return 1 if fallas else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("jb_id", choices=sorted(PROYECTOS))
    sys.exit(main(ap.parse_args().jb_id))
