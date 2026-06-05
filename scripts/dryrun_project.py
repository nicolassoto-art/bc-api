"""
dryrun_project.py — Validación DRY-RUN (solo lectura) de un proyecto con el pipeline v2.

NO escribe nada en bc-api. Flujo confiable (mantiene sesión):
  catálogo → buscar proyecto por NOMBRE → clic en su tarjeta → workview → tabs Stock/Documentos,
capturando PASIVAMENTE las respuestas de la API (stock-selectors=modelos, units-search=unidades,
files=fotos/docs). Arma el mapeo a bc-api EN MEMORIA y lo muestra + screenshots.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_NAME (default "Portal del Pinar Etapa 2"), DIAG_ID
"""
from __future__ import annotations
import asyncio, json, os, re, sys, time, unicodedata
from pathlib import Path
from collections import Counter

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
        jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"), imports_dir=OUT)
    await imp.login()
    page = imp._page

    # ── 1. Resolver por nombre (lista org, cliente con cookies) ──
    import httpx
    from app.services.jb_importer import JB_API_BASE, JB_HEADERS
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE,
                            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                                     "Authorization": f"Bearer {imp._jb_token}"}, cookies=jar, timeout=30.0)
    ts = int(time.time() * 1000)
    r = await cli.post(f"/project/organization/{ORG}/list/{ts}", json=LIST_BODY)
    await cli.aclose()
    projs = (r.json() or {}).get("projects", []) if r.status_code in (200, 201) else []
    print(f"### Lista org: {len(projs)} proyectos (status {r.status_code})", flush=True)

    if FORCED_ID:
        matches = [p for p in projs if p.get("id") == FORCED_ID] or [{"id": FORCED_ID, "name": "(forzado)"}]
    else:
        words = [w for w in norm(NAME).split() if w]
        matches = [p for p in projs if all(w in norm(p.get("name")) for w in words)]
    print(f"### Coincidencias para {NAME!r}: {len(matches)}", flush=True)
    for p in matches:
        print(f"   id={p.get('id'):12} name={p.get('name')!r:36} comuna={p.get('locality')!r} "
              f"tipologias={p.get('cachedTipologies')}", flush=True)
    if not matches:
        print("   ✗ No encontrado. Abort."); await imp.close(); return
    target = matches[0]; pid = target["id"]
    target_name = target.get("name") or NAME
    print(f"\n### Elegido: {target_name} (id {pid})\n", flush=True)

    # ── 2. Captura pasiva + navegación catálogo → buscar → clic → workview → tabs ──
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and any(
                k in resp.url for k in ("stock-selectors", "units-search", "marketplace/files", "workview")):
            e = {"url": resp.url, "status": resp.status}
            try:
                e["body"] = await resp.text()
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(3_000)
    await imp._dismiss_popups()
    await page.wait_for_timeout(800)
    # buscar por nombre
    try:
        sbox = None
        for sel in ("input[placeholder*='Buscar']", "input[type='text']", "input[type='search']", "input"):
            loc = page.locator(sel).first
            if await loc.count() > 0:
                sbox = loc; break
        if sbox:
            await sbox.fill(re.sub(r"(?i)etapa\s*\d+", "", target_name).strip() or target_name)
            await page.wait_for_timeout(3_000)
            print(f"   búsqueda escrita en catálogo", flush=True)
    except Exception as e:
        print(f"   search err: {str(e)[:50]}", flush=True)
    await page.screenshot(path=str(OUT / "jb-00-catalog.png"), full_page=True)
    # clic en la tarjeta cuyo texto matchee mejor (o la primera)
    clicked = False
    try:
        cards = await page.evaluate(r"""() => {
            const out=[]; let i=0;
            for (const el of document.querySelectorAll('.card-img-top.clickable')) {
                const card = el.closest('.card') || el.parentElement;
                const txt = (card?.innerText||'').replace(/\s+/g,' ').trim();
                const r = el.getBoundingClientRect();
                out.push({i:i++, txt:txt.slice(0,60), cx:Math.round(r.x+r.width/2), cy:Math.round(r.y+r.height/2)});
            }
            return out;
        }""")
        pick = None
        for c in cards:
            if norm(target_name).split()[0] in norm(c["txt"]):
                pick = c; break
        pick = pick or (cards[0] if cards else None)
        if pick:
            await page.mouse.click(pick["cx"], pick["cy"]); clicked = True
            print(f"   clic tarjeta: {pick['txt']!r}", flush=True)
    except Exception as e:
        print(f"   click err: {str(e)[:50]}", flush=True)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    wv_url = page.url
    print(f"   workview url: {wv_url}", flush=True)
    await page.screenshot(path=str(OUT / "jb-01-workview.png"), full_page=True)
    real_pid = (re.search(r"workview/([A-Za-z0-9]+)", wv_url) or [None, None])[1]
    if real_pid and real_pid != pid:
        print(f"   ⚠ pid navegado ({real_pid}) ≠ objetivo ({pid}) — uso el navegado", flush=True)
        pid = real_pid

    # clic tabs Stock y Documentos (coordenada) para disparar units-search/files
    async def click_tab(rx):
        t = await page.evaluate(r"""(rx) => {
            const re = new RegExp(rx, 'i');
            for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab]')) {
                const s=(el.innerText||'').replace(/\s+/g,' ').trim();
                if (s && re.test(s) && s.length<25){const r=el.getBoundingClientRect();
                  if(r.width>0&&r.height>0) return {cx:Math.round(r.x+r.width/2),cy:Math.round(r.y+r.height/2)};}
            }
            return null;
        }""", rx)
        if t:
            await page.mouse.click(t["cx"], t["cy"]); await page.wait_for_timeout(3_500)
            return True
        return False
    await click_tab("stock|unidad|disponib")
    await page.screenshot(path=str(OUT / "jb-02-stock.png"), full_page=True)
    await click_tab("documento")
    await page.wait_for_timeout(2_000)
    page.remove_listener("response", on_resp)
    await imp.close()

    # ── 3. Parsear capturas ──
    def latest(key):
        for c in reversed(cap):
            if key in c["url"] and c["status"] in (200, 201):
                try:
                    return json.loads(c["body"])
                except Exception:
                    return None
        return None
    wv = latest("workview") or {}
    ss = latest("stock-selectors") or {}
    us = latest("units-search") or {}
    fl = latest("marketplace/files") or {}
    api_models = ss.get("models", []) if isinstance(ss, dict) else []
    units = us.get("apartments", []) if isinstance(us, dict) else []
    files = fl.get("files", []) if isinstance(fl, dict) else []
    for nm, obj in (("workview", wv), ("models", ss), ("units", us), ("files", fl)):
        if obj:
            (OUT / f"{nm}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    print(f"\n   capturado: workview={'sí' if wv else 'NO'} modelos={len(api_models)} "
          f"unidades={len(units)} archivos={len(files)}", flush=True)

    # ── 4. Mapeo + reporte ──
    print(f"\n{'='*72}\n=== MAPEO QUE SE IMPORTARÍA (dry-run, SIN escribir bc-api) ===\n{'='*72}", flush=True)
    print(f"\n--- MODELOS ({len(api_models)}) ---", flush=True)
    tip = Counter(); plantas = set()
    for m in api_models:
        bp = (m.get("blueprint") or {}).get("id")
        t = derive_tipo(m.get("rooms"), m.get("bathrooms"))
        tip[t] += 1
        if bp: plantas.add(bp)
        sup = (m.get("name") or "").split("-")[-1].strip()
        print(f"   tipo={t}  {m.get('name')!r:42}  planta={bp!r}", flush=True)
    print(f"\n   → {len(api_models)} modelos · {len(plantas)} plantas DISTINTAS · tipologías={dict(tip)}", flush=True)
    colaps = {t: n for t, n in tip.items() if n > 1}
    if colaps:
        print(f"   ⚠ ANTI-COLAPSO: {colaps} → con el fix quedan {len(api_models)} modelos; sin fix, {len(tip)}.", flush=True)

    print(f"\n--- UNIDADES ({len(units)}) ---", flush=True)
    if units:
        bpset = {(m.get('blueprint') or {}).get('id') for m in api_models}
        huer = sum(1 for u in units if (u.get('apartmentModel') or {}).get('blueprint', {}).get('id') not in bpset)
        sup = sum(1 for u in units if u.get('surfaceTotal'))
        u0 = units[0]
        print(f"   ej: nº{u0.get('number')} planta_modelo={(u0.get('apartmentModel') or {}).get('blueprint',{}).get('id')} "
              f"ST={u0.get('surfaceTotal')} int={u0.get('surfaceInterior')} terr={u0.get('surfaceTerrace')} "
              f"precio={u0.get('price')} facing={u0.get('facing')}", flush=True)
        print(f"   enlazadas a modelo por planta: {len(units)-huer}/{len(units)} · con superficie: {sup}/{len(units)}", flush=True)

    print(f"\n--- FOTOS/DOCS ({len(files)} de {fl.get('count') if isinstance(fl,dict) else '?'}) ---", flush=True)
    print(f"   tipos: {dict(Counter(f.get('type') for f in files))}", flush=True)
    print(f"   cover (→ portada/fachada): {wv.get('cover')!r}", flush=True)

    print(f"\n--- FICHA (workview) ---", flush=True)
    for k in ("name", "address", "locality", "reserveBank", "reserveAccountNumber",
              "shellCompanyName", "pie", "reservaCLP", "apartmentsTotal", "description"):
        print(f"   {k}: {str(wv.get(k))[:60]!r}", flush=True)

    print(f"\n✓ Dry-run OK. JSON + screenshots en imports/_dryrun/ (NADA escrito en bc-api)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
