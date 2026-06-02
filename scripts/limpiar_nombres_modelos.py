"""
limpiar_nombres_modelos.py — Normaliza nombres de modelos y unidades.

Patrón JB: "1D1B - 1003 - TER - Terrazo" → nombre comercial real "1D1B".
Cuando el nombre tiene 3+ guiones " - ", tomar solo el primer segmento.

Aplica a:
  - extra.modelos[i].nombre
  - extra.modelos_dom[i].nombre  (para retro-compat)
  - unidades[i].modelo (para mantener la relación)

Reporta cuántos modelos+unidades quedaron huérfanos (unidad.modelo no existe en modelos).
"""
import os, httpx, re
from collections import Counter

jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)


def clean_nombre(s: str) -> str:
    """Si tiene patrón 'X - número - X - X' (3+ guiones), tomar primer segmento.
    Si no, dejar igual (modelos tipo 'L17_3al9' sin guiones quedan).
    """
    if not s: return s
    parts = [p.strip() for p in s.split(" - ")]
    # Detección: 4+ partes Y la 2da parece código numérico
    if len(parts) >= 4 and re.match(r'^\d+$', parts[1] or ''):
        return parts[0]
    return s


def main():
    listing = cli.get("/proyectos").json()
    print(f"Total proyectos: {len(listing)}\n")

    cambios_total = {"proyectos_actualizados": 0, "modelos_limpios": 0, "unidades_limpiadas": 0, "huerfanas": 0}
    detalle_huerfanas = []

    for p in listing:
        pid = p.get("id")
        if not pid: continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception:
            continue

        extra = full.get("extra") or {}
        modelos = extra.get("modelos") or []
        modelos_dom = extra.get("modelos_dom") or []
        unidades = full.get("unidades") or []
        nombre_proy = full.get("nombre", "")[:30]

        # 1) Limpiar modelos
        cambios_mod = 0
        rename_map = {}  # nombre_viejo → nombre_nuevo
        new_modelos = []
        for m in modelos if isinstance(modelos, list) else []:
            if not isinstance(m, dict): new_modelos.append(m); continue
            old = m.get("nombre") or ""
            new = clean_nombre(old)
            if new != old:
                rename_map[old] = new
                cambios_mod += 1
            new_modelos.append({**m, "nombre": new})
        new_modelos_dom = []
        for m in modelos_dom if isinstance(modelos_dom, list) else []:
            if not isinstance(m, dict): new_modelos_dom.append(m); continue
            old = m.get("nombre") or ""
            new = clean_nombre(old)
            if new != old and old not in rename_map:
                rename_map[old] = new
            new_modelos_dom.append({**m, "nombre": new})

        # 2) Validar/limpiar unidades.modelo
        modelo_names = {(m.get("nombre") or "").strip() for m in new_modelos if isinstance(m, dict) and m.get("nombre")}
        unidades_a_actualizar = []
        huerfanas_proj = 0
        for u in unidades:
            old_m = u.get("modelo") or ""
            # Aplicar renombre directo
            new_m = rename_map.get(old_m, old_m)
            # Si aún tiene formato largo, limpiarlo igual
            new_m_2 = clean_nombre(new_m)
            if new_m_2 != new_m: new_m = new_m_2
            # Si quedó huérfana, registrar
            if new_m and new_m not in modelo_names:
                huerfanas_proj += 1
            if new_m != old_m:
                unidades_a_actualizar.append({"id": u.get("id"), "old": old_m, "new": new_m, "u": u})

        # 3) Si hay cambios, PUT al proyecto + actualizar cada unidad
        if cambios_mod == 0 and not unidades_a_actualizar and huerfanas_proj == 0:
            continue

        # PUT proyecto con extra.modelos y extra.modelos_dom limpios
        new_extra = {**extra, "modelos": new_modelos, "modelos_dom": new_modelos_dom}
        body = {k: full[k] for k in full if k not in ("imagenes", "documentos", "unidades", "created_at", "updated_at")}
        body["extra"] = new_extra
        if cambios_mod > 0:
            try:
                r = cli.put(f"/proyectos/{pid}", json=body)
                if r.status_code not in (200, 201):
                    print(f"  ✗ PUT proyecto {pid}: HTTP {r.status_code} {r.text[:80]}")
                    continue
            except Exception as e:
                print(f"  ✗ PUT proyecto {pid}: {e}"); continue

        # PUT cada unidad
        unidades_ok = 0
        for upd in unidades_a_actualizar:
            u = upd["u"]
            body_u = {k: u.get(k) for k in ("numero","modelo","tipologia","tipo","orientacion","sup_total","sup_interior","sup_terraza","sup_logia","sup_jardin","precio_lista_uf","precio_final_uf","descuento_pct","bono_pie_pct","estac_flag","bodega_flag","pack_flag","disponible") if u.get(k) is not None}
            body_u["modelo"] = upd["new"]
            body_u["descuento_pct"] = u.get("descuento_pct") or 0
            body_u["bono_pie_pct"] = u.get("bono_pie_pct") or 0
            try:
                r = cli.put(f"/proyectos/{pid}/unidades/{upd['id']}", json=body_u)
                if r.status_code in (200, 201):
                    unidades_ok += 1
            except Exception: pass

        cambios_total["proyectos_actualizados"] += 1
        cambios_total["modelos_limpios"] += cambios_mod
        cambios_total["unidades_limpiadas"] += unidades_ok
        cambios_total["huerfanas"] += huerfanas_proj
        if huerfanas_proj:
            detalle_huerfanas.append((pid, nombre_proy, huerfanas_proj, len(unidades)))

        flag = f" · ⚠ {huerfanas_proj} huérfanas" if huerfanas_proj else ""
        print(f"  ✓ {pid[:30]:30s} {nombre_proy:30s} M:{cambios_mod} U:{unidades_ok}{flag}")

    print(f"\n=== RESUMEN ===")
    print(f"Proyectos actualizados: {cambios_total['proyectos_actualizados']}")
    print(f"Nombres de modelo limpiados: {cambios_total['modelos_limpios']}")
    print(f"Unidades con modelo renombrado: {cambios_total['unidades_limpiadas']}")
    print(f"Unidades huérfanas (modelo no existe): {cambios_total['huerfanas']}")
    if detalle_huerfanas:
        print(f"\n=== Proyectos con huérfanas ({len(detalle_huerfanas)}) ===")
        for pid, n, h, t in detalle_huerfanas:
            print(f"  {pid[:25]:25s} {n:30s}: {h}/{t} huérfanas")


if __name__ == "__main__":
    main()
