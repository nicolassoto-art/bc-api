"""Arma un proyecto de stock propio desde datos ya guardados por nosotros (sin red).

Fuentes de Laguna Centro Torre H (12-nov-2026):
  - ficha.json: copia que guarda nuestro Worker (/api/proyecto?id=IquFoRoO).
  - unidades.csv: pestaña Stock guardada por Nicolás (.webarchive).
Las imágenes y PDF se piden SOLO por nuestro Worker (/api/img), nunca directo a
*.jetbrokers.io (regla de Nicolás).

Precios (docs/fuentes-de-stock.md): el «Precio Final» de JetBrokers viene inflado por
el bono pie; se carga el «Precio» como lista + descuento + bono y bc-api calcula el final.
"""
import io
import re
from urllib.parse import quote, urlparse

import openpyxl

# Copia de app.routes.unidades.HEADERS (la prueba exige que sean iguales). No se importa
# la app para que el script corra en el workflow sin base de datos ni secretos.
HEADERS = [
    "numero_depto", "modelo", "tipologia", "tipo", "orientacion",
    "sup_total", "sup_interior", "sup_terraza", "sup_logia", "sup_jardin",
    "precio_lista_uf", "descuento_pct", "bono_pie_pct", "precio_final_uf",
    "estac_flag", "bodega_flag", "pack_flag", "disponible",
]

WORKER_HOST = "bigcapital-worker.nsotofchile.workers.dev"
# Misma dirección de origen que arma nuestro catálogo (catalogo-proyecto.html imgUrl);
# solo viaja como parámetro a nuestro Worker.
_GALERIA = "https://jetgallery.jetbrokers.io/api/gallery/download/uv13koru/"
_CAT = {"projectPerk": "jb-foto", "projectPerkCommonArea": "jb-foto-areas-comunes",
        "projectPerkNearby": "jb-foto-entorno"}
_DOC = {"projectBrochure": "Brochure", "projectFloor": "Plano"}
_FLAG = {"Opcional": "optional", "Obligatorio": "required", "Nunca": "never"}

PROYECTO_ID = "jb-iquforoo"
JB_ID = "IquFoRoO"


def url_nuestra(file_id: str) -> str:
    return f"https://{WORKER_HOST}/api/img?url=" + quote(_GALERIA + file_id, safe="")


def es_url_nuestra(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and u.netloc == WORKER_HOST and u.path == "/api/img"


def _n(s):
    """'2.955 UF' / '39,23' / '10 %' -> float. Punto = miles, coma = decimal."""
    s = str(s or "").replace("UF", "").replace("%", "").strip()
    return float(s.replace(".", "").replace(",", ".")) if s else None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def modelos(f: dict) -> list[dict]:
    return [{"id": _slug(m["name"]), "nombre": m["name"],
             "dormitorios": int(m.get("rooms") or 0), "banos": int(m.get("bathrooms") or 0),
             "blueprint_id": m["blueprintId"],
             "disponibles": int(m.get("apartmentsAvailable") or 0)} for m in f["models"]]


def lista_imagenes(f: dict) -> list[dict]:
    out = [{"file_id": f["coverId"], "categoria": "cover", "es_principal": True}]
    out += [{"file_id": x["id"], "categoria": _CAT[x["type"]], "es_principal": False}
            for x in f["files"] if x["type"] in _CAT and x["id"] != f["coverId"]]
    return out


def lista_documentos(f: dict) -> list[dict]:
    return [{"file_id": x["id"], "tipo": _DOC[x["type"]]} for x in f["files"] if x["type"] in _DOC]


def plan_pago() -> dict:
    return {"id": "estandar", "nombre": "Estándar", "orden": 0, "predeterminado": True,
            "activo": True, "pie_pct": 20, "cuoton_inicial_pct": 5, "cuotas_pago_inicial": 0,
            "pago_construccion_pct": 0, "cuotas_pre_entrega": 1, "cuoton_final_pct": 5,
            "cuotas_post_entrega": 12, "bono_pie_pct": 10,
            "nota_pago_pie": "Cuotón inicial y cuota pre-entrega con tarjeta de crédito o cheque. "
                             "12 cuotas post-entrega de $600.000 con tarjeta de crédito."}


def armar_proyecto(f: dict) -> dict:
    return {
        "id": PROYECTO_ID, "nombre": f["name"].strip(), "inmobiliaria": "Vitalia",
        "comuna": f["locality"], "region": "Metropolitana", "direccion": f["address"],
        "gps_lat": float(f["gpsLat"]), "gps_lon": float(f["gpsLon"]),
        "fase": "Entrega inmediata", "modalidad": "Nuevo", "activo": True, "disponible": True,
        "fecha_entrega": "Inmediata", "ano_entrega": int(f["yearOfDelivery"]),
        "extra": {
            "jb_id": JB_ID, "publicar_en_catalogo": True,
            "descripcion": f.get("description"), "constructora": f.get("buildingCompany"),
            "pisos": f.get("floors"), "ascensores": f.get("elevatorsCount"),
            "unidades_totales": f.get("apartmentCount"), "estac_totales": f.get("parkingCount"),
            "bodegas_totales": f.get("storeCount"),
            "equipamiento": f.get("perks"), "areas_comunes": f.get("perksCommonAreas"),
            "entorno": f.get("perksNearby"),
            "modelos": [{k: v for k, v in m.items() if k not in ("blueprint_id", "disponibles")}
                        for m in modelos(f)],
            "notas_text": (f"Estacionamiento desde {f['parkingFrom']} UF y bodega desde "
                           f"{f['storeFrom']} UF, ambos opcionales. Acepta cesión con "
                           "autorización de la inmobiliaria. Solicita preaprobación a la reserva."),
            "comercial": {
                "valor_reserva_clp": int(float(f["reserveCLP"])),
                "tipo_reserva": "Gastos operacionales",
                "destino_reserva": "BigCapital",
                "valor_cuota_clp": 600000,
                "nota_pago_pie": "La reserva se devuelve si el cliente no califica. "
                                 "12 cuotas post-entrega de $600.000 con tarjeta de crédito.",
            },
        },
    }


def armar_excel_unidades(filas: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in filas:
        v = {"numero_depto": r["numero"], "modelo": r["modelo"], "tipologia": r["tipologia"],
             "tipo": r["tipo_unidad"], "orientacion": r["orientacion"],
             "sup_total": _n(r["sup_total"]), "sup_interior": _n(r["sup_interior"]),
             "sup_terraza": _n(r["sup_terraza"]), "sup_logia": _n(r["sup_logia"]),
             "sup_jardin": _n(r["sup_jardin"]), "precio_lista_uf": _n(r["precio"]),
             "descuento_pct": _n(r["descuento"]), "bono_pie_pct": _n(r["bono_pie"]),
             "precio_final_uf": None, "estac_flag": _FLAG.get(r["estac"], "optional"),
             "bodega_flag": _FLAG.get(r["bodega"], "optional"), "pack_flag": "never",
             "disponible": True}
        ws.append([v.get(h) for h in HEADERS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
