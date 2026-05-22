"""Importa proyectos desde un EXPORT MANUAL del usuario logueado en JetBroker.

Flujo legítimo (sin scraping ni bot evasion):
  1. Vos entras a https://app.jetbrokers.io con tu sesión normal
  2. Corrés un snippet JS en la consola del browser (Chrome DevTools)
     que llama a los mismos endpoints que la UI usa normalmente y
     baja un JSON con tus proyectos. Es uso humano-asistido de tu
     propia sesión autorizada.
  3. Guardás ese JSON localmente.
  4. Este script lo lee y lo importa al bc-api.

El snippet JS está en: `scripts/jb_export_snippet.js`

Uso:
    python scripts/import_from_jetbroker.py \\
        --input ~/Downloads/jb_export.json \\
        --bcapi-url https://bc-api.178-105-91-29.nip.io \\
        --bcapi-email nicolas.soto@bigcapital.cl \\
        --bcapi-pass-file ~/.bcapi-admin-pass \\
        --org "Larraín Prieto"     # filtra antes de importar (opcional)
        --dry-run                   # opcional, no escribe a la DB
"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path

import httpx


def filter_by_org(projects: list[dict], org_query: str) -> list[dict]:
    """Filtra proyectos cuya organization matchee org_query (case-insensitive, fuzzy)."""
    q = re.sub(r"[^a-zA-Z]", "", org_query).lower()
    matched = []
    for p in projects:
        org = p.get("organization") or {}
        name = (org.get("name") if isinstance(org, dict) else org) or ""
        clean = re.sub(r"[^a-zA-Z]", "", str(name)).lower()
        if q in clean:
            matched.append(p)
    return matched


def to_bcapi_payload(jb_project: dict) -> dict:
    """Transforma proyecto JB → payload bc-api."""
    p = jb_project
    org = p.get("organization") or {}
    org_name = org.get("name") if isinstance(org, dict) else org
    pid = p.get("id")
    name = p.get("name") or "Sin nombre"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-") or ("proy-" + str(pid))

    extra = {}
    for k in ("locality", "address", "rooms", "bathrooms", "amenities",
              "deliveryDate", "modality", "stage", "downpaymentPercentage",
              "description", "totalUnits", "phase", "external_id"):
        if k in p:
            extra[k] = p[k]
    extra["jb_id"] = pid

    return {
        "id": slug,
        "nombre": name,
        "inmobiliaria": org_name,
        "comuna": p.get("locality") or p.get("commune"),
        "region": p.get("region"),
        "direccion": p.get("address"),
        "fase": p.get("stage") or p.get("phase"),
        "modalidad": p.get("modality"),
        "activo": True,
        "disponible": p.get("available", True),
        "fecha_entrega": p.get("deliveryDate"),
        "ano_entrega": _to_int(p.get("deliveryYear")),
        # NOTA: fotos NO se sacan de JB. Las pega bigcapital.cl desde su catálogo público.
        # Por ahora dejamos null; otro script las carga matcheando por nombre/slug.
        "foto_principal_url": None,
        "external_url": f"https://app.jetbrokers.io/projects/{pid}" if pid else None,
        "extra": extra,
    }


def units_to_payloads(jb_project: dict) -> list[dict]:
    units = jb_project.get("units") or []
    out = []
    for u in units:
        out.append({
            "numero": str(u.get("number", "")),
            "modelo": (u.get("apartmentModel") or {}).get("name") if isinstance(u.get("apartmentModel"), dict) else u.get("model"),
            "tipologia": _typology(u),
            "tipo": u.get("type", "apartment"),
            "orientacion": u.get("facing"),
            "sup_total": _to_float(u.get("surfaceTotal")),
            "sup_interior": _to_float(u.get("surfaceInterior")),
            "sup_terraza": _to_float(u.get("surfaceTerrace")),
            "sup_logia": _to_float(u.get("surfaceLogia")),
            "sup_jardin": _to_float(u.get("surfaceGarden")),
            "precio_lista_uf": _to_float(u.get("price")),
            "descuento_pct": _to_float(u.get("discountRate")) or 0,
            "bono_pie_pct": _to_float(u.get("bonoPie")) or 0,
            "precio_final_uf": _to_float(u.get("finalPrice")),
            "disponible": bool(u.get("available", True)),
        })
    return out


def _typology(u: dict) -> str | None:
    m = u.get("apartmentModel")
    if isinstance(m, dict):
        r, b = m.get("rooms"), m.get("bathrooms")
        if r and b:
            return f"{r}D - {b}B"
    return u.get("typology")


def _to_int(v):
    try: return int(v) if v is not None else None
    except: return None


def _to_float(v):
    try: return float(v) if v is not None and v != "" else None
    except: return None


def bcapi_login(url: str, email: str, password: str) -> str:
    r = httpx.post(f"{url}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def bcapi_upsert(url: str, token: str, payload: dict, units: list[dict]) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    pid = payload["id"]
    r = httpx.put(f"{url}/proyectos/{pid}", json=payload, headers=h, timeout=30)
    if r.status_code == 404:
        r = httpx.post(f"{url}/proyectos", json=payload, headers=h, timeout=30)
    r.raise_for_status()
    inserted = 0
    for u in units:
        r = httpx.post(f"{url}/proyectos/{pid}/unidades", json=u, headers=h, timeout=20)
        if r.status_code in (200, 201):
            inserted += 1
    return {"project_id": pid, "units_inserted": inserted, "units_total": len(units)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="JSON exportado desde JB (con snippet)")
    ap.add_argument("--org", default=None, help="Filtrar por inmobiliaria (fuzzy match, opcional)")
    ap.add_argument("--bcapi-url", required=True)
    ap.add_argument("--bcapi-email", required=True)
    ap.add_argument("--bcapi-pass-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        raise SystemExit(f"No existe: {input_path}")

    data = json.loads(input_path.read_text())
    # Aceptar lista directa o {projects: [...]}
    projects = data if isinstance(data, list) else (data.get("projects") or data.get("data") or [])
    print(f"✓ Leídos {len(projects)} proyectos de {input_path.name}")

    if args.org:
        before = len(projects)
        projects = filter_by_org(projects, args.org)
        print(f"  Filtro '{args.org}': {before} → {len(projects)}")

    if args.limit:
        projects = projects[:args.limit]

    if not projects:
        print("✗ Nada que importar.")
        return

    if args.dry_run:
        print("\n(dry-run, no escribo a bc-api)")
        for p in projects[:20]:
            org = (p.get("organization") or {}).get("name") if isinstance(p.get("organization"), dict) else p.get("organization")
            print(f"  · {p.get('name')} [{org}] (id={p.get('id')}) · {len(p.get('units') or [])} unidades")
        return

    password = Path(args.bcapi_pass_file).expanduser().read_text().strip()
    token = bcapi_login(args.bcapi_url, args.bcapi_email, password)
    print(f"\n✓ Logueado a bc-api: {args.bcapi_url}")

    results = []
    for i, jb in enumerate(projects, 1):
        name = jb.get("name", "?")
        print(f"\n[{i}/{len(projects)}] {name}")
        try:
            payload = to_bcapi_payload(jb)
            units = units_to_payloads(jb)
            r = bcapi_upsert(args.bcapi_url, token, payload, units)
            results.append({"name": name, "status": "ok", **r})
            print(f"  ✓ {r['project_id']} (+{r['units_inserted']}/{r['units_total']} unidades)")
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)})
            print(f"  ✗ Error: {e}")
        time.sleep(0.2)  # ritmo respetuoso al bc-api

    ok = sum(1 for r in results if r.get("status") == "ok")
    err = len(results) - ok
    total_u = sum(r.get("units_inserted", 0) for r in results if r.get("status") == "ok")
    print(f"\n{'='*60}")
    print(f"Total: {ok} ok · {err} errores · {total_u} unidades importadas")
    print(f"{'='*60}")

    out_path = input_path.parent / f"{input_path.stem}_result.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nDetalle en: {out_path}")


if __name__ == "__main__":
    main()
