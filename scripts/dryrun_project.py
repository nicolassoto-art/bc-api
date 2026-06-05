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

    # ── 2. Captura pasiva navegando /projects/detail/{id} (vista de proyectos PROPIOS) ──
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and any(k in resp.url for k in (
                "/detail", "/notes", "/totals", "apartment-model", "project-detail-search",
                "stock-selectors", "units-search", "marketplace/files", "workview",
                "/tipology", "/facing", "project-js-files", "/file/")):
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = await resp.text()
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    # Vista de proyecto PROPIO: /projects/detail/{id} (no bota sesión, todo 200).
    await page.goto(f"https://app.jetbrokers.io/projects/detail/{pid}",
                    wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    print(f"   detail url: {page.url}", flush=True)
    await page.screenshot(path=str(OUT / "jb-01-detail.png"), full_page=True)
    # recorrer tabs internos para disparar units/fotos/docs
    for _ in range(8):
        clicked = await page.evaluate(r"""() => {
            const re=/modelo|tipolog|unidad|stock|disponib|foto|galer|documento/i;
            const done = window.__c || (window.__c=new Set());
            for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab]')) {
                const s=(el.innerText||'').replace(/\s+/g,' ').trim();
                if (s && re.test(s) && s.length<22 && !done.has(s)){const r=el.getBoundingClientRect();
                  if(r.width>0&&r.height>0){done.add(s); el.click(); return s;}}
            }
            return null;
        }""")
        if not clicked:
            break
        await page.wait_for_timeout(2_500)
    for _ in range(5):
        await page.mouse.wheel(0, 600); await page.wait_for_timeout(350)
    await page.wait_for_timeout(2_000)
    await page.screenshot(path=str(OUT / "jb-02-stock.png"), full_page=True)

    # httpx con Referer = detail page (por si habilita los endpoints sin navegar)
    api = {}
    dcli = httpx.AsyncClient(base_url=JB_API_BASE,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": f"https://app.jetbrokers.io/projects/detail/{pid}"},
        cookies=jar, timeout=30.0)
    for key, ep in (("detail", f"/project/{pid}/detail"),
                    ("models", f"/apartment-model/project/{pid}/all"),
                    ("notes", f"/project/{pid}/notes"),
                    ("totals", f"/project/{pid}/totals")):
        try:
            rr = await dcli.get(ep)
            print(f"   httpx GET {ep} → {rr.status_code}", flush=True)
            if rr.status_code == 200:
                try: api[key] = rr.json()
                except Exception: api[key] = rr.text
        except Exception as e:
            print(f"   httpx {ep} ERR: {str(e)[:50]}", flush=True)
    try:
        uts = int(time.time() * 1000)
        ubody = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
                 "projectId": pid, "availability": None, "number": None, "element": 0, "elements": 9999}
        ur = await dcli.post(f"/apartment/project-detail-search/{uts}", json=ubody)
        print(f"   httpx POST project-detail-search → {ur.status_code}", flush=True)
        if ur.status_code in (200, 201):
            api["units"] = ur.json()
    except Exception as e:
        print(f"   project-detail-search ERR: {str(e)[:50]}", flush=True)
    await dcli.aclose()
    page.remove_listener("response", on_resp)
    await imp.close()

    # ── 3. Consolidar (httpx primero, passive del navegador como fallback) ──
    def latest(key):
        for c in reversed(cap):
            if key in c["url"] and c["status"] in (200, 201):
                try:
                    return json.loads(c["body"])
                except Exception:
                    return None
        return None
    wv = (api.get("detail") if isinstance(api.get("detail"), dict) else None) or latest(f"/project/{pid}/detail") or {}
    ss = api.get("models") or latest("apartment-model/project") or []
    us = api.get("units") or latest("project-detail-search") or {}
    notes = api.get("notes") or latest(f"/project/{pid}/notes")
    api_models = ss if isinstance(ss, list) else (ss.get("models", []) if isinstance(ss, dict) else [])
    if isinstance(us, dict):
        units = us.get("apartments") or us.get("elements") or us.get("data") or []
    elif isinstance(us, list):
        units = us
    else:
        units = []
    files = []
    for nm, obj in (("detail", wv), ("models", api_models), ("units", units)):
        if obj:
            (OUT / f"{nm}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    notes_len = len(notes) if isinstance(notes, str) else len(json.dumps(notes)) if notes else 0
    print(f"\n   capturado: ficha={'sí' if wv else 'NO'} modelos={len(api_models)} "
          f"unidades={len(units)} notas={notes_len}b", flush=True)

    # ── 4. Mapeo + reporte ──
    print(f"\n{'='*72}\n=== MAPEO QUE SE IMPORTARÍA (dry-run, SIN escribir bc-api) ===\n{'='*72}", flush=True)
    print(f"\n--- MODELOS ({len(api_models)}) ---", flush=True)
    if api_models:
        print(f"   [modelo crudo #0]: {json.dumps(api_models[0], ensure_ascii=False)[:400]}", flush=True)
    tip = Counter(); plantas = set()
    for m in api_models:
        bp = (m.get("blueprint") or {}).get("id")
        t = derive_tipo(m.get("rooms"), m.get("bathrooms"))
        tip[t] += 1
        if bp: plantas.add(bp)
        print(f"   tipo={t}  name={m.get('name')!r:42}  planta={bp!r}", flush=True)
    print(f"\n   → {len(api_models)} modelos · {len(plantas)} plantas DISTINTAS · tipologías={dict(tip)}", flush=True)
    colaps = {t: n for t, n in tip.items() if n > 1}
    if colaps:
        print(f"   ⚠ ANTI-COLAPSO: {colaps} → con el fix quedan {len(api_models)} modelos; sin fix, {len(tip)}.", flush=True)

    print(f"\n--- UNIDADES ({len(units)}) ---", flush=True)
    if units:
        print(f"   [unidad cruda #0]: {json.dumps(units[0], ensure_ascii=False)[:500]}", flush=True)
        bpset = {(m.get('blueprint') or {}).get('id') for m in api_models}
        def ubp(u):
            am = u.get('apartmentModel') or u.get('model') or {}
            return (am.get('blueprint') or {}).get('id') if isinstance(am, dict) else None
        huer = sum(1 for u in units if ubp(u) not in bpset)
        print(f"   enlazadas a modelo por planta: {len(units)-huer}/{len(units)} huérfanas={huer}", flush=True)

    print(f"\n--- NOTAS / FICHA ---", flush=True)
    print(f"   cover (→ portada/fachada): {wv.get('cover')!r}", flush=True)
    if isinstance(notes, str):
        print(f"   notas HTML: {len(notes)} chars · muestra: {notes[:120]!r}", flush=True)
    for k in ("name", "address", "locality", "reserveBank", "reserveAccountNumber",
              "shellCompanyName", "pie", "reservaCLP", "apartmentsTotal", "description"):
        print(f"   {k}: {str(wv.get(k))[:60]!r}", flush=True)

    print(f"\n✓ Dry-run OK. JSON + screenshots en imports/_dryrun/ (NADA escrito en bc-api)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
