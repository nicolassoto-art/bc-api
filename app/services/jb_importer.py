"""
jb_importer.py — Importador JetBrokers → bc-api.

Módulo reusable. Diseñado para correr en GitHub Actions (ubuntu-latest)
con credenciales JB en GitHub Secrets y bc-api accesible via HTTPS.

Pipeline:
  1. Login JB (Playwright)
  2. Fetch API JB (rápido, sin DOM)
  3. Scrape editor DOM (campos privados: notas, cuenta reserva, SPA, etc.)
  4. Download assets (fotos, planos, docs) con cookies de sesión activa
  5. Upload assets a bc-api (POST /proyectos/{id}/imagenes)
  6. Build payload con extra.X correcto
  7. PUT /proyectos/{id} a bc-api

Uso:
  from app.services.jb_importer import JBImporter

  async def main():
      imp = JBImporter(
          jb_email=os.environ["JETBROKERS_EMAIL"],
          jb_password=os.environ["JETBROKERS_PASS"],
          bc_api_base=os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io"),
          bc_jwt=os.environ["BC_API_JWT"],
      )
      await imp.login()
      report = await imp.run("Sfp8j2Sq")
      print(report)
      await imp.close()
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import httpx
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger("jb_importer")

# ── Configuración ─────────────────────────────────────────────────────────────
JB_API_BASE = "https://app.jetbrokers.io/api"
JB_ORG_ID_DEFAULT = "uv13koru"
JB_HEADERS = {
    "jet-brokers-version": "7.42.0",
    "device": "w",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Origin": "https://app.jetbrokers.io",
    "Referer": "https://app.jetbrokers.io/",
}

# Selectors DOM por tab. Si un selector no matchea, se loguea y sigue.
TABS_SELECTORS = {
    "General": {
        # Cuenta reserva
        "extra.cuenta_reserva.titular_nombre": 'input[formcontrolname="reservationBankAccountHolder"]',
        "extra.cuenta_reserva.titular_rut":    'input[formcontrolname="reservationBankAccountHolderRut"]',
        "extra.cuenta_reserva.banco":          'mat-select[formcontrolname="reservationBank"] .mat-mdc-select-value-text span',
        "extra.cuenta_reserva.tipo_cuenta":    'mat-select[formcontrolname="reservationAccountType"] .mat-mdc-select-value-text span',
        "extra.cuenta_reserva.numero_cuenta":  'input[formcontrolname="reservationAccountNumber"]',
        "extra.cuenta_reserva.link_pago":      'input[formcontrolname="reservationPaymentLink"]',
        # SPA
        "extra.spa_proyecto.nombre":           'input[formcontrolname="sellerName"]',
        "extra.spa_proyecto.rut":              'input[formcontrolname="sellerRut"]',
        "extra.spa_proyecto.direccion":        'input[formcontrolname="sellerAddress"]',
        # Datos físicos
        "extra.fisicos.pisos":                 'input[formcontrolname="floors"]',
        "extra.fisicos.ascensores":            'input[formcontrolname="elevators"]',
        "extra.fisicos.constructora":          'input[formcontrolname="builder"]',
        "extra.fisicos.unidades_totales":      'input[formcontrolname="apartmentsTotal"]',
        "extra.fisicos.unidades_por_piso":     'input[formcontrolname="apartmentsPerFloor"]',
        "extra.fisicos.estacionamientos_totales": 'input[formcontrolname="parkingsTotal"]',
        "extra.fisicos.bodegas_totales":       'input[formcontrolname="storesTotal"]',
        "extra.fisicos.permiso_construccion":  'mat-select[formcontrolname="buildingPermit"] .mat-mdc-select-value-text span',
        "extra.fisicos.numero_permiso":        'input[formcontrolname="buildingPermitNumber"]',
        "extra.fisicos.acepta_cesion":         'input[formcontrolname="assignmentAccepted"]',
        # Formas pago pie
        "extra.formas_pago_pie.cuotas_pre_entrega":  'input[formcontrolname="prePaymentInstallments"]',
        "extra.formas_pago_pie.pago_pre_entrega":    'mat-select[formcontrolname="prePaymentMethod"] .mat-mdc-select-value-text span',
        "extra.formas_pago_pie.cuotas_post_entrega": 'input[formcontrolname="postPaymentInstallments"]',
        "extra.formas_pago_pie.pago_post_entrega":   'mat-select[formcontrolname="postPaymentMethod"] .mat-mdc-select-value-text span',
        "extra.formas_pago_pie.pago_cuoton_inicial": 'mat-select[formcontrolname="initialPaymentMethod"] .mat-mdc-select-value-text span',
        "extra.formas_pago_pie.valor_cuota_clp":     'input[formcontrolname="installmentValue"]',
        "extra.formas_pago_pie.destino_reserva":     'mat-select[formcontrolname="reservationDestination"] .mat-mdc-select-value-text span',
        # Comercial extra
        "extra.comercial.cuoton_inicial_pct":  'input[formcontrolname="initialInstallment"]',
        "extra.comercial.cuoton_final_pct":    'input[formcontrolname="finalInstallment"]',
        # Stock type / preap
        "extra.stock_type":                    'mat-select[formcontrolname="stock"] .mat-mdc-select-value-text span',
        "extra.solicita_preaprobacion":        'mat-select[formcontrolname="preApprovalRequired"] .mat-mdc-select-value-text span',
        # Inmobiliaria detallada
        "extra.inmobiliaria.nombre":           'input[formcontrolname="developerName"]',
        "extra.inmobiliaria.web":              'input[formcontrolname="developerWeb"]',
        "extra.inmobiliaria.rut":              'input[formcontrolname="developerRut"]',
        "extra.inmobiliaria.direccion":        'input[formcontrolname="developerAddress"]',
    },
}

# Tabs especiales: scraping personalizado (no es solo input value)
NOTAS_SELECTOR = 'quill-editor .ql-editor'
ETIQUETAS_SELECTOR = 'mat-chip-list[formcontrolname="tags"] mat-chip-row, mat-chip-grid[formcontrolname="tags"] mat-chip-row'


@dataclass
class ImportReport:
    jb_id: str
    proyecto_id: str = ""
    started_at: float = 0
    finished_at: float = 0
    fields_extracted: int = 0
    photos_downloaded: int = 0
    photos_uploaded: int = 0
    planos_downloaded: int = 0
    planos_uploaded: int = 0
    docs_downloaded: int = 0
    docs_uploaded: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)  # contenido del extra.X

    @property
    def duration_s(self) -> float:
        return round(self.finished_at - self.started_at, 1)

    def to_dict(self) -> dict:
        return {**asdict(self), "duration_s": self.duration_s}


class JBImporter:
    def __init__(
        self,
        jb_email: str,
        jb_password: str,
        bc_api_base: str,
        bc_jwt: str,
        org_id: str = JB_ORG_ID_DEFAULT,
        imports_dir: Optional[Path] = None,
        headless: bool = True,
    ):
        if not jb_email or not jb_password:
            raise ValueError("JETBROKERS_EMAIL y JETBROKERS_PASS son requeridos")
        if not bc_jwt:
            raise ValueError("bc_jwt es requerido (obtener vía /auth/exchange)")
        self.jb_email = jb_email
        self.jb_password = jb_password
        self.bc_api_base = bc_api_base.rstrip("/")
        self.bc_jwt = bc_jwt
        self.org_id = org_id
        self.imports_dir = imports_dir or Path("imports")
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

        self._pw = None
        self._browser: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._jb_token: Optional[str] = None

        # Cliente bc-api
        self._bc_client = httpx.AsyncClient(
            base_url=self.bc_api_base,
            headers={"Authorization": f"Bearer {self.bc_jwt}", "Accept": "application/json"},
            timeout=60.0,
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────
    async def login(self) -> None:
        log.info("🔑 Login en JetBrokers...")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        self._ctx = await self._browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )

        # Capturar JWT desde respuestas de red
        token_found: Optional[str] = None

        async def on_response(resp):
            nonlocal token_found
            if token_found:
                return
            if "jetbrokers.io/api" not in resp.url:
                return
            try:
                body = await resp.json()
            except Exception:
                return
            body_str = json.dumps(body)
            jwt_matches = re.findall(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", body_str)
            if jwt_matches:
                token_found = jwt_matches[0]

        self._page = await self._ctx.new_page()
        self._page.on("response", on_response)

        await self._page.goto("https://app.jetbrokers.io/", wait_until="domcontentloaded", timeout=60_000)
        await self._page.wait_for_timeout(2_000)
        await self._page.fill('input[type="text"], input[type="email"]', self.jb_email)
        await self._page.fill('input[type="password"]', self.jb_password)
        try:
            await self._page.click('button:has-text("Acceder")', timeout=5_000)
        except Exception:
            await self._page.keyboard.press("Enter")

        # Esperar a que cargue la app (dashboard, no /login)
        for i in range(15):
            url = self._page.url
            if "login" not in url.lower() and "jetbrokers.io" in url:
                # Logueado: leer broker-storage_broker-user-token específicamente
                # (JB guarda el token JSON-encoded en esa key — string corto ~8 chars)
                try:
                    raw = await self._page.evaluate(
                        "() => localStorage.getItem('broker-storage_broker-user-token')"
                    )
                    if raw:
                        # JSON-encoded → quitar quotes
                        try:
                            parsed = json.loads(raw)
                            if isinstance(parsed, str) and len(parsed) >= 4:
                                token_found = parsed
                                log.info(f"   ✓ Token JB desde localStorage ({len(parsed)} chars)")
                                break
                        except Exception:
                            # No es JSON: usar raw
                            if len(raw) >= 4:
                                token_found = raw.strip('"')
                                log.info(f"   ✓ Token JB (raw) desde localStorage ({len(raw)} chars)")
                                break
                except Exception as e:
                    log.warning(f"   read broker-token: {e}")
            if token_found:
                break
            await self._page.wait_for_timeout(2_000)
        if not token_found:
            # Debug: capturar screenshot + HTML + URL + localStorage
            try:
                debug_dir = self.imports_dir / "_debug_login"
                debug_dir.mkdir(parents=True, exist_ok=True)
                await self._page.screenshot(path=str(debug_dir / "login_fail.png"), full_page=True)
                html = await self._page.content()
                (debug_dir / "login_fail.html").write_text(html, encoding="utf-8")
                ls = await self._page.evaluate("() => Object.fromEntries(Object.entries(localStorage).map(([k,v])=>[k, v?.length || 0]))")
                (debug_dir / "localStorage_keys.json").write_text(json.dumps(ls, indent=2), encoding="utf-8")
                log.error(f"   Debug login: URL={self._page.url}")
                log.error(f"   localStorage keys+lengths: {ls}")
            except Exception as e:
                log.error(f"   No pude guardar debug: {e}")
            raise RuntimeError("Login JB falló: no se capturó el token")
        self._jb_token = token_found
        log.info(f"   ✓ Token JB capturado ({token_found[:20]}...)")

        # Esperar a que la app cargue
        await self._page.wait_for_timeout(3_000)

    async def close(self) -> None:
        await self._bc_client.aclose()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # ── API JB ────────────────────────────────────────────────────────────
    def _jb_httpx(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=JB_API_BASE,
            headers={**JB_HEADERS, "Authorization": f"Bearer {self._jb_token}"},
            timeout=30.0,
        )

    async def fetch_api(self, jb_id: str) -> dict:
        """Llama endpoints API JB para extraer la metadata base + unidades + modelos."""
        log.info(f"📡 API JB para {jb_id}...")
        async with self._jb_httpx() as cli:
            proj = (await cli.get(f"/projects/{jb_id}")).json()
            # Unidades
            try:
                units_r = await cli.get(f"/store/project/{jb_id}/available")
                units = units_r.json()
                if isinstance(units, dict):
                    units = units.get("data") or units.get("elements") or []
            except Exception:
                units = []
        log.info(f"   ✓ project + {len(units)} units")
        return {"project": proj, "units": units}

    # ── DOM scraping ──────────────────────────────────────────────────────
    async def scrape_editor(self, jb_id: str) -> dict:
        """Navega al editor y extrae todos los campos visibles."""
        log.info(f"🖱  Scrapeando editor de {jb_id}...")
        edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
        await self._page.goto(edit_url, wait_until="networkidle", timeout=60_000)
        await self._page.wait_for_timeout(5_000)

        out: dict[str, Any] = {}

        # Tab General — ya está abierto por default
        general = TABS_SELECTORS["General"]
        for path, selector in general.items():
            try:
                val = await self._read_field(selector)
                if val is not None and val != "":
                    self._set_path(out, path, val)
            except Exception as e:
                log.warning(f"   selector {path} → {e}")

        # Etiquetas (chips)
        try:
            chips = await self._page.query_selector_all(ETIQUETAS_SELECTOR)
            tags = [(await c.inner_text()).strip().replace("cancel", "").strip() for c in chips]
            tags = [t for t in tags if t]
            if tags:
                self._set_path(out, "extra.etiquetas", tags)
        except Exception as e:
            log.warning(f"   etiquetas → {e}")

        # Tab Notas
        try:
            await self._click_tab("Notas")
            await self._page.wait_for_timeout(1_500)
            html = await self._page.evaluate(
                f"() => document.querySelector('{NOTAS_SELECTOR}')?.innerHTML || ''"
            )
            if html and len(html) > 20:
                self._set_path(out, "extra.notas_html", html)
        except Exception as e:
            log.warning(f"   notas → {e}")

        log.info(f"   ✓ {self._count_leaves(out)} campos extraídos del DOM")
        return out

    async def _read_field(self, selector: str) -> Optional[str]:
        """Lee el valor de un input/select. Lo normaliza a string o None."""
        if "mat-select" in selector or "mat-mdc-select" in selector:
            # Select de Material: leer el texto visible
            el = await self._page.query_selector(selector)
            if not el:
                return None
            txt = (await el.inner_text() or "").strip()
            return txt if txt else None
        # Input nativo
        el = await self._page.query_selector(selector)
        if not el:
            return None
        val = await el.get_attribute("value")
        if val is None:
            val = await el.input_value() if (await el.evaluate("e => e.tagName")) in ("INPUT", "TEXTAREA") else None
        if val is None or val == "":
            return None
        return val.strip()

    async def _click_tab(self, tab_label: str) -> None:
        """Click en un tab del editor JB por su label visible."""
        # Probar locators progresivamente
        for locator_fn in (
            lambda: self._page.get_by_role("tab", name=re.compile(rf"^{re.escape(tab_label)}$", re.I)),
            lambda: self._page.locator(f"button:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"a:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"mat-tab:has-text('{tab_label}')").first,
        ):
            try:
                loc = locator_fn()
                count = await loc.count()
                if count > 0:
                    await loc.first.click(timeout=5_000)
                    return
            except Exception:
                continue
        raise RuntimeError(f"Tab '{tab_label}' no encontrado")

    # ── Modelos (combinar API + DOM) ──────────────────────────────────────
    def _extract_modelos(self, units: list[dict]) -> list[dict]:
        """Extrae modelos únicos desde el array de units, con sus blueprints."""
        seen: dict[str, dict] = {}
        for u in units:
            am = u.get("apartmentModel") or {}
            mid = am.get("id")
            if not mid or mid in seen:
                continue
            bp_id = ((am.get("blueprint") or {}).get("id")) if isinstance(am.get("blueprint"), dict) else None
            seen[mid] = {
                "id": mid,
                "nombre": am.get("name"),
                "dormitorios": am.get("rooms"),
                "banos": am.get("bathrooms"),
                "estac_req": am.get("requiredParking"),
                "bodega_req": am.get("requiredStorage"),
                "pack_req": am.get("requiredPack"),
                "blueprint_jb_id": bp_id,
                "plano_url": None,  # se llena después tras download/upload
            }
        return list(seen.values())

    # ── Assets ────────────────────────────────────────────────────────────
    async def download_assets(
        self,
        jb_id: str,
        modelos: list[dict],
        cover_url: Optional[str],
        skip: bool = False,
    ) -> dict[str, list[Path]]:
        """Descarga planos de modelos + cover. Devuelve dict con paths locales."""
        out_dir = self.imports_dir / jb_id / "assets"
        if skip:
            return {"planos": [], "fotos": [], "docs": []}
        out_dir.mkdir(parents=True, exist_ok=True)

        # Cookies de la sesión Playwright
        cookies = await self._ctx.cookies()
        cookie_jar = {c["name"]: c["value"] for c in cookies}

        async def fetch_with_retry(url: str, dest: Path, max_tries: int = 3) -> bool:
            for attempt in range(1, max_tries + 1):
                try:
                    async with httpx.AsyncClient(cookies=cookie_jar, timeout=60.0, follow_redirects=True) as c:
                        r = await c.get(url, headers={"User-Agent": JB_HEADERS["User-Agent"], "Referer": JB_HEADERS["Referer"]})
                        if r.status_code == 200 and len(r.content) > 1024:
                            dest.write_bytes(r.content)
                            return True
                        log.warning(f"   asset {url} → HTTP {r.status_code} (try {attempt})")
                except Exception as e:
                    log.warning(f"   asset {url} → {e} (try {attempt})")
                await asyncio.sleep(2 ** attempt)
            return False

        planos: list[Path] = []
        for m in modelos:
            bp = m.get("blueprint_jb_id")
            if not bp:
                continue
            url = f"https://api.jetbrokers.io/api/gallery/download/{self.org_id}/{bp}"
            dest = out_dir / f"plano-{m['id']}.jpg"
            if await fetch_with_retry(url, dest):
                planos.append(dest)
                m["_local_path"] = dest

        fotos: list[Path] = []
        if cover_url:
            dest = out_dir / "cover.jpg"
            if await fetch_with_retry(cover_url, dest):
                fotos.append(dest)

        log.info(f"   ⬇ planos: {len(planos)}, fotos: {len(fotos)}")
        return {"planos": planos, "fotos": fotos, "docs": []}

    # ── Upload a bc-api ──────────────────────────────────────────────────
    async def upload_to_bc_api(
        self,
        proyecto_id: str,
        assets: dict[str, list[Path]],
        modelos: list[dict],
    ) -> dict:
        """Sube assets como imágenes a bc-api. Devuelve URLs públicas."""
        uploaded = {"planos": {}, "fotos": []}

        # Planos por modelo
        for m in modelos:
            local = m.get("_local_path")
            if not local or not Path(local).exists():
                continue
            url = await self._upload_imagen(
                proyecto_id,
                Path(local),
                categoria=f"plano-modelo-{m['id']}",
            )
            if url:
                m["plano_url"] = url
                uploaded["planos"][m["id"]] = url

        # Fotos (cover principalmente)
        for f in assets.get("fotos", []):
            url = await self._upload_imagen(proyecto_id, f, categoria="cover")
            if url:
                uploaded["fotos"].append(url)

        return uploaded

    async def _upload_imagen(self, proyecto_id: str, path: Path, categoria: str) -> Optional[str]:
        """POST multipart a /proyectos/{id}/imagenes. Devuelve URL pública."""
        try:
            with open(path, "rb") as fh:
                files = {"files": (path.name, fh.read(), self._guess_mime(path))}
            data = {"categoria": categoria}
            r = await self._bc_client.post(
                f"/proyectos/{proyecto_id}/imagenes",
                files=files,
                data=data,
            )
            if r.status_code in (200, 201):
                items = r.json()
                if isinstance(items, list) and items:
                    return items[0].get("url")
            log.warning(f"   upload {path.name} → HTTP {r.status_code}")
        except Exception as e:
            log.warning(f"   upload {path.name} → {e}")
        return None

    @staticmethod
    def _guess_mime(p: Path) -> str:
        ext = p.suffix.lower()
        return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".pdf": "application/pdf", ".webp": "image/webp"}.get(ext, "application/octet-stream")

    # ── PUT bc-api ───────────────────────────────────────────────────────
    async def get_proyecto(self, proyecto_id: str) -> dict:
        r = await self._bc_client.get(f"/proyectos/{proyecto_id}")
        r.raise_for_status()
        return r.json()

    async def find_proyecto_by_jb_id(self, jb_id: str) -> Optional[dict]:
        """Busca el proyecto cuyo extra.jb_id == jb_id."""
        r = await self._bc_client.get("/proyectos")
        if not r.is_success:
            return None
        for p in r.json():
            # listing devuelve summary sin extra; necesitamos GET completo
            pid = p.get("id")
            if not pid:
                continue
            if jb_id in (pid or ""):  # heurística: slug típico es nombre-jbid
                full = await self.get_proyecto(pid)
                if (full.get("extra") or {}).get("jb_id") == jb_id:
                    return full
        # fallback: linear GET de todos
        for p in r.json():
            try:
                full = await self.get_proyecto(p["id"])
                if (full.get("extra") or {}).get("jb_id") == jb_id:
                    return full
            except Exception:
                continue
        return None

    async def put_proyecto(self, proyecto_id: str, current: dict, scraped_extra: dict, modelos: list[dict]) -> dict:
        """Build payload completo y PUT."""
        new_extra = {**(current.get("extra") or {})}
        # Merge scraped_extra paths (con dot-notation ya resueltos en out)
        for k, v in scraped_extra.get("extra", {}).items() if "extra" in scraped_extra else scraped_extra.items():
            # scrape_editor() devolvió {extra: {...}} → tomar lo de dentro
            pass
        # Cuidado: scrape_editor devuelve {extra: {cuenta_reserva: {...}}}
        # Si la key top-level es "extra", usar su contenido
        if "extra" in scraped_extra and isinstance(scraped_extra["extra"], dict):
            for k, v in scraped_extra["extra"].items():
                self._deep_merge(new_extra, {k: v})
        else:
            for k, v in scraped_extra.items():
                self._deep_merge(new_extra, {k: v})

        new_extra["modelos"] = modelos
        new_extra["_jb_imported_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        body = {
            "nombre": current["nombre"],
            "inmobiliaria": current.get("inmobiliaria"),
            "comuna": current.get("comuna"),
            "region": current.get("region"),
            "direccion": current.get("direccion"),
            "gps_lat": current.get("gps_lat"),
            "gps_lon": current.get("gps_lon"),
            "fase": current.get("fase"),
            "modalidad": current.get("modalidad"),
            "activo": current.get("activo", True),
            "disponible": current.get("disponible", True),
            "fecha_entrega": current.get("fecha_entrega"),
            "ano_entrega": current.get("ano_entrega"),
            "foto_principal_url": current.get("foto_principal_url"),
            "external_url": current.get("external_url"),
            "notas": current.get("notas"),
            "extra": new_extra,
        }
        r = await self._bc_client.put(f"/proyectos/{proyecto_id}", json=body)
        if not r.is_success:
            raise RuntimeError(f"PUT /proyectos/{proyecto_id} → HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    # ── Helpers internos ─────────────────────────────────────────────────
    @staticmethod
    def _set_path(obj: dict, dot_path: str, value: Any) -> None:
        keys = dot_path.split(".")
        cur = obj
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = value

    @staticmethod
    def _deep_merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
                JBImporter._deep_merge(dst[k], v)
            else:
                dst[k] = v

    @staticmethod
    def _count_leaves(obj: Any) -> int:
        if isinstance(obj, dict):
            return sum(JBImporter._count_leaves(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(JBImporter._count_leaves(v) for v in obj)
        return 1

    # ── Pipeline completo ────────────────────────────────────────────────
    async def run(self, jb_id: str, skip_assets: bool = False, dry_run: bool = False) -> ImportReport:
        rep = ImportReport(jb_id=jb_id, started_at=time.time())
        try:
            # 1. Buscar proyecto en bc-api por extra.jb_id
            current = await self.find_proyecto_by_jb_id(jb_id)
            if not current:
                rep.errors.append(f"Proyecto con extra.jb_id={jb_id} no encontrado en bc-api")
                return rep
            rep.proyecto_id = current["id"]

            # 2. API JB
            api_data = await self.fetch_api(jb_id)
            modelos = self._extract_modelos(api_data.get("units") or [])
            cover_url = None
            cv = (api_data.get("project") or {}).get("cover")
            if isinstance(cv, dict):
                cover_url = cv.get("url") or (
                    f"https://api.jetbrokers.io/api/gallery/download/{self.org_id}/{cv.get('id')}"
                    if cv.get("id") else None
                )

            # 3. DOM editor
            scraped = await self.scrape_editor(jb_id)
            rep.fields_extracted = self._count_leaves(scraped)
            rep.extracted = scraped

            # 4. Download assets
            if not skip_assets:
                assets = await self.download_assets(jb_id, modelos, cover_url)
                rep.planos_downloaded = len(assets.get("planos", []))
                rep.photos_downloaded = len(assets.get("fotos", []))
            else:
                assets = {"planos": [], "fotos": [], "docs": []}

            # 5. Upload assets + 6. PUT proyecto
            if not dry_run:
                if not skip_assets:
                    uploaded = await self.upload_to_bc_api(rep.proyecto_id, assets, modelos)
                    rep.planos_uploaded = len(uploaded.get("planos", {}))
                    rep.photos_uploaded = len(uploaded.get("fotos", []))
                # PUT
                await self.put_proyecto(rep.proyecto_id, current, scraped, modelos)
                log.info(f"   ✓ PUT /proyectos/{rep.proyecto_id} OK")
            else:
                log.info(f"   (dry-run) skip PUT")

            rep.finished_at = time.time()

            # Guardar reporte
            out_dir = self.imports_dir / jb_id
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "report.json").write_text(json.dumps(rep.to_dict(), indent=2, default=str))

            return rep
        except Exception as e:
            log.exception("run() failed")
            rep.errors.append(str(e))
            rep.finished_at = time.time()
            return rep
