"""Planes de pago por proyecto (extra.comercial.planes_pago) — 2026-11-05.

Un proyecto puede tener varios planes de pago con nombre (ej. «Estándar», «Pie en cuotas»),
más el monto de la seriedad de la promesa (extra.comercial.seriedad_promesa_uf). Los escribe
SOLO PATCH /proyectos/{id}/planes-pago (que valida la cuadratura de cada plan); el PUT del
editor no los pisa, el alta no los copia y el catálogo público no los ve (solo /comercial,
asesor con sesión).
"""
import io
import json
import threading
import time
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Proyecto, Usuario
from app.routes import unidades as rutas_unidades
from app.routes.proyectos import set_planes_pago
from app.schemas.proyecto import _c
from app.services.auth import create_token, hash_password
from app.settings import settings


def _plan(id_="estandar", **over):
    p = {"id": id_, "nombre": "Estándar", "orden": 0, "predeterminado": True, "activo": True,
         "pie_pct": 20, "cuoton_inicial_pct": 5, "cuotas_pago_inicial": 3,
         "pago_construccion_pct": 10, "cuotas_pre_entrega": 24,
         "cuoton_final_pct": 3, "cuotas_post_entrega": 12, "bono_pie_pct": 2,
         "nota_pago_pie": "Pie en cuotas sin interés."}
    p.update(over)
    return p


def _otro_plan(**over):
    base = dict(nombre="Pie en cuotas", orden=1, predeterminado=False, pie_pct=10,
                cuoton_inicial_pct=0, pago_construccion_pct=10, cuoton_final_pct=0, bono_pie_pct=0)
    return _plan("pie-en-cuotas", **{**base, **over})


def _proy(db, base, extra=None):
    """Proyecto NUEVO por corrida (id único): una corrida previa contra la misma BD no contamina."""
    pid = f"{base}-{uuid.uuid4().hex[:8]}"
    db.add(Proyecto(id=pid, nombre="Edificio Prueba Interna", activo=True, extra=extra or {}))
    db.commit()
    return pid


def _extra(db, pid):
    db.expire_all()
    return db.get(Proyecto, pid).extra


def _patch(client, h, pid, body):
    return client.patch(f"/proyectos/{pid}/planes-pago",
                        headers={**h, "Content-Type": "application/json"}, content=json.dumps(body))


def test_patch_guarda_y_comercial_devuelve(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-guardar",
                extra={"comercial": {"pie_pct": 15, "tipo_bono_pie": "Todo"}, "otro": 1})
    r = _patch(client, h, pid, {"planes_pago": [_plan(), _otro_plan()], "seriedad_promesa_uf": 10})
    assert r.status_code == 200, r.text
    com = r.json()["comercial"]
    assert [p["id"] for p in com["planes_pago"]] == ["estandar", "pie-en-cuotas"]
    assert com["seriedad_promesa_uf"] == 10 and com["pie_pct"] == 15
    ex = _extra(db, pid)
    assert ex["otro"] == 1 and ex["comercial"]["tipo_bono_pie"] == "Todo"
    assert ex["comercial"]["planes_pago"][0]["cuotas_pago_inicial"] == 3
    # valores por defecto completos al guardar
    assert ex["comercial"]["planes_pago"][1]["descuentos_adicionales"] == []
    # /comercial (cualquier asesor con sesión) los devuelve
    c = client.get(f"/proyectos/{pid}/comercial", headers=h).json()["comercial"]
    assert c["seriedad_promesa_uf"] == 10
    assert c["planes_pago"][0]["nombre"] == "Estándar"
    assert c["planes_pago"][0]["nota_pago_pie"] == "Pie en cuotas sin interés."


def test_comercial_filtra_claves_desconocidas_de_cada_plan(client, admin, db):
    _, h = admin
    plan = {**_plan(), "comision_secreta": 3}
    pid = _proy(db, "test-planes-filtro", extra={"comercial": {"planes_pago": [plan]}})
    c = client.get(f"/proyectos/{pid}/comercial", headers=h).json()["comercial"]
    assert "comision_secreta" not in c["planes_pago"][0]
    assert c["planes_pago"][0]["pie_pct"] == 20


