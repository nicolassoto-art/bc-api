"""
fix_huerfanas_modelos.py — Para cada unidad huérfana (modelo no existe en
extra.modelos[]), crea un modelo placeholder con ese nombre.

Garantiza la relación 1:1 (unidad → modelo) en TODOS los proyectos.

Causa raíz: JB usa códigos cortos en la columna Modelo de Unidades (B1, C,
D2A, 918, etc.) que NO coinciden con los nombres de los modelos definidos en
la tab Modelos (1D1B, 2D2B, etc.). Los placeholder se enriquecen con
dormitorios/baños derivados de la tipología si está disponible.
"""
import os, httpx, re
from collections import Counter

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)


def parse_tipologia(t: str) -> tuple[int|None, int|None]:
    """1D-1B → (1,1); 2D2B → (2,2); 3D-2B(5) → (3,2)."""
    if not t: return (None, None)
    m = re.search(r'(\d+)\s*D[^\d]*(\d+)\s*B', t.upper())
    if m: return (int(m.group(1)), int(m.group(2)))
    return (None, None)


def main():
    listing = cli.get("/proyectos").json()
    total_creados = 0
    total_proyectos = 0
    detalle = []

    for p in listing:
        pid = p.get("id")
        if not pid: continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception: continue

        extra = full.get("extra") or {}
        modelos = extra.get("modelos") or []
        unidades = full.get("unidades") or []
        if not isinstance(modelos, list): modelos = []
        if not unidades: continue

        existing_names = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict) and m.get("nombre")}

        # Detectar huérfanas + agrupar por nombre con tipología más común
        huerfanos = Counter()  # nombre → cnt
        huerfanos_tip = {}  # nombre → tipologia más común
        for u in unidades:
            mn = (u.get("modelo") or "").strip()
            if not mn or mn in existing_names: continue
            huerfanos[mn] += 1
            if mn not in huerfanos_tip and u.get("tipologia"):
                huerfanos_tip[mn] = u.get("tipologia")

        if not huerfanos: continue

        # Crear placeholder para cada nombre huérfano
        new_modelos = list(modelos)
        nombre_proy = full.get("nombre","")[:30]
        for nom, cnt in huerfanos.items():
            tip = huerfanos_tip.get(nom, "")
            dorm, banos = parse_tipologia(tip)
            new_modelos.append({
                "id": f"auto-{re.sub(r'[^A-Za-z0-9]+', '-', nom.lower())[:20]}",
                "nombre": nom,
                "dormitorios": str(dorm) if dorm else "",
                "banos": str(banos) if banos else "",
                "cotiza_bodega": "Opcional",
                "cotiza_estac": "Opcional",
                "cotiza_pack": "Nunca",
                "planta_url": "",
                "_auto_generated": True,
                "_unidades_count": cnt,
            })
            total_creados += 1

        # PUT proyecto con nuevos modelos
        body = {k: full[k] for k in full if k not in ("imagenes","documentos","unidades","created_at","updated_at")}
        body["extra"] = {**extra, "modelos": new_modelos}
        try:
            r = cli.put(f"/proyectos/{pid}", json=body)
            if r.status_code in (200, 201):
                total_proyectos += 1
                detalle.append((pid, nombre_proy, len(huerfanos), sum(huerfanos.values())))
                print(f"  ✓ {pid[:30]:30s} {nombre_proy:30s} +{len(huerfanos)} placeholders ({sum(huerfanos.values())} unidades vinculadas)")
            else:
                print(f"  ✗ {pid[:30]:30s} HTTP {r.status_code} {r.text[:80]}")
        except Exception as e:
            print(f"  ✗ {pid[:30]:30s} {e}")

    print(f"\n=== RESUMEN ===")
    print(f"Proyectos actualizados: {total_proyectos}")
    print(f"Placeholders de modelo creados: {total_creados}")
    print(f"\nDetalle:")
    for pid, n, m_cnt, u_cnt in detalle:
        print(f"  {pid[:25]:25s} {n:30s} +{m_cnt:>3d} modelos · cubre {u_cnt:>4d} unidades")


if __name__ == "__main__":
    main()
