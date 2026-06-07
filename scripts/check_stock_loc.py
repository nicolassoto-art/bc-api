"""check_stock_loc.py — Inspecciona DÓNDE están los estac/bodegas/packs en cada proyecto."""
import os, json, httpx
BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = os.environ.get("PIDS","vistamar,etapa-2-portal-del-pinar,vista-llacol-n-torre-b,vista-llacolen-torre-a,cordillera-oriente-etapa-1").split(",")
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
for pid in PIDS:
    pid = pid.strip()
    p = cli.get(f"/proyectos/{pid}").json()
    extra = p.get("extra") or {}
    keys_extra = sorted(extra.keys())
    has_estac_dom = "estacionamientos_dom" in extra
    has_bod_dom = "bodegas_dom" in extra
    has_packs_dom = "packs_dom" in extra
    # top-level arrays?
    print(f"\n=== {pid} ===")
    print(f"  top-level estacionamientos: {type(p.get('estacionamientos')).__name__} ({len(p.get('estacionamientos') or [])} items)")
    print(f"  top-level bodegas:          {type(p.get('bodegas')).__name__} ({len(p.get('bodegas') or [])} items)")
    print(f"  top-level packs:            {type(p.get('packs')).__name__} ({len(p.get('packs') or [])} items)")
    print(f"  extra.estacionamientos_dom: {has_estac_dom} ({len(extra.get('estacionamientos_dom') or [])} items)")
    print(f"  extra.bodegas_dom:          {has_bod_dom} ({len(extra.get('bodegas_dom') or [])} items)")
    print(f"  extra.packs_dom:            {has_packs_dom} ({len(extra.get('packs_dom') or [])} items)")
    print(f"  extra._estac_dom?:          {'_estacionamientos_dom' in extra}")
    print(f"  extra._bodegas_dom?:        {'_bodegas_dom' in extra}")
    # alternativas
    alts = [k for k in extra if 'estac' in k.lower() or 'bodega' in k.lower() or 'pack' in k.lower()]
    if alts: print(f"  otras keys con 'estac/bodega/pack': {alts}")
    # ¿dom es vacío o falta?
    if has_estac_dom and not extra.get("estacionamientos_dom"):
        print(f"  ⚠ extra.estacionamientos_dom EXISTE pero está VACÍA")
