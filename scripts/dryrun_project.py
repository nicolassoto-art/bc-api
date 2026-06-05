"""
dryrun_project.py — Validación DRY-RUN (solo lectura) de un proyecto con el pipeline v2.

NO escribe nada en bc-api. Trae todo desde la API JB 7.43.1 + scrapea nombres comerciales
de modelos, arma el mapeo a bc-api EN MEMORIA y lo muestra, para validar el plan antes de
importar de verdad. También captura pantallazos (JB workview/stock/editor).

Resuelve el proyecto POR NOMBRE (como pidió el usuario): busca en la lista org y muestra las
coincidencias. Pasa DIAG_NAME (default "Portal del Pinar Etapa 2") o DIAG_ID directo.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, re, sys, time, unicodedata
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_dryrun"); OUT.mkdir(parents=True, exist_ok=True)
NAME = os.environ.get("DIAG_NAME", "Portal del Pinar Etapa 2")
FORCED_ID = os.environ.get("DIAG_ID", "").strip()
ORG = os.environ.get("JB_ORG", "uv13koru")
LIST_BODY = {"locality": None, "stage": None, "year": None, "available": None, "tipology": None,
             "developer": None, "priceFrom": None, "priceTo": None, "jetStock": None,
             "modalityType": None, "projectTags": [], "element": 0, "elements": 9999}


def norm(s):
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def derive_tipo(rooms, baths):
    try:
        return f"{int(rooms)}D{int(baths)}B"
    except Exception:
        return "?"


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

    # Cliente httpx CON cookies de la sesión del navegador (stock-selectors/files lo exigen)
    import httpx
    from app.services.jb_importer import JB_API_BASE, JB_HEADERS

    async def cookie_cli():
        cookies = await imp._ctx.cookies()
        jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
        return httpx.AsyncClient(
            base_url=JB_API_BASE,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}"},
            cookies=jar, timeout=30.0)

    # ── 1. Resolver por nombre ──
    cli = await cookie_cli()
    ts = int(time.time() * 1000)
    r = await cli.post(f"/project/organization/{ORG}/list/{ts}", json=LIST_BODY)
    projs = (r.json() or {}).get("projects", []) if r.status_code in (200, 201) else []
    print(f"### Lista org: {len(projs)} proyectos (status {r.status_code})", flush=True)

    if FORCED_ID:
        target = next((p for p in projs if p.get("id") == FORCED_ID), {"id": FORCED_ID, "name": "(forzado)"})
        matches = [target]
    else:
        nq = norm(NAME)
        # match por todas las palabras del query
        words = [w for w in nq.split() if w]
        matches = [p for p in projs if all(w in norm(p.get("name")) for w in words)]
        if not matches:  # fallback: substring del nombre principal
            key = norm(NAME).replace("etapa 2", "").strip()
            matches = [p for p in projs if key and key in norm(p.get("name"))]
    print(f"\n### Coincidencias para {NAME!r}: {len(matches)}", flush=True)
    for p in matches:
        print(f"   id={p.get('id'):12} name={p.get('name')!r:36} comuna={p.get('locality')!r} "
              f"org={(p.get('organization') or {}).get('name')!r} tipologias={p.get('cachedTipologies')}", flush=True)
    if not matches:
        print("   ✗ No se encontró. Abort.", flush=True)
        await imp.close(); return
    target = matches[0]
    pid = target["id"]
    print(f"\n### Proyecto elegido: {target.get('name')} (id {pid})\n", flush=True)

    # ── 2. Capturar tráfico passive + traer data por API ──
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and resp.request.method in ("GET", "POST"):
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = (await resp.text())
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    data = {}
    for key, ep in (("workview", f"/marketplace/{pid}/workview"),
                    ("models", f"/marketplace/stock-selectors/{pid}"),
                    ("files", f"/marketplace/files/{pid}/0")):
        try:
            rr = await cli.get(ep)
            print(f"   API GET {ep} → {rr.status_code}", flush=True)
            if rr.status_code == 200:
                data[key] = rr.json()
                (OUT / f"{key}.json").write_text(json.dumps(data[key], indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"   API GET {ep} ERR: {str(e)[:60]}", flush=True)
    # units-search por API (POST con cookies). Body típico capturado de la app:
    try:
        uts = int(time.time() * 1000)
        ubody = {"project": pid, "facing": None, "tipology": None, "available": None,
                 "priceFrom": None, "priceTo": None, "element": 0, "elements": 9999}
        ur = await cli.post(f"/marketplace/units-search/{uts}", json=ubody)
        print(f"   API POST /marketplace/units-search → {ur.status_code}", flush=True)
        if ur.status_code in (200, 201):
            data["units"] = (ur.json() or {}).get("apartments", [])
            (OUT / "units.json").write_text(json.dumps(data["units"], indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"   units-search ERR: {str(e)[:60]}", flush=True)
    await cli.aclose()

    # ── 3. Navegar workview UI (screenshots) + fallback passive de units ──
    units = data.get("units") or []
    try:
        await page.goto(f"https://app.jetbrokers.io/marketplace/workview/{pid}",
                        wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(3_500)
        await imp._dismiss_popups()
        print(f"   UI workview url: {page.url}", flush=True)
        await page.screenshot(path=str(OUT / "jb-01-workview.png"), full_page=True)
        # click tab interno por coordenada (robusto, como diag_workview)
        tabs = await page.evaluate(r"""() => {
            const out = [];
            for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab]')) {
                const t = (el.innerText||'').replace(/\s+/g,' ').trim();
                if (t && /stock|unidad|disponib/i.test(t) && t.length < 25) {
                    const r = el.getBoundingClientRect();
                    if (r.width>0 && r.height>0) out.push({t, cx:Math.round(r.x+r.width/2), cy:Math.round(r.y+r.height/2)});
                }
            }
            return out;
        }""")
        if tabs:
            await page.mouse.click(tabs[0]["cx"], tabs[0]["cy"])
            await page.wait_for_timeout(4_000)
        await page.screenshot(path=str(OUT / "jb-02-stock.png"), full_page=True)
        if not units:
            for c in cap:
                if "units-search" in c["url"] and c["status"] in (200, 201):
                    try:
                        units = json.loads(c["body"]).get("apartments", [])
                    except Exception:
                        pass
        print(f"   unidades (API+passive): {len(units)}", flush=True)
    except Exception as e:
        print(f"   UI workview ERR: {str(e)[:80]}", flush=True)

    # ── 4. Scrapear editor tab Modelos → nombre comercial + planta_id ──
    scraped_models = []
    try:
        await page.goto(f"https://app.jetbrokers.io/projects/edit/{pid}",
                        wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(4_000)
        await imp._dismiss_popups()
        body_txt = await page.evaluate("() => document.body.innerText.slice(0,400)")
        notfound = "no encontrado" in (body_txt or "").lower()
        print(f"   editor cargó: {'NO (proyecto no encontrado)' if notfound else 'sí'}", flush=True)
        if not notfound:
            # click tab Modelos por coordenada
            mtab = await page.evaluate(r"""() => {
                for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab],span,div')) {
                    const t = (el.innerText||'').replace(/\s+/g,' ').trim();
                    if (t === 'Modelos') {
                        const r = el.getBoundingClientRect();
                        if (r.width>0 && r.height>0) return {cx:Math.round(r.x+r.width/2), cy:Math.round(r.y+r.height/2)};
                    }
                }
                return null;
            }""")
            if mtab:
                await page.mouse.click(mtab["cx"], mtab["cy"])
            await page.wait_for_timeout(3_500)
            # scroll para cargar lazy-rows
            for _ in range(6):
                await page.mouse.wheel(0, 500)
                await page.wait_for_timeout(400)
            await page.wait_for_timeout(1_500)
            await page.screenshot(path=str(OUT / "jb-04-editor-modelos.png"), full_page=True)
            scraped_models = await page.evaluate(r"""() => {
                const out = [];
                const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                let rows = scope.querySelectorAll('table tbody tr');
                if (!rows.length) rows = scope.querySelectorAll('.mat-row,[role=row],.model-row,.card');
                for (const tr of rows) {
                    const inp = tr.querySelector('input');
                    const name = (inp ? inp.value : (tr.querySelector('td,.cell')?.innerText || '')).trim();
                    let plantaId = null;
                    const img = tr.querySelector('img');
                    if (img && img.src) {
                        const m = img.src.match(/download\/([A-Za-z0-9_-]{4,})/);
                        if (m) plantaId = m[1];
                    }
                    if (name || plantaId) out.push({name, plantaId});
                }
                return out;
            }""")
            if not scraped_models:
                # dump HTML del tab activo para debug
                html = await page.evaluate("""() => {
                    const s = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                    return s.innerHTML.slice(0, 8000);
                }""")
                (OUT / "editor-modelos-tab.html").write_text(html)
        print(f"   modelos scrapeados del editor: {len(scraped_models)}", flush=True)
        for m in scraped_models[:30]:
            print(f"      name={m.get('name')!r:28} planta_id={m.get('plantaId')!r}", flush=True)
        if scraped_models:
            (OUT / "scraped_models.json").write_text(json.dumps(scraped_models, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"   editor scrape ERR: {str(e)[:80]}", flush=True)

    page.remove_listener("response", on_resp)
    await imp.close()

    # ── 5. Armar mapeo en memoria y reportar ──
    print(f"\n{'='*72}\n=== MAPEO QUE SE IMPORTARÍA (dry-run, sin escribir) ===\n{'='*72}", flush=True)

    api_models = (data.get("models") or {}).get("models", []) if isinstance(data.get("models"), dict) else []
    # índice nombre comercial por planta_id (del scraper)
    name_by_planta = {m["plantaId"]: m["name"] for m in scraped_models if m.get("plantaId") and m.get("name")}

    print(f"\n--- MODELOS ({len(api_models)} en API) ---", flush=True)
    tip_counter = Counter()
    plantas_distintas = set()
    for m in api_models:
        bp = (m.get("blueprint") or {}).get("id")
        tipo = derive_tipo(m.get("rooms"), m.get("bathrooms"))
        tip_counter[tipo] += 1
        if bp:
            plantas_distintas.add(bp)
        comercial = name_by_planta.get(bp)
        nombre_final = comercial or f"{tipo} · {m.get('name','').split('-')[-1].strip()}"
        flag = "✓ comercial(scraper)" if comercial else "⚠ derivado (scraper no dio nombre)"
        print(f"   {nombre_final!r:26} tipo={tipo} dorm={m.get('rooms')} ban={m.get('bathrooms')} "
              f"planta={bp!r} api_name={m.get('name')!r}  [{flag}]", flush=True)

    print(f"\n   → {len(api_models)} modelos, {len(plantas_distintas)} plantas DISTINTAS", flush=True)
    print(f"   → tipologías: {dict(tip_counter)}", flush=True)
    colaps = {t: n for t, n in tip_counter.items() if n > 1}
    if colaps:
        print(f"   ⚠ TEST ANTI-COLAPSO: tipologías con varios modelos (NO deben colapsarse): {colaps}", flush=True)
        print(f"     → con el fix, quedan {len(api_models)} modelos separados; SIN el fix quedarían {len(tip_counter)}.", flush=True)

    # unidades
    print(f"\n--- UNIDADES ({len(units)}) ---", flush=True)
    if units:
        u0 = units[0]
        print(f"   ejemplo: numero={u0.get('number')} modelo_blueprint={(u0.get('apartmentModel') or {}).get('blueprint',{}).get('id')} "
              f"supTotal={u0.get('surfaceTotal')} int={u0.get('surfaceInterior')} terr={u0.get('surfaceTerrace')} "
              f"precio={u0.get('price')} final={u0.get('finalPrice')} facing={u0.get('facing')}", flush=True)
        # validar enlace unidad→modelo por planta
        bp_models = {(m.get("blueprint") or {}).get("id") for m in api_models}
        huerfanas = sum(1 for u in units if (u.get("apartmentModel") or {}).get("blueprint", {}).get("id") not in bp_models)
        print(f"   unidades enlazadas a un modelo por planta_id: {len(units)-huerfanas}/{len(units)} (huérfanas: {huerfanas})", flush=True)
        sup5 = sum(1 for u in units if u.get("surfaceTotal"))
        print(f"   con superficie total: {sup5}/{len(units)}", flush=True)

    # fotos / fachada
    files = (data.get("files") or {}).get("files", []) if isinstance(data.get("files"), dict) else []
    cover = (data.get("workview") or {}).get("cover")
    print(f"\n--- FOTOS / DOCUMENTOS ({len(files)} en página 0 de {(data.get('files') or {}).get('count')}) ---", flush=True)
    tipos = Counter(f.get("type") for f in files)
    print(f"   tipos de archivo: {dict(tipos)}", flush=True)
    print(f"   cover (→ foto principal/fachada): {cover!r}", flush=True)

    # ficha (workview) — campos privados
    wv = data.get("workview") or {}
    print(f"\n--- FICHA (workview) — campos clave ---", flush=True)
    for k in ("name", "address", "locality", "reserveBank", "reserveAccountNumber",
              "shellCompanyName", "pie", "reservaCLP", "description"):
        v = wv.get(k)
        print(f"   {k}: {str(v)[:60]!r}", flush=True)

    print(f"\n✓ Dry-run completo. JSON + screenshots en imports/_dryrun/  (NADA escrito en bc-api)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
