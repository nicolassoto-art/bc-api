"""Geocodificar masivamente proyectos sin GPS usando Nominatim (OpenStreetMap).

83 de 84 proyectos en bc-api tienen gps_lat/gps_lon vacíos. Resultado: el mapa
del catálogo (y de la ficha) está casi vacío. Este script intenta resolver
dirección+comuna+región a coordenadas usando la API pública de Nominatim
(gratis pero con rate limit estricto de 1 req/seg).

Uso:
    python -m scripts.geocode_proyectos --dry-run    # solo muestra qué resolvería
    python -m scripts.geocode_proyectos --apply      # actualiza BD (1 req/seg)
    python -m scripts.geocode_proyectos --apply --limit 20  # solo los primeros 20

Política de respeto a Nominatim:
- Header User-Agent identificable (requerido)
- Pausa 1.1s entre requests
- countrycodes=cl (Chile)
- Reintento por proyecto si falla (1 vez)
"""
from __future__ import annotations
import argparse
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime

from app.db import SessionLocal
from app.models import Proyecto


NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "BigCapital-Geocoder/1.0 (nicolas@bigcapital.cl)"
PAUSE_SEC = 1.1  # respetar 1 req/s de la política Nominatim


def geocode(direccion: str, comuna: str | None, region: str | None) -> tuple[float, float] | None:
    """Devuelve (lat, lon) o None si no resuelve."""
    # Construir query: dir + comuna + región + Chile.
    partes = [direccion]
    if comuna and comuna.lower() not in direccion.lower():
        partes.append(comuna)
    if region and region.lower() not in (direccion or "").lower():
        partes.append(region)
    partes.append("Chile")
    q = ", ".join(p for p in partes if p)
    params = urllib.parse.urlencode({
        "q": q, "format": "json", "limit": 1, "countrycodes": "cl"
    })
    url = f"{NOMINATIM}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                # Validar que esté dentro de Chile (sanity: lat -56..-17, lon -76..-66)
                if -56 < lat < -17 and -76 < lon < -66:
                    return lat, lon
    except Exception as e:
        print(f"    error nominatim: {e}")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=999, help="Máximo a procesar")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # Candidatos: sin GPS válido (None o cerca de 0) + con dirección o comuna
        candidatos = []
        for p in db.query(Proyecto).all():
            tiene_gps = (p.gps_lat is not None and p.gps_lon is not None
                         and abs(p.gps_lat) > 0.1 and abs(p.gps_lon) > 0.1)
            if tiene_gps:
                continue
            if not (p.direccion or p.comuna):
                continue
            candidatos.append(p)

        candidatos = candidatos[: args.limit]
        print(f"\nCandidatos a geocodificar: {len(candidatos)}\n")

        if args.dry_run:
            for p in candidatos[:20]:
                q = ", ".join(filter(None, [p.direccion, p.comuna, p.region, "Chile"]))
                print(f"  {p.id[:22]:22} · {p.nombre[:30]:30} → query: '{q}'")
            if len(candidatos) > 20:
                print(f"  ...y {len(candidatos) - 20} más")
            print("\n(dry-run — sin cambios. Re-correr con --apply.)")
            return

        # --apply: real
        ok, fail = 0, 0
        for i, p in enumerate(candidatos, 1):
            q = ", ".join(filter(None, [p.direccion, p.comuna, p.region]))
            print(f"[{i}/{len(candidatos)}] {p.nombre[:35]:35} — query: '{q[:50]}'", end="", flush=True)
            result = geocode(p.direccion or "", p.comuna, p.region)
            if result:
                p.gps_lat, p.gps_lon = result
                p.updated_at = datetime.utcnow()
                db.commit()
                ok += 1
                print(f" ✓ {result[0]:.5f}, {result[1]:.5f}")
            else:
                fail += 1
                print(f" ✗ sin match")
            time.sleep(PAUSE_SEC)  # respetar rate limit Nominatim

        print(f"\nResultado: ✓ {ok} resueltos · ✗ {fail} sin match")
    finally:
        db.close()


if __name__ == "__main__":
    main()
