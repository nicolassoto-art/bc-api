"""review_issues.py — Auditoría de proyectos importados v2. Reporta lo que requiere atención."""
import os, httpx, re
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
ENUMS_CRUDOS = {"voluntary","required","all","onlyApartment","downPayment","expense",
                "projectDeveloper","broker","yesAuthorized","yesPromise","inProcess","Corriente","shared"}


def main():
    jwt = os.environ["BC_API_JWT"]
    if not jwt:
        raise SystemExit("BC_API_JWT vacío — login falló")
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=60)
    r = cli.get("/proyectos")
    if r.status_code != 200:
        raise SystemExit(f"GET /proyectos → {r.status_code}: {r.text[:200]}")
    lst = r.json()

    rows = []
    for p in lst:
        pid = p.get("id"); nombre = p.get("nombre") or ""
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception:
            continue
        extra = full.get("extra") or {}
        inmob = full.get("inmobiliaria") or ""
        modelos = extra.get("modelos") or []
        unidades = full.get("unidades") or []
        estac = extra.get("estacionamientos") or extra.get("estacionamientos_dom") or []
        bodegas = extra.get("bodegas") or extra.get("bodegas_dom") or []
        packs = extra.get("packs") or extra.get("packs_dom") or []
        warnings_extra = extra.get("_deptos_con_warning") or []

        # huérfanas / modelo no existe
        nombres_modelos = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
        huerfanas_vacio = sum(1 for u in unidades if not u.get("modelo"))
        huerfanas_inv = sum(1 for u in unidades if u.get("modelo") and u.get("modelo") not in nombres_modelos)
        # modelos sin planta
        sin_planta = sum(1 for m in modelos if isinstance(m, dict) and not (m.get("planta_url") or m.get("plano_url")))
        # enums crudos
        ficha_str = " ".join(str(full.get(k)) for k in ("tipo_pie","tipo_descuento","tipo_bono_pie","tipo_reserva",
                                                        "destino_reserva","acepta_cesion","permiso_construccion",
                                                        "tipo_cuenta","stock_type","solicita_preaprobacion") if full.get(k))
        enums_raw = [w for w in ENUMS_CRUDOS if w in ficha_str]

        problems = []
        if not inmob or inmob.strip() in ("", "BigCapital", "Sin asignar"):
            problems.append(f"inmob='{inmob}'")
        if huerfanas_vacio:
            problems.append(f"{huerfanas_vacio} uds sin modelo")
        if huerfanas_inv:
            problems.append(f"{huerfanas_inv} uds con modelo inválido")
        if warnings_extra:
            problems.append(f"{len(warnings_extra)} en _deptos_con_warning")
        if sin_planta and len(modelos) > 0:
            problems.append(f"{sin_planta}/{len(modelos)} modelos sin planta")
        if not unidades:
            problems.append("0 unidades")
        if not modelos:
            problems.append("0 modelos")
        if not estac and not bodegas and not packs:
            problems.append("sin estac/bod/pack")
        if enums_raw:
            problems.append(f"enums crudos: {','.join(enums_raw[:3])}")

        rows.append({
            "pid": pid, "nombre": nombre, "inmob": inmob,
            "uds": len(unidades), "mod": len(modelos), "spl": sin_planta,
            "e": len(estac), "b": len(bodegas), "p": len(packs),
            "warn": len(warnings_extra), "huv": huerfanas_vacio, "hui": huerfanas_inv,
            "problems": problems,
        })

    # Categorizar
    criticos = [r for r in rows if any("uds" in p or "0 modelos" in p or "inmob=" in p or "inválido" in p for p in r["problems"])]
    warnings = [r for r in rows if r["problems"] and r not in criticos]
    ok = [r for r in rows if not r["problems"]]

    print(f"\n{'═'*100}\n  AUDITORÍA bc-api · {len(rows)} proyectos totales\n{'═'*100}\n")

    print(f"🟢 SIN ISSUES ({len(ok)}):")
    for r in sorted(ok, key=lambda x: x["nombre"].lower()):
        print(f"   ✓ {r['inmob'][:14]:<14} {r['nombre'][:38]:<38} ({r['uds']}u/{r['mod']}m · {r['e']}/{r['b']}/{r['p']})")

    if criticos:
        print(f"\n🔴 CRÍTICOS — requieren acción ({len(criticos)}):")
        for r in sorted(criticos, key=lambda x: -len(x["problems"])):
            print(f"   ⚠ {r['inmob'][:14]:<14} {r['nombre'][:38]:<38} ({r['uds']}u/{r['mod']}m) → {'; '.join(r['problems'])}")

    if warnings:
        print(f"\n🟡 REVISAR ({len(warnings)}):")
        for r in sorted(warnings, key=lambda x: -len(x["problems"])):
            print(f"   • {r['inmob'][:14]:<14} {r['nombre'][:38]:<38} ({r['uds']}u/{r['mod']}m · {r['e']}/{r['b']}/{r['p']}) → {'; '.join(r['problems'])}")

    print(f"\n{'═'*100}")
    print(f"  RESUMEN: {len(ok)} OK · {len(warnings)} revisar · {len(criticos)} críticos")
    print(f"{'═'*100}")


if __name__ == "__main__":
    main()
