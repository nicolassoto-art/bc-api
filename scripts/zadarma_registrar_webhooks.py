"""Registra en Zadarma la URL del webhook de bc-api y activa la transcripción.

Uso (en el VPS, con .env.zadarma cargado):
    .venv/bin/python scripts/zadarma_registrar_webhooks.py --base https://bc-api.178-105-91-29.nip.io
    .venv/bin/python scripts/zadarma_registrar_webhooks.py --base … --aplicar

Sin --aplicar solo muestra lo que haría y la configuración actual. Nunca imprime
la clave, el secreto ni el token completos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.zadarma import firma_api  # noqa: E402
from app.settings import settings  # noqa: E402

API = "https://api.zadarma.com"


def _llamar(verbo: str, metodo: str, params: dict) -> dict:
    cabecera = {"Authorization": f"{settings.zadarma_api_key}:{firma_api(metodo, params, settings.zadarma_api_secret)}"}
    if verbo == "GET":
        r = httpx.get(API + metodo, params=params, headers=cabecera, timeout=20)
    else:
        r = httpx.post(API + metodo, data=params, headers=cabecera, timeout=20)
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="URL pública de bc-api, sin barra final")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios en Zadarma")
    a = ap.parse_args()

    faltan = [n for n in ("zadarma_api_key", "zadarma_api_secret", "zadarma_webhook_token") if not getattr(settings, n)]
    if faltan:
        print("Faltan en el entorno:", ", ".join(faltan))
        return 1

    url = f"{a.base.rstrip('/')}/webhooks/zadarma?k={settings.zadarma_webhook_token}"
    print("URL del webhook:", url.replace(settings.zadarma_webhook_token, settings.zadarma_webhook_token[:4] + "…"))
    print("Configuración actual en Zadarma:", _llamar("GET", "/v1/pbx/webhooks/", {}))

    if not a.aplicar:
        print("Modo prueba: agrega --aplicar para registrar la URL y activar la transcripción.")
        return 0

    print("URL:", _llamar("POST", "/v1/pbx/webhooks/url/", {"url": url}))
    print("Transcripción:", _llamar("POST", "/v1/pbx/webhooks/hooks/", {"speech_recognition": "true"}))
    print("Configuración final:", _llamar("GET", "/v1/pbx/webhooks/", {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
