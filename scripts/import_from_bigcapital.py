"""Importa proyectos desde la API pública del Cloudflare Worker de bigcapital.cl

La API no requiere autenticación y devuelve los 175 proyectos (market + private).
Las fotos vienen de JetBrokers (organización uv13koru), también públicas.

Uso:
    python scripts/import_from_bigcapital.py \\
        --bcapi-url https://bc-api.178-105-91-29.nip.io \\
        --bcapi-email nicolas.soto@bigcapital.cl \\
        --bcapi-pass-file ~/.bcapi-admin-pass \\
        --org "LARRAIN PRIETO"   # opcional, filtra por developerName
        --dry-run               # opcional
        --limit 10              # opcional

Fuente de datos:
  Lista: https://bigcapital-worker.nsotofchile.workers.dev/api/proyectos
  Detalle: https://bigcapital-worker.nsotofchile.workers.dev/api/proyecto?id=<id>
  Fotos: https://api.jetbrokers.io/api/gallery/download/uv13koru/<fileId>
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

BC_WORKER = "https://bigcapital-worker.nsotofchile.workers.dev"
JB_GALLERY = "https://api.jetbrokers.io/api/gallery/download/uv13koru"

STAGE_MAP = {
    "deliveryReady": "Entrega inmediata",
    "green": "En verde",
    "white": "En blanco",
}


def list_projects(org: str | None) -> list[dict]:
    print("1) Descargando lista de proyectos…")
    r = httpx.get(f"{BC_WORKER}/api/proyectos", timeout=30)
    r.raise_for_status()
    projects = r.json()
    print(f"   ✓ {len(projects)} proyectos encontrados")

    if org:
        q = re.sub(r"[^a-zA-Z]", "", org).lower()
        before = len(projects)
        projects = [
            p for p in projects
            if q in re.sub(r"[^a-zA-Z]", "", (p.get("developerName") or "")).lower()
        ]
        print(f"   Filtro '{org}': {before} → {len(projects)}")

    return projects


def get_detail(project_id: str) -> dict:
    r = httpx.get(f"{BC_WORKER}/api/proyecto", params={"id": project_id}, timeout=30)
    r.raise_for_status()
    return r.json()


def to_bcapi_payload(d: dict) -> dict:
    name = d.get("name") or "Sin nombre"
    pid = d.get("id") or ""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-") or f"proy-{pid}"

    stage_raw = d.get("stage") or ""
    fase = STAGE_MAP.get(stage_raw, stage_raw)

    # Foto principal: URL pública desde JetBrokers
    cover_id = d.get("coverId")
    foto_url = f"{JB_GALLERY}/{cover_id}" if cover_id else None

    return {
        "id": slug,
        "nombre": name,
        "inmobiliaria": d.get("developerName") or d.get("organization"),
        "comuna": d.get("locality"),
        "region": None,  # no viene en el worker
        "direccion": d.get("address"),
        "fase": fase,
        "modalidad": "Nuevo",
        "activo": True,
        "disponible": d.get("scope") != "private",
        "fecha_entrega": str(d.get("dateOfDelivery") or ""),
        "ano_entrega": _to_int(d.get("yearOfDelivery")),
        "foto_principal_url": foto_url,
        "external_url": f"https://www.bigcapital.cl/proyecto.html?id={pid}",
        "extra": {
            "bc_id": pid,
            "scope": d.get("scope"),
            "stage": stage_raw,
            "floors": d.get("floors"),
            "apartmentCount": d.get("apartmentCount"),
            "storeCount": d.get("storeCount"),
            "parkingCount": d.get("parkingCount"),
            "elevatorsCount": d.get("elevatorsCount"),
            "apartmentFrom": d.get("apartmentFrom"),
            "apartmentTo": d.get("apartmentTo"),
            "reserveCLP": d.get("reserveCLP"),
            "fee": d.get("fee"),
            "perks": d.get("perks"),
            "perksCommonAreas": d.get("perksCommonAreas"),
            "perksNearby": d.get("perksNearby"),
            "models": [
                {
                    "name": m.get("name"),
                    "rooms": m.get("rooms"),
                    "bathrooms": m.get("bathrooms"),
                    "surfaceTotal": m.get("surfaceTotal"),
                    "surfaceInterior": m.get("surfaceInterior"),
                    "priceBase": m.get("priceBase"),
                    "priceFinal": m.get("priceFinal"),
                    "apartmentsAvailable": m.get("apartmentsAvailable"),
                }
                for m in (d.get("models") or [])
            ],
        },
    }


def foto_payloads(d: dict) -> list[dict]:
    """Extrae las fotos del proyecto (URLs públicas JetBrokers)."""
    files = d.get("files") or []
    fotos = []
    for f in files:
        if not (f.get("mime") or "").startswith("image/"):
            continue
        fid = f.get("id")
        if not fid:
            continue
        tipo = f.get("type") or ""
        if "Blueprint" in tipo or "Floor" in tipo:
            cat = "Plano"
        elif "CommonArea" in tipo:
            cat = "Áreas comunes"
        elif "Perk" in tipo:
            cat = "Entorno"
        elif "Spec" in tipo or "Presentation" in tipo or "Brochure" in tipo:
            cat = "Exterior"
        else:
            cat = "Otro"
        fotos.append({
            "url": f"{JB_GALLERY}/{fid}",
            "categoria": cat,
            "es_principal": False,
        })

    # La portada es la principal
    cover = d.get("coverId")
    if cover:
        existing = next((x for x in fotos if x["url"].endswith(cover)), None)
        if existing:
            existing["es_principal"] = True
            existing["categoria"] = "Exterior"
        else:
            fotos.insert(0, {"url": f"{JB_GALLERY}/{cover}", "categoria": "Exterior", "es_principal": True})

    return fotos


def _to_int(v):
    try: return int(v) if v is not None else None
    except: return None


def bcapi_login(url: str, email: str, password: str) -> str:
    r = httpx.post(f"{url}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def bcapi_upsert(url: str, token: str, payload: dict) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    pid = payload["id"]
    r = httpx.put(f"{url}/proyectos/{pid}", json=payload, headers=h, timeout=30)
    if r.status_code == 404:
        r = httpx.post(f"{url}/proyectos", json=payload, headers=h, timeout=30)
    r.raise_for_status()
    return r.json()


def bcapi_upload_foto_url(url: str, token: str, pid: str, foto: dict) -> bool:
    """Sube una foto como JSON con URL (no multipart)."""
    h = {"Authorization": f"Bearer {token}"}
    body = {
        "url": foto["url"],
        "categoria": foto["categoria"],
        "es_principal": foto["es_principal"],
    }
    r = httpx.post(f"{url}/proyectos/{pid}/imagenes/url", json=body, headers=h, timeout=20)
    return r.status_code in (200, 201)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bcapi-url", required=True)
    ap.add_argument("--bcapi-email", required=True)
    ap.add_argument("--bcapi-pass-file", required=True)
    ap.add_argument("--org", default=None, help="Filtrar por inmobiliaria (fuzzy)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-fotos", action="store_true", help="No importar imágenes")
    args = ap.parse_args()

    projects = list_projects(args.org)
    if args.limit:
        projects = projects[:args.limit]
    if not projects:
        print("✗ Nada que importar.")
        return

    if args.dry_run:
        print("\n(dry-run — no escribo a bc-api)")
        for p in projects[:30]:
            scope = "🔒 privado" if p.get("scope") == "private" else "🌐 público"
            print(f"  {scope} · {p.get('name')} [{p.get('developerName')}] · {p.get('locality')}")
        if len(projects) > 30:
            print(f"  … y {len(projects)-30} más")
        return

    password = Path(args.bcapi_pass_file).expanduser().read_text().strip()
    token = bcapi_login(args.bcapi_url, args.bcapi_email, password)
    print(f"\n✓ Logueado a bc-api: {args.bcapi_url}\n")

    results = []
    for i, basic in enumerate(projects, 1):
        pid_bc = basic.get("id", "")
        name = basic.get("name", "?")
        print(f"[{i}/{len(projects)}] {name}")
        try:
            detail = get_detail(pid_bc)
            payload = to_bcapi_payload(detail)
            fotos = foto_payloads(detail) if not args.skip_fotos else []

            proj = bcapi_upsert(args.bcapi_url, token, payload)
            internal_id = proj.get("id") or payload["id"]
            print(f"  ✓ proyecto '{internal_id}'")

            fotos_ok = 0
            for f in fotos:
                ok = bcapi_upload_foto_url(args.bcapi_url, token, internal_id, f)
                if ok: fotos_ok += 1

            results.append({"name": name, "status": "ok", "fotos": fotos_ok})
            if fotos_ok:
                print(f"     + {fotos_ok} foto(s)")
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)})
            print(f"  ✗ {e}")

        time.sleep(0.5)

    ok = sum(1 for r in results if r["status"] == "ok")
    err = len(results) - ok
    print(f"\n{'='*60}")
    print(f"Total: {ok} ok · {err} errores")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
