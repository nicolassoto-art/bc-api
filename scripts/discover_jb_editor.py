"""
discover_jb_editor.py — Descubre qué expone el editor de JetBrokers para 1 proyecto.

Estrategia: login con Playwright → navegar a /projects/edit/{id} → capturar
TODAS las XHR del navegador + DOM de cada tab del editor.

Uso:
  python scripts/discover_jb_editor.py Sfp8j2Sq

Salida:
  output/discover_{id}_network.json   — lista de requests con method/url/status/body-snippet
  output/discover_{id}_dom_<tab>.html — DOM completo de cada tab visitado
  output/discover_{id}_summary.md     — resumen humano-legible
"""
from __future__ import annotations
import asyncio, json, os, sys, time, re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    # Fallback manual si dotenv no está
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

EMAIL    = os.environ.get("JETBROKERS_EMAIL", "")
PASSWORD = os.environ.get("JETBROKERS_PASS",  "")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"

OUT_DIR = Path(__file__).parent.parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


async def run(project_id: str):
    from playwright.async_api import async_playwright

    requests_log: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        # Captura todas las requests XHR / fetch
        async def on_response(resp):
            try:
                url = resp.url
                # Filtrar solo XHR/fetch al backend JB (no estáticos)
                if not ("jetbrokers.io" in url or "jetgallery" in url):
                    return
                if any(url.endswith(ext) for ext in (".js", ".css", ".woff2", ".png", ".jpg", ".svg", ".ico")):
                    return
                rt = resp.request.resource_type
                if rt in ("stylesheet", "image", "font", "media"):
                    return
                body_snippet = ""
                try:
                    if "json" in (resp.headers.get("content-type") or ""):
                        body = await resp.text()
                        body_snippet = body[:500]
                except Exception:
                    pass
                requests_log.append({
                    "ts": time.time(),
                    "method": resp.request.method,
                    "url": url,
                    "status": resp.status,
                    "type": rt,
                    "body_snippet": body_snippet,
                })
            except Exception as e:
                log(f"   resp handler error: {e}")

        page.on("response", on_response)

        # ── 1. LOGIN ─────────────────────────────────────────────
        log("🔑 Login en app.jetbrokers.io...")
        await page.goto("https://app.jetbrokers.io/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        # Buscar inputs de login
        try:
            await page.fill('input[type="email"], input[name="email"]', EMAIL, timeout=10000)
            await page.fill('input[type="password"], input[name="password"]', PASSWORD, timeout=5000)
            # Botón submit (varios selectores posibles)
            await page.click('button[type="submit"], button:has-text("Iniciar"), button:has-text("Login")', timeout=5000)
        except Exception as e:
            log(f"   Login UI no encontrado por selectores: {e}")
            log("   Esperando manualmente login (60s)...")
            await asyncio.sleep(60)

        # Esperar a redirect post-login
        try:
            await page.wait_for_url(re.compile(r".*app\.jetbrokers\.io/(?!login).*"), timeout=30000)
        except Exception:
            log("   No detecté redirect post-login, sigo igual")

        await asyncio.sleep(3)
        log(f"   Post-login URL: {page.url}")

        # ── 2. NAVEGAR A EDITOR ──────────────────────────────────
        edit_url = f"https://app.jetbrokers.io/projects/edit/{project_id}"
        log(f"📂 Navegando a {edit_url}")
        await page.goto(edit_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)

        # Guardar DOM inicial
        html = await page.content()
        (OUT_DIR / f"discover_{project_id}_dom_initial.html").write_text(html, encoding="utf-8")
        log(f"   DOM inicial guardado ({len(html)} chars)")

        # Screenshot inicial
        await page.screenshot(path=str(OUT_DIR / f"discover_{project_id}_initial.png"), full_page=True)

        # ── 3. CLICK EN CADA TAB ─────────────────────────────────
        # Identificar tabs por texto visible en el editor
        tab_candidates = [
            "General", "Datos generales", "Información general",
            "Stock", "Unidades", "Departamentos",
            "Modelos", "Tipologías",
            "Estacionamientos", "Bodegas",
            "Condiciones", "Comercial", "Plan de pago",
            "Notas", "Notas comerciales",
            "Fotos", "Galería", "Imágenes",
            "Documentos", "Archivos",
            "SPA", "Datos bancarios", "Reserva",
        ]
        tabs_visited = []
        for tab_name in tab_candidates:
            try:
                # Buscar elementos clickeables con ese texto
                loc = page.locator(f"text=/^{re.escape(tab_name)}$/i").first
                count = await loc.count() if hasattr(loc, "count") else 0
                if not count:
                    # Intentar locators alternativos
                    loc = page.get_by_role("tab", name=re.compile(rf"^{re.escape(tab_name)}$", re.I)).first
                    count = await loc.count() if hasattr(loc, "count") else 0
                if not count:
                    continue
                log(f"   → Click tab '{tab_name}'")
                await loc.click(timeout=5000)
                await asyncio.sleep(3)
                # Guardar DOM
                html = await page.content()
                safe = re.sub(r'[^a-zA-Z0-9_]+', '_', tab_name).lower()
                (OUT_DIR / f"discover_{project_id}_dom_{safe}.html").write_text(html, encoding="utf-8")
                await page.screenshot(path=str(OUT_DIR / f"discover_{project_id}_{safe}.png"), full_page=True)
                tabs_visited.append(tab_name)
            except Exception as e:
                log(f"   tab '{tab_name}' no clickeable: {str(e)[:80]}")

        # ── 4. GUARDAR LOG NETWORK ───────────────────────────────
        # Dedup por method+url
        seen = set()
        unique = []
        for r in requests_log:
            key = (r["method"], r["url"].split("?")[0])
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        log(f"📡 {len(requests_log)} requests totales, {len(unique)} únicas")
        (OUT_DIR / f"discover_{project_id}_network.json").write_text(
            json.dumps(unique, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # ── 5. RESUMEN ───────────────────────────────────────────
        summary_lines = [
            f"# Discovery JB editor — proyecto {project_id}",
            "",
            f"**Tabs visitados**: {len(tabs_visited)} — {', '.join(tabs_visited) or '(ninguno)'}",
            f"**Requests únicas**: {len(unique)}",
            "",
            "## Endpoints únicos detectados (XHR/fetch)",
            "",
        ]
        for r in unique:
            url_short = r["url"].replace("https://app.jetbrokers.io", "")
            summary_lines.append(f"- `{r['method']} {url_short}` → {r['status']}")
        (OUT_DIR / f"discover_{project_id}_summary.md").write_text(
            "\n".join(summary_lines),
            encoding="utf-8",
        )
        log("✅ Discovery completo")
        log(f"   Tabs visitados: {tabs_visited}")
        log(f"   Output en: {OUT_DIR}")

        await browser.close()


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "Sfp8j2Sq"
    if not EMAIL or not PASSWORD:
        sys.exit("❌ Faltan JETBROKERS_EMAIL / JETBROKERS_PASS en .env")
    asyncio.run(run(pid))
