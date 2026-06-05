"""
diag_detail_page.py — Explora /projects/detail/{id} (vista de proyectos PROPIOS de BigCapital).

Pista del usuario: https://app.jetbrokers.io/projects/detail/exrBr6Tp
Captura TODAS las llamadas /api/ que dispara esa vista (los endpoints de stock de proyectos
propios, distintos del marketplace) + screenshots, para descubrir modelos/unidades/plantas.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS, DIAG_ID (default exrBr6Tp)
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
PID = os.environ.get("DIAG_ID", "exrBr6Tp")
KW = ["apartment", "model", "stock", "unit", "store", "parking", "pack", "tipolog",
      "facing", "project", "file", "blueprint", "document", "marketplace"]


async def main():
    imp = JBImporter(
        jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
        bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
        bc_jwt=os.environ.get("BC_API_JWT", "dummy-no-write"), imports_dir=OUT)
    await imp.login()
    page = imp._page
    cap = []

    async def on_resp(resp):
        if "jetbrokers.io/api" in resp.url:
            e = {"m": resp.request.method, "url": resp.url, "status": resp.status}
            try:
                e["body"] = (await resp.text())[:18000]
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    print(f"### Navegando /projects/detail/{PID}", flush=True)
    await page.goto(f"https://app.jetbrokers.io/projects/detail/{PID}",
                    wait_until="networkidle", timeout=50_000)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    print(f"   url final: {page.url}", flush=True)
    body_txt = await page.evaluate("() => document.body.innerText.slice(0,300)")
    print(f"   ¿login? {'SÍ (sesión perdida)' if 'login' in page.url.lower() or 'contraseña' in (body_txt or '').lower() else 'no'}", flush=True)
    await page.screenshot(path=str(OUT / "detail-00.png"), full_page=True)

    # recorrer pestañas/botones internos
    tabwords = "modelo|tipolog|unidad|stock|disponib|bodega|estacion|plano|foto|galer|documento"
    for i in range(8):
        clicked = await page.evaluate(r"""(rx) => {
            const re = new RegExp(rx, 'i');
            const done = window.__clicked || (window.__clicked = new Set());
            for (const el of document.querySelectorAll('button,a,[role=tab],.nav-link,.tab,[class*=tab],span,div')) {
                const s=(el.innerText||'').replace(/\s+/g,' ').trim();
                if (s && re.test(s) && s.length<22 && !done.has(s)) {
                    const r=el.getBoundingClientRect();
                    if(r.width>0&&r.height>0){done.add(s); el.click(); return s;}
                }
            }
            return null;
        }""", tabwords)
        if not clicked:
            break
        await page.wait_for_timeout(2_500)
        print(f"   clic tab: {clicked!r}", flush=True)
    await page.screenshot(path=str(OUT / "detail-01-tabs.png"), full_page=True)
    # scroll para lazy
    for _ in range(6):
        await page.mouse.wheel(0, 600); await page.wait_for_timeout(400)
    await page.wait_for_timeout(2_000)
    await page.screenshot(path=str(OUT / "detail-02-scrolled.png"), full_page=True)

    page.remove_listener("response", on_resp)
    await imp.close()

    # reporte
    print(f"\n### {len(cap)} llamadas API. Histograma: {dict(Counter(c['status'] for c in cap))}", flush=True)
    print(f"\n### Endpoints relevantes (status + tipo de respuesta):", flush=True)
    seen = set()
    for c in cap:
        path = c["url"].split("/api", 1)[-1].split("?")[0]
        low = path.lower()
        if not any(k in low for k in KW):
            continue
        sig = f"{c['m']} {path}"
        if sig in seen:
            continue
        seen.add(sig)
        info = ""
        if c["status"] in (200, 201) and c.get("body"):
            try:
                j = json.loads(c["body"])
                if isinstance(j, list):
                    info = f"list[{len(j)}]" + (f" keys={list(j[0].keys())[:18]}" if j and isinstance(j[0], dict) else "")
                elif isinstance(j, dict):
                    info = f"dict keys={list(j.keys())[:18]}"
                    # guardar bodies con modelos/unidades
                    if any(k in low for k in ("model", "apartment", "stock", "unit")):
                        fn = "detailapi-" + c["m"] + "-" + path.strip("/").replace("/", "_")[:60] + ".json"
                        (OUT / fn).write_text(c["body"])
            except Exception:
                info = f"({len(c['body'])}b)"
        print(f"   [{c['status']}] {c['m']:4} {path[:70]}   {info}", flush=True)
    print(f"\n✓ bodies + screenshots en imports/_diag/", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
