"""Arriendo Garantizado por la inmobiliaria (extra.garantia_arriendo) — 2026-11-03.

Caso real: Exequiel Fernández 2000 (Larraín Prieto) garantiza el arriendo hasta septiembre
2029 con un canon en UF por depto. La tabla vive en el proyecto, la escribe solo
PATCH /proyectos/{id}/garantia-arriendo, el PUT del editor no la pisa, al catálogo sale sin
la tabla y cada depto nuevo toma su monto de ella (sin pisar montos ya cargados).
"""
import io
import uuid

from openpyxl import Workbook

from app.models import Proyecto, Unidad, Usuario
from app.services.auth import create_token, hash_password
from app.settings import settings

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _garantia(pid, **over):
    g = {"hasta": "2029-09", "condiciones": "Lo garantiza la inmobiliaria según su tabla oficial.",
         "documento_url": f"/uploads/{pid}/canon.pdf", "moneda": "UF",
         "canon": {"201": 11.1, "508": 11.48, "509": 12.25}}
    g.update(over)
    return g


def _proy(db, base, extra=None, unidades=()):
    """Proyecto NUEVO por corrida (id único): una corrida previa contra la misma BD no contamina."""
    pid = f"{base}-{uuid.uuid4().hex[:8]}"
    db.add(Proyecto(id=pid, nombre="Edificio Prueba Interna", activo=True, extra=extra or {}))
    db.flush()
    for numero, kw in unidades:
        db.add(Unidad(id="u-" + uuid.uuid4().hex[:10], proyecto_id=pid, numero=numero,
                      tipo=kw.pop("tipo", "Depto"), disponible=kw.pop("disponible", True), **kw))
    db.commit()
    return pid


def _unidad(db, pid, numero):
    db.expire_all()
    return db.query(Unidad).filter(Unidad.proyecto_id == pid, Unidad.numero == numero).one()


def _extra(db, pid):
    db.expire_all()
    return db.get(Proyecto, pid).extra


def _patch(client, h, pid, body, **params):
    # JSON null explícito para quitar (httpx con json=None no manda cuerpo, y sin cuerpo es 422).
    import json
    return client.patch(f"/proyectos/{pid}/garantia-arriendo", params=params,
                        headers={**h, "Content-Type": "application/json"}, content=json.dumps(body))


# ── Guardar / leer / quitar ────────────────────────────────────────────────

def test_guardar_leer_y_quitar_sin_tocar_el_resto_de_extra(client, admin, db):
    _, h = admin
    otros = {"comercial": {"pie_pct": 20}, "timeline": [{"id": "tl-1", "tipo": "Excel Stock"}],
             "arriendos": {"201": {"valor": 10, "moneda": "UF"}}}
    pid = _proy(db, "test-garantia-guardar", extra=dict(otros),
                unidades=[("201", {}), ("508", {}), ("318", {}), ("E-1", {"tipo": "Estacionamiento"})])
    r = _patch(client, h, pid, _garantia(pid))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["aplicadas"] == 2 and out["sin_canon"] == ["318"]
    assert out["garantia_arriendo"]["canon"] == {"201": 11.1, "508": 11.48, "509": 12.25}
    ex = _extra(db, pid)
    assert ex["garantia_arriendo"]["hasta"] == "2029-09"
    for k, v in otros.items():
        assert ex[k] == v
    # GET /proyectos/{id} (ficha privada) la trae completa, con la tabla
    g = client.get(f"/proyectos/{pid}", headers=h).json()["extra"]["garantia_arriendo"]
    assert g["canon"]["508"] == 11.48
    u = _unidad(db, pid, "508")
    assert (u.arriendo_garantizado, u.arriendo_moneda) == (11.48, "UF")
    assert _unidad(db, pid, "318").arriendo_garantizado is None
    assert _unidad(db, pid, "E-1").arriendo_garantizado is None          # solo deptos

    r = _patch(client, h, pid, None)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "aplicadas": 0, "sin_canon": [], "garantia_arriendo": None}
    ex = _extra(db, pid)
    assert "garantia_arriendo" not in ex
    for k, v in otros.items():
        assert ex[k] == v
    assert _unidad(db, pid, "508").arriendo_garantizado == 11.48         # quitar no borra montos