def test_patch_no_cuadra_422_en_espanol(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-cuadra")
    r = _patch(client, h, pid, {"planes_pago": [_plan(pie_pct=20.5)]})
    assert r.status_code == 422
    assert r.json()["detail"] == 'El plan "Estándar" no cuadra: faltan 0,5%'
    r = _patch(client, h, pid, {"planes_pago": [_plan(cuoton_final_pct=4)]})
    assert r.status_code == 422
    assert r.json()["detail"] == 'El plan "Estándar" no cuadra: sobran 1%'
    assert "planes_pago" not in (_extra(db, pid).get("comercial") or {})
    # decimales que en binario no suman exacto, en centésimas sí cuadran
    ok = _plan(pie_pct=0.3, cuoton_inicial_pct=0.1, pago_construccion_pct=0.2,
               cuoton_final_pct=0, bono_pie_pct=0)
    assert _patch(client, h, pid, {"planes_pago": [ok]}).status_code == 200


def test_ids_duplicados_y_dos_predeterminados_422(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-ids")
    r = _patch(client, h, pid, {"planes_pago": [_plan(), _plan(predeterminado=False)]})
    assert r.status_code == 422 and r.json()["detail"] == "Hay dos planes con el mismo id"
    r = _patch(client, h, pid, {"planes_pago": [_plan(), _otro_plan(predeterminado=True)]})
    assert r.status_code == 422 and r.json()["detail"] == "Solo puede haber un plan predeterminado"
    assert _patch(client, h, pid, {"planes_pago": [_plan(id="Con Mayúscula")]}).status_code == 422
    assert _patch(client, h, pid, {"planes_pago": [_plan(nombre="  ")]}).status_code == 422
    r = _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 1001})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert "planes_pago" not in (_extra(db, pid).get("comercial") or {})


