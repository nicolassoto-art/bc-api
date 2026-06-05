"""
diag_click.py — Observa a la app cargar un DETALLE real haciendo clic en una tarjeta.

Las URLs de detalle adivinadas redirigen a '/'. La forma real de abrir el detalle es
hacer clic en una tarjeta del catálogo (Angular mantiene el estado de ruta). Este script
hace ese clic y captura: la URL resultante + TODAS las llamadas /api/ que dispara la app
(con status y cuerpo) → revela los endpoints de detalle reales y autorizados.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)


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
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url:
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = (await resp.text())[:8000]
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(3_500)
    await imp._dismiss_popups()
    await page.wait_for_timeout(1_500)
    await page.screenshot(path=str(OUT / "click-00-catalog.png"), full_page=True)

    # ── Inspeccionar tarjetas candidatas ──
    cards = await page.evaluate(r"""() => {
        const out = [];
        const els = [...document.querySelectorAll('a,[routerlink],[ng-reflect-router-link],[class*=card],[class*=Card],[class*=project]')];
        for (const el of els) {
            const r = el.getBoundingClientRect();
            if (r.width < 140 || r.height < 120 || r.top < 0) continue;
            out.push({
                tag: el.tagName,
                cls: (el.className||'').toString().slice(0,50),
                href: el.getAttribute('href'),
                rl: el.getAttribute('routerlink') || el.getAttribute('ng-reflect-router-link'),
                text: (el.innerText||'').replace(/\s+/g,' ').slice(0,45),
                cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
            });
        }
        return out.slice(0, 10);
    }""")
    print("### Tarjetas candidatas en /catalog:", flush=True)
    for c in cards:
        print(f"   {c['tag']:6} cls={c['cls']:40} href={c['href']} rl={c['rl']} @({c['cx']},{c['cy']}) '{c['text']}'", flush=True)

    cap_mark = len(cap)
    url_before = page.url

    # ── Clickear el cover clickeable de la primera tarjeta de proyecto ──
    clicked = False
    for sel in (".card-img-top.clickable", ".card-img-top", ".card .clickable", ".card-container .card"):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.scroll_into_view_if_needed(timeout=4_000)
                await loc.click(timeout=5_000)
                clicked = True
                print(f"\n### Click en selector '{sel}'", flush=True)
                break
        except Exception as e:
            print(f"   sel '{sel}' err: {str(e)[:50]}", flush=True)
    if not clicked:
        print("\n### No se pudo clickear ninguna tarjeta", flush=True)

    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    await page.screenshot(path=str(OUT / "click-01-after.png"), full_page=True)
    print(f"### URL antes: {url_before}", flush=True)
    print(f"### URL después: {page.url}", flush=True)

    new_calls = cap[cap_mark:]
    print(f"\n### {len(new_calls)} llamadas /api/ tras el clic:", flush=True)
    seen = set()
    for c in new_calls:
        path = c["url"].split("/api", 1)[-1].split("?")[0]
        sig = f"{c['m']} {path}"
        if sig in seen:
            continue
        seen.add(sig)
        tag = ""
        if c["status"] == 200 and c.get("body"):
            b = c["body"]
            if any(k in b for k in ('apartmentModel', 'tipology', 'blueprint', 'bedroom', '"models"', 'surface')):
                tag = "  ★ posible DETALLE"
        print(f"   [{c['status']}] {c['m']} {path}{tag}", flush=True)
        # guardar bodies 200 interesantes
        if c["status"] == 200 and c.get("body") and ("project" in path.lower() or "apartment" in path.lower() or "model" in path.lower() or "store" in path.lower()):
            fn = "click-body-" + c["m"] + "-" + path.strip("/").replace("/", "_")[:60] + ".json"
            (OUT / fn).write_text(c["body"])

    (OUT / "click_all_calls.json").write_text(json.dumps(cap, indent=2, default=str)[:200000])
    await imp.close()
    print(f"\n✓ screenshots + bodies en imports/_diag/", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