def test_aplicar_vacios_no_pisa_y_sobrescribir_si(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-aplicar",
                unidades=[("201", {"arriendo_garantizado": 10.0, "arriendo_moneda": "UF"}), ("508", {})])
    r = _patch(client, h, pid, _garantia(pid))
    assert r.json()["aplicadas"] == 1
    assert _unidad(db, pid, "201").arriendo_garantizado == 10.0
    r = _patch(client, h, pid, _garantia(pid), aplicar="sobrescribir")
    assert r.json()["aplicadas"] == 1
    assert _unidad(db, pid, "201").arriendo_garantizado == 11.1
    # «aplicar» también puede venir en el cuerpo
    r = _patch(client, h, pid, {**_garantia(pid, canon={"201": 13.0}), "aplicar": "sobrescribir"})
    assert r.status_code == 200, r.text
    assert _unidad(db, pid, "201").arriendo_garantizado == 13.0
    assert "aplicar" not in _extra(db, pid)["garantia_arriendo"]


def test_validaciones_rechazan_datos_malos(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-valida")
    malos = [
        _garantia(pid, hasta="2029-13"),
        _garantia(pid, hasta="sep 2029"),
        _garantia(pid, hasta=None),
        _garantia(pid, condiciones="x" * 601),
        _garantia(pid, condiciones=123),
        _garantia(pid, documento_url="https://otro.sitio/canon.pdf"),
        _garantia(pid, documento_url="/uploads/otro-proyecto/canon.pdf"),
        _garantia(pid, documento_url=f"/uploads/{pid}/../otro/canon.pdf"),
        _garantia(pid, moneda="USD"),
        _garantia(pid, canon={"201": 0}),
        _garantia(pid, canon={"201": -5}),
        _garantia(pid, canon={"201": 1000.5}),
        _garantia(pid, canon={"201": "11,1"}),
        _garantia(pid, canon={"201": True}),
        _garantia(pid, canon={" ": 11.1}),
        _garantia(pid, canon=[11.1]),
        {**_garantia(pid), "otro_campo": 1},
        [1, 2],
        "texto",
    ]
    for body in malos:
        r = _patch(client, h, pid, body)
        assert r.status_code == 422, (body, r.text)
    assert _patch(client, h, pid, _garantia(pid), aplicar="todo").status_code == 422
    assert "garantia_arriendo" not in _extra(db, pid)
    # en el límite: se acepta
    ok = _garantia(pid, condiciones="x" * 600, canon={"201": 1000}, documento_url=None)
    r = _patch(client, h, pid, ok)
    assert r.status_code == 200, r.text
    assert r.json()["garantia_arriendo"]["documento_url"] is None


def test_sin_permiso_de_stock_da_403(client, db):
    pid = _proy(db, "test-garantia-403")
    email = "asesor.prueba.interna@test.local"
    if not db.query(Usuario).filter(Usuario.email == email).first():
        db.add(Usuario(email=email, nombre="Prueba Interna", password_hash=hash_password("x1234567"),
                       is_admin=False, activo=True))
        db.commit()
    h = {"Authorization": f"Bearer {create_token(sub=email)[0]}"}
    assert _patch(client, h, pid, _garantia(pid)).status_code == 403
    assert _patch(client, {}, pid, _garantia(pid)).status_code in (401, 403)
    assert "garantia_arriendo" not in _extra(db, pid)


def test_sin_cuerpo_no_quita_la_garantia(client, admin, db):
    """Un PATCH vacío (por error) no se interpreta como «quitar»: hay que mandar null."""
    _, h = admin
    pid = _proy(db, "test-garantia-vacio")
    assert _patch(client, h, pid, _garantia(pid)).status_code == 200
    r = client.patch(f"/proyectos/{pid}/garantia-arriendo", headers=h)
    assert r.status_code == 422
    assert _extra(db, pid)["garantia_arriendo"]["hasta"] == "2029-09"


def test_proyecto_inexistente_da_404(client, admin):
    _, h = admin
    assert _patch(client, h, "no-existe-garantia", _garantia("no-existe-garantia")).status_code == 404


# ── PUT del editor ──────────────────────────────────────────────────────────

def test_put_viejo_no_la_borra_y_otro_valor_no_la_cambia(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-put")
    assert _patch(client, h, pid, _garantia(pid)).status_code == 200
    base = {"nombre": "Edificio Prueba Interna", "extra": {"comercial": {"pie_pct": 15}}}
    r = client.put(f"/proyectos/{pid}", headers=h, json=base)               # pestaña vieja: sin la clave
    assert r.status_code == 200, r.text
    ex = _extra(db, pid)
    assert ex["garantia_arriendo"] == _garantia(pid) and ex["comercial"] == {"pie_pct": 15}
    otra = {**base, "extra": {**base["extra"], "garantia_arriendo": {"hasta": "2020-01", "canon": {}}}}
    assert client.put(f"/proyectos/{pid}", headers=h, json=otra).status_code == 200
    assert _extra(db, pid)["garantia_arriendo"] == _garantia(pid)
    # sin garantía en el servidor, lo que mande el navegador se descarta
    assert _patch(client, h, pid, None).status_code == 200
    assert client.put(f"/proyectos/{pid}", headers=h, json=otra).status_code == 200
    assert "garantia_arriendo" not in _extra(db, pid)


# ── Catálogo (Worker) ───────────────────────────────────────────────────────

def test_public_trae_la_garantia_sin_la_tabla(client, admin, db, monkeypatch):
    _, h = admin
    pid = _proy(db, "test-garantia-public", extra={"publicar_en_catalogo": True}, unidades=[("508", {})])
    assert _patch(client, h, pid, _garantia(pid)).status_code == 200
    monkeypatch.setattr(settings, "bc_api_service_token", "sk_test_garantia")
    r = client.get(f"/proyectos/public/{pid}", headers={"Authorization": "Bearer sk_test_garantia"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["garantia_arriendo"] == {"hasta": "2029-09", "moneda": "UF",
                                      "condiciones": "Lo garantiza la inmobiliaria según su tabla oficial.",
                                      "documento_url": f"/uploads/{pid}/canon.pdf"}
    assert "canon" not in d["garantia_arriendo"] and "11.48" not in str(d["garantia_arriendo"])
    u = next(x for x in d["unidades"] if x["numero"] == "508")
    assert (u["arriendo_garantizado"], u["arriendo_moneda"]) == (11.48, "UF")


def test_public_sin_garantia_no_trae_la_clave():
    from app.routes.proyectos import _public_extra
    assert "garantia_arriendo" not in _public_extra({"publicar_en_catalogo": True})
    assert "garantia_arriendo" not in _public_extra({"garantia_arriendo": "dato roto"})


# ── Unidades nuevas heredan el canon ────────────────────────────────────────

def _excel(filas):
    """Excel JB mínimo (Unidad Número, Modelo, ValorUF): el de la inmobiliaria no trae arriendo."""
    wb = Workbook()
    wb.remove(wb.active)
    wb.create_sheet("INSTRUCCIONES")
    u = wb.create_sheet("UNIDAD")
    u.append(["REQ", "REQ", "REQ"])
    u.append(["Unidad Número", "Modelo", "ValorUF"])
    for f in filas:
        u.append(f)
    for hoja in ("ESTACIONAMIENTOS", "BODEGAS"):
        s = wb.create_sheet(hoja)
        s.append(["OPC", "OPC"])
        s.append(["Número", "PrecioUF"])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def _subir(client, h, pid, filas):
    r = client.post(f"/proyectos/{pid}/unidades/excel/upload", headers=h,
                    files={"file": ("x.xlsx", _excel(filas), XLSX)})
    assert r.status_code == 200, r.text
    return r.json()


def test_excel_depto_nuevo_hereda_canon_y_no_pisa_montos(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-excel",
                unidades=[("508", {"arriendo_garantizado": 10.5, "arriendo_moneda": "UF"}), ("201", {})])
    db.expire_all()
    p = db.get(Proyecto, pid)
    p.extra = {"garantia_arriendo": _garantia(pid)}            # sin pasar por el PATCH: 201 sigue vacío
    db.commit()
    _subir(client, h, pid, [["508", "A1", 2500], ["201", "A1", 2400], ["509", "A1", 2600], ["318", "A1", 2300]])
    assert _unidad(db, pid, "509").arriendo_garantizado == 12.25             # nuevo: hereda
    assert _unidad(db, pid, "509").arriendo_moneda == "UF"
    assert _unidad(db, pid, "201").arriendo_garantizado == 11.1              # existente vacío: se rellena
    assert _unidad(db, pid, "508").arriendo_garantizado == 10.5              # monto existente: no se pisa
    assert _unidad(db, pid, "318").arriendo_garantizado is None              # sin canon: queda vacío
    assert _unidad(db, pid, "318").arriendo_moneda is None


def test_excel_sin_garantia_queda_igual(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-excel-sin")
    _subir(client, h, pid, [["509", "A1", 2600]])
    assert _unidad(db, pid, "509").arriendo_garantizado is None


def test_post_y_put_unidad_toman_el_canon_sin_pisar(client, admin, db):
    _, h = admin
    pid = _proy(db, "test-garantia-crud")
    assert _patch(client, h, pid, _garantia(pid)).status_code == 200
    base = f"/proyectos/{pid}/unidades"
    r = client.post(base, headers=h, json={"numero": "509", "tipo": "Depto"})
    assert r.status_code == 201, r.text
    assert (r.json()["arriendo_garantizado"], r.json()["arriendo_moneda"]) == (12.25, "UF")
    r = client.post(base, headers=h, json={"numero": "201", "arriendo_garantizado": 9.0, "arriendo_moneda": "UF"})
    assert r.json()["arriendo_garantizado"] == 9.0                          # trae monto: se respeta
    r = client.post(base, headers=h, json={"numero": "318"})
    assert r.json()["arriendo_garantizado"] is None                         # sin canon
    r = client.post(base, headers=h, json={"numero": "E-509", "tipo": "Estacionamiento"})
    assert r.json()["arriendo_garantizado"] is None

    uid = _unidad(db, pid, "201").id
    # editor viejo: PUT con el arriendo vacío → conserva el monto que ya tenía
    r = client.put(f"{base}/{uid}", headers=h, json={"numero": "201", "precio_lista_uf": 2400})
    assert r.status_code == 200, r.text
    assert (r.json()["arriendo_garantizado"], r.json()["arriendo_moneda"]) == (9.0, "UF")
    # un monto explícito sí cambia
    r = client.put(f"{base}/{uid}", headers=h, json={"numero": "201", "arriendo_garantizado": 11.1,
                                                     "arriendo_moneda": "UF"})
    assert r.json()["arriendo_garantizado"] == 11.1
    # unidad vacía + PUT vacío → toma el canon
    db.expire_all()
    u = _unidad(db, pid, "509")
    u.arriendo_garantizado, u.arriendo_moneda = None, None
    db.commit()
    r = client.put(f"{base}/{u.id}", headers=h, json={"numero": "509"})
    assert (r.json()["arriendo_garantizado"], r.json()["arriendo_moneda"]) == (12.25, "UF")
    # depto sin canon: el PUT vacío sigue limpiando como siempre
    uid318 = _unidad(db, pid, "318").id
    client.put(f"{base}/{uid318}", headers=h, json={"numero": "318", "arriendo_garantizado": 8.0})
    r = client.put(f"{base}/{uid318}", headers=h, json={"numero": "318"})
    assert r.json()["arriendo_garantizado"] is None
