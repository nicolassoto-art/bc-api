"""diag_vm_cotizar.py — Clic en 'Cotizar' de un depto; captura inventario estac/bodega/pack."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa

PID = os.environ.get("DIAG_ID", "utPNS9kv")
OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy", imports_dir=OUT)
    await imp.login()
    page = imp._page
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url:
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = (await resp.text())[:6000]
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    await page.goto(f"https://app.jetbrokers.io/marketplace/workview/{PID}", wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    for sel in ('a:has-text("Stock")', '[role=tab]:has-text("Stock")', 'li:has-text("Stock")'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000); break
        except Exception:
            continue
    await page.wait_for_timeout(3_500)
    mark = len(cap)
    # clic en "Cotizar" del primer depto
    clicked = False
    for sel in ('button:has-text("Cotizar")', 'a:has-text("Cotizar")', 'text="Cotizar"'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=5_000); clicked = True
                print(f"   clic Cotizar via {sel}", flush=True); break
        except Exception as e:
            print(f"   {sel}: {str(e)[:40]}", flush=True)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    print(f"   url tras Cotizar: {page.url}", flush=True)
    await page.screenshot(path=str(OUT / "cotizar-00.png"), full_page=True)
    # ¿hay selectores/secciones de estacionamiento/bodega/pack?
    txt = (await page.evaluate("() => document.body.innerText") or "").lower()
    print(f"   menciona estacionamiento={'estacionamiento' in txt} bodega={'bodega' in txt} pack={'pack' in txt}", flush=True)
    # clic en pestañas/botones estac/bodega/pack dentro de la cotización
    for word in ("estacionamiento", "bodega", "pack"):
        try:
            loc = page.locator(f'text=/{word}/i').first
            if await loc.count() > 0:
                await loc.click(timeout=3_000)
                await page.wait_for_timeout(2_500)
                await page.screenshot(path=str(OUT / f"cotizar-{word}.png"), full_page=True)
                print(f"   clic '{word}'", flush=True)
        except Exception:
            pass
    page.remove_listener("response", on_resp)
    await imp.close()

    print(f"\n### Endpoints tras Cotizar ({len(cap)-mark} nuevos):", flush=True)
    seen = set()
    for c in cap[mark:]:
        p = c["url"].split("/api", 1)[-1].split("?")[0]
        if p in seen: continue
        seen.add(p)
        info = ""
        if c["status"] == 200 and c.get("body"):
            b = c["body"]
            if any(k in b.lower() for k in ("parking", "store", '"number"', "available")):
                try:
                    j = json.loads(b)
                    if isinstance(j, list): info = f"list[{len(j)}] {json.dumps(j[0],ensure_ascii=False)[:120] if j else ''}"
                    elif isinstance(j, dict): info = f"dict {list(j.keys())[:8]}"
                except Exception:
                    info = "(body)"
        print(f"   [{c['status']}] {c['m']:4} {p[:60]}   {info}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
