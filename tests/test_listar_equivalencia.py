"""GET /proyectos (2026-10-18): la versión rápida (solo columnas del resumen + claves de
`extra` extraídas en la base) debe devolver EXACTAMENTE lo mismo que la versión anterior
(cargaba el Proyecto completo). Se compara campo por campo contra una copia de esa lógica."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, Integer

from app.models import Imagen, Proyecto, Unidad
from app.routes.proyectos import _estado_stock_seguro
from app.schemas import ProyectoSummary

PREF = "zz-eq-"


def _listar_referencia(db):
    """Copia literal de la lógica anterior de `listar` (sin filtros)."""
    stmt = select(Proyecto).where(Proyecto.deleted_at.is_(None)).order_by(Proyecto.updated_at.desc())
    proys = db.execute(stmt).scalars().all()
    rows = db.execute(
        select(Unidad.proyecto_id, func.count(Unidad.id), func.sum(func.cast(Unidad.disponible, Integer)))
        .group_by(Unidad.proyecto_id)
    ).all()
    counts = {pid: (t or 0, d or 0) for pid, t, d in rows}
    precio_rows = db.execute(
        select(Unidad.proyecto_id, func.min(Unidad.precio_lista_uf))
        .where(Unidad.disponible == True).where(Unidad.precio_lista_uf > 0)  # noqa: E712
        .group_by(Unidad.proyecto_id)
    ).all()
    precios_min = {pid: pr for pid, pr in precio_rows if pr}
    all_imgs = db.execute(
        select(Imagen.id, Imagen.proyecto_id, Imagen.url, Imagen.categoria).order_by(Imagen.id)
    ).all()

    def _is_facade(cat):
        c = (cat or "").lower()
        return c in {"jb-foto", "foto", "fachada", "exterior", ""} or "foto" in c

    first, facade = {}, {}
    for r in all_imgs:
        if r.proyecto_id not in first:
            first[r.proyecto_id] = r.url
        if _is_facade(r.categoria) and r.proyecto_id not in facade:
            facade[r.proyecto_id] = r.url
    first = {**first, **facade}
    out = []
    ahora = datetime.now(timezone.utc)
    for p in proys:
        total, disp = counts.get(p.id, (0, 0))
        extra = p.extra or {}
        comercial = extra.get("comercial") or {}
        out.append(ProyectoSummary.model_validate(p).model_copy(update={
            "unidades_total": int(total), "unidades_disponibles": int(disp),
            "pie_pct": comercial.get("pie_pct"), "precio_desde_uf": precios_min.get(p.id),
            "publicar_en_catalogo": bool(extra.get("publicar_en_catalogo")),
            "gps_verificado": bool(extra.get("gps_verificado")),
            "foto_principal_url": p.foto_principal_url or first.get(p.id) or None,
            "estado_stock": _estado_stock_seguro(p, ahora),
        }))
    return out


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture
def datos(db):
    """Proyectos sintéticos con los casos raros del listado. Se borran al terminar."""
    ahora = datetime.now(timezone.utc)
    n = lambda dt: dt.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731
    robot = {"id": "tl-1", "tipo": "Excel Stock", "fecha": _iso(ahora - timedelta(hours=5)),
             "usuario": "mnk-scraper@bigcapital.cl", "origen_auto": True,
             "detalles": "Actualización automática (scraper Ingevec) — 2 deptos nuevos"}
    alerta = {"id": "tl-2", "tipo": "Alerta", "fecha": _iso(ahora - timedelta(hours=1)),
              "usuario": "mnk-scraper@bigcapital.cl", "origen_auto": True,
              "titulo": "Subida con problema", "detalles": "upload_failed"}
    persona = {"id": "tl-3", "tipo": "Revisión", "fecha": _iso(ahora - timedelta(days=2)),
               "usuario": "beatriz.vinet@bigcapital.cl", "detalles": "sin cambios"}
    casos = [
        # (sufijo, columnas, extra, imágenes[(id, categoria)], unidades[(disp, precio)])
        ("a", dict(foto_principal_url="https://x/foto.jpg", stock_ok_at=n(ahora - timedelta(days=1))),
         {"comercial": {"pie_pct": 10}, "publicar_en_catalogo": True, "gps_verificado": True,
          "timeline": [robot], "unidades_dom": [{"n": i} for i in range(300)]}, [], [(True, 3000.5), (False, 100)]),
        ("b", dict(inmobiliaria="Vellatrix", stock_ok_at=n(ahora - timedelta(days=6))),
         {"comercial": {"pie_pct": 12.5}, "publicar_en_catalogo": True, "timeline": [robot, alerta]},
         [("img-1", "jb-planta-3d"), ("img-2", "Foto"), ("img-3", "")], [(True, 2500)]),
        ("c", dict(inmobiliaria="Ingevec"), {"comercial": {"pie_pct": None}, "publicar_en_catalogo": False},
         [("img-1", "jb-planta-3d"), ("img-2", "otro")], []),
        ("d", dict(), {"comercial": {}, "gps_verificado": 0, "publicar_en_catalogo": "si", "timeline": [persona]},
         [("img-9", "jb-foto"), ("img-1", "fachada-lateral")], [(True, 0), (True, None)]),
        ("e", dict(), {}, [("img-1", "exterior"), ("img-0", "plano")], [(False, 900)]),
        ("f", dict(foto_principal_url=""), {"publicar_en_catalogo": True, "timeline": [alerta]}, [("i", "x")], []),
        ("g", dict(activo=False, ultima_revision_at=n(ahora - timedelta(hours=2))),
         {"publicar_en_catalogo": True, "timeline": "roto"}, [], [(True, 1)]),
        ("h", dict(deleted_at=n(ahora)), {"publicar_en_catalogo": True}, [], []),
        ("i", dict(extra=None, stock_updated_at=n(ahora - timedelta(days=9))), None, [], []),
    ]
    ids = []
    for i, (suf, cols, extra, imgs, unis) in enumerate(casos):
        pid = f"{PREF}{suf}"
        ids.append(pid)
        cols = dict(cols)
        cols.pop("extra", None)
        p = Proyecto(id=pid, nombre=f"Proyecto Eq {suf}", comuna="Ñuñoa" if i % 2 else "Las Condes",
                     fase="Verde", extra=extra if extra is not None else {},
                     updated_at=datetime.utcnow() - timedelta(minutes=i), **cols)
        db.add(p)
        db.flush()
        for iid, cat in imgs:
            db.add(Imagen(id=f"{pid}-{iid}", proyecto_id=pid, url=f"/uploads/{pid}/{iid}.jpg", categoria=cat))
        for k, (disp, precio) in enumerate(unis):
            db.add(Unidad(id=f"{pid}-u{k}", proyecto_id=pid, numero=str(k), disponible=disp, precio_lista_uf=precio))
    db.commit()
    yield ids
    db.rollback()
    for pid in ids:
        obj = db.get(Proyecto, pid)
        if obj:
            db.delete(obj)
    db.commit()


def test_listado_identico_a_la_version_anterior(client, admin, db, datos):
    _, h = admin
    r = client.get("/proyectos", headers=h)
    assert r.status_code == 200, r.text
    nuevo = r.json()
    viejo = jsonable_encoder(_listar_referencia(db))
    assert [p["id"] for p in nuevo] == [p["id"] for p in viejo]  # mismo orden
    assert {p["id"] for p in nuevo} >= {i for i in datos if not i.endswith("-h")}
    assert f"{PREF}h" not in {p["id"] for p in nuevo}  # papelera fuera
    for a, b in zip(nuevo, viejo):
        assert a == b, a["id"]


def test_listado_con_filtros_identico(client, admin, db, datos):
    _, h = admin
    r = client.get("/proyectos", params={"q": "eq", "activo": "true", "comuna": "Ñuñoa"}, headers=h)
    assert r.status_code == 200, r.text
    ids = [p["id"] for p in r.json()]
    assert ids and all(i.startswith(PREF) for i in ids)
    ref = {p["id"]: p for p in jsonable_encoder(_listar_referencia(db))}
    for p in r.json():
        assert p == ref[p["id"]]
