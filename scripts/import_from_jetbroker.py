"""Importa proyectos desde JetBroker usando una cookie de sesión del usuario.

Flujo:
  1. Lee cookie de `.jb_session` (formato: NAME=VALUE, una por línea)
  2. Llama POST https://api.jetbrokers.io/api/gallery/projects para listar
     proyectos (puede requerir organizationId o trae todo lo accesible)
  3. Filtra por organization (default: "Larraín Prieto" o el flag --org)
  4. Para cada proyecto: GET detalles, units, gallery
  5. POST a bc-api /proyectos (con bearer del admin de bc-api)
  6. Actualiza IMPORT_LOG.md

Uso:
    python scripts/import_from_jetbroker.py \\
        --org "Larraín Prieto" \\
        --bcapi-url https://bc-api.178-105-91-29.nip.io \\
        --bcapi-email nicolas.soto@bigcapital.cl \\
        --bcapi-pass-file ~/.bcapi-admin-pass \\
        --dry-run  # opcional, no escribe a la DB

    # En el VPS sería:
    sudo -u bcapi /opt/bc-api/.venv/bin/python /opt/bc-api/scripts/import_from_jetbroker.py \\
        --org "Larraín Prieto" \\
        --bcapi-url http://127.0.0.1:8011 \\
        --bcapi-email nicolas.soto@bigcapital.cl \\
        --bcapi-pass-file /root/.bcapi-admin-pass
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx


JB_BASE = "https://api.jetbrokers.io"


def parse_session(path: Path) -> dict[str, str]:
    """Lee archivo de sesión con líneas NAME=VALUE. Ignora comentarios y vacías."""
    if not path.exists():
        raise SystemExit(f"No existe el archivo de sesión: {path}")
    cookies = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        cookies[k.strip()] = v.strip()
    if not cookies:
        raise SystemExit(f"El archivo {path} no tiene cookies en formato NAME=VALUE")
    return cookies


def list_projects(client: httpx.Client) -> list[dict]:
    """Intenta listar todos los proyectos visibles a la sesión.
    JetBroker tiene varias variantes; probamos las más comunes."""
    # Variante 1: GET /api/projects (catálogo del broker)
    for url, method in [
        ("/api/projects", "GET"),
        ("/api/gallery/projects", "POST"),
        ("/api/v1/projects", "GET"),
        ("/api/catalog/projects", "GET"),
    ]:
        try:
            if method == "GET":
                r = client.get(JB_BASE + url, timeout=30)
            else:
                r = client.post(JB_BASE + url, json={}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                # Algunos APIs envuelven en {data: [...]} o {projects: [...]}
                if isinstance(data, list):
                    return data
                for k in ("data", "projects", "items", "results"):
                    if k in data and isinstance(data[k], list):
                        return data[k]
                print(f"  · {method} {url} → 200 pero formato desconocido: keys={list(data.keys())[:5]}")
            else:
                print(f"  · {method} {url} → HTTP {r.status_code}")
        except Exception as e:
            print(f"  · {method} {url} → error: {e}")
    raise SystemExit("No pude listar proyectos. Verificá que la cookie esté válida.")


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


def get_project_detail(client: httpx.Client, pid: str) -> dict:
    """Trae detalle del proyecto + units + gallery."""
    detail = {}
    # Detalle base
    r = client.get(f"{JB_BASE}/api/project/{pid}", timeout=30)
    if r.status_code == 200:
        detail["project"] = r.json()
    # Units
    r = client.get(f"{JB_BASE}/api/project/{pid}/units", timeout=30)
    if r.status_code == 200:
        detail["units"] = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
    # Gallery (si lista; cada item se descarga después)
    org_id_in_proj = detail.get("project", {}).get("organization", {}).get("id") or "uv13koru"
    r = client.get(f"{JB_BASE}/api/gallery/details/{org_id_in_proj}/{pid}", timeout=30)
    if r.status_code == 200:
        detail["gallery"] = r.json()
    return detail


def to_bcapi_payload(jb_project: dict, jb_detail: dict) -> dict:
    """Transforma proyecto JB → payload bc-api."""
    p = jb_detail.get("project", jb_project)
    org = p.get("organization") or {}
    org_name = org.get("name") if isinstance(org, dict) else org

    pid = p.get("id") or jb_project.get("id")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (p.get("name") or pid).lower()).strip("-")
    if not slug:
        slug = "proy-" + pid

    extra = {}
    for k in ("locality", "address", "rooms", "bathrooms", "amenities",
              "deliveryDate", "modality", "stage", "downpaymentPercentage"):
        if k in p:
            extra[k] = p[k]

    return {
        "id": slug,
        "nombre": p.get("name") or "Sin nombre",
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
        "foto_principal_url": p.get("mainImage") or (p.get("images", [{}])[0].get("url") if p.get("images") else None),
        "external_url": f"https://app.jetbrokers.io/projects/{pid}",
        "extra": extra,
    }


def units_to_payloads(jb_detail: dict) -> list[dict]:
    out = []
    for u in (jb_detail.get("units") or []):
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


def bcapi_upsert_project(url: str, token: str, payload: dict, units: list[dict]) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    # PUT → si 404 caemos a POST
    pid = payload["id"]
    r = httpx.put(f"{url}/proyectos/{pid}", json=payload, headers=h, timeout=30)
    if r.status_code == 404:
        r = httpx.post(f"{url}/proyectos", json=payload, headers=h, timeout=30)
    r.raise_for_status()
    # Upsert unidades una por una (la API tiene POST individual)
    inserted_u = 0
    for u in units:
        r = httpx.post(f"{url}/proyectos/{pid}/unidades", json=u, headers=h, timeout=20)
        if r.status_code in (201, 200):
            inserted_u += 1
        elif r.status_code == 409:
            pass  # ya existe
        else:
            print(f"    ⚠ unidad {u['numero']}: HTTP {r.status_code} {r.text[:100]}")
    return {"project_id": pid, "units_inserted": inserted_u, "units_total": len(units)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=".jb_session", help="Archivo con cookies de JB")
    ap.add_argument("--org", default="Larraín Prieto", help="Inmobiliaria a importar (fuzzy match)")
    ap.add_argument("--bcapi-url", required=True)
    ap.add_argument("--bcapi-email", required=True)
    ap.add_argument("--bcapi-pass-file", required=True, help="Archivo con el password del admin bc-api")
    ap.add_argument("--dry-run", action="store_true", help="No escribe a bc-api, solo lista")
    ap.add_argument("--limit", type=int, default=0, help="Máx proyectos a importar (0=todos)")
    args = ap.parse_args()

    session_file = Path(args.session).expanduser()
    cookies = parse_session(session_file)
    print(f"✓ Cookies cargadas: {list(cookies.keys())}")

    with httpx.Client(cookies=cookies, headers={"User-Agent": "bc-api-importer/1.0"}) as jb:
        print(f"\nListando proyectos visibles en JetBroker...")
        projects = list_projects(jb)
        print(f"✓ {len(projects)} proyectos totales accesibles")

        orgs = {}
        for p in projects:
            o = p.get("organization") or {}
            n = (o.get("name") if isinstance(o, dict) else o) or "—"
            orgs.setdefault(n, 0)
            orgs[n] += 1
        print(f"\nOrganizations encontradas:")
        for n, c in sorted(orgs.items(), key=lambda x: -x[1])[:20]:
            print(f"  {c:4d}  {n}")

        matched = filter_by_org(projects, args.org)
        print(f"\nMatch '{args.org}': {len(matched)} proyectos")
        if args.limit:
            matched = matched[:args.limit]

        if not matched:
            print("✗ Nada que importar.")
            return

        if args.dry_run:
            print("\n(dry-run, no escribo a bc-api)")
            for p in matched[:10]:
                print(f"  · {p.get('name')} (id={p.get('id')})")
            return

        # Auth bc-api
        password = Path(args.bcapi_pass_file).expanduser().read_text().strip()
        token = bcapi_login(args.bcapi_url, args.bcapi_email, password)
        print(f"\n✓ Logueado a bc-api ({args.bcapi_url})")

        results = []
        for i, jb_proj in enumerate(matched, 1):
            pid = jb_proj.get("id")
            name = jb_proj.get("name")
            print(f"\n[{i}/{len(matched)}] {name} ({pid})")
            try:
                detail = get_project_detail(jb, pid)
                payload = to_bcapi_payload(jb_proj, detail)
                units = units_to_payloads(detail)
                print(f"  · {len(units)} unidades")
                r = bcapi_upsert_project(args.bcapi_url, token, payload, units)
                results.append({"name": name, "status": "ok", **r})
                print(f"  ✓ Importado {r['project_id']} (+{r['units_inserted']} unidades)")
            except Exception as e:
                results.append({"name": name, "status": "error", "error": str(e)})
                print(f"  ✗ Error: {e}")
            time.sleep(0.3)  # rate-limit friendly

        # Resumen
        ok = sum(1 for r in results if r.get("status") == "ok")
        err = len(results) - ok
        total_u = sum(r.get("units_inserted", 0) for r in results if r.get("status") == "ok")
        print(f"\n{'='*60}")
        print(f"Total: {ok} ok · {err} errores · {total_u} unidades importadas")
        print(f"{'='*60}")

        # Volcar resultado para el log
        out_path = Path("import_result.json")
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nDetalle en: {out_path.resolve()}")


if __name__ == "__main__":
    main()
