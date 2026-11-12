"""Carga (idempotente) un proyecto de stock propio en bc-api por HTTP.

Uso (desde el workflow `cargar-proyecto-propio.yml`):
    python -m scripts.proyecto_propio.cargar --datos scripts/data/laguna_centro_torre_h          # ensayo
    python -m scripts.proyecto_propio.cargar --datos scripts/data/laguna_centro_torre_h --aplicar

Ensayo = solo lecturas (GET) y un resumen de lo que haría. Ninguna petición va directo
a *.jetbrokers.io: las imágenes se piden por nuestro Worker (`bajar_seguro`).
"""
import argparse
import copy
import csv
import json
import os
import sys
from pathlib import Path

import httpx

from scripts.proyecto_propio.armar import (
    PROYECTO_ID, armar_excel_unidades, armar_proyecto, es_url_nuestra, lista_documentos,
    lista_imagenes, modelos, plan_pago, url_nuestra,
)

_CAT_GESTIONADAS = ("cover", "jb-foto", "jb-planta-")
_TIPOS_DOC = ("Brochure", "Plano")
# Campos de ProyectoIn (PUT reemplaza todo: se manda siempre el cuerpo completo).
_CAMPOS = ("id", "nombre", "inmobiliaria", "comuna", "region", "direccion", "gps_lat", "gps_lon",
           "fase", "modalidad", "activo", "disponible", "fecha_entrega", "ano_entrega",
           "foto_principal_url", "external_url", "notas", "extra")


def bajar_seguro(url: str) -> bytes:
    if not es_url_nuestra(url):
        raise ValueError(f"Dirección no permitida (solo nuestro Worker): {url}")
    r = httpx.get(url, timeout=60, follow_redirects=False)
    if r.status_code != 200:
        raise ValueError(f"{r.status_code} al pedir {url}")
    return r.content


def _tipo(b: bytes):
    if b[:2] == b"\xff\xd8":
        return "image/jpeg", ".jpg"
    if b[:4] == b"\x89PNG":
        return "image/png", ".png"
    if b[:4] == b"%PDF":
        return "application/pdf", ".pdf"
    return None, None


def _es_jb(url) -> bool:
    return "jetbrokers" in str(url or "")


def mezclar(actual: dict, nuevo: dict) -> dict:
    """Mezcla profunda: los dict se combinan; listas y escalares nuevos reemplazan."""
    out = copy.deepcopy(actual)
    for k, v in nuevo.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = mezclar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _cuerpo(p: dict) -> dict:
    return {k: p.get(k) for k in _CAMPOS if k in p}


def _urls_jb(p: dict) -> list:
    urls = [p.get("foto_principal_url")]
    urls += [i.get("url") for i in p.get("imagenes") or []]
    urls += [d.get("url") for d in p.get("documentos") or []]
    urls += [m.get("planta_url") for m in (p.get("extra") or {}).get("modelos") or []]
    return [u for u in urls if _es_jb(u)]


