"""
scrape_jb_quotes.py — Baja TODAS las cotizaciones de la organización desde
JetBroker (server-side, solo lectura) para alimentar el Informe Comercial de
Herramientas BC.

Hoy Herramientas BC solo captura cotizaciones JB importadas a mano (PDFs,
origen=pdf_jb). Este script usa el mismo endpoint que la UI de /quotes
(`POST /api/quote/organization/search`, descubierto por diag_quotes_explore.py)
para traer el listado completo, paginado, con: fecha, broker (createdBy),
cliente (customer + rut), proyecto/inmobiliaria, UF y unidad.

Flujo (idéntico patrón de auth que el importer de stock):
  1. login() de JBImporter (Playwright headless, secrets JETBROKERS_*).
  2. Navega a /quotes e INTERCEPTA la request real de búsqueda para copiar su
     postData + headers exactos (no se adivina el contrato).
  3. Reproduce esa request paginando (incrementa el offset) hasta juntar las
     `count` cotizaciones.
  4. Normaliza cada una y escribe imports/_jb_quotes/quotes_jb.json.

PII: el archivo de salida trae rut/nombre de cliente (necesario para el dedup
"una cotización por cliente, la más alta"). NUNCA se sube como artefacto ni se
commitea -- el workflow lo copia por SCP directo al VPS de Herramientas
(/var/www/herramientas/data/cotizaciones_jb/) donde ya viven las otras
cotizaciones con PII. Los logs solo imprimen KEYS y conteos, jamás valores.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS
Salida: imports/_jb_quotes/quotes_jb.json  (+ meta.json con conteos)
"""
from __future__ import annotations
import asyncio, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_jb_quotes")
OUT.mkdir(parents=True, exist_ok=True)

SEARCH_PATH = "/api/quote/organization/search"

# Claves de paginación candidatas (nombre de campo -> es_offset). El contrato
# real se detecta mirando el postData capturado; esto es solo el orden de
# preferencia si aparecen varias.
OFFSET_KEYS = ("offset", "skip", "from", "start")
LIMIT_KEYS = ("limit", "take", "size", "pageSize", "perPage")
PAGE_KEYS = ("page", "pageNumber", "pageIndex")


def _pick(d: dict, keys):
    for k in keys:
        if k in d:
            return k
    return None


def _first(d: dict, *names):
    """Primer valor no vacío entre varios nombres de campo posibles."""
    for n in names:
        if isinstance(d, dict) and d.get(n):
            return d.get(n)
    return None


