"""
diag_investigate.py — Investiga los 3 puntos problemáticos del lote CSV:

1. Terrazzo (72GkWnlW): 6 modelos, 0 con blueprint. ¿Por qué?
2. Los 5 con 0 unidades: capturar units-search del navegador (passive con Stock tab).
3. Abdón Cifuentes (G3jWrRoE): 142 modelos. ¿Cuántos blueprints únicos? ¿Duplicados?

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

OUT = Path("imports/_invest"); OUT.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "terrazzo_0blueprint": ("72GkWnlW", "Terrazzo"),
    "abdon_142modelos":    ("G3jWrRoE", "Abdón Cifuentes"),
    "diagonal_0uds":       ("NeOU0rvU", "Diagonal Paraguay 240"),
    "froilan_0uds":        ("jfkJBrPQ", "Froilán Roa"),
    "vm1796_0uds":         ("1kvflc3m", "V.Mackenna 1796"),
    "alerces_0uds":        ("WWMCny3E", "Los Alerces"),
    "santarosa_0uds":      ("T8UuEf2r", "Santa Rosa 250"),
}


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=OUT)
    await imp.login()
    page = imp._page

    # ── 1. TERRAZZO: dump crudo de modelos ──
    print(f"\n{'='*72}\n=== 1. TERRAZZO (72GkWnlW) — modelos crudos ===\n{'='*72}", flush=True)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": "https://app.jetbrokers.io/projects/detail/72GkWnlW"})
    r = await cli.get("/apartment-model/project/72GkWnlW/all")
    if r.status_code == 200:
        models = r.json()
        print(f"   {len(models)} modelos. Crudo:", flush=True)
        for m in models:
            print(f"     {json.dumps(m, ensure_ascii=False)[:200]}", flush=True)
        (OUT / "terrazzo_models.json").write_text(json.dumps(models, indent=2, ensure_ascii=False))
    # ¿qué dispara la app al cargar el tab Modelos del editor?
    # Navegar al editor + tab Modelos y capturar pasivo
    cap_modelos = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url and any(k in resp.url for k in
                ("apartment-model", "blueprint", "/file/", "tipolog", "facing")):
            try:
                cap_modelos.append({"m": resp.request.method, "url": resp.url, "status": resp.status,
                                    "body": (await resp.text())[:3000]})
            except Exception:
                pass
    page.on("response", on_resp)
    await page.goto("https://app.jetbrokers.io/projects/detail/72GkWnlW", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(3_500)
    # clic en tab Modelos si existe
    for sel in ('a:has-text("Modelos")', '[role=tab]:has-text("Modelos")', 'li:has-text("Modelos")'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000)
                break
        except Exception:
            pass
    await page.wait_for_timeout(3_000)
    await page.screenshot(path=str(OUT / "terrazzo-modelos.png"), full_page=True)
    page.remove_listener("response", on_resp)
    print(f"\n   Endpoints relacionados a modelos capturados ({len(cap_modelos)}):", flush=True)
    seen = set()
    for c in cap_modelos:
        p = c["url"].split("/api", 1)[-1].split("?")[0]
        if p in seen: continue
        seen.add(p)
        print(f"     [{c['status']}] {c['m']} {p}", flush=True)

    # ── 2. ABDÓN CIFUENTES: ver duplicación de modelos ──
    print(f"\n{'='*72}\n=== 2. ABDÓN CIFUENTES (G3jWrRoE) — 142 modelos ===\n{'='*72}", flush=True)
    cli2 = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": "https://app.jetbrokers.io/projects/detail/G3jWrRoE"})
    r = await cli2.get("/apartment-model/project/G3jWrRoE/all")
    if r.status_code == 200:
        models = r.json()
        print(f"   {len(models)} modelos totales.", flush=True)
        # blueprints únicos
        bps = [m.get("blueprint") for m in models]
        bp_ids = set()
        for bp in bps:
            if isinstance(bp, dict):
                bp_ids.add(bp.get("id"))
            elif isinstance(bp, str):
                bp_ids.add(bp)
        print(f"   Modelos con blueprint: {sum(1 for b in bps if b)}", flush=True)
        print(f"   Blueprints DISTINTOS: {len(bp_ids - {None})}", flush=True)
        # nombres por tipología
        tipologias = Counter()
        for m in models:
            t = f"{m.get('rooms')}D{m.get('bathrooms')}B"
            tipologias[t] += 1
        print(f"   Distribución tipologías: {dict(tipologias)}", flush=True)
        # primeros nombres
        print(f"   Ejemplos nombres (primeros 10):", flush=True)
        for m in models[:10]:
            bp = m.get("blueprint")
            bp_id = bp.get("id") if isinstance(bp, dict) else bp
            print(f"     {m.get('name')!r:40} {m.get('rooms')}D{m.get('bathrooms')}B  bp={bp_id}", flush=True)
        (OUT / "abdon_models.json").write_text(json.dumps(models, indent=2, ensure_ascii=False))

    # ── 3. Los 5 con 0 unidades: capturar units-search del navegador (Stock + scroll) ──
    print(f"\n{'='*72}\n=== 3. PROYECTOS CON 0 UNIDADES — captura passive del navegador ===\n{'='*72}", flush=True)
    cero_uds = [("NeOU0rvU", "Diagonal Paraguay 240"),
                ("jfkJBrPQ", "Froilán Roa"),
                ("1kvflc3m", "V.Mackenna 1796"),
                ("WWMCny3E", "Los Alerces"),
                ("T8UuEf2r", "Santa Rosa 250")]
    for jb_id, nombre in cero_uds:
        cap = []

        async def cap_u(resp):
            if "project-detail-search" in resp.url and resp.request.method == "POST":
                try:
                    cap.append({"status": resp.status, "body": await resp.text()})
                except Exception:
                    pass
        page.on("response", cap_u)
        try:
            await page.goto(f"https://app.jetbrokers.io/projects/detail/{jb_id}",
                            wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(3_500)
            # tab Stock
            for sel in ('a:has-text("Stock")', '[role=tab]:has-text("Stock")', 'li:has-text("Stock")'):
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.click(timeout=4_000)
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(3_500)
            # scroll agresivo para cargar tarjetas lazy
            for _ in range(40):
                try:
                    await page.mouse.wheel(0, 600)
                except Exception:
                    pass
                await page.wait_for_timeout(110)
            await page.wait_for_timeout(2_500)
        except Exception as e:
            print(f"   ⚠ {nombre}: nav err {str(e)[:50]}", flush=True)
        page.remove_listener("response", cap_u)

        # extraer del cap el JSON con más unidades
        best_uds = 0
        for c in cap:
            if c["status"] in (200, 201):
                try:
                    u = json.loads(c["body"]).get("apartments", [])
                    if len(u) > best_uds: best_uds = len(u)
                except Exception:
                    pass
        # contar tarjetas en DOM
        try:
            cards = await page.evaluate(r"""() => {
                const s=document.querySelector('mat-tab-body.mat-mdc-tab-body-active')||document.body;
                return s.querySelectorAll('.apartment, .card-apartment, [class*=apartment]').length;
            }""")
        except Exception:
            cards = 0
        print(f"   {nombre:<30} ({jb_id}): passive units-search={best_uds} · tarjetas DOM={cards}", flush=True)

    await cli.aclose(); await cli2.aclose()
    await imp.close()
    print(f"\n✓ artefactos en {OUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
