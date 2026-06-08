"""
import_detail.py — Importador v2 para proyectos PROPIOS de BigCapital (vía /projects/detail).

Pipeline 100% API (httpx con Referer=/projects/detail/{id}):
  GET  /project/{id}/detail              → ficha (incluye lo privado)
  GET  /apartment-model/project/{id}/all → modelos (nombre COMERCIAL + blueprint=planta)
  POST /apartment/project-detail-search  → unidades (5 superficies, precios)
  GET  /project/{id}/notes               → notas HTML
  (files endpoint autodetectado)         → fotos + documentos
  GET  /file/download/{fileId}/{w}/{h}   → imágenes

Correcciones del usuario:
  - inmobiliaria = developerName (ej "MNK"), NUNCA organization/BigCapital
  - nombres de modelo = comercial directo de la API
  - fachada (cover) = foto principal
  - no colapsar modelos por tipología (clave = apartmentModel.id; planta = blueprint)

DRY_RUN=1 (default) → NO escribe en bc-api, solo muestra el mapeo. DRY_RUN=0 → importa.
Env: JETBROKERS_EMAIL, JETBROKERS_PASS, BC_API_JWT (real para escribir), DIAG_ID o DIAG_LINK
"""
from __future__ import annotations
import asyncio, json, os, re, sys, time, unicodedata
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa: E402
import httpx  # noqa: E402

OUT = Path("imports/_detail"); OUT.mkdir(parents=True, exist_ok=True)
DRY = os.environ.get("DRY_RUN", "1") != "0"
# SAMPLE_PCT (1-100, default 100): solo importa el primer N% de unidades.
# Ficha + modelos + plantas + estac/bodegas/packs + fotos = SIEMPRE 100%.
try:
    SAMPLE_PCT = max(1, min(100, int(os.environ.get("SAMPLE_PCT", "100"))))
except Exception:
    SAMPLE_PCT = 100
LINK = os.environ.get("DIAG_LINK", "")
_m = re.search(r"(?:detail|workview|edit)/([A-Za-z0-9]+)", LINK)
PID = (_m.group(1) if _m else None) or os.environ.get("DIAG_ID", "").strip() or "exrBr6Tp"
# Tipo de proyecto: 'own' (BigCapital, /projects/detail|edit) o 'mkt' (reventa, /marketplace/workview)
MODE = "mkt" if ("workview" in LINK or os.environ.get("MODE") == "mkt") else "own"
REF_PATH = f"projects/detail/{PID}" if MODE == "own" else f"marketplace/workview/{PID}"

COTIZA = {"never": "Nunca", "optional": "Opcional", "required": "Obligatorio", None: "Opcional"}
STAGE = {"green": "En Verde", "deliveryReady": "Entrega Inmediata", "whiteWork": "Obra Gruesa",
         "construction": "En Construcción", "finished": "Terminado"}
MODALITY = {"new": "Nuevo", "used": "Usado"}
# Enums JB (inglés) → valores en español del catálogo del frontend (data/datasets.js)
PIE_T = {"voluntary": "Opcional", "optional": "Opcional", "required": "Obligatorio", "mandatory": "Obligatorio"}
DESC_T = {"all": "Todo", "onlyapartment": "Solo Unidad", "no": "No", "none": "No"}
BONO_T = {"all": "Todo", "onlyapartment": "Solo Unidad", "no": "No", "none": "No"}
RES_T = {"downpayment": "Pie", "pie": "Pie", "operationalexpenses": "Gastos operacionales",
         "expense": "Gastos operacionales", "expenses": "Gastos operacionales",
         "torefund": "A devolver", "refundable": "A devolver", "refund": "A devolver"}
DEST_T = {"projectdeveloper": "Inmobiliaria", "developer": "Inmobiliaria", "broker": "Broker"}
CESION_T = {"no": "No", "yesauthorized": "Si, con autorización de la inmobiliaria",
            "yesemergency": "Si, sólo en casos de emergencia", "yesopen": "Si, abierta", "yes": "Si, abierta"}
