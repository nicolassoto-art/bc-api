"""
playwright_export.py — Exporta los 83 proyectos del catálogo JetBrokers.

Filtro: JetStock=No + Disponible=Sí

Estrategia:
  1. Login via POST /api/auth/login → Bearer token
  2. Todas las calls de datos con httpx (no browser, sin consumir RAM)
  3. Si el login API falla, cae back a Playwright solo para obtener el token

Ejecutar:
  python scripts/playwright_export.py
  (lee JETBROKERS_EMAIL y JETBROKERS_PASS desde .env o env vars)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

EMAIL    = os.environ.get("JETBROKERS_EMAIL", "")
PASSWORD = os.environ.get("JETBROKERS_PASS",  "")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"

API_BASE = "https://app.jetbrokers.io/api"
JB_HEADERS = {
    "jet-brokers-version": "7.42.0",
    "device": "w",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Origin": "https://app.jetbrokers.io",
    "Referer": "https://app.jetbrokers.io/",
}

OUT_DIR    = Path(__file__).parent.parent / "output"
OUT_JSON   = OUT_DIR / "jb_playwright_export.json"
OUT_RAW    = OUT_DIR / "jb_playwright_raw.json"
CHECKPOINT = OUT_DIR / "jb_checkpoint.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Login ─────────────────────────────────────────────────────────────────────
def api_login(client: httpx.Client) -> str:
    """POST /api/auth/login → Bearer token."""
    log("🔑 Login via API...")

    # Probar varios endpoints conocidos de JetBrokers
    endpoints = [
        "/auth/login",
        "/auth/sign-in",
        "/user/login",
        "/broker/login",
        "/auth/authenticate",
    ]
    payload = {"email": EMAIL, "password": PASSWORD}

    for ep in endpoints:
        try:
            r = client.post(ep, json=payload, timeout=20)
            log(f"   {ep} → {r.status_code}")
            if r.status_code in (200, 201):
                data = r.json()
                # El token puede estar en varias keys
                token = (
                    data.get("token")
                    or data.get("accessToken")
                    or data.get("access_token")
                    or data.get("jwt")
                    or data.get("bearerToken")
                    or (data.get("data") or {}).get("token")
                    or (data.get("data") or {}).get("accessToken")
                    or (data.get("broker") or {}).get("token")
                    or (data.get("user") or {}).get("token")
                )
                if token:
                    log(f"   ✓ Token obtenido desde {ep} ({str(token)[:20]}...)")
                    return token
                log(f"   Keys en respuesta: {list(data.keys())}")
                log(f"   Respuesta: {str(data)[:300]}")
        except Exception as e:
            log(f"   {ep} error: {e}")

    raise RuntimeError(f"Login falló en todos los endpoints probados")


async def playwright_login() -> str:
    """Fallback: usa Playwright solo para extraer el token desde las respuestas de red."""
    log("🔑 Login via Playwright (capturando token de red)...")
    from playwright.async_api import async_playwright

    token_found = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()

        # Capturar el token desde las respuestas de red
        async def on_response(response):
            nonlocal token_found
            if token_found:
                return
            if "jetbrokers.io/api" not in response.url:
                return
            try:
                body = await response.json()
                body_str = json.dumps(body)
                # Buscar cualquier JWT (empieza con eyJ)
                jwt_matches = re.findall(r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+', body_str)
                if jwt_matches:
                    token_found = jwt_matches[0]
                    log(f"   ✓ Token capturado desde {response.url} ({token_found[:20]}...)")
                # También buscar por key conocida
                for key in ("token", "accessToken", "access_token", "jwt", "bearerToken"):
                    def find_key(d, k):
                        if isinstance(d, dict):
                            if k in d and isinstance(d[k], str) and len(d[k]) > 20:
                                return d[k]
                            for v in d.values():
                                r = find_key(v, k)
                                if r:
                                    return r
                        elif isinstance(d, list):
                            for item in d:
                                r = find_key(item, k)
                                if r:
                                    return r
                        return None
                    t = find_key(body, key)
                    if t and len(t) > 20:
                        token_found = t
                        log(f"   ✓ Token '{key}' desde {response.url[:60]}")
                        break
            except Exception:
                pass

        page.on("response", on_response)

        await page.goto("https://app.jetbrokers.io/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2_000)
        await page.fill('input[type="text"]', EMAIL)
        await page.fill('input[type="password"]', PASSWORD)

        # Intentar submit de 3 formas
        try:
            await page.click('button:has-text("Acceder")', timeout=5_000)
        except Exception:
            await page.keyboard.press("Enter")

        # Esperar el token (hasta 20 segundos)
        for _ in range(10):
            if token_found:
                break
            await page.wait_for_timeout(2_000)

        await browser.close()

    if not token_found:
        raise RuntimeError("No se pudo capturar el token del login")

    return token_found


def get_token() -> str:
    """Obtiene el Bearer token: primero intenta API, luego Playwright."""
    if not EMAIL or not PASSWORD:
        raise SystemExit("❌ Falta JETBROKERS_EMAIL o JETBROKERS_PASS")

    with httpx.Client(base_url=API_BASE, headers=JB_HEADERS) as client:
        try:
            return api_login(client)
        except Exception as e:
            log(f"   API login falló: {e}")
            log("   → Intentando con Playwright...")
            return asyncio.run(playwright_login())


# ── Cliente httpx ─────────────────────────────────────────────────────────────
def make_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={**JB_HEADERS, "Authorization": f"Bearer {token}"},
        timeout=30.0,
        follow_redirects=True,
    )


# ── Descarga de datos ─────────────────────────────────────────────────────────
def fetch_catalog(client: httpx.Client) -> list[dict]:
    """Catálogo paginado: JetStock=No + available=True."""
    log("📋 Descargando catálogo (JetStock:No, Disponible:Sí)...")
    projects: dict[str, dict] = {}
    offset = 0

    while True:
        payload = {"jetstock": False, "available": True, "element": offset, "quantity": 50}
        resp = client.post("/apartment/catalog-search", json=payload)
        resp.raise_for_status()
        data = resp.json()

        items = (data if isinstance(data, list) else
                 data.get("elements") or data.get("data") or data.get("apartments") or
                 data.get("items") or [])

        if not items:
            log(f"   Sin más items en offset={offset}")
            break

        for apt in items:
            pid = (apt.get("projectId") or apt.get("project_id") or
                   (apt.get("project") or {}).get("id"))
            if pid and str(pid) not in projects:
                projects[str(pid)] = {
                    "id": str(pid),
                    "name": (apt.get("projectName") or
                             (apt.get("project") or {}).get("name") or str(pid)),
                }

        log(f"   offset={offset}: {len(items)} aptos, {len(projects)} proyectos únicos")
        if len(items) < 50:
            break
        offset += 50

    log(f"   ✓ {len(projects)} proyectos en catálogo")
    return list(projects.values())


def fetch_project_detail(client: httpx.Client, pid: str) -> dict:
    resp = client.get(f"/project/{pid}")
    resp.raise_for_status()
    return resp.json()


def fetch_units(client: httpx.Client, pid: str) -> list[dict]:
    units, offset = [], 0
    while True:
        payload = {"projectId": pid, "jetstock": False, "element": offset, "quantity": 100}
        try:
            resp = client.post("/apartment/catalog-search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            items = (data if isinstance(data, list) else
                     data.get("elements") or data.get("data") or data.get("apartments") or [])
            if not items:
                break
            units.extend(items)
            if len(items) < 100:
                break
            offset += 100
        except Exception as e:
            log(f"      ⚠ Error unidades {pid}: {e}")
            break
    return units


def fetch_parking(client: httpx.Client, pid: str) -> list[dict]:
    try:
        r = client.get(f"/parking/project/{pid}/available")
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d, list) else (d.get("data") or d.get("elements") or [])
    except Exception:
        return []


def fetch_storage(client: httpx.Client, pid: str) -> list[dict]:
    try:
        r = client.get(f"/store/project/{pid}/available")
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d, list) else (d.get("data") or d.get("elements") or [])
    except Exception:
        return []


# ── Normalización ─────────────────────────────────────────────────────────────
def _str(v) -> str:
    return str(v).strip() if v is not None else ""


def _float(v) -> float | None:
    try:
        return float(str(v).replace(",", ".").replace("$", "").strip())
    except Exception:
        return None


def normalize(pid: str, detail: dict, units: list[dict],
              parking: list[dict], storage: list[dict]) -> dict:
    name = (_str(detail.get("name")) or _str(detail.get("projectName")) or pid)
    org_id = ((detail.get("organization") or {}).get("id") or
              detail.get("organizationId") or "uv13koru")

    # Fotos
    photos: list[str] = []
    for field in ("cover", "thumbnail", "image", "mainImage"):
        v = detail.get(field)
        if isinstance(v, dict):
            url = v.get("downloadUrl") or v.get("url")
            if url:
                photos.append(url)
        elif isinstance(v, str) and v.startswith("http"):
            photos.append(v)
    for field in ("coverId", "thumbnailId", "mainImageId"):
        fid = detail.get(field)
        if fid:
            photos.append(f"https://api.jetbrokers.io/api/gallery/download/{org_id}/{fid}")
    gallery = detail.get("gallery") or detail.get("images") or detail.get("files") or []
    for item in (gallery if isinstance(gallery, list) else []):
        if isinstance(item, dict):
            url = item.get("downloadUrl") or item.get("url") or item.get("path")
            if url:
                photos.append(url)
        elif isinstance(item, str) and item.startswith("http"):
            photos.append(item)
    photos = list(dict.fromkeys(photos))

    location = detail.get("location") or {}
    if isinstance(location, str):
        location = {}
    lat = _float(detail.get("latitude") or detail.get("lat") or
                 (location.get("lat") if isinstance(location, dict) else None))
    lon = _float(detail.get("longitude") or detail.get("lng") or
                 (location.get("lng") if isinstance(location, dict) else None))

    norm_units = []
    for u in units:
        norm_units.append({
            "numero": _str(u.get("number") or u.get("numero") or
                           u.get("unitNumber") or u.get("apartmentNumber") or u.get("id") or ""),
            "tipologia": _str(u.get("typology") or u.get("tipologia") or
                              u.get("model") or u.get("modelName") or u.get("type") or ""),
            "superficie": _float(u.get("surface") or u.get("area") or u.get("totalArea")),
            "precio": _float(u.get("price") or u.get("precio") or u.get("totalPrice")),
            "orientacion": _str(u.get("orientation") or u.get("orientacion") or ""),
            "piso": str(u["floor"]) if u.get("floor") is not None else None,
            "disponible": bool(u.get("available", True)),
            "_raw": u,
        })
    for pk in parking:
        n = _str(pk.get("number") or pk.get("parkingNumber") or pk.get("id") or "")
        norm_units.append({
            "numero": f"E-{n}" if n else "E",
            "tipologia": "Estacionamiento",
            "precio": _float(pk.get("price")),
            "disponible": True,
            "_raw": pk,
        })
    for st in storage:
        n = _str(st.get("number") or st.get("storeNumber") or st.get("id") or "")
        norm_units.append({
            "numero": f"B-{n}" if n else "B",
            "tipologia": "Bodega",
            "precio": _float(st.get("price")),
            "disponible": True,
            "_raw": st,
        })

    return {
        "id": pid,
        "nombre": name,
        "inmobiliaria": _str(detail.get("realEstate") or detail.get("realEstateName") or
                             detail.get("inmobiliaria") or detail.get("developer") or ""),
        "direccion": _str(detail.get("address") or detail.get("direccion") or
                         (location.get("address") if isinstance(location, dict) else None) or ""),
        "comuna": _str(detail.get("commune") or detail.get("comuna") or
                      (location.get("commune") if isinstance(location, dict) else None) or ""),
        "region": _str(detail.get("region") or
                      (location.get("region") if isinstance(location, dict) else None) or
                      "Metropolitana"),
        "gps_lat": lat,
        "gps_lon": lon,
        "estado": _str(detail.get("status") or detail.get("estado") or "En construcción"),
        "fecha_entrega": _str(detail.get("deliveryDate") or detail.get("delivery") or
                              detail.get("fechaEntrega") or "") or None,
        "fotos": photos,
        "activo": False,
        "unidades": norm_units,
        "_raw_detail": detail,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    if not EMAIL or not PASSWORD:
        raise SystemExit("❌ Falta JETBROKERS_EMAIL o JETBROKERS_PASS")

    # Checkpoint
    checkpoint: list[dict] = []
    done_ids: set[str] = set()
    if CHECKPOINT.exists():
        checkpoint = json.loads(CHECKPOINT.read_text())
        done_ids = {str(p.get("id")) for p in checkpoint}
        log(f"🔄 Checkpoint: {len(checkpoint)} proyectos ya listos")

    # Token
    token = get_token()

    with make_client(token) as client:
        catalog = fetch_catalog(client)
        if not catalog:
            raise SystemExit("❌ Catálogo vacío — revisar credenciales o filtros")

        log(f"\n✅ {len(catalog)} proyectos en catálogo\n")
        to_scrape = [p for p in catalog if str(p["id"]) not in done_ids]
        log(f"   {len(to_scrape)} pendientes, {len(done_ids)} en checkpoint\n")

        raw_all: list[dict] = []
        results: list[dict] = list(checkpoint)

        for i, proj in enumerate(to_scrape, start=len(checkpoint) + 1):
            pid   = str(proj["id"])
            pname = proj.get("name", pid)
            log(f"   [{i}/{len(catalog)}] {pname} (id={pid})")

            try:
                detail  = fetch_project_detail(client, pid)
                units   = fetch_units(client, pid)
                parking = fetch_parking(client, pid)
                storage = fetch_storage(client, pid)

                raw_all.append({"id": pid, "detail": detail, "units": units,
                                 "parking": parking, "storage": storage})
                norm = normalize(pid, detail, units, parking, storage)
                results.append(norm)
                log(f"      ✓ {len(units)} aptos, {len(parking)} estac., {len(storage)} bodegas")

                if len(results) % 5 == 0:
                    CHECKPOINT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
                    log(f"   💾 Checkpoint ({len(results)}/{len(catalog)})")

                time.sleep(0.8)

            except Exception as e:
                log(f"   ❌ Error {pname}: {e}")
                results.append({"id": pid, "nombre": pname, "_error": str(e), "unidades": []})

    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    OUT_RAW.write_text(json.dumps(raw_all, ensure_ascii=False, indent=2))
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()

    log(f"\n🎉 Listo. {len(results)} proyectos → {OUT_JSON.name}")
    log(f"   Sube el archivo al validador:")
    log(f"   https://herramientas.bigcapital.cl/src/importador/")


if __name__ == "__main__":
    main()
