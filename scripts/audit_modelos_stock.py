"""
audit_modelos_stock.py — Auditoría profunda de unidades + modelos.

Inspecciona cada proyecto y revisa:
  - Modelos: nombre, planta_url, dormitorios, baños, cotiza_X
  - Unidades: numero, modelo, tipologia, sup_total, precio, descuento, disponible
  - Cross-check: cada u.modelo debe existir en modelos[].nombre
  - Detección: duplicados de numero, unidades sin modelo asociado

Output:
  - audit_modelos_stock.csv (todas las métricas por proyecto)
  - AUDITORIA_MODELOS_STOCK.md (vista humana, agrupada)
"""
from __future__ import annotations
import csv
import os
import sys
from collections import Counter, defaultdict
import httpx


def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)

    r = cli.get("/proyectos")
    r.raise_for_status()
    listing = r.json()
    print(f"📚 Total proyectos en bc-api: {len(listing)}")

    rows: list[dict] = []
    md_lines: list[str] = []
    md_lines.append("# Auditoría profunda — Modelos y Stock")
    md_lines.append("")
    md_lines.append(f"Generado a partir de {len(listing)} proyectos.\n")
    md_lines.append("Por proyecto se reporta:")
    md_lines.append("- **M**: total modelos en `extra.modelos`")
    md_lines.append("- **U**: total unidades")
    md_lines.append("- **M.con-planta**: modelos con `planta_url` no vacío")
    md_lines.append("- **U.con-precio**: unidades con `precio_lista_uf > 0`")
    md_lines.append("- **U.con-sup**: unidades con `sup_total > 0`")
    md_lines.append("- **U.huérfanas**: unidades cuyo `modelo` no aparece en modelos")
    md_lines.append("- **U.dups**: pares duplicados de `numero`")
    md_lines.append("")

    # Stats agregados
    agg = {
        "total": 0, "M": 0, "U": 0,
        "M_planta_ok": 0, "M_planta_falta": 0,
        "U_precio_ok": 0, "U_precio_falta": 0,
        "U_sup_ok": 0, "U_sup_falta": 0,
        "U_huerfanas_total": 0,
        "U_dups_total": 0,
        "proyectos_con_huerfanas": 0,
        "proyectos_con_dups": 0,
        "proyectos_sin_modelos": 0,
        "proyectos_sin_unidades": 0,
        "proyectos_modelos_sin_planta_total": 0,
    }

    # Issues para listar al final
    sin_modelos = []
    sin_unidades = []
    con_huerfanas = []
    modelos_sin_planta_completos = []
    unidades_sin_precio = []

    for p in sorted(listing, key=lambda x: (x.get("inmobiliaria") or "", x.get("nombre") or "")):
        pid = p.get("id")
        if not pid:
            continue
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"  ✗ {pid}: {e}")
            continue
        agg["total"] += 1
        extra = full.get("extra") or {}
        modelos = extra.get("modelos") or extra.get("modelos_dom") or []
        if not isinstance(modelos, list):
            modelos = []
        unidades = full.get("unidades") or []
        nombre = full.get("nombre") or ""
        inmo = full.get("inmobiliaria") or ""
        jb_id = extra.get("jb_id") or ""

        M = len(modelos)
        U = len(unidades)
        agg["M"] += M
        agg["U"] += U

        M_planta_ok = sum(1 for m in modelos if isinstance(m, dict) and (m.get("planta_url") or m.get("plano_url")))
        M_planta_falta = M - M_planta_ok
        agg["M_planta_ok"] += M_planta_ok
        agg["M_planta_falta"] += M_planta_falta

        U_precio_ok = sum(1 for u in unidades if u.get("precio_lista_uf") and float(u.get("precio_lista_uf") or 0) > 0)
        U_precio_falta = U - U_precio_ok
        agg["U_precio_ok"] += U_precio_ok
        agg["U_precio_falta"] += U_precio_falta

        U_sup_ok = sum(1 for u in unidades if u.get("sup_total") and float(u.get("sup_total") or 0) > 0)
        U_sup_falta = U - U_sup_ok
        agg["U_sup_ok"] += U_sup_ok
        agg["U_sup_falta"] += U_sup_falta

        # Cross-check huérfanas
        modelo_names = set()
        for m in modelos:
            if isinstance(m, dict):
                n = (m.get("nombre") or m.get("name") or "").strip()
                if n:
                    modelo_names.add(n.lower())
        U_huerfanas = 0
        for u in unidades:
            um = (u.get("modelo") or "").strip().lower()
            if um and um not in modelo_names:
                U_huerfanas += 1
        agg["U_huerfanas_total"] += U_huerfanas
        if U_huerfanas:
            agg["proyectos_con_huerfanas"] += 1
            con_huerfanas.append({"jb_id": jb_id, "nombre": nombre, "huerfanas": U_huerfanas, "total": U})

        # Duplicados
        numeros = [str(u.get("numero") or "").strip() for u in unidades]
        dup_counter = Counter(n for n in numeros if n)
        U_dups = sum(c - 1 for c in dup_counter.values() if c > 1)
        agg["U_dups_total"] += U_dups
        if U_dups:
            agg["proyectos_con_dups"] += 1

        if M == 0 and jb_id:
            agg["proyectos_sin_modelos"] += 1
            sin_modelos.append({"jb_id": jb_id, "nombre": nombre, "inmo": inmo})
        if U == 0 and jb_id:
            agg["proyectos_sin_unidades"] += 1
            sin_unidades.append({"jb_id": jb_id, "nombre": nombre, "inmo": inmo, "M": M})

        if M > 0 and M_planta_ok == 0:
            agg["proyectos_modelos_sin_planta_total"] += 1
            modelos_sin_planta_completos.append({"jb_id": jb_id, "nombre": nombre, "M": M})

        if U > 0 and U_precio_ok == 0:
            unidades_sin_precio.append({"jb_id": jb_id, "nombre": nombre, "U": U})

        row = {
            "jb_id": jb_id,
            "id": pid,
            "inmobiliaria": inmo,
            "nombre": nombre,
            "M": M, "M_planta_ok": M_planta_ok, "M_planta_falta": M_planta_falta,
            "U": U, "U_precio_ok": U_precio_ok, "U_precio_falta": U_precio_falta,
            "U_sup_ok": U_sup_ok, "U_sup_falta": U_sup_falta,
            "U_huerfanas": U_huerfanas, "U_dups": U_dups,
        }
        rows.append(row)

    # CSV
    with open("audit_modelos_stock.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("📊 CSV: audit_modelos_stock.csv")

    # Markdown
    md_lines.append("## 📈 Estadísticas globales")
    md_lines.append("")
    md_lines.append(f"| Métrica | Valor |")
    md_lines.append(f"|---|---|")
    md_lines.append(f"| Proyectos auditados | {agg['total']} |")
    md_lines.append(f"| Modelos totales | {agg['M']} |")
    md_lines.append(f"| Modelos con planta_url | {agg['M_planta_ok']} ({100*agg['M_planta_ok']//max(agg['M'],1)}%) |")
    md_lines.append(f"| Modelos sin planta_url | {agg['M_planta_falta']} ({100*agg['M_planta_falta']//max(agg['M'],1)}%) |")
    md_lines.append(f"| Unidades totales | {agg['U']:,} |")
    md_lines.append(f"| Unidades con precio | {agg['U_precio_ok']:,} ({100*agg['U_precio_ok']//max(agg['U'],1)}%) |")
    md_lines.append(f"| Unidades sin precio | {agg['U_precio_falta']:,} |")
    md_lines.append(f"| Unidades con sup_total | {agg['U_sup_ok']:,} ({100*agg['U_sup_ok']//max(agg['U'],1)}%) |")
    md_lines.append(f"| Unidades sin sup_total | {agg['U_sup_falta']:,} |")
    md_lines.append(f"| Unidades huérfanas (modelo no existe) | {agg['U_huerfanas_total']:,} |")
    md_lines.append(f"| Duplicados de numero | {agg['U_dups_total']:,} |")
    md_lines.append(f"| Proyectos sin modelos | {agg['proyectos_sin_modelos']} |")
    md_lines.append(f"| Proyectos sin unidades | {agg['proyectos_sin_unidades']} |")
    md_lines.append(f"| Proyectos con huérfanas | {agg['proyectos_con_huerfanas']} |")
    md_lines.append(f"| Proyectos con duplicados | {agg['proyectos_con_dups']} |")
    md_lines.append(f"| Proyectos con M sin planta | {agg['proyectos_modelos_sin_planta_total']} |")
    md_lines.append("")

    # Detalle por proyecto
    md_lines.append("## 📋 Detalle por proyecto")
    md_lines.append("")
    md_lines.append("| Inmo | Nombre | M | M.planta | U | U.precio | U.sup | U.huérf | U.dup |")
    md_lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        # Marcar warnings con emoji
        m_planta_str = f"{r['M_planta_ok']}/{r['M']}" if r['M'] > 0 else "—"
        u_precio_str = f"{r['U_precio_ok']}/{r['U']}" if r['U'] > 0 else "—"
        u_sup_str = f"{r['U_sup_ok']}/{r['U']}" if r['U'] > 0 else "—"
        u_huerf = f"⚠ {r['U_huerfanas']}" if r['U_huerfanas'] > 0 else "✓"
        u_dup = f"⚠ {r['U_dups']}" if r['U_dups'] > 0 else "✓"
        md_lines.append(
            f"| {(r['inmobiliaria'] or '?')[:20]} | {r['nombre'][:35]} | "
            f"{r['M']} | {m_planta_str} | {r['U']} | {u_precio_str} | {u_sup_str} | {u_huerf} | {u_dup} |"
        )
    md_lines.append("")

    # Listas de issues
    if sin_unidades:
        md_lines.append(f"## ⚠ Proyectos sin unidades ({len(sin_unidades)})")
        md_lines.append("")
        for s in sin_unidades:
            md_lines.append(f"- `{s['jb_id']}` **{s['nombre']}** ({s['inmo']}) — {s['M']} modelos pero 0 unidades")
        md_lines.append("")

    if sin_modelos:
        md_lines.append(f"## ⚠ Proyectos sin modelos ({len(sin_modelos)})")
        md_lines.append("")
        for s in sin_modelos:
            md_lines.append(f"- `{s['jb_id']}` **{s['nombre']}** ({s['inmo']})")
        md_lines.append("")

    if con_huerfanas:
        md_lines.append(f"## ⚠ Proyectos con unidades huérfanas ({len(con_huerfanas)})")
        md_lines.append("(unidad tiene `modelo` que no existe en `extra.modelos[].nombre`)")
        md_lines.append("")
        for c in con_huerfanas[:30]:
            md_lines.append(f"- `{c['jb_id']}` **{c['nombre']}** — {c['huerfanas']}/{c['total']} huérfanas")
        if len(con_huerfanas) > 30:
            md_lines.append(f"- ... y {len(con_huerfanas)-30} más")
        md_lines.append("")

    if modelos_sin_planta_completos:
        md_lines.append(f"## ⚠ Proyectos con modelos pero NINGUNO con planta_url ({len(modelos_sin_planta_completos)})")
        md_lines.append("")
        for m in modelos_sin_planta_completos:
            md_lines.append(f"- `{m['jb_id']}` **{m['nombre']}** — {m['M']} modelos sin planta")
        md_lines.append("")

    if unidades_sin_precio:
        md_lines.append(f"## ⚠ Proyectos con unidades pero NINGUNA con precio ({len(unidades_sin_precio)})")
        md_lines.append("")
        for u in unidades_sin_precio:
            md_lines.append(f"- `{u['jb_id']}` **{u['nombre']}** — {u['U']} unidades sin precio_lista_uf")
        md_lines.append("")

    with open("AUDITORIA_MODELOS_STOCK.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print("📄 Markdown: AUDITORIA_MODELOS_STOCK.md")

    print()
    print("="*60)
    print(f"  Proyectos:    {agg['total']}")
    print(f"  Modelos:      {agg['M']} ({100*agg['M_planta_ok']//max(agg['M'],1)}% con planta)")
    print(f"  Unidades:     {agg['U']:,} ({100*agg['U_precio_ok']//max(agg['U'],1)}% con precio)")
    print(f"  Sin modelos:  {agg['proyectos_sin_modelos']} proyectos")
    print(f"  Sin unidades: {agg['proyectos_sin_unidades']} proyectos")
    print(f"  Huérfanas:    {agg['U_huerfanas_total']} unidades en {agg['proyectos_con_huerfanas']} proyectos")
    print(f"  Duplicados:   {agg['U_dups_total']} en {agg['proyectos_con_dups']} proyectos")
    print("="*60)


if __name__ == "__main__":
    main()
