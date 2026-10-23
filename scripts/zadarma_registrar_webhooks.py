"""Registra en Zadarma la URL del webhook de bc-api y activa la transcripción.

Uso (en el VPS, con .env.zadarma cargado):
    .venv/bin/python scripts/zadarma_registrar_webhooks.py --base https://bc-api.178-105-91-29.nip.io
    .venv/bin/python scripts/zadarma_registrar_webhooks.py --base … --aplicar

Sin --aplicar solo muestra lo que haría y la configuración actual. Nunca imprime
la clave, el secreto ni el token completos.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.zadarma import firma_api  # noqa: E402
from app.settings import settings  # noqa: E402

API = "https://api.zadarma.com"


def _oculto(x):
    """Texto de la respuesta sin el token del webhook (la URL registrada lo lleva en ?k=)."""
    t = json.dumps(x, ensure_ascii=False)
    tok = settings.zadarma_webhook_token
    return t.replace(tok, tok[:4] + "…") if tok else t


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
    print("Configuración actual en Zadarma:", _oculto(_llamar("GET", "/v1/pbx/webhooks/", {})))

    if not a.aplicar:
        print("Modo prueba: agrega --aplicar para registrar la URL y activar la transcripción.")
        return 0

    actual = _llamar("GET", "/v1/pbx/webhooks/", {})
    # Zadarma responde 400 si se registra una URL igual a la que ya tiene.
    if actual.get("url") != url:
        print("URL:", _oculto(_llamar("POST", "/v1/pbx/webhooks/url/", {"url": url})))
    else:
        print("URL: ya estaba registrada")
    # Zadarma responde 400 si se pide activar algo que ya está activo.
    if (actual.get("hooks") or {}).get("speech_recognition") != "true":
        print("Transcripción:", _oculto(_llamar("POST", "/v1/pbx/webhooks/hooks/", {"speech_recognition": "true"})))
    else:
        print("Transcripción: ya estaba activa")

    # Avisos de llamadas de la centralita (inicio, contestación, fin): es OTRA
    # dirección en Zadarma ("Sobre llamadas a la centralita"), con su propia API.
    antes = _llamar("GET", "/v1/pbx/callinfo/", {})
    print("Avisos de llamadas, antes:", _oculto({**antes, "url": "(registrada)" if antes.get("url") else ""}))
    if antes.get("url") != url:
        print("Avisos de llamadas, URL:", _oculto(_llamar("POST", "/v1/pbx/callinfo/url/", {"url": url}).get("status")))
    else:
        print("Avisos de llamadas, URL: ya estaba registrada")
    avisos = {k: "true" for k in ("notify_start", "notify_end", "notify_out_start", "notify_out_end", "notify_answer")}
    try:
        print("Avisos de llamadas, eventos:", _oculto(_llamar("POST", "/v1/pbx/callinfo/notifications/", avisos)))
    except httpx.HTTPStatusError as e:
        print("Avisos de llamadas, eventos: Zadarma respondió", e.response.status_code, "(puede que ya estén activos)")
    print("Avisos de llamadas, después:", _oculto(_llamar("GET", "/v1/pbx/callinfo/", {})))
    print("Configuración final:", _oculto(_llamar("GET", "/v1/pbx/webhooks/", {})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