CUENTA_T = {"cta corriente": "Cuenta Corriente", "cuenta corriente": "Cuenta Corriente",
            "corriente": "Cuenta Corriente", "checking": "Cuenta Corriente",
            "cta vista": "Cuenta Vista", "cuenta vista": "Cuenta Vista", "vista": "Cuenta Vista",
            "ahorro": "Cuenta de Ahorro", "cuenta de ahorro": "Cuenta de Ahorro", "savings": "Cuenta de Ahorro",
            "rut": "CuentaRUT", "cuentarut": "CuentaRUT"}
PERMISO_T = {"yes": "1", "no": "0", "inprocess": "tramite", "processing": "tramite", "intramite": "tramite"}
PREAP_T = {"no": "No", "atpromise": "Aprobación a la promesa", "atreservation": "Aprobación a la reserva",
           "yespromise": "Si, a la promesa", "yesreservation": "Si, a la reserva"}
STOCK_T = {"shared": "Compartido", "exclusive": "Exclusivo", "own": "Propio", "private": "Propio"}


def emap(d, v):
    """Mapea un enum JB a su valor español; si no está en el mapa, deja el original."""
    if v in (None, ""):
        return v
    return d.get(str(v).strip().lower(), v)
FILES_EPS = ["/organization/project-js-files/{id}/0", "/marketplace/files/{id}/0", "/project-file/{id}/list/0"]


