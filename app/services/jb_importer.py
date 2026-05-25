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
    live_verify: dict = field(default_factory=dict)  # resultado verify final contra bc-api

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
        self._pending_plantas: list[dict] = []  # de modelos_dom para descargar luego

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
    # Mapeo (section, label) → path. Si section es "" matchea cualquier sección.
    # Labels son los EXACTOS que JB devuelve (incluyendo acentos y guiones).
    LABEL_MAP = {
        # Sección sin header (top del form) — datos básicos del proyecto
        ("", "Nombre"):                     "_nombre",  # placeholder (top-level)
        ("", "Dirección"):                  "_direccion",
        ("", "Comuna"):                     "_comuna",
        ("", "Región"):                     "_region",
        ("", "Fecha de entrega"):           "_fecha_entrega",
        ("", "Año de entrega"):             "_ano_entrega",
        ("", "Estado"):                     "_estado",
        ("", "Modalidad"):                  "_modalidad",
        ("", "Disponible"):                 "_disponible",
        ("", "Stock"):                      "extra.stock_type",
        ("", "Solicita Preaprobación"):     "extra.solicita_preaprobacion",
        ("", "Descripción"):                "extra.descripcion",
        # Datos físicos (top del form también, pero pueden estar en sección)
        ("", "Pisos"):                      "extra.fisicos.pisos",
        ("", "Unidades totales"):           "extra.fisicos.unidades_totales",
        ("", "Unidades por piso"):          "extra.fisicos.unidades_por_piso",
        ("", "Estacionamientos totales"):   "extra.fisicos.estacionamientos_totales",
        ("", "Bodegas totales"):            "extra.fisicos.bodegas_totales",
        ("", "Ascensores"):                 "extra.fisicos.ascensores",
        ("", "Constructora"):               "extra.fisicos.constructora",
        ("", "Permiso construcción"):       "extra.fisicos.permiso_construccion",
        ("", "Número permiso"):             "extra.fisicos.numero_permiso",
        ("", "Acepta cesión"):              "extra.fisicos.acepta_cesion",
        # Sección "Inmobiliaria"
        ("Inmobiliaria", "Nombre"):         "extra.inmobiliaria.nombre",
        ("Inmobiliaria", "Web"):            "extra.inmobiliaria.web",
        ("Inmobiliaria", "RUT"):            "extra.inmobiliaria.rut",
        ("Inmobiliaria", "Dirección"):      "extra.inmobiliaria.direccion",
        # Sección "Condiciones Comerciales"
        ("Condiciones Comerciales", "Pie"):              "extra.comercial.pie_pct",
        ("Condiciones Comerciales", "Tipo Pie"):         "extra.comercial.tipo_pie",
        ("Condiciones Comerciales", "Cuotón Inicial"):   "extra.comercial.cuoton_inicial_pct",
        ("Condiciones Comerciales", "Cuotón Final"):     "extra.comercial.cuoton_final_pct",
        ("Condiciones Comerciales", "Tipo Descuento"):   "extra.comercial.tipo_descuento",
        ("Condiciones Comerciales", "Tipo Bono Pie"):    "extra.comercial.tipo_bono_pie",
        ("Condiciones Comerciales", "Reserva"):          "extra.comercial.valor_reserva_clp",
        ("Condiciones Comerciales", "Tipo Reserva"):     "extra.comercial.tipo_reserva",
        ("Condiciones Comerciales", "Destino Reserva"):  "extra.comercial.destino_reserva",
        # Sección "Formas de pagar pie" / "Plan de pago"
        ("Formas de pagar el pie", "Cuotas Pre-entrega"):  "extra.formas_pago_pie.cuotas_pre_entrega",
        ("Formas de pagar el pie", "Cuotas Post-entrega"): "extra.formas_pago_pie.cuotas_post_entrega",
        ("Formas de pagar el pie", "Pago Pre-entrega"):    "extra.formas_pago_pie.pago_pre_entrega",
        ("Formas de pagar el pie", "Pago Post-entrega"):   "extra.formas_pago_pie.pago_post_entrega",
        ("Formas de pagar el pie", "Pago Cuotón Inicial"): "extra.formas_pago_pie.pago_cuoton_inicial",
        ("Formas de pagar el pie", "Valor Cuota"):         "extra.formas_pago_pie.valor_cuota_clp",
        ("Formas de pagar el pie", "Valor en UF"):         "extra.formas_pago_pie.valor_cuota_uf",
        ("Formas de pagar el pie", "Destino Reserva"):     "extra.formas_pago_pie.destino_reserva",
        # Sección "Cuenta reserva" (JB usa este nombre exacto)
        ("Cuenta reserva", "Nombre"):           "extra.cuenta_reserva.titular_nombre",
        ("Cuenta reserva", "RUT"):              "extra.cuenta_reserva.titular_rut",
        ("Cuenta reserva", "Tipo de cuenta"):   "extra.cuenta_reserva.tipo_cuenta",
        ("Cuenta reserva", "Numero de cuenta"): "extra.cuenta_reserva.numero_cuenta",
        ("Cuenta reserva", "Banco"):            "extra.cuenta_reserva.banco",
        ("Cuenta reserva", "Link de Pago Online"): "extra.cuenta_reserva.link_pago",
        # Sección "Reserva" (separada de Condiciones Comerciales)
        ("Reserva", "Reserva"):              "extra.comercial.valor_reserva_clp",
        ("Reserva", "Tipo Reserva"):         "extra.comercial.tipo_reserva",
        ("Reserva", "Destino Reserva"):      "extra.comercial.destino_reserva",
        # Sección SPA
        ("SPA del Proyecto", "Nombre"):    "extra.spa_proyecto.nombre",
        ("SPA del Proyecto", "RUT"):       "extra.spa_proyecto.rut",
        ("SPA del Proyecto", "Dirección"): "extra.spa_proyecto.direccion",
    }

    async def _dismiss_popups(self) -> None:
        """Cierra el modal '¿Ya descargaste nuestra APP?' u otros que tapan el contenido.
        Sin esto, los screenshots y scrapes pueden quedar bloqueados por el popup."""
        try:
            await self._page.evaluate("""() => {
                document.querySelectorAll('mat-dialog-container button, .modal button, .cdk-overlay-container button').forEach(b => {
                    const t = (b.innerText || '').trim().toLowerCase();
                    if (/^(cerrar|cancelar|cancel|×|x|no gracias|ahora no|m[áa]s tarde|close)$/i.test(t)) {
                        try { b.click(); } catch(e){}
                    }
                });
                document.querySelectorAll('mat-dialog-container [mat-dialog-close], mat-dialog-container .close, mat-dialog-container [aria-label*="close" i]').forEach(b => { try { b.click(); } catch(e){} });
                document.querySelectorAll('.cdk-overlay-backdrop').forEach(b => { try { b.click(); } catch(e){} });
            }""")
            await self._page.wait_for_timeout(400)
        except Exception:
            pass

    async def scrape_editor(self, jb_id: str) -> dict:
        """Navega al editor y extrae todos los campos visibles via label-based scraping."""
        log.info(f"🖱  Scrapeando editor de {jb_id}...")
        edit_url = f"https://app.jetbrokers.io/projects/edit/{jb_id}"
        await self._page.goto(edit_url, wait_until="networkidle", timeout=60_000)
        await self._page.wait_for_timeout(5_000)
        await self._dismiss_popups()

        debug_dir = self.imports_dir / jb_id / "_debug_scrape"
        debug_dir.mkdir(parents=True, exist_ok=True)

        # ── Dump del HTML del tab General ──
        html_general = await self._page.content()
        (debug_dir / "tab-general.html").write_text(html_general, encoding="utf-8")
        await self._page.screenshot(path=str(debug_dir / "tab-general.png"), full_page=True)

        out: dict[str, Any] = {}

        # ── Estrategia label+section-based ──
        all_pairs = await self._page.evaluate("""() => {
            const out = [];
            const visible = el => {
                if (!el.offsetParent && el.tagName !== 'OPTION') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const findLabel = (el) => {
                if (el.id) {
                    const l = document.querySelector(`label[for="${el.id}"]`);
                    if (l) return l.innerText.trim();
                }
                let p = el.parentElement;
                let hops = 0;
                while (p && hops < 5) {
                    const lbl = p.querySelector('label');
                    if (lbl && lbl.contains(el) === false) {
                        const t = lbl.innerText.trim();
                        if (t) return t;
                    }
                    const prev = p.previousElementSibling;
                    if (prev && prev.tagName === 'LABEL') return prev.innerText.trim();
                    p = p.parentElement;
                    hops++;
                }
                const placeholder = el.placeholder || el.getAttribute?.('aria-label') || '';
                return placeholder.trim();
            };
            // Buscar la sección: JB usa Angular con <div class="card">...<div class="card-header">SECTION</div>...</div>
            // Estrategia: ancestor más cercano con .card-header como hijo directo o nieto
            const findSection = (el) => {
                // 1. Ascender por ancestros buscando un .card
                let node = el.parentElement;
                while (node && node !== document.body) {
                    if (node.classList && (node.classList.contains('card') || node.classList.contains('panel') || node.classList.contains('section'))) {
                        // Buscar card-header dentro de este card
                        const header = node.querySelector(':scope > .card-header, :scope > .panel-heading, :scope > header, :scope > h1, :scope > h2, :scope > h3, :scope > h4');
                        if (header) {
                            const t = header.innerText.trim().split('\\n')[0].trim();
                            if (t) return t;
                        }
                    }
                    node = node.parentElement;
                }
                // 2. Fallback: cualquier .card-header anterior en el DOM
                const headers = document.querySelectorAll('.card-header, .panel-heading, h1, h2, h3, h4, h5, legend');
                let lastBefore = null;
                for (const h of headers) {
                    if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
                        lastBefore = h;
                    }
                }
                if (lastBefore) {
                    return lastBefore.innerText.trim().split('\\n')[0].trim();
                }
                return '';
            };
            const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea, mat-select, ng-select, [role="combobox"]');
            inputs.forEach(el => {
                if (!visible(el)) return;
                let v = el.value;
                if (el.tagName === 'SELECT') {
                    v = el.options[el.selectedIndex]?.text || el.value;
                } else if (el.tagName === 'MAT-SELECT' || el.tagName === 'NG-SELECT' || el.getAttribute('role') === 'combobox') {
                    // Angular Material: leer el texto visible del valor seleccionado
                    const txt = el.querySelector('.mat-mdc-select-value-text, .ng-value-label, [class*="select-value"]')?.innerText
                              || el.querySelector('span:not([class*="placeholder"])')?.innerText
                              || el.innerText;
                    v = (txt || '').trim();
                    // Filtrar placeholder text típicos
                    if (/^(seleccion|elegir|placeholder)/i.test(v)) v = '';
                }
                // Capturamos TODO los inputs que tengan label, incluyendo valores '' y '0'.
                // Esto permite ver que el campo EXISTE en JB aunque tenga valor 0/vacío.
                const label = findLabel(el);
                if (!label) return;
                const section = findSection(el);
                out.push({label, section, value: (v == null ? '' : v), type: el.type || el.tagName, name: el.name || el.id || ''});
            });
            return out;
        }""")

        log.info(f"   {len(all_pairs)} pares label/value encontrados")
        (debug_dir / "labels_found.json").write_text(json.dumps(all_pairs, indent=2, ensure_ascii=False), encoding="utf-8")

        # ── Scrape directo por formcontrolname (más robusto para mat-select Angular) ──
        # Algunos labels (Tipo Pie/Descuento/Bono Pie) no quedan asociados via <label for=...>
        # porque están dentro de mat-form-field con <mat-label> en vez de <label>.
        # Estrategia: leer mat-select por formcontrolname directamente.
        FCN_TO_PATH = {
            "preApproval":           "extra.solicita_preaprobacion",
            "depositType":           "extra.comercial.tipo_pie",
            "downpaymentBonusType":  "extra.comercial.tipo_bono_pie",
            "discountType":          "extra.comercial.tipo_descuento",
            "reservationType":       "extra.comercial.tipo_reserva",
            "reservationDestination":"extra.comercial.destino_reserva",
            "reservationBank":       "extra.cuenta_reserva.banco",
            "reservationAccountType":"extra.cuenta_reserva.tipo_cuenta",
            "buildingPermit":        "extra.fisicos.permiso_construccion",
            "stock":                 "extra.stock_type",
            # plan de pago
            "prePaymentMethod":      "extra.formas_pago_pie.pago_pre_entrega",
            "postPaymentMethod":     "extra.formas_pago_pie.pago_post_entrega",
            "initialPaymentMethod":  "extra.formas_pago_pie.pago_cuoton_inicial",
        }
        fcn_values = await self._page.evaluate(r"""(fcns) => {
            const out = {};
            for (const fcn of fcns) {
                // mat-select tiene [formcontrolname=X]
                const sel = document.querySelector(`mat-select[formcontrolname="${fcn}"]`);
                if (sel) {
                    const txt = sel.querySelector('.mat-mdc-select-value-text, [class*="select-value"]')?.innerText
                             || sel.innerText || '';
                    const v = txt.trim();
                    if (v && !/^(seleccion|elegir)/i.test(v)) {
                        out[fcn] = v;
                    }
                    continue;
                }
                // input[formcontrolname=X] como fallback
                const inp = document.querySelector(`input[formcontrolname="${fcn}"], textarea[formcontrolname="${fcn}"]`);
                if (inp && inp.value) out[fcn] = inp.value.trim();
            }
            return out;
        }""", list(FCN_TO_PATH.keys()))

        fcn_matched = 0
        for fcn, val in fcn_values.items():
            if val and fcn in FCN_TO_PATH:
                self._set_path(out, FCN_TO_PATH[fcn], val)
                fcn_matched += 1
        if fcn_matched:
            log.info(f"   ✓ {fcn_matched} campos extra via formcontrolname (mat-select Angular)")
        (debug_dir / "formcontrolname_values.json").write_text(json.dumps(fcn_values, indent=2, ensure_ascii=False), encoding="utf-8")

        # Mapear (section, label) → path
        def norm(s):
            return s.lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u").replace("ñ","n").strip()

        # Normalizar valor numérico: "20,00" → 20.0, "200.000" → 200000
        def normalize_value(path: str, value: str):
            # Paths que son numéricos
            numeric_paths = (
                "pie_pct", "cuoton_", "_pct", "valor_", "cuotas_",
                "pisos", "unidades_", "estacionamientos_", "bodegas_", "ascensores",
                "_clp", "_uf",
            )
            if not any(p in path for p in numeric_paths):
                return value
            if value is None or value == "":
                return None
            try:
                s = str(value).strip()
                # Heurística español:
                # - Con coma → coma=decimal, punto=miles. "1.234,56" → 1234.56
                # - Sin coma + punto seguido de exactamente 3 dígitos al final → miles. "200.000" → 200000
                # - Sin coma + punto con otros dígitos → decimal. "20.5" → 20.5
                if "," in s:
                    s = s.replace(".", "").replace(",", ".")
                else:
                    # Sin coma. Si todos los grupos post-dot tienen 3 dígitos → thousand sep
                    import re as _re
                    parts = s.split(".")
                    if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                        s = s.replace(".", "")
                n = float(s)
                return int(n) if n == int(n) else n
            except Exception:
                return value

        unmatched = []
        for pair in all_pairs:
            label = pair.get("label", "").strip()
            section = pair.get("section", "").strip()
            value = pair.get("value", "").strip()
            nlabel = norm(label)
            nsection = norm(section)

            # Buscar match: primero (section, label), después ("", label) si no
            matched_path = None
            for (sec_key, lbl_key), path in self.LABEL_MAP.items():
                if norm(lbl_key) == nlabel:
                    if sec_key == "" or norm(sec_key) in nsection or nsection in norm(sec_key):
                        matched_path = path
                        if sec_key:  # match con sección específica gana sobre genérico
                            break

            if matched_path and not matched_path.startswith("_"):
                self._set_path(out, matched_path, normalize_value(matched_path, value))
            elif not matched_path:
                unmatched.append({"section": section, "label": label, "value": value[:60]})

        # Dump no-matcheados para iterar
        (debug_dir / "unmatched_labels.json").write_text(json.dumps(unmatched, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"   ⚠ {len(unmatched)} labels sin mapeo (ver unmatched_labels.json)")

        # ── Etiquetas (chips): buscar elementos con texto cortos en row de Etiquetas ──
        try:
            chip_texts = await self._page.evaluate("""() => {
                const candidates = [
                    'mat-chip-row', 'mat-chip', '.chip', '.tag',
                    '[class*="chip"]', '[class*="tag"]',
                ];
                const seen = new Set();
                for (const sel of candidates) {
                    const els = document.querySelectorAll(sel);
                    if (els.length) {
                        const texts = [...els].map(e => e.innerText.replace(/cancel|×|x/gi,'').trim()).filter(t => t && t.length < 50);
                        return texts;
                    }
                }
                return [];
            }""")
            if chip_texts:
                self._set_path(out, "extra.etiquetas", chip_texts)
        except Exception as e:
            log.warning(f"   etiquetas → {e}")

        # ── Tab Documentos: contiene fotos + planos + PDFs todos juntos ──
        try:
            # Interceptar respuestas API mientras se carga el tab (para encontrar endpoint de docs)
            api_responses = []
            async def capture_api(resp):
                try:
                    url = resp.url
                    if "jetbrokers.io/api" not in url:
                        return
                    if not resp.headers.get("content-type", "").startswith("application/json"):
                        return
                    body = await resp.json()
                    api_responses.append({"url": url, "status": resp.status, "body": body})
                except Exception:
                    pass
            self._page.on("response", capture_api)

            await self._click_tab("Documentos")
            await self._page.wait_for_timeout(3_000)
            self._page.remove_listener("response", capture_api)

            await self._page.screenshot(path=str(debug_dir / "tab-documentos.png"), full_page=True)
            html_docs = await self._page.content()
            (debug_dir / "tab-documentos.html").write_text(html_docs, encoding="utf-8")

            # Dump las API responses para encontrar la que tiene la lista de docs
            api_dump = []
            for r in api_responses:
                b = r["body"]
                # Resumen: solo URL + estructura del body
                summary = {"url": r["url"], "status": r["status"]}
                if isinstance(b, list):
                    summary["type"] = f"list({len(b)})"
                    if b:
                        summary["first_keys"] = list(b[0].keys()) if isinstance(b[0], dict) else None
                        summary["sample"] = b[0] if isinstance(b[0], dict) else None
                elif isinstance(b, dict):
                    summary["type"] = "dict"
                    summary["keys"] = list(b.keys())[:10]
                    # Si tiene data/items/elements como array, capturar primer item
                    for key in ("data", "items", "elements", "files", "documents", "photos", "medias"):
                        if key in b and isinstance(b[key], list) and b[key]:
                            summary["sample"] = {"key": key, "len": len(b[key]), "first": b[key][0]}
                            break
                api_dump.append(summary)
            (debug_dir / "tab-documentos_api.json").write_text(
                json.dumps(api_dump, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            log.info(f"   📡 {len(api_responses)} API responses capturadas durante tab Documentos")

            # Extraer rows de la tabla de documentos
            docs_rows = await self._page.evaluate("""() => {
                // JB típicamente usa <table> con rows
                const tables = document.querySelectorAll('table');
                let bestTable = null;
                let bestRows = 0;
                tables.forEach(t => {
                    const rows = t.querySelectorAll('tbody tr');
                    if (rows.length > bestRows) {
                        bestTable = t;
                        bestRows = rows.length;
                    }
                });
                if (!bestTable) return [];
                const rows = bestTable.querySelectorAll('tbody tr');
                return [...rows].map(tr => {
                    const cells = [...tr.querySelectorAll('td')].map(c => c.innerText.trim());
                    // Buscar link a archivo en la row
                    const links = [...tr.querySelectorAll('a')].map(a => a.href).filter(h => h && h !== '#');
                    const imgs = [...tr.querySelectorAll('img')].map(i => i.src).filter(s => s && !s.startsWith('data:'));
                    // Botones (que disparan download)
                    const btns = [...tr.querySelectorAll('button, [role="button"]')].map(b => b.title || b.getAttribute('aria-label') || b.innerText.trim()).filter(Boolean);
                    return {cells, links, imgs, btn_titles: btns};
                });
            }""")
            (debug_dir / "documentos_rows.json").write_text(json.dumps(docs_rows, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info(f"   📄 Documentos: {len(docs_rows)} rows encontradas")
            # Clasificar por tipo (columna 2 o 3)
            classified = {"fotos": [], "planos": [], "documentos": []}
            for r in docs_rows:
                cells = r.get("cells", [])
                tipo = (cells[2] if len(cells) > 2 else "").lower()
                ext = (cells[4] if len(cells) > 4 else "").lower()
                item = {"tipo": cells[2] if len(cells) > 2 else "", "fecha": cells[0] if cells else "", "ext": ext, "links": r.get("links", [])}
                if "foto" in tipo or "imagen" in tipo or ext in ("jpg", "jpeg", "png", "webp", "gif"):
                    classified["fotos"].append(item)
                elif "planta" in tipo or "plano" in tipo or "subter" in tipo:
                    classified["planos"].append(item)
                else:
                    classified["documentos"].append(item)
            out.setdefault("extra", {})["_jb_documentos_summary"] = {
                "fotos_count": len(classified["fotos"]),
                "planos_count": len(classified["planos"]),
                "documentos_count": len(classified["documentos"]),
            }
            log.info(f"   📊 Clasificación: {len(classified['fotos'])} fotos, {len(classified['planos'])} planos, {len(classified['documentos'])} docs")
        except Exception as e:
            log.warning(f"   documentos → {e}")

        # ── Tab Modelos: tabla con plantas (Plano column) ──
        try:
            await self._click_tab("Modelos")
            await self._page.wait_for_timeout(2_500)
            await self._page.screenshot(path=str(debug_dir / "tab-modelos.png"), full_page=True)
            modelos_rows = await self._scrape_table_rows()
            if modelos_rows:
                (debug_dir / "tab-modelos_rows.json").write_text(
                    json.dumps(modelos_rows, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                modelos_data = []
                for r in modelos_rows:
                    cells = r.get("cells", [])
                    if not cells:
                        continue
                    thumb_src = (r.get("imgs") or [None])[0]
                    # Extraer planta_id del thumb URL: .../download/{id}/35/35 o .../download/{id}
                    planta_id = None
                    if thumb_src:
                        m = re.search(r"/download/([A-Za-z0-9_-]{4,})", thumb_src)
                        if m:
                            planta_id = m.group(1)
                    # JB columnas Modelos: Nombre, Dormitorios, Baños, Cotiza Bodega, Cotiza Estac, Cotiza Pack, [Plano]
                    modelos_data.append({
                        "nombre": cells[0] if len(cells) > 0 else "",
                        "dormitorios": cells[1] if len(cells) > 1 else "",
                        "banos": cells[2] if len(cells) > 2 else "",
                        "cotiza_bodega": cells[3] if len(cells) > 3 else "",
                        "cotiza_estac": cells[4] if len(cells) > 4 else "",
                        "cotiza_pack": cells[5] if len(cells) > 5 else "",
                        "planta_thumb_src": thumb_src,
                        "planta_id": planta_id,
                    })
                if modelos_data:
                    self._set_path(out, "extra.modelos_dom", modelos_data)
                    plantas_count = sum(1 for m in modelos_data if m.get("planta_id"))
                    log.info(f"   📐 Modelos tab: {len(modelos_data)} modelos, {plantas_count} con planta")
                    # Guardar para descarga posterior en download_assets
                    self._pending_plantas = [m for m in modelos_data if m.get("planta_id")]
        except Exception as e:
            log.warning(f"   modelos tab → {e}")

        # ── Tab Bodegas: tabla con bodegas individuales ──
        try:
            await self._click_tab("Bodegas")
            await self._page.wait_for_timeout(2_500)
            # Dump HTML para inspeccionar paginación
            html_bod = await self._page.content()
            (debug_dir / "tab-bodegas.html").write_text(html_bod, encoding="utf-8")
            # Paginar/scroll para cargar TODAS las bodegas (JB pagina de 30 en 30)
            total = await self._load_all_table_rows()
            log.info(f"   📦 Bodegas tras paginación: {total} rows totales")
            await self._page.screenshot(path=str(debug_dir / "tab-bodegas.png"), full_page=True)
            bodegas_rows = await self._scrape_table_rows()
            if bodegas_rows:
                (debug_dir / "tab-bodegas_rows.json").write_text(
                    json.dumps(bodegas_rows, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                bodegas_data = []
                for r in bodegas_rows:
                    if not r.get("cells"): continue
                    # Detectar columna disponible: la que tenga al menos un check o close icon
                    icons = r.get("cells_icons") or []
                    disponible = None
                    for ic in icons:
                        if ic.get("hasCheck"):
                            disponible = True; break
                        if ic.get("hasClose"):
                            disponible = False; break
                    bodegas_data.append({
                        "cells": r.get("cells", []),
                        "disponible": disponible,  # None si no se detectó, True/False si sí
                    })
                if bodegas_data:
                    self._set_path(out, "extra.bodegas_dom", bodegas_data)
                    n_dis = sum(1 for b in bodegas_data if b.get("disponible") is True)
                    n_no  = sum(1 for b in bodegas_data if b.get("disponible") is False)
                    log.info(f"   📦 Bodegas tab: {len(bodegas_data)} rows ({n_dis} disp, {n_no} no-disp)")
        except Exception as e:
            log.warning(f"   bodegas tab → {e}")

        # ── Tab Estacionamientos: tabla con estac individuales ──
        try:
            await self._click_tab("Estacionamientos")
            await self._page.wait_for_timeout(2_500)
            total = await self._load_all_table_rows()
            log.info(f"   🅿  Estac tras paginación: {total} rows totales")
            await self._page.screenshot(path=str(debug_dir / "tab-estac.png"), full_page=True)
            estac_rows = await self._scrape_table_rows()
            if estac_rows:
                (debug_dir / "tab-estac_rows.json").write_text(
                    json.dumps(estac_rows, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                estac_data = []
                for r in estac_rows:
                    if not r.get("cells"): continue
                    icons = r.get("cells_icons") or []
                    disponible = None
                    for ic in icons:
                        if ic.get("hasCheck"):
                            disponible = True; break
                        if ic.get("hasClose"):
                            disponible = False; break
                    estac_data.append({
                        "cells": r.get("cells", []),
                        "disponible": disponible,
                    })
                if estac_data:
                    self._set_path(out, "extra.estacionamientos_dom", estac_data)
                    n_dis = sum(1 for e in estac_data if e.get("disponible") is True)
                    n_no  = sum(1 for e in estac_data if e.get("disponible") is False)
                    log.info(f"   🅿  Estac tab: {len(estac_data)} rows ({n_dis} disp, {n_no} no-disp)")
        except Exception as e:
            log.warning(f"   estac tab → {e}")

        # ── Tab Stock: descargar Excel del stock (formato canónico para futuras updates) ──
        try:
            await self._click_tab("Stock")
            await self._page.wait_for_timeout(2_500)
            await self._page.screenshot(path=str(debug_dir / "tab-stock.png"), full_page=True)
            # Buscar botón "Descargar Excel" / "Exportar" / "Excel"
            xlsx_path = self.imports_dir / jb_id / f"stock-jb-{time.strftime('%Y%m%d')}.xlsx"
            xlsx_path.parent.mkdir(parents=True, exist_ok=True)
            for btn_text in ("Descargar Excel", "Exportar", "Excel", "Descargar"):
                try:
                    async with self._page.expect_download(timeout=15_000) as dl_info:
                        await self._page.locator(f"button:has-text('{btn_text}'), a:has-text('{btn_text}')").first.click(timeout=4_000)
                    download = await dl_info.value
                    await download.save_as(str(xlsx_path))
                    if xlsx_path.exists() and xlsx_path.stat().st_size > 1024:
                        log.info(f"   📊 Excel stock descargado: {xlsx_path.name} ({xlsx_path.stat().st_size} bytes)")
                        self._set_path(out, "extra._jb_stock_excel", {
                            "path": str(xlsx_path),
                            "size": xlsx_path.stat().st_size,
                            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        })
                        break
                except Exception:
                    continue
            else:
                log.warning(f"   stock excel → no se encontró botón de descarga")
        except Exception as e:
            log.warning(f"   stock tab → {e}")

        # ── Tab Notas ──
        try:
            await self._click_tab("Notas")
            await self._page.wait_for_timeout(2_000)
            await self._page.screenshot(path=str(debug_dir / "tab-notas.png"), full_page=True)
            html_notas = await self._page.evaluate("""() => {
                // Probar múltiples selectores comunes de editores rich
                const selectors = [
                    'quill-editor .ql-editor',
                    '.ql-editor',
                    'div[contenteditable="true"]',
                    'textarea[name*="not"]',
                    'textarea',
                    '.note-editable',
                    '.tox-edit-area iframe',
                ];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) {
                        const content = el.innerHTML || el.value || '';
                        if (content && content.length > 20) return content;
                    }
                }
                return '';
            }""")
            if html_notas and len(html_notas) > 20:
                self._set_path(out, "extra.notas_html", html_notas)
                # También guardar como texto plano (más legible / buscable)
                notas_text = self._html_to_text(html_notas)
                if notas_text:
                    self._set_path(out, "extra.notas_text", notas_text)
                log.info(f"   ✓ Notas extraídas ({len(html_notas)} chars HTML, {len(notas_text)} chars texto)")
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

    async def _load_all_table_rows(self) -> int:
        """Paginación robusta: detecta JB Angular custom (no Material/Bootstrap estándar).
        Estrategias en orden:
          1. Cambiar page-size dropdown a max (100/200/All) si existe
          2. Click 'Cargar más' / 'Ver más' iterativo
          3. Click 'next' / '>' / icon-arrow-right del paginador
          4. Scroll-to-bottom (lazy loading)
        """
        # 1) Probar cambiar page-size a un valor grande
        try:
            await self._page.evaluate("""() => {
                document.querySelectorAll('select').forEach(s => {
                    const opts = [...s.options].map(o => ({v: o.value, t: o.text.trim().toLowerCase()}));
                    // Buscar opción tipo "100", "200", "todos", "all"
                    const big = opts.reverse().find(o =>
                        /^(100|200|500|1000|todos|todas|all)$/i.test(o.t)
                        || (/^\\d+$/.test(o.t) && parseInt(o.t) >= 100)
                    );
                    if (big) {
                        s.value = big.v;
                        s.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                });
            }""")
            await self._page.wait_for_timeout(1500)
        except Exception:
            pass

        for _ in range(60):
            try:
                # Scroll completo dentro del scope visible
                await self._page.evaluate("""() => {
                    const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.scrollingElement;
                    scope.scrollTo({top: scope.scrollHeight});
                    window.scrollTo({top: document.body.scrollHeight});
                }""")
                await self._page.wait_for_timeout(350)
                # 2) Botones por texto
                more_btn = await self._page.evaluate("""() => {
                    const all = document.querySelectorAll('button, a, span[role="button"], .page-link, .pagination li');
                    for (const b of all) {
                        if (!b.offsetParent || b.disabled || b.classList.contains('disabled')) continue;
                        const t = (b.innerText || '').trim().toLowerCase();
                        if (/^(cargar m[áa]s|ver m[áa]s|mostrar m[áa]s|load more|siguiente|next|›|»|>)$/i.test(t)) {
                            b.click(); return 'text:' + t;
                        }
                    }
                    return null;
                }""")
                if more_btn:
                    await self._page.wait_for_timeout(900)
                    continue
                # 3) Iconos arrow / chevron
                icon_clicked = await self._page.evaluate("""() => {
                    const sels = [
                        'button[aria-label*="next" i]:not([disabled])',
                        'button[aria-label*="siguiente" i]:not([disabled])',
                        'a[aria-label*="next" i]',
                        '.pagination-next:not(.disabled)',
                        'li.next:not(.disabled)',
                        '[class*="paginat"] [class*="next"]:not([disabled])',
                        'fa-icon[icon*="chevron-right"]', 'fa-icon[data-icon="chevron-right"]',
                        '.fa-chevron-right', '.fa-angle-right', '.fa-arrow-right',
                        'button:has(fa-icon[data-icon*="right"]):not([disabled])'
                    ];
                    for (const sel of sels) {
                        try {
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent) {
                                const clickable = el.closest('button, a, li') || el;
                                if (!clickable.classList.contains('disabled')) {
                                    clickable.click(); return sel;
                                }
                            }
                        } catch(e){}
                    }
                    return null;
                }""")
                if icon_clicked:
                    await self._page.wait_for_timeout(900)
                    continue
                break
            except Exception:
                break
        # Volver al top para que el screenshot quede igual que antes
        try:
            await self._page.evaluate("""() => {
                const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document.body;
                scope.scrollTo({top: 0});
            }""")
        except Exception:
            pass
        # Contar rows
        try:
            n = await self._page.evaluate("""() => {
                const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active') || document;
                let best = 0;
                scope.querySelectorAll('table').forEach(t => {
                    const n = t.querySelectorAll('tbody tr').length;
                    if (n > best) best = n;
                });
                return best;
            }""")
            return n or 0
        except Exception:
            return 0

    async def _scrape_table_rows(self) -> list[dict]:
        """Scrapea la tabla principal de la página actual. Devuelve lista de rows con cells/links/imgs.
        Cada row además trae cells_icons (lista por celda con mat-icon name + flags de check/close)
        para detectar disponible/no-disponible cuando el texto está vacío y solo hay un ícono."""
        return await self._page.evaluate(r"""() => {
            // CRÍTICO: restringir búsqueda al tab ACTIVO de JB, sino picamos tablas
            // de otros tabs (ej: 'Descuentos por entidad' con bancos) que tienen más rows.
            const scope = document.querySelector('mat-tab-body.mat-mdc-tab-body-active, .mat-tab-body-active, [class*="tab-body-active"]')
                || document.querySelector('mat-card mat-card-content:not([style*="display: none"])')
                || document;
            const tables = scope.querySelectorAll('table');
            let best = null, bestN = 0;
            tables.forEach(t => {
                // Sanity: ignorar tablas invisibles
                const rect = t.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const n = t.querySelectorAll('tbody tr').length;
                if (n > bestN) { best = t; bestN = n; }
            });
            if (!best) return [];
            const headers = [...best.querySelectorAll('thead th')].map(h => (h.innerText || '').trim());
            return [...best.querySelectorAll('tbody tr')].map(tr => {
                const tds = [...tr.querySelectorAll('td')];
                const cells = tds.map(c => c.innerText.trim());
                const cells_icons = tds.map(c => {
                    const icons = [...c.querySelectorAll('mat-icon, .material-icons, .mat-icon')]
                        .map(i => (i.innerText || i.getAttribute('fonticon') || '').trim().toLowerCase())
                        .filter(t => t);
                    const inner = c.innerHTML || '';
                    const hasCheck = icons.some(i => /check|done/.test(i)) || /class="[^"]*(check|done|available|green|success)/i.test(inner);
                    const hasClose = icons.some(i => /close|clear|cancel/.test(i)) || /class="[^"]*(close|clear|cancel|red|danger|warn)/i.test(inner);
                    return {icons, hasCheck, hasClose};
                });
                const links = [...tr.querySelectorAll('a')].map(a => a.href).filter(h => h && h !== '#');
                const imgs = [...tr.querySelectorAll('img')].map(i => i.src).filter(s => s);
                return {cells, cells_icons, links, imgs, headers};
            });
        }""")

    async def _click_tab(self, tab_label: str) -> None:
        """Click en un tab del editor JB por su label visible. Tolerante a icons/badges."""
        # Cerrar popup que puede reaparecer tras navegar
        await self._dismiss_popups()
        # Regex flexible: matchea el label aunque tenga texto extra alrededor
        flex_pattern = re.compile(re.escape(tab_label), re.I)
        for locator_fn in (
            lambda: self._page.get_by_role("tab", name=flex_pattern),
            lambda: self._page.get_by_role("link", name=flex_pattern),
            lambda: self._page.get_by_role("button", name=flex_pattern),
            lambda: self._page.locator(f"button:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"a:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"li:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"div[role='tab']:has-text('{tab_label}')").first,
            lambda: self._page.locator(f"nav >> text=/{re.escape(tab_label)}/i").first,
            lambda: self._page.locator(f"text=/^\\s*{re.escape(tab_label)}\\s*$/i").first,
        ):
            try:
                loc = locator_fn()
                count = await loc.count()
                if count > 0:
                    await loc.first.click(timeout=4_000)
                    return
            except Exception:
                continue
        # Fallback: click por JS evaluando elementos visibles con ese texto
        try:
            clicked = await self._page.evaluate(f"""(label) => {{
                const all = document.querySelectorAll('a, button, li, [role="tab"], div');
                for (const el of all) {{
                    const t = (el.innerText || '').trim();
                    if (t === label || t.startsWith(label)) {{
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {{
                            el.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""", tab_label)
            if clicked:
                return
        except Exception:
            pass
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
    async def fetch_project_files(self, jb_id: str) -> list[dict]:
        """Llama /api/project-file/{jb_id}/list/0 para listar todos los archivos del proyecto.

        Prueba varios endpoints alternativos en caso de paginación o filtros.
        """
        files: list[dict] = []
        endpoints_to_try = [
            f"/project-file/{jb_id}/list/0",
            f"/project-file/{jb_id}/list/1",
            f"/project-file/{jb_id}/list/2",
            f"/project-file/{jb_id}/list/all",
            f"/project-file/{jb_id}",
        ]
        seen_ids = set()
        async with self._jb_httpx() as cli:
            for ep in endpoints_to_try:
                try:
                    r = await cli.get(ep)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    if isinstance(data, list):
                        items = data
                    else:
                        items = []
                        for k in ("data", "items", "elements", "files", "documents"):
                            if k in data and isinstance(data[k], list):
                                items = data[k]
                                break
                    for it in items:
                        fid = it.get("id")
                        if fid and fid not in seen_ids:
                            seen_ids.add(fid)
                            files.append(it)
                except Exception:
                    continue
        log.info(f"   project-file/list: {len(files)} archivos únicos (vía {len(endpoints_to_try)} endpoints)")
        # Imprimir distribución por type
        from collections import Counter
        types_count = Counter((f.get("type") or "_no_type") for f in files)
        for t, c in types_count.most_common():
            log.info(f"     {c} × {t}")
        return files

    async def download_assets(
        self,
        jb_id: str,
        modelos: list[dict],
        cover_url: Optional[str],
        skip: bool = False,
    ) -> dict[str, list[Path]]:
        """Descarga TODOS los archivos del proyecto (fotos+planos+docs) + cover."""
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
        fotos: list[Path] = []
        docs: list[Path] = []

        # ── 1. Listar TODOS los archivos del proyecto via API JB ──
        files_list = await self.fetch_project_files(jb_id)
        log.info(f"   📋 {len(files_list)} archivos en project-file/list")

        # Helper para clasificar
        def classify(f: dict) -> str:
            mime = (f.get("mime") or "").lower()
            tipo = (f.get("type") or "").lower()
            details = (f.get("details") or "").lower()
            # PLANTAS: tipos del modelo, planta, blueprint, subterráneo
            if any(k in tipo for k in ("apartmentmodel", "blueprint", "model", "floor", "planta")):
                return "plano"
            if any(k in details for k in ("plant", "plano", "subter", "modelo")):
                return "plano"
            # DOCUMENTOS PDF
            if "pdf" in mime:
                return "doc"
            # FOTOS (imágenes)
            if mime.startswith("image/"):
                return "foto"
            if mime.startswith("application/"):
                return "doc"
            return "foto"  # default

        for f in files_list:
            fid = f.get("id")
            if not fid:
                continue
            cat = classify(f)
            ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "application/pdf": ".pdf"}
            ext = ext_map.get((f.get("mime") or "").lower(), ".bin")
            url = f"https://api.jetbrokers.io/api/gallery/download/{self.org_id}/{fid}"
            dest = out_dir / f"{cat}-{fid}{ext}"
            if await fetch_with_retry(url, dest):
                # Guardar metadata para upload posterior
                f["_local_path"] = str(dest)
                f["_category"] = cat
                if cat == "foto":
                    fotos.append(dest)
                elif cat == "plano":
                    planos.append(dest)
                else:
                    docs.append(dest)

        # ── 2. Plantas de modelos (del tab Modelos DOM scrape) ──
        # modelos arg viene de API (5 unique). Pero scrape DOM dejó modelos_dom en extra
        # con planta_id por cada uno. Lo pasamos vía atributo en la instancia.
        if self._pending_plantas:
            for p in self._pending_plantas:
                pid = p.get("planta_id")
                if not pid:
                    continue
                # URL full-size: sin /35/35 al final
                url = f"https://app.jetbrokers.io/api/file-unauthenticated/download/{pid}"
                slug = re.sub(r"[^a-z0-9]+", "-", (p.get("nombre") or pid).lower()).strip("-")[:30]
                dest = out_dir / f"planta-{slug}-{pid}.png"
                if await fetch_with_retry(url, dest):
                    planos.append(dest)
                    p["_local_path"] = str(dest)

        # ── 3. Cover (puede ser separado) ──
        if cover_url:
            dest = out_dir / "cover.jpg"
            if await fetch_with_retry(cover_url, dest):
                fotos.append(dest)

        log.info(f"   ⬇ fotos: {len(fotos)}, plantas: {len(planos)}, docs: {len(docs)}")
        return {"planos": planos, "fotos": fotos, "docs": docs, "_files_metadata": files_list}

    # ── Upload a bc-api ──────────────────────────────────────────────────
    async def _delete_existing_jb_assets(self, proyecto_id: str) -> int:
        """Borra todas las Imagenes con categoria que empieza con 'jb-' o 'cover'.
        Hace los re-runs idempotentes (no acumula duplicados).
        """
        deleted = 0
        try:
            r = await self._bc_client.get(f"/proyectos/{proyecto_id}")
            if r.status_code != 200:
                return 0
            proj = r.json()
            for img in proj.get("imagenes", []):
                cat = (img.get("categoria") or "").lower()
                if cat.startswith("jb-") or cat == "cover":
                    img_id = img.get("id")
                    if not img_id:
                        continue
                    dr = await self._bc_client.delete(f"/proyectos/{proyecto_id}/imagenes/{img_id}")
                    if dr.status_code in (200, 204):
                        deleted += 1
        except Exception as e:
            log.warning(f"   delete existing jb-*: {e}")
        if deleted:
            log.info(f"   🧹 Borrados {deleted} assets previos (jb-*/cover) para idempotencia")
        return deleted

    async def upload_to_bc_api(
        self,
        proyecto_id: str,
        assets: dict[str, list[Path]],
        modelos: list[dict],
    ) -> dict:
        """Sube TODOS los assets descargados a bc-api con categoria apropiada.

        IDEMPOTENTE: borra los assets previos con categoría jb-* o cover antes de subir.
        """
        # Idempotencia: limpiar antes de subir
        await self._delete_existing_jb_assets(proyecto_id)

        uploaded = {"fotos": [], "planos": [], "docs": []}

        # Subir cada archivo con su metadata
        for f_meta in assets.get("_files_metadata", []):
            local = f_meta.get("_local_path")
            cat = f_meta.get("_category", "foto")
            if not local or not Path(local).exists():
                continue
            local_path = Path(local)
            details = f_meta.get("details", "")
            mime = f_meta.get("mime", "")
            jb_type = f_meta.get("type", "")
            # Categoría más informativa: tipo-{details slug}
            categoria = f"jb-{cat}"
            if details:
                slug = re.sub(r"[^a-z0-9]+", "-", details.lower()).strip("-")[:40]
                categoria = f"jb-{cat}-{slug}"
            url = await self._upload_imagen(proyecto_id, local_path, categoria=categoria)
            if url:
                uploaded[f"{cat}s"].append({"url": url, "jb_id": f_meta.get("id"), "details": details})

        # Cover separado (si existe en assets.fotos y no estaba en files_metadata)
        files_meta_paths = {Path(f.get("_local_path", "")).name for f in assets.get("_files_metadata", [])}
        for f in assets.get("fotos", []):
            if f.name in files_meta_paths:
                continue  # ya subido por el loop anterior
            url = await self._upload_imagen(proyecto_id, f, categoria="cover")
            if url:
                uploaded["fotos"].append({"url": url, "details": "cover"})

        # Plantas (del tab Modelos DOM scrape, ya descargadas)
        for p in self._pending_plantas:
            local = p.get("_local_path")
            if not local or not Path(local).exists():
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", (p.get("nombre") or "").lower()).strip("-")[:30]
            url = await self._upload_imagen(proyecto_id, Path(local), categoria=f"jb-planta-{slug}")
            if url:
                p["planta_url"] = url
                uploaded["planos"].append({"url": url, "modelo": p.get("nombre"), "jb_id": p.get("planta_id")})

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

    # ── Unidades: subir directo via POST /unidades ───────────────────────
    async def upload_unidades(self, proyecto_id: str, units: list[dict]) -> dict:
        """Inserta unidades en bc-api desde el array de API JB.

        Usa el campo apartmentModel para derivar tipologia, modelo, etc.
        Idempotente porque el wipe interno ya borró todas las unidades antes.
        """
        inserted = 0
        errors: list[str] = []
        seen = set()
        for u in units:
            numero = str(u.get("number") or u.get("numero") or "").strip()
            if not numero or numero in seen:
                continue
            seen.add(numero)
            am = u.get("apartmentModel") if isinstance(u.get("apartmentModel"), dict) else {}
            # Filtrar parking/bodega: solo importar si tiene rooms (es depto)
            # u.type también puede indicar: 'apartment' vs 'parking' vs 'storage'
            u_type = (u.get("type") or "").lower()
            if u_type in ("parking", "storage", "store", "bodega", "estacionamiento"):
                continue
            r, b = am.get("rooms"), am.get("bathrooms")
            tipologia = f"{r}D - {b}B" if r and b else ""
            data = {
                "numero": numero,
                "modelo": am.get("name") if isinstance(am, dict) else (u.get("model") or ""),
                "tipologia": tipologia,
                "tipo": "Depto",
                "orientacion": u.get("facing") or "",
                "sup_total": float(u.get("surfaceTotal") or 0) or None,
                "sup_interior": float(u.get("surfaceInterior") or 0) or None,
                "sup_terraza": float(u.get("surfaceTerrace") or 0) or None,
                "sup_logia": float(u.get("surfaceLogia") or 0) or None,
                "sup_jardin": float(u.get("surfaceGarden") or 0) or None,
                "precio_lista_uf": float(u.get("price") or 0) or None,
                "descuento_pct": float(u.get("discountRate") or 0),
                "bono_pie_pct": float(u.get("bonoPie") or 0),
                "precio_final_uf": float(u.get("finalPrice") or 0) or None,
                "estac_flag": "optional",
                "bodega_flag": "optional",
                "pack_flag": "optional",
                "disponible": bool(u.get("available", True)),
            }
            try:
                resp = await self._bc_client.post(f"/proyectos/{proyecto_id}/unidades", json=data)
                if resp.status_code in (200, 201):
                    inserted += 1
                else:
                    errors.append(f"{numero}: HTTP {resp.status_code} {resp.text[:80]}")
            except Exception as e:
                errors.append(f"{numero}: {e}")
        log.info(f"   📦 Unidades insertadas: {inserted}/{len(units)} (errors: {len(errors)})")
        return {"inserted": inserted, "errors": errors}

    async def upload_jb_excel(self, proyecto_id: str, xlsx_path: Path) -> dict:
        """Sube el Excel JB descargado a /excel/upload de bc-api.
        bc-api parsea las hojas UNIDAD / ESTACIONAMIENTOS / BODEGAS y los inserta
        completos (incluyendo los que JB pagina y el DOM scrape no captura)."""
        if not xlsx_path.exists() or xlsx_path.stat().st_size < 1024:
            log.warning(f"   excel upload: archivo no existe o vacío ({xlsx_path})")
            return {"status": "skipped"}
        try:
            with open(xlsx_path, "rb") as f:
                files = {"file": (xlsx_path.name, f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = await self._bc_client.post(
                f"/excel/upload?proyecto_id={proyecto_id}",
                files=files,
                timeout=120.0,
            )
            if r.is_success:
                data = r.json()
                log.info(f"   📊 Excel JB → bc-api: {data.get('inserted',0)} ins, {data.get('updated',0)} upd, {len(data.get('errors',[]))} err")
                return data
            log.warning(f"   excel upload HTTP {r.status_code}: {r.text[:200]}")
            return {"status": "error", "code": r.status_code, "body": r.text[:200]}
        except Exception as e:
            log.warning(f"   excel upload exception: {e}")
            return {"status": "error", "error": str(e)}

    # ── Verificación final en vivo contra bc-api ─────────────────────────
    async def verify_live(self, proyecto_id: str, expected: dict) -> dict:
        """GET /proyectos/{id} y compara contra expected counts. Devuelve dict con diff."""
        try:
            r = await self._bc_client.get(f"/proyectos/{proyecto_id}")
            if r.status_code != 200:
                return {"ok": False, "error": f"GET {r.status_code}"}
            d = r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        live = {
            "unidades": len(d.get("unidades") or []),
            "imagenes": len(d.get("imagenes") or []),
            "jb_fotos": sum(1 for i in (d.get("imagenes") or []) if (i.get("categoria") or "").startswith("jb-foto")),
            "jb_plantas": sum(1 for i in (d.get("imagenes") or []) if (i.get("categoria") or "").startswith("jb-planta-")),
            "extra_keys": sorted((d.get("extra") or {}).keys()),
            "notas_html_chars": len((d.get("extra") or {}).get("notas_html") or ""),
            "modelos_dom_count": len(((d.get("extra") or {}).get("modelos_dom")) or []),
            "bodegas_dom_count": len(((d.get("extra") or {}).get("bodegas_dom")) or []),
            "estacionamientos_dom_count": len(((d.get("extra") or {}).get("estacionamientos_dom")) or []),
        }
        # Comparar contra expected
        checks = []
        for k, exp_val in expected.items():
            live_val = live.get(k)
            ok = (live_val == exp_val) if isinstance(exp_val, int) else bool(live_val)
            checks.append({"field": k, "expected": exp_val, "live": live_val, "ok": ok})
        all_ok = all(c["ok"] for c in checks)
        return {"ok": all_ok, "live": live, "checks": checks}

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
    def _html_to_text(html: str) -> str:
        """Convierte HTML a texto plano legible, preservando estructura.
        - <p>, <br>, </tr>, </li> → newline
        - <li> → "- "
        - tablas → cells separadas con " | "
        - imágenes y blob: → omitidos
        - resto de tags → eliminados
        """
        if not html:
            return ""
        s = html
        # Quitar imágenes (incluyendo blob:)
        s = re.sub(r'<img[^>]*>', '', s, flags=re.IGNORECASE)
        # Tablas: cell separator + row separator
        s = re.sub(r'</td>\s*<td[^>]*>', ' | ', s, flags=re.IGNORECASE)
        s = re.sub(r'</tr>', '\n', s, flags=re.IGNORECASE)
        # Listas
        s = re.sub(r'<li[^>]*>', '\n- ', s, flags=re.IGNORECASE)
        # Párrafos y line breaks
        s = re.sub(r'<br[^>]*/?>', '\n', s, flags=re.IGNORECASE)
        s = re.sub(r'</p>', '\n\n', s, flags=re.IGNORECASE)
        s = re.sub(r'</h[1-6]>', '\n\n', s, flags=re.IGNORECASE)
        s = re.sub(r'</div>', '\n', s, flags=re.IGNORECASE)
        # Resto de tags → ""
        s = re.sub(r'<[^>]+>', '', s)
        # Entidades HTML comunes
        replacements = {
            '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
            '&quot;': '"', '&#39;': "'", '&apos;': "'", '&ntilde;': 'ñ',
            '&Ntilde;': 'Ñ', '&aacute;': 'á', '&eacute;': 'é',
            '&iacute;': 'í', '&oacute;': 'ó', '&uacute;': 'ú',
        }
        for ent, ch in replacements.items():
            s = s.replace(ent, ch)
        # Normalizar whitespace
        # Quitar espacios al inicio/fin de cada línea
        lines = [ln.strip() for ln in s.split('\n')]
        # Colapsar 3+ líneas vacías en 2 (max 1 línea en blanco entre párrafos)
        out_lines = []
        blank_count = 0
        for ln in lines:
            if ln == "":
                blank_count += 1
                if blank_count <= 1:
                    out_lines.append("")
            else:
                blank_count = 0
                out_lines.append(ln)
        return "\n".join(out_lines).strip()

    @staticmethod
    def _count_leaves(obj: Any) -> int:
        if isinstance(obj, dict):
            return sum(JBImporter._count_leaves(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(JBImporter._count_leaves(v) for v in obj)
        return 1

    # ── Wipe interno (parte del pipeline) ────────────────────────────────
    async def _wipe_proyecto_full(self, proyecto_id: str, current: dict) -> dict:
        """Borra TODO del proyecto antes de importar.
        - Todas las unidades
        - Todas las imagenes (cualquier categoría)
        - Reset extra (preservando solo jb_id)
        Hace los re-imports 100% idempotentes (JB como single source of truth).
        """
        deleted = {"imagenes": 0, "unidades": 0, "extra_keys": 0}

        # Imágenes
        for img in current.get("imagenes", []):
            try:
                r = await self._bc_client.delete(f"/proyectos/{proyecto_id}/imagenes/{img['id']}")
                if r.status_code in (200, 204):
                    deleted["imagenes"] += 1
            except Exception as e:
                log.warning(f"   wipe imagen {img.get('id')}: {e}")

        # Unidades
        for u in current.get("unidades", []):
            try:
                r = await self._bc_client.delete(f"/proyectos/{proyecto_id}/unidades/{u['id']}")
                if r.status_code in (200, 204):
                    deleted["unidades"] += 1
            except Exception as e:
                log.warning(f"   wipe unidad {u.get('id')}: {e}")

        # Extra (preservar solo jb_id)
        old_extra = current.get("extra") or {}
        jb_id_preserved = old_extra.get("jb_id")
        new_extra = {"jb_id": jb_id_preserved} if jb_id_preserved else {}
        deleted["extra_keys"] = len(old_extra) - len(new_extra)
        # PUT con extra reseteado (mantenemos campos top-level del proyecto)
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
            "foto_principal_url": None,  # se re-importa
            "external_url": current.get("external_url"),
            "notas": None,  # se re-importa
            "extra": new_extra,
        }
        try:
            await self._bc_client.put(f"/proyectos/{proyecto_id}", json=body)
        except Exception as e:
            log.warning(f"   wipe extra reset: {e}")

        log.info(f"   🧹 Wipe: {deleted['imagenes']} imgs, {deleted['unidades']} units, {deleted['extra_keys']} extra keys")
        return deleted

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

            # 2. WIPE — etapa inherente del pipeline (JB = single source of truth)
            if not dry_run:
                wipe_stats = await self._wipe_proyecto_full(rep.proyecto_id, current)
                rep.warnings.append(f"wipe: {wipe_stats}")
                # Re-fetch current para tener el estado post-wipe
                current = await self.get_proyecto(rep.proyecto_id)

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

            # ── HEALTH CHECK: detectar run degradado ──
            # Si el scraping extrae <20 campos, JB rechazó o falló silenciosamente
            MIN_FIELDS_OK = 20
            if rep.fields_extracted < MIN_FIELDS_OK:
                rep.warnings.append(
                    f"⚠ HEALTH: solo {rep.fields_extracted} campos extraídos "
                    f"(esperado >={MIN_FIELDS_OK}). JB pudo haber bloqueado el scrape."
                )
                # Si <5 es fail crítico: el proyecto está fundamentalmente sin data
                if rep.fields_extracted < 5:
                    rep.errors.append(f"HEALTH FAIL: solo {rep.fields_extracted} campos extraídos")
                    rep.finished_at = time.time()
                    # Guardar reporte ANTES de hacer raise para tener traza
                    out_dir = self.imports_dir / jb_id
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "report.json").write_text(json.dumps(rep.to_dict(), indent=2, default=str))
                    raise RuntimeError(
                        f"Run degradado: fields={rep.fields_extracted} < 5. "
                        f"JB pudo estar caído o el token expiró durante el scrape."
                    )

            # 4. Download assets
            if not skip_assets:
                assets = await self.download_assets(jb_id, modelos, cover_url)
                rep.planos_downloaded = len(assets.get("planos", []))
                rep.photos_downloaded = len(assets.get("fotos", []))
            else:
                assets = {"planos": [], "fotos": [], "docs": []}

            # 5. Upload assets + 6. PUT proyecto + 7. Upload unidades
            if not dry_run:
                if not skip_assets:
                    uploaded = await self.upload_to_bc_api(rep.proyecto_id, assets, modelos)
                    rep.planos_uploaded = len(uploaded.get("planos", []))
                    rep.photos_uploaded = len(uploaded.get("fotos", []))
                    rep.docs_uploaded = len(uploaded.get("docs", []))
                    rep.docs_downloaded = len(assets.get("docs", []))
                # PUT proyecto (con extra completo)
                await self.put_proyecto(rep.proyecto_id, current, scraped, modelos)
                log.info(f"   ✓ PUT /proyectos/{rep.proyecto_id} OK")
                # Insertar unidades (gap: el wipe las borra, esto las re-crea)
                api_units = api_data.get("units") or []
                if api_units:
                    units_result = await self.upload_unidades(rep.proyecto_id, api_units)
                    rep.warnings.append(f"unidades: {units_result['inserted']} inserted")
                # 7b. SUBIR EXCEL JB → bc-api parsea hojas UNIDAD/BODEGAS/ESTAC completas.
                # Esto resuelve los casos donde DOM scrape se queda corto por paginación.
                jb_excel = (scraped.get("extra") or {}).get("_jb_stock_excel") or {}
                if jb_excel.get("path"):
                    excel_result = await self.upload_jb_excel(rep.proyecto_id, Path(jb_excel["path"]))
                    if excel_result.get("inserted") or excel_result.get("updated"):
                        rep.warnings.append(f"excel JB: {excel_result.get('inserted',0)} ins, {excel_result.get('updated',0)} upd")
            else:
                log.info(f"   (dry-run) skip PUT")

            # 8. VERIFICACIÓN FINAL EN VIVO contra bc-api
            if not dry_run:
                expected_modelos = self._count_leaves({"modelos_dom": self._pending_plantas}) if self._pending_plantas else 0
                # Computar expectations desde lo que scrape + uploaded
                api_units = api_data.get("units") or []
                expected = {
                    "unidades": len(set(str(u.get("number") or "") for u in api_units if u.get("number"))),
                    "jb_fotos": rep.photos_uploaded,
                    "jb_plantas": rep.planos_uploaded,
                }
                live_check = await self.verify_live(rep.proyecto_id, expected)
                rep.live_verify = live_check
                if live_check.get("ok"):
                    log.info(f"   ✅ VERIFY LIVE: paridad 100% con bc-api")
                else:
                    log.warning(f"   ⚠ VERIFY LIVE: mismatch — {live_check.get('checks')}")
                    rep.warnings.append(f"live_verify: {live_check}")

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
