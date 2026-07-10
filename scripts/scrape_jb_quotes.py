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


async def _dump_paginator(page):
    """Diagnóstico (sin PII): vuelca la estructura del paginador de /quotes
    para saber en la próxima corrida cómo pasar de página. Solo estructura:
    aria-labels de botones + outerHTML de elementos tipo paginator + opciones
    del selector de tamaño de página."""
    try:
        info = await page.evaluate("""() => {
            const out = {buttons: [], paginators: [], selects: []};
            document.querySelectorAll('button[aria-label]').forEach(b => {
                const a = b.getAttribute('aria-label') || '';
                if (/page|página|next|siguiente|anterior|prev/i.test(a))
                    out.buttons.push({aria: a, disabled: b.disabled, cls: b.className});
            });
            document.querySelectorAll('[class*="paginat"], mat-paginator').forEach(p => {
                out.paginators.push((p.outerHTML || '').slice(0, 400));
            });
            document.querySelectorAll('mat-select, select').forEach(s => {
                out.selects.push(s.getAttribute('aria-label') || s.className || 'select');
            });
            return out;
        }""")
        print(f"   [diag paginador] botones={info.get('buttons')}", flush=True)
        print(f"   [diag paginador] selects={info.get('selects')}", flush=True)
        for h in info.get("paginators", [])[:2]:
            print(f"   [diag paginador] html={h}", flush=True)
        await page.screenshot(path=str(OUT / "quotes_paginator.png"), full_page=True)
    except Exception as ex:
        print(f"   [diag paginador] err: {str(ex)[:100]}", flush=True)


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
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

    # ── 1. Capturar TODAS las requests de búsqueda + descubrir la paginación
    # haciendo click real en "página siguiente" (la paginación no va en la
    # request inicial -- la UI la agrega al pasar de página). Comparando la
    # request de página 1 vs página 2 se ve qué param cambió (URL o body). ──
    search_reqs = []
    captured = {"headers": None}

    async def on_request(req):
        if SEARCH_PATH in req.url and req.method == "POST":
            search_reqs.append({"url": req.url, "post_data": req.post_data})
            if captured["headers"] is None:
                captured["headers"] = dict(req.headers)

    page.on("request", on_request)
    print("### /quotes: cargando y haciendo scroll para descubrir la paginación", flush=True)
    await page.goto("https://app.jetbrokers.io/quotes", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(4_000)
    n_inicial = len(search_reqs)

    # La lista es virtual-scroll (Angular CDK): no hay paginador con botones
    # (diag lo confirmó: 0 botones, 0 selects). Los siguientes lotes se cargan
    # al hacer SCROLL. Se scrollea el viewport (y la ventana) repetido hasta
    # que aparezca una request de búsqueda distinta a la inicial.
    async def _scroll_burst():
        await page.evaluate("""() => {
            const vp = document.querySelector('cdk-virtual-scroll-viewport')
                    || document.querySelector('[class*="scroll"]')
                    || document.scrollingElement || document.body;
            vp.scrollTop = vp.scrollHeight;
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        await page.keyboard.press("End")

    for _ in range(6):
        await _scroll_burst()
        await page.wait_for_timeout(1_800)
        if any(r["url"] != search_reqs[0]["url"] or r["post_data"] != search_reqs[0]["post_data"]
               for r in search_reqs[n_inicial:]):
            print("   ✓ scroll disparó una request de búsqueda distinta", flush=True)
            break

    # Backup: si algún día vuelve a haber paginador con botones, intentar click.
    if not any(r["url"] != search_reqs[0]["url"] or r["post_data"] != search_reqs[0]["post_data"]
               for r in search_reqs[n_inicial:]):
        for sel in ('button[aria-label="Página siguiente"]', 'button[aria-label="Next page"]',
                    'button.mat-mdc-paginator-navigation-next'):
            try:
                btn = page.locator(sel).first
                if await btn.count() and await btn.is_enabled():
                    await btn.click()
                    await page.wait_for_timeout(3_000)
                    break
            except Exception:
                continue
    page.remove_listener("request", on_request)
    print(f"   requests de búsqueda capturadas: {len(search_reqs)}", flush=True)

    if not search_reqs:
        print("✗ No se capturó ninguna request de búsqueda -- la UI cambió?", flush=True)
        await imp.close()
        sys.exit(1)

    req0 = search_reqs[0]
    parts = urlsplit(req0["url"])
    qs0 = dict(parse_qsl(parts.query))
    try:
        body0 = json.loads(req0["post_data"]) if req0["post_data"] else {}
    except Exception:
        body0 = {}

    # request de "página 2" = la primera que difiere de req0 (aparece recién
    # tras el click).
    req_next = next((r for r in search_reqs[n_inicial:]
                     if r["url"] != req0["url"] or r["post_data"] != req0["post_data"]), None)

    # Descubrir qué cambió (query o body) entre página 1 y página 2.
    # scheme(i) -> (url, post_data_str) para la página índice i (0 = primera).
    scheme = None
    pag_desc = "ninguna"
    if req_next is not None:
        qsN = dict(parse_qsl(urlsplit(req_next["url"]).query))
        try:
            bodyN = json.loads(req_next["post_data"]) if req_next["post_data"] else {}
        except Exception:
            bodyN = {}

        def _num_or_none(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        # Buscar la clave numérica que cambió (primero en query, luego en body).
        changed = None  # (origen, key, base, delta)
        for key in set(qs0) | set(qsN):
            v0, v1 = _num_or_none(qs0.get(key)), _num_or_none(qsN.get(key))
            if v0 is not None and v1 is not None and v1 != v0:
                changed = ("query", key, v0, v1 - v0)
                break
        if changed is None:
            for key in set(body0) | set(bodyN):
                v0, v1 = _num_or_none(body0.get(key)), _num_or_none(bodyN.get(key))
                if v0 is not None and v1 is not None and v1 != v0:
                    changed = ("body", key, v0, v1 - v0)
                    break

        if changed:
            origen, key, base, delta = changed
            pag_desc = f"click: {origen}.{key} base={base} delta={delta}"

            def scheme(i, _o=origen, _k=key, _b=base, _d=delta):
                if _o == "query":
                    q = dict(qs0); q[_k] = _b + i * _d
                    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
                    return url, (req0["post_data"] or "{}")
                else:
                    b = dict(body0); b[_k] = _b + i * _d
                    return req0["url"], json.dumps(b)

    # Cliente HTTP ligado a la sesión del browser (comparte cookies/auth).
    req_ctx = page.request
    headers = {k: v for k, v in (captured["headers"] or {}).items()
               if k.lower() not in ("content-length", "host")}

    async def _raw(url_i, data_i):
        r = await req_ctx.post(url_i, data=data_i, headers=headers)
        if not r.ok:
            return None
        d = await r.json()
        return (d.get("quotes") if isinstance(d, dict) else d) or []

    # Fallback A: subir el LÍMITE de filas en el body -- muchos POST /search
    # devuelven N filas con un `limit`/`take`/`length` que por defecto es 30;
    # subirlo trae todo en una sola request (no hace falta paginar). Se prueba
    # cada candidato pidiendo un número grande y se usa el que devuelva >30.
    single_shot = None  # (nombre, body_str) que trae el lote completo
    if scheme is None:
        base_quotes = await _raw(req0["url"], req0["post_data"] or "{}")
        base_ids = {q.get("id") for q in (base_quotes or [])}
        BIG = 10000
        for lim_key in ("limit", "take", "length", "pageSize", "perPage", "size", "rows", "count", "pageSize"):
            b = {**body0, lim_key: BIG}
            got = await _raw(req0["url"], json.dumps(b))
            if got and len(got) > len(base_quotes or []):
                single_shot = (lim_key, json.dumps(b))
                pag_desc = f"limit-grande: body.{lim_key}={BIG} -> {len(got)} filas"
                break
            await page.wait_for_timeout(150)

    # Fallback B: si subir el límite no sirvió, PROBAR candidatos de paginación
    # en el body (page/offset/skip...), verificando que la página 1 traiga ids
    # distintos a la 0.
    if scheme is None and single_shot is None:
        # (nombre, origen, builder-de-página-1) -- se prueba con i=1
        probes = [
            ("body.page(1based)", "body", lambda i: {**body0, "page": 1 + i}),
            ("body.page(0based)", "body", lambda i: {**body0, "page": i}),
            ("body.offset", "body", lambda i: {**body0, "offset": i * 30}),
            ("body.skip", "body", lambda i: {**body0, "skip": i * 30}),
            ("body.skip+take", "body", lambda i: {**body0, "skip": i * 30, "take": 30}),
            ("body.start+length", "body", lambda i: {**body0, "start": i * 30, "length": 30}),
            ("body.pageNumber", "body", lambda i: {**body0, "pageNumber": 1 + i}),
        ]
        for nombre, origen, build in probes:
            b1 = build(1)
            p1 = await _raw(req0["url"], json.dumps(b1))
            if p1 and ({q.get("id") for q in p1} - base_ids):
                pag_desc = f"probe: {nombre}"

                def scheme(i, _build=build):
                    return req0["url"], json.dumps(_build(i))
                break
            await page.wait_for_timeout(200)

    # Fallback C: bisección por VENTANA DE FECHAS. El endpoint devuelve siempre
    # 30 (cap server-side) e ignora todo param de paginación, PERO el postData
    # trae filtros reales dateFrom/dateTo. Estrategia: partir el rango
    # completo (2020->hoy) y, si una ventana devuelve el tope (=cap), partirla
    # al medio recursivamente hasta que cada sub-ventana traiga menos del cap
    # (= totalmente capturada). Garantiza completitud sin depender de la
    # paginación oculta. Se verifica primero que el endpoint SÍ filtre por
    # fecha (una ventana antigua vacía devuelve 0, no 30).
    date_window_quotes = None
    if scheme is None and single_shot is None:
        from datetime import date, timedelta

        async def _win(d_from, d_to):
            b = {**body0, "dateFrom": d_from.isoformat(), "dateTo": d_to.isoformat()}
            return await _raw(req0["url"], json.dumps(b)) or []

        cap = len(base_quotes or []) or 30
        vieja = await _win(date(2015, 1, 1), date(2015, 1, 2))
        if len(vieja) < cap:  # el filtro de fecha funciona (ventana vieja no llena el cap)
            collected = {}
            reqs = [0]

            async def _rec(d_from, d_to, depth=0):
                reqs[0] += 1
                qs = await _win(d_from, d_to)
                for q in qs:
                    collected[q.get("id")] = q
                if len(qs) >= cap and (d_to - d_from).days > 1 and depth < 40:
                    mid = d_from + (d_to - d_from) / 2
                    await _rec(d_from, mid, depth + 1)
                    await _rec(mid, d_to, depth + 1)

            await _rec(date(2020, 1, 1), date.today() + timedelta(days=2))
            date_window_quotes = list(collected.values())
            pag_desc = f"ventana-fechas: {len(date_window_quotes)} en {reqs[0]} requests (cap={cap})"
        else:
            print(f"   ⚠ el endpoint ignora dateFrom/dateTo (ventana vieja devolvió {len(vieja)})", flush=True)

    print(f"   paginación descubierta: {pag_desc}", flush=True)

    async def _fetch_page(i):
        if scheme is not None:
            url_i, data_i = scheme(i)
        else:
            url_i, data_i = req0["url"], (req0["post_data"] or "{}")
        r = await req_ctx.post(url_i, data=data_i, headers=headers)
        if not r.ok:
            return None, None, r.status
        d = await r.json()
        qs_ = d.get("quotes") if isinstance(d, dict) else d
        cnt = d.get("count") if isinstance(d, dict) else None
        return qs_, cnt, r.status

    # ── Camino A: una sola request con límite grande trajo todo ──
    if single_shot is not None:
        r = await req_ctx.post(req0["url"], data=single_shot[1], headers=headers)
        d = await r.json()
        all_quotes = (d.get("quotes") if isinstance(d, dict) else d) or []
        total_count = d.get("count") if isinstance(d, dict) else None
        can_paginate = False
        print(f"   single-shot: {len(all_quotes)} cotizaciones (count={total_count})", flush=True)
    elif date_window_quotes is not None:
        # ── Camino C: recolectado por bisección de ventanas de fecha ──
        all_quotes = date_window_quotes
        total_count = None
        can_paginate = False
    else:
        # ── Camino B: paginar (o solo página 0 si no se descubrió cómo) ──
        page0, total_count, st0 = await _fetch_page(0)
        if page0 is None:
            print(f"   ✗ página 0: HTTP {st0}", flush=True)
            # Diagnóstico: volcar el paginador de la UI para saber cómo pasar
            # de página en la próxima corrida (sin PII -- solo estructura).
            await _dump_paginator(page)
            await imp.close()
            sys.exit(1)
        page0_ids = {q.get("id") for q in page0}
        page_size = len(page0) or 30
        all_quotes = list(page0)
        seen_ids = set(page0_ids)
        can_paginate = scheme is not None
        print(f"   página 0: {len(page0)} (de {total_count})", flush=True)
        if not can_paginate:
            print("   ⚠ no se descubrió forma de paginar -- solo página 0", flush=True)
            await _dump_paginator(page)

    i = 1
    while can_paginate and i < 400:  # tope de seguridad
        quotes, _, st = await _fetch_page(i)
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