def _num(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        try:
            return float(str(v))
        except ValueError:
            return 0.0


def normalize_quote(q: dict) -> dict:
    """Cotización JB cruda -> record chico y estable para Herramientas BC.
    Defensivo con los nombres de campo anidados (customer/createdBy/project
    pueden venir como dict o como string según la versión de la API)."""
    customer = q.get("customer") or {}
    created_by = q.get("createdBy") or {}
    project = q.get("project") or {}
    developer = q.get("developer") or {}

    def _name(v, *keys):
        if isinstance(v, dict):
            return _first(v, *keys)
        return v if isinstance(v, str) else None

    # UF del departamento -- mismo criterio que las cotizaciones PDF ya
    # importadas (financiero.precio_uf = precio del depto en UF). Los campos
    # *CLP son la versión en pesos; los sin sufijo son UF.
    uf = _num(_first(q, "apartmentPrice") or _first(q, "totalWithoutBonoPie") or _first(q, "totalPriceBonoPie"))

    return {
        "id": q.get("id"),
        "reference": q.get("reference"),
        "created_at": q.get("createdAt"),
        "broker_name": _name(created_by, "name", "fullName", "title") or _name(q.get("name"), "name"),
        # El listado de /quotes NO trae rut del cliente -- customer solo tiene
        # {id, name}. El customer.id de JB es un identificador estable por
        # cliente, así que sirve igual como clave de dedup "una cotización por
        # cliente, la más alta". Se guarda con prefijo jbc: para no chocar con
        # ruts reales de las otras fuentes (propuestas/simulaciones).
        "rut": (f"jbc:{customer.get('id')}" if isinstance(customer, dict) and customer.get("id") else None),
        "cliente_nombre": _name(customer, "fullName", "name"),
        "precio_uf": uf,
        "proyecto": _name(project, "name") or (developer if isinstance(developer, str) else _name(developer, "name")),
        "developer": _name(developer, "name") if isinstance(developer, dict) else developer,
        "unidad": q.get("apartmentNumber"),
        "modelo": q.get("modelName"),
        "jetstock": q.get("jetstock"),
    }


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"],
        jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"),
        imports_dir=OUT,
    )
    await imp.login()
    page = imp._page

    # ── 1. Capturar la request real de búsqueda ──
    captured = {"url": None, "post_data": None, "headers": None}

    async def on_request(req):
        if SEARCH_PATH in req.url and req.method == "POST" and captured["url"] is None:
            captured["url"] = req.url
            captured["post_data"] = req.post_data
            captured["headers"] = dict(req.headers)

    page.on("request", on_request)

    print("### Navegando a /quotes para capturar la request de búsqueda", flush=True)
    await page.goto("https://app.jetbrokers.io/quotes", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(4_000)
    page.remove_listener("request", on_request)

    if not captured["url"]:
        print("✗ No se capturó la request de búsqueda -- la UI de /quotes cambió?", flush=True)
        await imp.close()
        sys.exit(1)

    try:
        body = json.loads(captured["post_data"]) if captured["post_data"] else {}
    except Exception:
        body = {}
    # La paginación NO va en el postData (ahí solo hay filtros: reference,
    # broker, project, priceFrom/To, dateFrom/To, tipology, element) -- va en
    # el QUERY de la URL. Se parsea de la URL capturada. Sin PII: son params
    # de paginación/filtro vacíos, no datos de cliente.
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(captured["url"])
    qs = dict(parse_qsl(parts.query))
    print(f"   ✓ request capturada. postData keys={list(body.keys())} | query keys={list(qs.keys())}", flush=True)

    off_key = _pick(qs, OFFSET_KEYS)
    lim_key = _pick(qs, LIMIT_KEYS)
    page_key = _pick(qs, PAGE_KEYS)
    page_size = int(qs.get(lim_key)) if lim_key and str(qs.get(lim_key)).isdigit() else 30
    page_base = int(qs.get(page_key)) if page_key and str(qs.get(page_key)).isdigit() else 1
    print(f"   paginación (query URL): offset_key={off_key} page_key={page_key} "
          f"limit_key={lim_key} page_size={page_size} page_base={page_base}", flush=True)

    # Cliente HTTP ligado a la sesión del browser (comparte cookies/auth).
    req_ctx = page.request
    headers = {k: v for k, v in (captured["headers"] or {}).items()
               if k.lower() not in ("content-length", "host")}

    def _url_with(param_updates):
        q = dict(qs)
        q.update(param_updates)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

    async def _fetch(url_i):
        r = await req_ctx.post(url_i, data=(captured["post_data"] or "{}"), headers=headers)
        if not r.ok:
            return None, r.status
        d = await r.json()
        qs_ = d.get("quotes") if isinstance(d, dict) else d
        cnt = d.get("count") if isinstance(d, dict) else None
        return (qs_, cnt), r.status

    # Página 0 (ids base para verificar que la paginación avance de verdad).
    (page0, total_count), st0 = await _fetch(captured["url"])
    if page0 is None:
        print(f"   ✗ página 0: HTTP {st0}", flush=True)
        await imp.close()
        sys.exit(1)
    page0_ids = {q.get("id") for q in page0}

    # Esquema de paginación: usa la clave explícita si el query la trae; si no
    # (la UI la agrega recién al pasar de página), PRUEBA candidatos y se queda
    # con el primero cuya "página 1" traiga ids distintos a la página 0.
    scheme = None  # (fn i -> {param: valor})
    if off_key is not None:
        scheme = lambda i: {off_key: i * page_size}  # noqa: E731
    elif page_key is not None:
        scheme = lambda i: {page_key: page_base + i}  # noqa: E731
    else:
        candidates = [
            ("page", lambda i: {"page": 1 + i}),
            ("offset", lambda i: {"offset": i * page_size}),
            ("skip", lambda i: {"skip": i * page_size}),
            ("page(base0)", lambda i: {"page": i}),
            ("pageNumber", lambda i: {"pageNumber": 1 + i}),
        ]
        for nombre, fn in candidates:
            (p1, _), _ = await _fetch(_url_with(fn(1)))
            if p1 and {q.get("id") for q in p1} - page0_ids:
                scheme = fn
                print(f"   ✓ paginación por prueba: '{nombre}' (página 1 trae ids nuevos)", flush=True)
                break
            await page.wait_for_timeout(250)

    all_quotes = list(page0)
    seen_ids = set(page0_ids)
    can_paginate = scheme is not None
    print(f"   página 0: {len(page0)} (de {total_count})", flush=True)
    if not can_paginate:
        print("   ⚠ no se encontró forma de paginar -- solo página 0 (30 filas)", flush=True)

    i = 1
    while can_paginate and i < 400:  # tope de seguridad
        (quotes, _), st = await _fetch(_url_with(scheme(i)))
        if quotes is None:
            print(f"   ✗ página {i}: HTTP {st}", flush=True)
            break
        if not quotes:
            break
        # Anti-loop: si la página no trae ids nuevos, la paginación no avanza.
        nuevos = [q for q in quotes if q.get("id") not in seen_ids]
        if not nuevos:
            print(f"   ✗ página {i} sin ids nuevos (paginación no avanza) -- corto", flush=True)
            break
        for q in nuevos:
            seen_ids.add(q.get("id"))
        all_quotes.extend(nuevos)
        if i % 20 == 0 or (total_count and len(all_quotes) >= total_count):
            print(f"   página {i}: acum {len(all_quotes)}"
                  + (f" / {total_count}" if total_count else ""), flush=True)
        if total_count is not None and len(all_quotes) >= total_count:
            break
        if len(quotes) < page_size:
            break
        i += 1
        await page.wait_for_timeout(300)  # cortesía, no martillar la API

    print(f"   total juntado: {len(all_quotes)}"
          + (f" / {total_count}" if total_count else ""), flush=True)

    await imp.close()

    # ── 3. Normalizar + escribir (PII solo al disco, jamás a logs) ──
    if all_quotes:
        keys0 = list(all_quotes[0].keys())
        print(f"\n   keys de una cotización cruda: {keys0}", flush=True)
        cust = all_quotes[0].get("customer")
        cb = all_quotes[0].get("createdBy")
        print(f"   customer type={type(cust).__name__} keys={list(cust.keys()) if isinstance(cust, dict) else '-'}", flush=True)
        print(f"   createdBy type={type(cb).__name__} keys={list(cb.keys()) if isinstance(cb, dict) else '-'}", flush=True)

    records = [normalize_quote(q) for q in all_quotes]
    # Sanidad (sin exponer PII): cuántos records tienen rut/broker/uf.
    con_rut = sum(1 for r in records if r["rut"])
    con_broker = sum(1 for r in records if r["broker_name"])
    con_uf = sum(1 for r in records if r["precio_uf"])
    print(f"\n   normalizados: {len(records)} (con rut={con_rut}, con broker={con_broker}, con uf>0={con_uf})", flush=True)

    (OUT / "quotes_jb.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps({
        "total_crudas": len(all_quotes), "total_count_api": total_count,
        "normalizadas": len(records), "con_rut": con_rut, "con_broker": con_broker, "con_uf": con_uf,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK -> {OUT/'quotes_jb.json'} ({len(records)} cotizaciones)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
