"""diag_vm_stock.py — Abre el tab Stock del workview y captura TODO lo que dispara."""
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
            cap.append({"m": resp.request.method, "url": resp.url, "status": resp.status})
    page.on("response", on_resp)

    await page.goto(f"https://app.jetbrokers.io/marketplace/workview/{PID}", wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    mark = len(cap)
    # clic robusto en tab Stock
    clicked = False
    for sel in ('a:has-text("Stock")', 'button:has-text("Stock")', '[role=tab]:has-text("Stock")',
                'li:has-text("Stock")', 'text="Stock"'):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000); clicked = True
                print(f"   clic Stock via {sel}", flush=True); break
        except Exception:
            continue
    await page.wait_for_timeout(4_000)
    await imp._dismiss_popups()
    # scroll
    for _ in range(5):
        await page.mouse.wheel(0, 600); await page.wait_for_timeout(350)
    await page.wait_for_timeout(1_500)
    await page.screenshot(path=str(OUT / "vm-stock.png"), full_page=True)
    # ¿texto de la página menciona estacionamiento/bodega/pack?
    txt = (await page.evaluate("() => document.body.innerText") or "").lower()
    print(f"   menciona 'estacionamiento': {'estacionamiento' in txt} · 'bodega': {'bodega' in txt} · 'pack': {'pack' in txt}", flush=True)
    page.remove_listener("response", on_resp)
    await imp.close()

    print(f"\n### Endpoints tras abrir Stock ({len(cap)-mark} nuevos):", flush=True)
    seen = set()
    for c in cap[mark:]:
        p = c["url"].split("/api", 1)[-1].split("?")[0]
        sig = f"{c['m']} {p}"
        if sig in seen: continue
        seen.add(sig)
        print(f"   [{c['status']}] {c['m']:4} {p[:70]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