def test_predeterminado_inactivo_422(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-inactivo")
    r = _patch(client, h, pid, {"planes_pago": [_plan(activo=False)]})
    assert r.status_code == 422 and r.json()["detail"] == "El plan predeterminado debe estar activo"


def test_sin_permiso_de_stock_da_403(client, db):
    pid = _proy(db, "test-planes-403")
    email = "asesor.prueba.interna@test.local"
    if not db.query(Usuario).filter(Usuario.email == email).first():
        db.add(Usuario(email=email, nombre="Prueba Interna", password_hash=hash_password("x1234567"),
                       is_admin=False, activo=True))
        db.commit()
    h = {"Authorization": f"Bearer {create_token(sub=email)[0]}"}
    assert _patch(client, h, pid, {"planes_pago": [_plan()]}).status_code == 403
    assert _patch(client, {}, pid, {"planes_pago": [_plan()]}).status_code in (401, 403)
    assert "comercial" not in _extra(db, pid)


def test_proyecto_inexistente_da_404(client, admin):
    _, h = admin
    assert _patch(client, h, "no-existe-planes", {"planes_pago": [_plan()]}).status_code == 404


def test_put_viejo_no_borra_planes(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-put")
    body = {"planes_pago": [_plan()], "seriedad_promesa_uf": 5}
    assert _patch(client, h, pid, body).status_code == 200
    guardado = _extra(db, pid)["comercial"]["planes_pago"]
    base = {"nombre": "Edificio Prueba Interna", "extra": {"comercial": {"pie_pct": 15}}}
    r = client.put(f"/proyectos/{pid}", headers=h, json=base)          # pestaña vieja: sin las claves
    assert r.status_code == 200, r.text
    com = _extra(db, pid)["comercial"]
    assert com["pie_pct"] == 15 and com["planes_pago"] == guardado and com["seriedad_promesa_uf"] == 5
    otra = {**base, "extra": {"comercial": {"pie_pct": 15, "planes_pago": [{"id": "x"}],
                                            "seriedad_promesa_uf": 99}}}
    assert client.put(f"/proyectos/{pid}", headers=h, json=otra).status_code == 200
    com = _extra(db, pid)["comercial"]
    assert com["planes_pago"] == guardado and com["seriedad_promesa_uf"] == 5


def test_put_wipe_importador_no_borra_planes(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-wipe")
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 5}).status_code == 200
    r = client.put(f"/proyectos/{pid}", headers=h,
                   json={"nombre": "Edificio Prueba Interna", "extra": {"jb_id": "x"}})
    assert r.status_code == 200, r.text
    ex = _extra(db, pid)
    assert ex["jb_id"] == "x"
    assert ex["comercial"]["planes_pago"][0]["id"] == "estandar"
    assert ex["comercial"]["seriedad_promesa_uf"] == 5


def test_put_sin_planes_en_servidor_no_los_crea(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-put-sin", extra={"comercial": {"pie_pct": 10}})
    r = client.put(f"/proyectos/{pid}", headers=h, json={
        "nombre": "Edificio Prueba Interna",
        "extra": {"comercial": {"pie_pct": 12, "planes_pago": [_plan()], "seriedad_promesa_uf": 3}}})
    assert r.status_code == 200, r.text
    assert _extra(db, pid)["comercial"] == {"pie_pct": 12}


def test_post_no_guarda_planes(client, admin, db):
    """Alta (o «duplicar proyecto») con planes en extra.comercial: se descartan."""
    _, h = admin
    pid = f"test-planes-post-{uuid.uuid4().hex[:8]}"
    r = client.post("/proyectos", headers=h, json={
        "id": pid, "nombre": "Edificio Prueba Interna",
        "extra": {"comercial": {"pie_pct": 10, "planes_pago": [{"id": "basura"}],
                                "seriedad_promesa_uf": -4}}})
    assert r.status_code == 201, r.text
    assert _extra(db, pid)["comercial"] == {"pie_pct": 10}


def test_patch_lista_vacia_borra_clave(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-vacia", extra={"comercial": {"pie_pct": 10}})
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 5}).status_code == 200
    r = _patch(client, h, pid, {"planes_pago": [], "seriedad_promesa_uf": None})
    assert r.status_code == 200, r.text
    # la versión sobrevive al borrado: si volviera a 0, una pestaña vieja podría coincidir con ella
    assert _extra(db, pid)["comercial"] == {"pie_pct": 10, "planes_rev": 2}
    assert "planes_pago" not in r.json()["comercial"]


def test_public_no_expone_planes(client, admin, db, monkeypatch):
    _, h = admin
    pid = _proy(db, "test-planes-public",
                extra={"publicar_en_catalogo": True, "comercial": {"pie_pct": 20}})
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 5}).status_code == 200
    monkeypatch.setattr(settings, "bc_api_service_token", "sk_test_planes")
    r = client.get(f"/proyectos/public/{pid}", headers={"Authorization": "Bearer sk_test_planes"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["comercial"]["pie_pct"] == 20
    assert "planes_pago" not in json.dumps(d) and "seriedad_promesa_uf" not in json.dumps(d)


def test_timeline_registra_evento(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-evento", extra={"timeline": [{"id": "tl-viejo", "tipo": "Nota"}]})
    assert _patch(client, h, pid, {"planes_pago": [_plan(), _otro_plan()],
                                   "seriedad_promesa_uf": 10}).status_code == 200
    tl = _extra(db, pid)["timeline"]
    assert tl[0]["tipo"] == "Planes de pago" and tl[1]["id"] == "tl-viejo"
    assert tl[0]["usuario"] == "admin@test.local" and tl[0]["origen_auto"] is False
    assert "2 planes" in tl[0]["detalles"] and "Estándar" in tl[0]["detalles"]
    assert _patch(client, h, pid, {"planes_pago": [], "seriedad_promesa_uf": None}).status_code == 200
    tl = _extra(db, pid)["timeline"]
    assert tl[0]["tipo"] == "Planes de pago" and tl[0]["detalles"] == "Planes de pago quitados"


def test_error_de_forma_422_en_espanol(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-forma")
    r = _patch(client, h, pid, {"planes_pago": [_plan("Estandar-MAYUS")]})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert isinstance(d, str)
    assert d.startswith("Los datos del plan no son válidos")
    assert "planes_pago[0].id" in d


def test_infinito_y_nan_dan_422_no_500(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-inf")
    ct = {**h, "content-type": "application/json"}
    for malo in ("Infinity", "NaN"):
        cuerpos = [
            '{"planes_pago": [], "seriedad_promesa_uf": %s}' % malo,
            json.dumps({"planes_pago": [_plan(cuota_pre_entrega_uf=0)]}).replace(
                '"cuota_pre_entrega_uf": 0', '"cuota_pre_entrega_uf": ' + malo),
            json.dumps({"planes_pago": [_plan(descuentos_adicionales=[
                {"id": "d", "nombre": "D", "monto": 0}])]}).replace('"monto": 0', '"monto": ' + malo),
        ]
        for c in cuerpos:
            r = client.patch(f"/proyectos/{pid}/planes-pago", headers=ct, content=c)
            assert r.status_code == 422, (malo, c, r.status_code)
            assert isinstance(r.json()["detail"], str)


def test_maximo_10_planes_422(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-max")
    plan = lambda i: _plan(f"plan-{i}", nombre=f"Plan {i}", orden=i, predeterminado=False)
    assert _patch(client, h, pid, {"planes_pago": [plan(i) for i in range(10)]}).status_code == 200
    r = _patch(client, h, pid, {"planes_pago": [plan(i) for i in range(11)]})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert "planes_pago" in r.json()["detail"]


def test_patch_sin_seriedad_la_conserva(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-conserva")
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 7}).status_code == 200
    r = _patch(client, h, pid, {"planes_pago": [_plan(nombre="Otro nombre")]})
    assert r.status_code == 200, r.text
    com = _extra(db, pid)["comercial"]
    assert com["seriedad_promesa_uf"] == 7
    assert com["planes_pago"][0]["nombre"] == "Otro nombre"


def test_descuento_del_plan_conserva_unidad(client, admin, db):
    """El editor envía {id, nombre, monto, unidad, tipo, alcance}: la unidad no se pierde al guardar."""
    _, h = admin
    pid = _proy(db, "test-planes-desc-unidad")
    desc = {"id": "d1", "nombre": "Descuento lanzamiento", "monto": 50, "unidad": "UF",
            "tipo": "propiedad", "alcance": "todo"}
    r = _patch(client, h, pid, {"planes_pago": [_plan(descuentos_adicionales=[desc])]})
    assert r.status_code == 200, r.text
    guardado = _extra(db, pid)["comercial"]["planes_pago"][0]["descuentos_adicionales"][0]
    assert guardado["unidad"] == "UF" and guardado["monto"] == 50


def test_mes_de_inicio_de_cuotas_como_yyyy_mm(client, admin, db):
    """El editor usa <input type=month>: el mes de inicio viaja como texto «YYYY-MM»."""
    _, h = admin
    pid = _proy(db, "test-planes-mes-inicio")
    plan = _plan(cuotas_auto_decremento=True, cuotas_inicio_mes="2026-11",
                 cuotas_post_auto_decremento=True, cuotas_post_inicio_mes="2027-03")
    r = _patch(client, h, pid, {"planes_pago": [plan]})
    assert r.status_code == 200, r.text
    c = client.get(f"/proyectos/{pid}/comercial", headers=h).json()["comercial"]
    assert c["planes_pago"][0]["cuotas_inicio_mes"] == "2026-11"
    assert c["planes_pago"][0]["cuotas_post_inicio_mes"] == "2027-03"
    # vacío = sin mes
    r = _patch(client, h, pid, {"planes_pago": [_plan(cuotas_inicio_mes="", cuotas_post_inicio_mes=None)]})
    assert r.status_code == 200, r.text
    assert _extra(db, pid)["comercial"]["planes_pago"][0]["cuotas_inicio_mes"] is None
    # mes inválido → 422 en español
    for malo in ("2026-13", "2026-1", "11", 11):
        r = _patch(client, h, pid, {"planes_pago": [_plan(cuotas_inicio_mes=malo)]})
        assert r.status_code == 422, (malo, r.text)
        d = r.json()["detail"]
        assert isinstance(d, str) and d.startswith("Los datos del plan no son válidos")
        assert "cuotas_inicio_mes" in d


# ── Control de versión (extra.comercial.planes_rev) ───────────────────────────────────

MSG_CONFLICTO = "Otra persona cambió los planes de este proyecto. Recarga la página para ver la última versión."


def test_rev_sube_con_cada_cambio_y_se_entrega(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-rev")
    r = _patch(client, h, pid, {"planes_pago": [_plan()]})
    assert r.status_code == 200 and r.json()["comercial"]["planes_rev"] == 1
    r = _patch(client, h, pid, {"planes_pago": [_plan(nombre="Otro")]})
    assert r.json()["comercial"]["planes_rev"] == 2
    assert client.get(f"/proyectos/{pid}/comercial", headers=h).json()["comercial"]["planes_rev"] == 2
    assert client.get(f"/proyectos/{pid}", headers=h).json()["extra"]["comercial"]["planes_rev"] == 2


def test_rev_vieja_da_409_y_no_toca_nada(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-409")
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "planes_rev": 0}).status_code == 200
    assert _patch(client, h, pid, {"planes_pago": [_plan(nombre="Dos")], "planes_rev": 1}).status_code == 200
    antes = _extra(db, pid)
    r = _patch(client, h, pid, {"planes_pago": [], "planes_rev": 1})      # pestaña vieja
    assert r.status_code == 409 and r.json()["detail"] == MSG_CONFLICTO
    assert _extra(db, pid) == antes


def test_rev_contra_proyecto_sin_rev_se_compara_con_cero(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-rev-cero")
    r = _patch(client, h, pid, {"planes_pago": [_plan()], "planes_rev": 3})
    assert r.status_code == 409 and r.json()["detail"] == MSG_CONFLICTO
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "planes_rev": 0}).status_code == 200


def test_sin_rev_o_null_se_comporta_como_hoy(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-sin-rev")
    assert _patch(client, h, pid, {"planes_pago": [_plan()]}).status_code == 200
    assert _patch(client, h, pid, {"planes_pago": [_plan(nombre="B")]}).status_code == 200
    assert _patch(client, h, pid, {"planes_pago": [_plan(nombre="C")], "planes_rev": None}).status_code == 200
    assert _extra(db, pid)["comercial"]["planes_rev"] == 3


@pytest.mark.parametrize("malo", [True, "1", 1.5])
def test_rev_de_tipo_invalido_422(client, admin, db, malo):
    _, h = admin
    pid = _proy(db, "test-planes-rev-tipo")
    r = _patch(client, h, pid, {"planes_pago": [_plan()], "planes_rev": malo})
    assert r.status_code == 422 and "planes_rev" in r.json()["detail"]


def test_rev_no_sale_en_publico(client, admin, db, monkeypatch):
    _, h = admin
    pid = _proy(db, "test-planes-rev-pub", extra={"publicar_en_catalogo": True, "comercial": {"pie_pct": 20}})
    assert _patch(client, h, pid, {"planes_pago": [_plan()]}).status_code == 200
    monkeypatch.setattr(settings, "bc_api_service_token", "sk_test_planes")
    r = client.get(f"/proyectos/public/{pid}", headers={"Authorization": "Bearer sk_test_planes"})
    assert r.status_code == 200 and "planes_rev" not in r.text
    r = client.get("/proyectos/public", headers={"Authorization": "Bearer sk_test_planes"})
    assert r.status_code == 200 and "planes_rev" not in r.text


def test_put_y_post_protegen_rev(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-rev-put")
    assert _patch(client, h, pid, {"planes_pago": [_plan()]}).status_code == 200
    base = {"nombre": "Edificio Prueba Interna"}
    assert client.put(f"/proyectos/{pid}", headers=h, json={
        **base, "extra": {"comercial": {"planes_rev": 99}}}).status_code == 200
    assert _extra(db, pid)["comercial"]["planes_rev"] == 1
    assert client.put(f"/proyectos/{pid}", headers=h, json={**base, "extra": {}}).status_code == 200
    assert _extra(db, pid)["comercial"]["planes_rev"] == 1
    sin = _proy(db, "test-planes-rev-put-sin")
    assert client.put(f"/proyectos/{sin}", headers=h, json={
        **base, "extra": {"comercial": {"pie_pct": 1, "planes_rev": 9}}}).status_code == 200
    assert _extra(db, sin)["comercial"] == {"pie_pct": 1}
    nuevo = f"test-planes-rev-post-{uuid.uuid4().hex[:8]}"
    assert client.post("/proyectos", headers=h, json={
        "id": nuevo, **base, "extra": {"comercial": {"pie_pct": 1, "planes_rev": 9}}}).status_code == 201
    assert _extra(db, nuevo)["comercial"] == {"pie_pct": 1}


# ── Sin cambios: no crece el timeline ni sube la versión ─────────────────────────────

def test_patch_identico_no_agrega_evento_ni_sube_rev(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-igual")
    body = {"planes_pago": [_plan(), _otro_plan()], "seriedad_promesa_uf": 10}
    assert _patch(client, h, pid, body).status_code == 200
    db.expire_all()
    antes = db.get(Proyecto, pid)
    extra_antes, updated_antes = antes.extra, antes.updated_at
    db.rollback()
    r = _patch(client, h, pid, {**body, "planes_rev": 1})
    assert r.status_code == 200 and r.json() == {"ok": True, "comercial": extra_antes["comercial"]}
    assert _patch(client, h, pid, {"planes_pago": body["planes_pago"]}).status_code == 200   # seriedad no viene
    db.expire_all()
    despues = db.get(Proyecto, pid)
    assert despues.extra == extra_antes and despues.updated_at == updated_antes
    assert len(despues.extra["timeline"]) == 1


def test_lista_vacia_sin_planes_no_es_cambio(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-vacia-igual", extra={"otro": 1})
    r = _patch(client, h, pid, {"planes_pago": [], "seriedad_promesa_uf": None})
    assert r.status_code == 200
    assert _extra(db, pid) == {"otro": 1}


def test_solo_seriedad_cuenta_como_cambio(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-seriedad")
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 10}).status_code == 200
    assert _patch(client, h, pid, {"planes_pago": [_plan()], "seriedad_promesa_uf": 11}).status_code == 200
    ex = _extra(db, pid)
    assert ex["comercial"]["planes_rev"] == 2 and len(ex["timeline"]) == 2


def test_rev_vieja_gana_aunque_no_haya_cambio(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-igual-409")
    assert _patch(client, h, pid, {"planes_pago": [_plan()]}).status_code == 200
    r = _patch(client, h, pid, {"planes_pago": [_plan()], "planes_rev": 0})
    assert r.status_code == 409


# ── Bloqueo de fila: PATCH y PUT se serializan ───────────────────────────────────────

def _en_hilo(fn):
    out = {}
    t = threading.Thread(target=lambda: out.update(r=fn()), daemon=True)
    t.start()
    return t, out


def _bloquear_y_escribir(db, pid, hilo, comercial):
    """La fila ya está bloqueada por `db`: confirma que el hilo espera, escribe y suelta."""
    time.sleep(0.4)
    assert hilo.is_alive(), "la petición no esperó el bloqueo de fila"
    fila = db.execute(select(Proyecto).where(Proyecto.id == pid)).scalars().one()
    fila.extra = {**(fila.extra or {}), "comercial": comercial}
    db.commit()
    hilo.join(15)
    assert not hilo.is_alive()


def _bloquear(db, pid):
    db.expire_all()
    db.execute(select(Proyecto).where(Proyecto.id == pid).with_for_update()).scalars().one()


def test_patch_espera_y_parte_de_la_ultima_version(admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-lock-patch")
    _bloquear(db, pid)
    hilo, out = _en_hilo(lambda: _patch(TestClient(app), h, pid, {"planes_pago": [_plan()]}))
    _bloquear_y_escribir(db, pid, hilo, {"planes_rev": 7, "pie_pct": 33})
    assert out["r"].status_code == 200, out["r"].text
    com = _extra(db, pid)["comercial"]
    assert com["planes_rev"] == 8 and com["pie_pct"] == 33


def test_patch_que_espero_detecta_conflicto(admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-lock-409")
    _bloquear(db, pid)
    hilo, out = _en_hilo(lambda: _patch(TestClient(app), h, pid, {"planes_pago": [_plan()], "planes_rev": 0}))
    _bloquear_y_escribir(db, pid, hilo, {"planes_rev": 1, "planes_pago": [_otro_plan()]})
    assert out["r"].status_code == 409
    assert _extra(db, pid)["comercial"]["planes_pago"][0]["id"] == "pie-en-cuotas"


def test_put_espera_y_repone_desde_la_lectura_bloqueada(admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-lock-put", extra={"comercial": {"pie_pct": 1}})
    _bloquear(db, pid)
    cuerpo = {"nombre": "Edificio Prueba Interna", "extra": {"comercial": {"pie_pct": 15}}}
    hilo, out = _en_hilo(lambda: TestClient(app).put(f"/proyectos/{pid}", headers=h, json=cuerpo))
    _bloquear_y_escribir(db, pid, hilo, {"pie_pct": 1, "planes_pago": [_plan()],
                                         "seriedad_promesa_uf": 4, "planes_rev": 5})
    assert out["r"].status_code == 200, out["r"].text
    com = _extra(db, pid)["comercial"]
    assert com["pie_pct"] == 15 and com["planes_pago"][0]["id"] == "estandar"
    assert com["seriedad_promesa_uf"] == 4 and com["planes_rev"] == 5


def _fila_libre(pid) -> bool:
    otra = SessionLocal()
    try:
        otra.execute(select(Proyecto.id).where(Proyecto.id == pid).with_for_update(nowait=True)).all()
        return True
    except Exception:
        return False
    finally:
        otra.rollback()
        otra.close()


@pytest.mark.parametrize("rev,codigo", [(99, 409), (1, None)])
def test_patch_suelta_el_bloqueo_antes_de_responder(admin, db, rev, codigo):
    """Respuestas sin escritura (409 y «sin cambios»): la fila no queda bloqueada hasta cerrar la sesión."""
    usuario, h = admin
    pid = _proy(db, "test-planes-suelta")
    _patch(TestClient(app), h, pid, {"planes_pago": [_plan()]})
    sesion = SessionLocal()
    try:
        try:
            set_planes_pago(proyecto_id=pid, raw={"planes_pago": [_plan()], "planes_rev": rev},
                            db=sesion, usuario=usuario)
            assert codigo is None
        except HTTPException as e:
            assert e.status_code == codigo
        assert _fila_libre(pid)
    finally:
        sesion.close()


# ── Validaciones ─────────────────────────────────────────────────────────────────────

_NUL = "Prueba\u0000Interna"
_DESC = {"id": "d1", "nombre": "Descuento"}


@pytest.mark.parametrize("over,campo", [
    ({"nombre": _NUL}, "nombre"),
    ({"promocion": _NUL}, "promocion"),
    ({"nota_pago_pie": _NUL}, "nota_pago_pie"),
    ({"descuentos_adicionales": [{**_DESC, "id": _NUL}]}, "descuentos_adicionales[0].id"),
    ({"descuentos_adicionales": [{**_DESC, "nombre": _NUL}]}, "descuentos_adicionales[0].nombre"),
    ({"descuentos_adicionales": [{**_DESC, "unidad": "\u0000"}]}, "descuentos_adicionales[0].unidad"),
    ({"descuentos_adicionales": [{**_DESC, "tipo": "\u0000"}]}, "descuentos_adicionales[0].tipo"),
    ({"descuentos_adicionales": [{**_DESC, "alcance": "\u0000"}]}, "descuentos_adicionales[0].alcance"),
])
def test_caracter_nul_da_422_en_espanol(client, admin, db, over, campo):
    _, h = admin
    pid = _proy(db, "test-planes-nul")
    r = _patch(client, h, pid, {"planes_pago": [_plan(**over)]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == f"Los datos del plan no son válidos: revisa planes_pago[0].{campo}"


@pytest.mark.parametrize("x,esperado", [
    (0.125, 13), (0.135, 14), (0.025, 3), (1.005, 100), (4.35, 435), (1.1, 110), (0, 0), (None, 0), (100, 10000),
    (-0.125, -12),
])
def test_centesimas_igual_que_math_round(x, esperado):
    assert _c(x) == esperado


_PCTS = ("pie_pct", "cuoton_inicial_pct", "pago_construccion_pct", "cuoton_final_pct", "bono_pie_pct")


@pytest.mark.parametrize("campo", _PCTS)
def test_mas_de_dos_decimales_422(client, admin, db, campo):
    _, h = admin
    pid = _proy(db, "test-planes-decimales")
    r = _patch(client, h, pid, {"planes_pago": [_plan(**{campo: 1.125})]})
    assert r.status_code == 422
    assert r.json()["detail"] == 'El plan "Estándar": cada porcentaje puede tener como máximo 2 decimales'


def test_dos_decimales_que_en_binario_no_son_exactos_pasan(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-dos-dec")
    ok = _plan(pie_pct=16.45, cuoton_inicial_pct=4.35, pago_construccion_pct=1.1,
               cuoton_final_pct=0.07, bono_pie_pct=10.93)
    r = _patch(client, h, pid, {"planes_pago": [ok]})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("over,campo", [
    ({"orden": -1}, "orden"),
    ({"orden": 1001}, "orden"),
    ({"cuota_pre_entrega_uf": 100000.5}, "cuota_pre_entrega_uf"),
    ({"descuentos_adicionales": [{**_DESC, "monto": 100001}]}, "descuentos_adicionales[0].monto"),
    ({"pie_pct": True}, "pie_pct"),
    ({"cuoton_inicial_pct": True}, "cuoton_inicial_pct"),
    ({"pago_construccion_pct": False}, "pago_construccion_pct"),
    ({"cuoton_final_pct": False}, "cuoton_final_pct"),
    ({"bono_pie_pct": True}, "bono_pie_pct"),
    ({"pie_pct": "20"}, "pie_pct"),
    ({"descuentos_adicionales": [{**_DESC, "pct": True}]}, "descuentos_adicionales[0].pct"),
])
def test_topes_y_booleanos_422(client, admin, db, over, campo):
    _, h = admin
    pid = _proy(db, "test-planes-topes")
    r = _patch(client, h, pid, {"planes_pago": [_plan(**over)]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == f"Los datos del plan no son válidos: revisa planes_pago[0].{campo}"


def test_topes_en_el_borde_pasan(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-borde")
    plan = _plan(orden=1000, cuota_pre_entrega_uf=100000,
                 descuentos_adicionales=[{**_DESC, "monto": 100000, "pct": 2.5}])
    r = _patch(client, h, pid, {"planes_pago": [plan]})
    assert r.status_code == 200, r.text


def test_numero_gigante_y_sustituto_suelto_no_dan_500(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-planes-raros")
    ct = {**h, "content-type": "application/json"}
    grande = "1" + "0" * 400
    base = json.dumps({"planes_pago": [_plan(cuota_pre_entrega_uf=0, promocion="x")]})
    for c in (base.replace('"pie_pct": 20', '"pie_pct": ' + grande),
              base.replace('"cuota_pre_entrega_uf": 0', '"cuota_pre_entrega_uf": ' + grande),
              base.replace('"promocion": "x"', '"promocion": "\\ud800"')):
        r = TestClient(app, raise_server_exceptions=False).patch(
            f"/proyectos/{pid}/planes-pago", headers=ct, content=c)
        assert r.status_code == 422, (c[:80], r.status_code, r.text[:200])