def cargar(api, datos_dir: Path, aplicar: bool, bajar=bajar_seguro, headers=None) -> dict:
    h = headers or {}
    datos_dir = Path(datos_dir)
    ficha = json.loads((datos_dir / "ficha.json").read_text(encoding="utf-8"))
    filas = list(csv.DictReader((datos_dir / "unidades.csv").open(encoding="utf-8-sig"), delimiter=";"))
    nuevo = armar_proyecto(ficha)
    imgs, docs, mods = lista_imagenes(ficha), lista_documentos(ficha), modelos(ficha)
    base = f"/proyectos/{PROYECTO_ID}"
    res = {"estado_previo": None, "proyecto": None, "unidades": None, "imagenes": 0,
           "documentos": 0, "planos": 0, "urls_jetbrokers_previas": [], "errores": [],
           "plan": {"unidades": len(filas), "imagenes": len(imgs), "documentos": len(docs),
                    "planos": len(mods)}}

    # 1. Estado previo
    r = api.get(base, headers=h)
    actual = r.json() if r.status_code == 200 else None
    res["estado_previo"] = "activo" if actual else "no existe"
    if actual:
        res["urls_jetbrokers_previas"] = _urls_jb(actual)
    if not aplicar:
        res["proyecto"] = "ensayo"
        return res

    # 2. Proyecto (papelera -> restaurar; existe -> GET + mezcla + PUT completo)
    if actual is None:
        r = api.post("/proyectos", json=nuevo, headers=h)
        if r.status_code == 409:
            rr = api.post(f"{base}/restaurar", headers=h)
            if rr.status_code != 200:
                res["errores"].append(f"restaurar: {rr.status_code} {rr.text[:200]}")
                return res
            res["estado_previo"] = "papelera"
            actual = api.get(base, headers=h).json()
            res["urls_jetbrokers_previas"] = _urls_jb(actual)
        elif r.status_code != 201:
            res["errores"].append(f"crear proyecto: {r.status_code} {r.text[:300]}")
            return res
        else:
            res["proyecto"] = "creado"
    if actual is not None:
        cuerpo = mezclar(_cuerpo(actual), nuevo)
        if _es_jb(cuerpo.get("foto_principal_url")):
            cuerpo["foto_principal_url"] = None
        r = api.put(base, json=cuerpo, headers=h)
        if r.status_code != 200:
            res["errores"].append(f"actualizar proyecto: {r.status_code} {r.text[:300]}")
            return res
        res["proyecto"] = "actualizado"

    # 3. Plan de pago
    r = api.patch(f"{base}/planes-pago", json={"planes_pago": [plan_pago()]}, headers=h)
    if r.status_code != 200:
        res["errores"].append(f"plan de pago: {r.status_code} {r.text[:300]}")

    # 4. Unidades por Excel (upsert por número; las que no vienen quedan no disponibles)
    xlsx = armar_excel_unidades(filas)
    r = api.post(f"{base}/unidades/excel/upload", headers=h, files={"file": (
        "laguna_unidades.xlsx", xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    if r.status_code != 200:
        res["errores"].append(f"unidades: {r.status_code} {r.text[:300]}")
    else:
        res["unidades"] = r.json()

    # 5. Imágenes: borrar las gestionadas y las que apuntan a JetBrokers; subir de nuevo
    for i in api.get(f"{base}/imagenes", headers=h).json():
        if str(i.get("categoria") or "").startswith(_CAT_GESTIONADAS) or _es_jb(i.get("url")):
            api.delete(f"{base}/imagenes/{i['id']}", headers=h)
    for i in imgs:
        try:
            b = bajar(url_nuestra(i["file_id"]))
        except Exception as e:  # noqa: BLE001 — se informa y se sigue
            res["errores"].append(f"imagen {i['file_id']}: {e}")
            continue
        mime, ext = _tipo(b)
        if not mime or mime == "application/pdf":
            res["errores"].append(f"imagen {i['file_id']}: no es JPG/PNG")
            continue
        r = api.post(f"{base}/imagenes", headers=h,
                     data={"categoria": i["categoria"], "es_principal": str(i["es_principal"]).lower()},
                     files={"files": (f"{i['file_id']}{ext}", b, mime)})
        if r.status_code == 201:
            res["imagenes"] += 1
        else:
            res["errores"].append(f"imagen {i['file_id']}: {r.status_code} {r.text[:200]}")

    # 6. Documentos (brochure y planta general)
    for d in api.get(f"{base}/documentos", headers=h).json():
        if d.get("tipo") in _TIPOS_DOC or _es_jb(d.get("url")):
            api.delete(f"{base}/documentos/{d['id']}", headers=h)
    for d in docs:
        try:
            b = bajar(url_nuestra(d["file_id"]))
        except Exception as e:  # noqa: BLE001
            res["errores"].append(f"documento {d['file_id']}: {e}")
            continue
        if _tipo(b)[0] != "application/pdf":
            res["errores"].append(f"documento {d['file_id']}: no es PDF")
            continue
        r = api.post(f"{base}/documentos", headers=h, data={"tipo": d["tipo"]},
                     files={"files": (f"{d['tipo'].lower()}-laguna-centro-torre-h.pdf", b, "application/pdf")})
        if r.status_code == 201:
            res["documentos"] += 1
        else:
            res["errores"].append(f"documento {d['file_id']}: {r.status_code} {r.text[:200]}")

    # 7. Planos de cada modelo -> extra.modelos[].planta_url
    plantas = {}
    for m in mods:
        try:
            b = bajar(url_nuestra(m["blueprint_id"]))
        except Exception as e:  # noqa: BLE001
            res["errores"].append(f"plano {m['nombre']}: {e}")
            continue
        mime, ext = _tipo(b)
        if not mime or mime == "application/pdf":
            res["errores"].append(f"plano {m['nombre']}: no es JPG/PNG")
            continue
        r = api.post(f"{base}/imagenes", headers=h, data={"categoria": f"jb-planta-{m['id']}"},
                     files={"files": (f"planta-{m['id']}{ext}", b, mime)})
        if r.status_code == 201:
            plantas[m["id"]] = r.json()[0]["url"]
            res["planos"] += 1
        else:
            res["errores"].append(f"plano {m['nombre']}: {r.status_code} {r.text[:200]}")
    actual = api.get(base, headers=h).json()
    cuerpo = _cuerpo(actual)
    ex = cuerpo.setdefault("extra", {})
    ex["modelos"] = [{**m, **({"planta_url": plantas[m["id"]]} if m.get("id") in plantas else {})}
                     for m in ex.get("modelos") or []]
    portada = next((i["url"] for i in actual.get("imagenes") or [] if i.get("es_principal")), None)
    if portada:
        cuerpo["foto_principal_url"] = portada
    r = api.put(base, json=cuerpo, headers=h)
    if r.status_code != 200:
        res["errores"].append(f"planos en modelos: {r.status_code} {r.text[:300]}")

    # 8. Publicar en el catálogo
    r = api.patch(f"{base}/publicar", json={"publicar": True}, headers=h)
    if r.status_code != 200:
        res["errores"].append(f"publicar: {r.status_code} {r.text[:200]}")

    # 9. Comprobación final: nada apuntando a JetBrokers
    final = api.get(base, headers=h).json()
    if _urls_jb(final):
        res["errores"].append(f"quedan URLs de JetBrokers: {_urls_jb(final)[:5]}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--datos", required=True)
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    base, jwt = os.environ["BC_API_BASE"], os.environ["BC_API_JWT"]
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {jwt}"}, timeout=60) as api:
        res = cargar(api, Path(a.datos), aplicar=a.aplicar)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 1 if res["errores"] else 0


if __name__ == "__main__":
    sys.exit(main())
