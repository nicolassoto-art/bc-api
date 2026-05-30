"""Lee extra.fisicos.unidades_totales + stock_type para los 5 sin detalle."""
import os, httpx

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

VACIOS = [
    ("jb-sffaxziq", "Vicuna Mackenna 1194"),
    ("jb-48t1iinf", "EDIFICIO CONEXION INDEPENDENCIA"),
    ("jb-t8uuef2r", "Santa Rosa 250"),
    ("jb-wwmcny3e", "Los Alerces"),
    ("jb-1kvflc3m", "Vicuna Mackenna 1796"),
]

for pid, nombre in VACIOS:
    try:
        p = cli.get(f"/proyectos/{pid}").json()
    except Exception as e:
        print(f"{pid}: error {e}")
        continue
    extra = p.get("extra") or {}
    fis = extra.get("fisicos") or {}
    print(f"\n=== {nombre} ({pid}) ===")
    print(f"  unidades_totales (extra.fisicos): {fis.get('unidades_totales')}")
    print(f"  estac_totales:    {fis.get('estacionamientos_totales')}")
    print(f"  bodegas_totales:  {fis.get('bodegas_totales')}")
    print(f"  stock_type:       {extra.get('stock_type')}")
    print(f"  unidades (detalle en bc-api): {len(p.get('unidades') or [])}")
    print(f"  modelos:          {len(extra.get('modelos') or extra.get('modelos_dom') or [])}")
    print(f"  top-level unidades_total/disp: {p.get('unidades_total')}/{p.get('unidades_disponibles')}")
