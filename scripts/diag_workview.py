"""
diag_workview.py — Mapea los sub-endpoints del workview (modelos/unidades/galería).

/marketplace/{id}/workview da la ficha de proyecto. Faltan modelos+plantas, unidades
y galería. Este script entra al workview (catálogo→clic), recorre sus pestañas internas
y captura los endpoints + cuerpos de modelos/unidades/fotos.

Solo lectura. Env: JETBROKERS_EMAIL, JETBROKERS_PASS
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter  # noqa: E402

OUT = Path("imports/_diag"); OUT.mkdir(parents=True, exist_ok=True)
TAB_WORDS = ["Modelo", "Tipolog", "Unidad", "Stock", "Galer", "Foto", "Documento",
             "Plano", "Disponib", "Bodega", "Estacion"]


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
                e["body"] = (await resp.text())[:15000]
            except Exception:
                pass
            cap.append(e)
    page.on("response", on_resp)

    # ── Entrar al workview vía catálogo→clic ──
    await page.goto("https://app.jetbrokers.io/catalog", wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(3_000)
    await imp._dismiss_popups()
    await page.wait_for_timeout(1_000)
    try:
        await page.locator(".card-img-top.clickable").first.click(timeout=6_000)
    except Exception as e:
        print(f"click card err: {e}", flush=True)
    await page.wait_for_timeout(5_000)
    await imp._dismiss_popups()
    wv_url = page.url
    print(f"### En workview: {wv_url}", flush=True)
    await page.screenshot(path=str(OUT / "wv-00-overview.png"), full_page=True)

    # ── Descubrir pestañas/botones internos ──
    tabs = await page.evaluate(r"""(words) => {
        const out = [];
        const els = [...document.querySelectorAll('button, a, [role=tab], .nav-link, .tab, mat-tab, [class*=tab]')];
        for (const el of els) {
            const t = (el.innerText||'').replace(/\s+/g,' ').trim();
            if (!t || t.length > 30) continue;
            if (words.some(w => t.toLowerCase().includes(w.toLowerCase()))) {
                const r = el.getBoundingClientRect();
                if (r.width>0 && r.height>0)
                    out.push({text: t, cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2)});
            }
        }
        return out;
    }""", TAB_WORDS)
    uniq = {}
    for t in tabs:
        uniq.setdefault(t["text"], t)
    print(f"### Pestañas/botones internos detectados: {[t for t in uniq]}", flush=True)

    # ── Clickear cada pestaña y capturar ──
    for txt, t in list(uniq.items())[:10]:
        mark = len(cap)
        try:
            await page.mouse.click(t["cx"], t["cy"])
            await page.wait_for_timeout(3_000)
            new = cap[mark:]
            rel = [c for c in new if any(k in c["url"].lower() for k in
                   ("apartment", "model", "tipolog", "store", "gallery", "file", "parking", "pack", "blueprint", "image", "document"))]
            print(f"   ▸ tab '{txt}': {len(new)} calls, {len(rel)} relevantes", flush=True)
            seen = set()
            for c in rel:
                p = c["url"].split("/api", 1)[-1].split("?")[0]
                if p in seen: continue
                seen.add(p)
                print(f"        [{c['status']}] {c['m']} {p}", flush=True)
            await page.screenshot(path=str(OUT / f"wv-tab-{txt[:10].replace('/','_')}.png"), full_page=True)
        except Exception as e:
            print(f"   tab '{txt}' err: {str(e)[:50]}", flush=True)

    page.remove_listener("response", on_resp)
    await imp.close()

    # ── Dump + guardar bodies de endpoints de datos ──
    (OUT / "workview_all_calls.json").write_text(json.dumps(cap, indent=2, default=str)[:400000])
    print(f"\n### TODOS los endpoints 200 únicos vistos ###", flush=True)
    seen = set()
    for c in cap:
        if c["status"] != 200:
            continue
        p = c["url"].split("/api", 1)[-1].split("?")[0]
        sig = f"{c['m']} {p}"
        if sig in seen: continue
        seen.add(sig)
        if any(k in p.lower() for k in ("marketplace", "apartment", "model", "tipolog", "store", "gallery", "blueprint", "parking", "pack", "document")):
            print(f"   [200] {c['m']} {p}", flush=True)
            fn = "wv-body-" + c["m"] + "-" + p.strip("/").replace("/", "_")[:70] + ".json"
            (OUT / fn).write_text(c.get("body", ""))
    print(f"\n✓ workview_all_calls.json + wv-body-*.json + screenshots", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