def norm(s):
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def fnum(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def yn(v):
    return str(v).lower() in ("yes", "true", "1", "sí", "si")


def facing_es(f):
    """JB facing (inglés) → orientación chilena abreviada (N/S/O/P y combinaciones)."""
    if not f:
        return None
    k = str(f).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    m = {"north": "N", "south": "S", "east": "O", "west": "P",
         "northeast": "NO", "northwest": "NP", "southeast": "SO", "southwest": "SP",
         "eastnorth": "NO", "westnorth": "NP", "eastsouth": "SO", "westsouth": "SP"}
    return m.get(k, str(f)[:3].upper())


def asset_num(s):
    """assets number 'E100B38 [ 413,00 UF ] [...]' → 'E100B38' (lo de antes del primer corchete)."""
    return str(s or "").split("[")[0].strip()


def asset_uf(s):
    m = re.search(r"\[\s*([\d.,]+)\s*UF", str(s or ""))
    return fnum(m.group(1)) if m else None


def asset_m2(s):
    m = re.search(r"\[\s*([\d.,]+)\s*m2", str(s or ""))
    return fnum(m.group(1)) if m else None


async def jb_get(cli, ep):
    r = await cli.get(ep)
    return r.json() if r.status_code == 200 else None


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy"), imports_dir=OUT)
    await imp.login()
    page = imp._page
    # abrir la página del proyecto (establece contexto de sesión + token fresco)
    await page.goto(f"https://app.jetbrokers.io/{REF_PATH}", wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=40.0,
                            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                                     "Authorization": f"Bearer {imp._jb_token}",
                                     "Referer": f"https://app.jetbrokers.io/{REF_PATH}"})

    # ── Fetch (según tipo de proyecto) ──
    print(f"### MODO: {MODE}  (id {PID})", flush=True)
    mkt_assets = {}
    if MODE == "own":
        detail = await jb_get(cli, f"/project/{PID}/detail") or {}
        models = await jb_get(cli, f"/apartment-model/project/{PID}/all") or []
        # project-detail-search: probar ambos availability (algunos proyectos solo
        # responden con uno) y quedarse con el que traiga más unidades.
        units = []
        for av in (None, "available"):
            uts = int(time.time() * 1000)
            ubody = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
                     "projectId": PID, "availability": av, "number": None, "element": 0, "elements": 9999}
            ru = await cli.post(f"/apartment/project-detail-search/{uts}", json=ubody)
            if ru.status_code in (200, 201):
                u = (ru.json() or {}).get("apartments", [])
                if len(u) > len(units):
                    units = u
    else:  # marketplace — httpx flaky en algunos proyectos; assets FRESCO 1º + unidades del navegador
        acli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": "https://app.jetbrokers.io/quotes"})
        mkt_assets = await jb_get(acli, f"/project/{PID}/assets") or {}
        await acli.aclose()
        detail = await jb_get(cli, f"/marketplace/{PID}/workview") or {}
        ss = await jb_get(cli, f"/marketplace/stock-selectors/{PID}") or {}
        models = ss.get("models", []) if isinstance(ss, dict) else []
        # unidades: capturar units-search del NAVEGADOR (Stock tab + scroll) — confiable
        cap_units = []

        async def _cap(resp):
            if "units-search" in resp.url and resp.request.method == "POST":
                try:
                    cap_units.append(await resp.text())
                except Exception:
                    pass
        page.on("response", _cap)
        for sel in ('a:has-text("Stock")', '[role=tab]:has-text("Stock")', 'li:has-text("Stock")'):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=5_000)
                    break
            except Exception:
                pass
        await page.wait_for_timeout(4_000)
        for _ in range(45):
            try:
                await page.mouse.wheel(0, 600)
            except Exception:
                pass
            await page.wait_for_timeout(110)
        await page.wait_for_timeout(2_000)
        page.remove_listener("response", _cap)
        units = []
        for body in cap_units:
            try:
                u = json.loads(body).get("apartments", [])
                if len(u) > len(units):
                    units = u
            except Exception:
                pass
        if not units:  # fallback httpx
            for av in ("available", None):
                uts = int(time.time() * 1000)
                ubody = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
                         "projectId": PID, "availability": av, "number": None, "element": 0, "elements": 9999}
                ru = await cli.post(f"/marketplace/units-search/{uts}", json=ubody)
                if ru.status_code in (200, 201):
                    u = (ru.json() or {}).get("apartments", [])
                    if len(u) > len(units):
                        units = u
    # notas (intentar en ambos modos)
    notes = None
    rn = await cli.get(f"/project/{PID}/notes")
    if rn.status_code == 200:
        notes = rn.text
    # files: autodetectar endpoint
    files = []
    files_ep = None
    for tmpl in FILES_EPS:
        fr = await jb_get(cli, tmpl.replace("{id}", PID))
        if fr:
            lst = fr.get("files") if isinstance(fr, dict) else (fr if isinstance(fr, list) else None)
            if lst:
                files = lst; files_ep = tmpl; break
    # estac/bodegas/packs:
    if MODE == "mkt":
        # reventa: ya traído arriba (assets fresco) — /parking,/store dan 401
        parkings = mkt_assets.get("parkings", []) if isinstance(mkt_assets, dict) else []
        stores = mkt_assets.get("stores", []) if isinstance(mkt_assets, dict) else []
        packs = mkt_assets.get("packs", []) if isinstance(mkt_assets, dict) else []
        src_stock = "assets"
    else:
        # propios: consultar AMBAS fuentes y mergear.
        # - /list/0 trae 'surface' como campo plano (bodegas) y 'level' (estac).
        # - /project/{id}/assets trae A VECES más items (los list/0 puede no traer todos),
        #   pero embebe precio y m² en el campo 'number' ("X [P UF] [S m2]").
        # Estrategia: usar la lista MÁS LARGA por tipo, completando 'surface'/'level' desde la otra.
        pk_l = await jb_get(cli, f"/parking/project/{PID}/list/0")
        st_l = await jb_get(cli, f"/store/project/{PID}/list/0")
        pc_l = await jb_get(cli, f"/pack/project/{PID}/list/0")
        parkings_list = (pk_l.get("parkings") if isinstance(pk_l, dict) else None) or []
        stores_list = (st_l.get("stores") if isinstance(st_l, dict) else None) or []
        packs_list = (pc_l.get("packs") if isinstance(pc_l, dict) else None) or []
        acli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30.0,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": "https://app.jetbrokers.io/quotes"})
        assets = await jb_get(acli, f"/project/{PID}/assets") or {}
        await acli.aclose()
        parkings_a = assets.get("parkings", []) if isinstance(assets, dict) else []
        stores_a = assets.get("stores", []) if isinstance(assets, dict) else []
        packs_a = assets.get("packs", []) if isinstance(assets, dict) else []

        def _merge(list_, assets_, key="surface"):
            """Toma la lista más larga, completa con datos de la otra por número."""
            base = list_ if len(list_) >= len(assets_) else assets_
            other = assets_ if base is list_ else list_
            other_by_num = {asset_num(o.get("number")): o for o in other if o.get("number")}
            out = []
            for it in base:
                num = asset_num(it.get("number"))
                merged = dict(it)
                comp = other_by_num.get(num)
                if comp:
                    # completar campos faltantes
                    for k, v in comp.items():
                        if not merged.get(k) and v is not None:
                            merged[k] = v
                out.append(merged)
            return out

        parkings = _merge(parkings_list, parkings_a)
        stores = _merge(stores_list, stores_a)
        packs = _merge(packs_list, packs_a)
        src_stock = f"list({len(parkings_list)}/{len(stores_list)}/{len(packs_list)}) + assets({len(parkings_a)}/{len(stores_a)}/{len(packs_a)})"
    await cli.aclose()

    print(f"### {detail.get('name')!r} (id {PID})", flush=True)
    disp_u = sum(1 for u in units if u.get("available"))
    print(f"   estacionamientos={len(parkings)} ({sum(1 for p in parkings if p.get('available'))} disp) "
          f"bodegas={len(stores)} · unidades disponibles={disp_u}/{len(units)}", flush=True)
    print(f"   modelos={len(models)} unidades={len(units)} notas={len(notes) if notes else 0}b "
          f"archivos={len(files)} (via {files_ep})", flush=True)
    print(f"   developerName(inmobiliaria)={detail.get('developerName')!r} buildingCompany={detail.get('buildingCompany')!r} "
          f"organization={detail.get('organization')!r}", flush=True)

    # ── Mapear extra + modelos ──
    # inmobiliaria: propio → developerName (MNK); marketplace → organization.name (Maestra).
    # NUNCA "BigCapital" (es el broker, no inmobiliaria).
    org = detail.get("organization")
    org_name = org.get("name") if isinstance(org, dict) else None
    if org_name and org_name.strip().lower() in ("bigcapital", "big capital"):
        org_name = None
    inmob = detail.get("developerName") or org_name or detail.get("buildingCompany") or "Sin asignar"
    extra = {
        "jb_id": PID, "jb_id_v2": True,
        "descripcion": detail.get("description"),
        "condiciones_especiales": detail.get("termDetails") or detail.get("saleRoomConditions"),
        "promocion_broker": detail.get("promoBroker"),
        "promocion_cliente": detail.get("promoCustomer"),
        "stock_type": emap(STOCK_T, detail.get("stockType")),
        "solicita_preaprobacion": emap(PREAP_T, detail.get("preApprovalRequired")),
        "etiquetas": detail.get("tags") or [],
        "equipamiento": detail.get("perks") or [],
        "areas_comunes": detail.get("perksCommonAreas") or [],
        "entorno": detail.get("perksNearby") or [],
        "notas_html": notes,
        "fisicos": {
            "pisos": detail.get("floors"),
            # Totales: si JB no los declara, fallback al conteo REAL de los arrays.
            "unidades_totales": detail.get("apartmentsTotal") or (len(units) if units else None),
            "unidades_por_piso": detail.get("apartmentsByFloor"),
            "estacionamientos_totales": detail.get("parkingsTotal") or (len(parkings) if parkings else None),
            "bodegas_totales": detail.get("storesTotal") or (len(stores) if stores else None),
            "ascensores": detail.get("elevatorsTotal"),
            "constructora": detail.get("buildingCompany"),
            "permiso_construccion": emap(PERMISO_T, detail.get("buildingPermit")),
            "numero_permiso": detail.get("buildingPermitNumber"),
            "acepta_cesion": emap(CESION_T, detail.get("allowTransfer")),
        },
        "comercial": {
            "pie_pct": fnum(detail.get("pie")), "tipo_pie": emap(PIE_T, detail.get("pieTipo")),
            "cuoton_inicial_pct": fnum(detail.get("cuotonInicial")),
            "cuoton_final_pct": fnum(detail.get("cuotonFinal")),
            "tipo_descuento": emap(DESC_T, detail.get("discountType")),
            "tipo_bono_pie": emap(BONO_T, detail.get("bonoPieTipo")),
            "valor_reserva_clp": detail.get("reservaCLP"),
            "tipo_reserva": emap(RES_T, detail.get("reservaTipo")),
            "destino_reserva": emap(DEST_T, detail.get("reservaDestino")),
            "valor_cuota_clp": detail.get("valorCuotaCLP"),
        },
        "formas_pago_pie": {
            "cuotas_pre_entrega": detail.get("cuotasPreEntrega"),
            "cuotas_post_entrega": detail.get("cuotasPostEntrega"),
            "pago_pre_entrega": detail.get("payMethodPreEntrega"),
            "pago_post_entrega": detail.get("payMethodPostEntrega"),
            "pago_cuoton_inicial": detail.get("payMethodCuotas"),
        },
        "cuenta_reserva": {
            "titular_nombre": detail.get("reserveName"), "titular_rut": detail.get("reserveTaxId"),
            "tipo_cuenta": emap(CUENTA_T, detail.get("reserveAccountType")), "numero_cuenta": detail.get("reserveAccountNumber"),
            "banco": detail.get("reserveBank"), "link_pago": detail.get("onlinePaymentLink"),
        },
        "spa_proyecto": {
            "nombre": detail.get("shellCompanyName"), "rut": detail.get("shellCompanyTaxId"),
            "direccion": detail.get("shellCompanyFulAddress"),
        },
    }
    # modelos (nombre comercial + planta por blueprint; clave = id, NO tipología)
    modelos = []
    for m in models:
        bp = m.get("blueprint")
        bp = bp.get("id") if isinstance(bp, dict) else bp
        modelos.append({
            "id": m.get("id"), "nombre": m.get("name"),
            "dormitorios": m.get("rooms"), "banos": m.get("bathrooms"),
            "cotiza_bodega": COTIZA.get(m.get("requiredStorage"), "Opcional"),
            "cotiza_estac": COTIZA.get(m.get("requiredParking"), "Opcional"),
            "cotiza_pack": COTIZA.get(m.get("requiredPack"), "Nunca"),
            "_blueprint": bp, "planta_url": None, "planta_thumb_src": None,
        })
    extra["modelos"] = modelos
    # estacionamientos / bodegas → extra.*_dom (formato cells que lee el frontend)
    # estac: 'level' viene de /list; assets embebe precio en number ("X [P UF] [- ]").
    extra["estacionamientos_dom"] = [
        {"cells": [None, asset_num(pk.get("number")),
                   pk.get("price") or asset_uf(pk.get("number")),
                   str(pk.get("level")) if pk.get("level") is not None else "",
                   (",".join(pk.get("type")) if isinstance(pk.get("type"), list) else str(pk.get("type") or ""))],
         "disponible": bool(pk.get("available", True))}
        for pk in parkings if pk.get("number")]
    # bodegas: /list/0 trae 'surface' como campo plano; assets embebe precio y m² en number.
    extra["bodegas_dom"] = [
        {"cells": [None, asset_num(st.get("number")),
                   st.get("price") or asset_uf(st.get("number")),
                   str(st.get("surface") or asset_m2(st.get("number")) or "")],
         "disponible": bool(st.get("available", True))}
        for st in stores if st.get("number")]
    extra["packs_dom"] = [
        {"numero": asset_num(pk.get("number")),
         "precio_uf": pk.get("price") or asset_uf(pk.get("number")),
         "estacionamientos": [asset_num(p.get("number")) for p in (pk.get("parkings") or [])],
         "bodegas": [asset_num(s.get("number")) for s in (pk.get("stores") or [])],
         "disponible": bool(pk.get("available", True))}
        for pk in packs if pk.get("number")]
    # mapa blueprint→nombre comercial + flags por modelo
    bp_name = {md["_blueprint"]: md["nombre"] for md in modelos if md.get("_blueprint")}
    id_name = {m.get("id"): m.get("name") for m in models}
    id_req = {m.get("id"): m for m in models}

    # ── Unidades ──
    def umodel(u):
        am = u.get("apartmentModel") or {}
        if isinstance(am, dict):
            return am.get("name") or bp_name.get((am.get("blueprint") or {}).get("id") if isinstance(am.get("blueprint"), dict) else am.get("blueprint")) or id_name.get(am.get("id"))
        return id_name.get(am)
    def uflags(u):
        am = u.get("apartmentModel") or {}
        mid = am.get("id") if isinstance(am, dict) else am
        md = id_req.get(mid) or (am if isinstance(am, dict) else {})
        return (md.get("requiredParking") or "optional",
                md.get("requiredStorage") or "optional",
                md.get("requiredPack") or "optional")
    unidades = []
    for u in units:
        est, bod, pak = uflags(u)
        unidades.append({
            "numero": u.get("number"), "modelo": umodel(u),
            "tipo": u.get("type") or "apartment", "orientacion": facing_es(u.get("facing")),
            "sup_total": fnum(u.get("surfaceTotal")), "sup_interior": fnum(u.get("surfaceInterior")),
            "sup_terraza": fnum(u.get("surfaceTerrace")), "sup_logia": fnum(u.get("surfaceLogia")),
            "sup_jardin": fnum(u.get("surfaceGarden")),
            "precio_lista_uf": fnum(u.get("price")), "precio_final_uf": fnum(u.get("finalPrice")),
            "descuento_pct": fnum(u.get("discountRate")) or 0, "bono_pie_pct": fnum(u.get("bonoPie")) or 0,
            "disponible": bool(u.get("available")), "id_externo": u.get("idExternal"),
            "estac_flag": est, "bodega_flag": bod, "pack_flag": pak,
        })

    # ── Reporte ──
    print(f"\n--- MODELOS ({len(modelos)}) ---", flush=True)
    tipc = Counter(); plset = set()
    for md in modelos:
        t = f"{md['dormitorios']}D{md['banos']}B"
        tipc[t] += 1
        if md.get("_blueprint"):  # ignorar None (modelos sin planta en JB)
            plset.add(md["_blueprint"])
        print(f"   {md['nombre']!r:8} {t}  planta={md['_blueprint']!r}  cotiza(bod/est/pack)="
              f"{md['cotiza_bodega']}/{md['cotiza_estac']}/{md['cotiza_pack']}", flush=True)
    con_planta = sum(1 for md in modelos if md.get("_blueprint"))
    print(f"   → {len(modelos)} modelos · {con_planta} con planta · {len(plset)} plantas DISTINTAS · {dict(tipc)}", flush=True)
    print(f"\n--- UNIDADES ({len(unidades)}) ---", flush=True)
    mset = {md["nombre"] for md in modelos}
    huer = sum(1 for u in unidades if u["modelo"] not in mset)
    print(f"   enlazadas a modelo: {len(unidades)-huer}/{len(unidades)} huérfanas={huer}", flush=True)
    disp_n = sum(1 for u in unidades if u["disponible"])
    orients = Counter(u["orientacion"] for u in unidades if u["orientacion"])
    print(f"   disponibles: {disp_n}/{len(unidades)} · orientaciones (ES abreviadas): {dict(orients)}", flush=True)
    if unidades:
        u0 = unidades[0]
        print(f"   ej: {u0['numero']} modelo={u0['modelo']!r} orient={u0['orientacion']!r} ST={u0['sup_total']} "
              f"int={u0['sup_interior']} precio={u0['precio_lista_uf']} disp={u0['disponible']} "
              f"flags(est/bod/pack)={u0['estac_flag']}/{u0['bodega_flag']}/{u0['pack_flag']}", flush=True)
    print(f"\n--- ESTACIONAMIENTOS / BODEGAS / PACKS ---", flush=True)
    print(f"   estacionamientos: {len(extra['estacionamientos_dom'])} · bodegas: {len(extra['bodegas_dom'])} · packs: {len(extra['packs_dom'])} (fuente: {src_stock})", flush=True)
    if extra["estacionamientos_dom"]:
        print(f"   ej estac: {extra['estacionamientos_dom'][0]}", flush=True)
    if extra["bodegas_dom"]:
        print(f"   ej bodega: {extra['bodegas_dom'][0]}", flush=True)
    if extra["packs_dom"]:
        print(f"   ej pack: {extra['packs_dom'][0]}", flush=True)
    print(f"\n--- FICHA → bc-api ---", flush=True)
    c = extra["comercial"]
    print(f"   ENUMS mapeados: tipo_pie={detail.get('pieTipo')!r}→{c['tipo_pie']!r} · "
          f"tipo_descuento={detail.get('discountType')!r}→{c['tipo_descuento']!r} · "
          f"tipo_bono_pie={detail.get('bonoPieTipo')!r}→{c['tipo_bono_pie']!r}", flush=True)
    print(f"   tipo_reserva={detail.get('reservaTipo')!r}→{c['tipo_reserva']!r} · "
          f"destino={detail.get('reservaDestino')!r}→{c['destino_reserva']!r} · "
          f"cesion={detail.get('allowTransfer')!r}→{extra['fisicos']['acepta_cesion']!r}", flush=True)
    print(f"   inmobiliaria={inmob!r} comuna={detail.get('locality')!r} direccion={detail.get('address')!r}", flush=True)
    print(f"   banco={extra['cuenta_reserva']['banco']!r} spa={extra['spa_proyecto']['nombre']!r} "
          f"cover/fachada={detail.get('cover')!r}", flush=True)
    if files:
        print(f"   archivos tipos: {dict(Counter(f.get('type') for f in files))}", flush=True)

    (OUT / "mapeo.json").write_text(json.dumps(
        {"extra": extra, "unidades": unidades[:3], "inmobiliaria": inmob, "n_unidades": len(unidades)},
        indent=2, ensure_ascii=False, default=str))

    if DRY:
        print(f"\n✓ DRY-RUN — nada escrito. (DRY_RUN=0 para importar de verdad)", flush=True)
        await imp.close(); return

    # ════════ ESCRITURA REAL EN BC-API ════════
    print(f"\n{'='*60}\n=== IMPORT REAL EN BC-API ===\n{'='*60}", flush=True)
    # buscar proyecto existente por jb_id o por nombre; si no, crear
    current = await imp.find_proyecto_by_jb_id(PID)
    if not current:
        listing = (await imp._bc_client.get("/proyectos")).json()
        for p in listing:
            if norm(detail.get("name")) and norm(detail.get("name")) == norm(p.get("nombre")):
                current = await imp.get_proyecto(p["id"]); break
    if not current:
        stub = {"nombre": detail.get("name"), "inmobiliaria": inmob, "modalidad": "Nuevo",
                "activo": True, "disponible": True, "extra": {"jb_id": PID}}
        r = await imp._bc_client.post("/proyectos", json=stub)
        current = r.json()
        print(f"   creado proyecto {current.get('id')}", flush=True)
    pid_bc = current["id"]
    print(f"   bc-api proyecto: {pid_bc}", flush=True)
    # wipe
    await imp._wipe_proyecto_full(pid_bc, current)
    current = await imp.get_proyecto(pid_bc)

    # descargar + subir plantas (por modelo) y fotos
    async def dl_upload(file_id, categoria, w=1600, h=1600, es_principal=False, ext="jpg"):
        try:
            url = f"https://app.jetbrokers.io/api/file/download/{file_id}/{w}/{h}"
            async with httpx.AsyncClient(timeout=60.0) as dc:
                resp = await dc.get(url, headers={"Authorization": f"Bearer {imp._jb_token}", **JB_HEADERS})
            if resp.status_code != 200 or len(resp.content) < 512:
                return None
            p = OUT / f"{file_id}.{ext}"
            p.write_bytes(resp.content)
            data = {"categoria": categoria, "es_principal": "true" if es_principal else "false"}
            with open(p, "rb") as fh:
                r = await imp._bc_client.post(f"/proyectos/{pid_bc}/imagenes",
                    files={"files": (p.name, fh.read(), "image/jpeg")}, data=data)
            if r.status_code in (200, 201):
                items = r.json()
                return items[0].get("url") if isinstance(items, list) and items else None
        except Exception as e:
            print(f"   asset {file_id} err: {str(e)[:50]}", flush=True)
        return None

    # plantas por modelo
    for md in modelos:
        if md.get("_blueprint"):
            u = await dl_upload(md["_blueprint"], f"jb-planta-{md['_blueprint']}")
            if u:
                md["planta_url"] = u
    # fachada (cover) como principal
    cover = detail.get("cover")
    if cover:
        await dl_upload(cover, "Fachada", es_principal=True)
    # fotos (perks) categorizadas
    CATMAP = {"projectPerkCommonArea": "Áreas comunes", "projectPerkNearby": "Entorno", "projectPerk": "Otro"}
    for f in files:
        t = f.get("type")
        if t in CATMAP and f.get("id"):
            await dl_upload(f["id"], CATMAP[t])

    extra["modelos"] = modelos  # con planta_url poblada
    # PUT proyecto
    body = {
        "nombre": detail.get("name"), "inmobiliaria": inmob,
        "comuna": detail.get("locality"), "direccion": detail.get("address"),
        "gps_lat": fnum(detail.get("gpsLat")), "gps_lon": fnum(detail.get("gpsLon")),
        "fase": STAGE.get(detail.get("stage"), detail.get("stage")),
        "modalidad": MODALITY.get(detail.get("modalityType"), "Nuevo"),
        "fecha_entrega": detail.get("dateOfDelivery"), "ano_entrega": detail.get("yearOfDelivery"),
        "disponible": yn(detail.get("available")), "activo": True,
        "notas": notes, "extra": {**(current.get("extra") or {}), **extra},
    }
    r = await imp._bc_client.put(f"/proyectos/{pid_bc}", json=body)
    print(f"   PUT proyecto → {r.status_code}", flush=True)
    # unidades — aplicar modo muestra si SAMPLE_PCT < 100
    unidades_a_insertar = unidades
    if SAMPLE_PCT < 100:
        n = max(1, len(unidades) * SAMPLE_PCT // 100)
        unidades_a_insertar = unidades[:n]
        print(f"   🎯 MODO MUESTRA {SAMPLE_PCT}%: {n}/{len(unidades)} unidades", flush=True)
    ok = 0
    for u in unidades_a_insertar:
        rr = await imp._bc_client.post(f"/proyectos/{pid_bc}/unidades", json=u)
        if rr.status_code in (200, 201):
            ok += 1
    print(f"   unidades insertadas: {ok}/{len(unidades_a_insertar)}"
          + (f" (de {len(unidades)} totales)" if SAMPLE_PCT < 100 else ""), flush=True)
    print(f"\n✓ IMPORT REAL completo: {pid_bc}", flush=True)
    print(f"   vista: https://herramientas.bigcapital.cl/src/stock-interno/proyecto-vista.html?id={pid_bc}", flush=True)
    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
