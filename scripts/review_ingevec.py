"""review_ingevec.py — Revisión consolidada de todos los proyectos Ingevec en bc-api."""
import os, httpx
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
INGEVEC = [
    ("los-lilenes",                    "LKubKmn0"),
    ("vespucio-capital",               "VgrH6Vg2"),
    ("brasil",                         "hvEkYVJq"),
    ("edificio-serrano-capital",       "AJBqsIIi"),
    ("nueva-esmeralda",                "LPJoCNEb"),
    ("vivaceta-864",                   "IaIQ9iTH"),
    ("don-ignacio",                    "is9kmud9"),
    ("coronel-godoy",                  "IDSvEAu8"),
    ("el-aromo",                       "sn2K1WIY"),
    ("vicu-a-mackenna-7589-etapa-i",   "OwPhi37z"),
    ("vicu-a-mackenna-7589-etapa-ii",  "v8tAVcOG"),
    ("matta",                          "CGFo7vDQ"),
    ("centenario-i",                   "86YW1rPt"),
    ("tocornal",                       "9MubHeQ8"),
    ("froilan-roa",                    "jfkJBrPQ"),
    ("vicu-a-mackenna-1796",           "1kvflc3m"),
    ("diagonal-paraguay-240",          "NeOU0rvU"),
    ("santa-rosa-250",                 "T8UuEf2r"),
    ("los-alerces",                    "WWMCny3E"),
    ("vima",                           "uRZc07TE"),
]


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    print(f"\n{'═'*130}")
    print(f"{'#':<3} {'bc-api id':<35} {'Inmob':<8} {'Comuna':<18} {'Mod(pl/uniq)':<14} {'Uds':<5} {'E/B/P':<13} {'Fotos':<6} {'Status'}")
    print("═" * 130)
    found = 0
    not_found = 0
    issues = []
    totals = {"uds": 0, "est": 0, "bod": 0, "pck": 0}
    for i, (pid, jb_id) in enumerate(INGEVEC, start=1):
        try:
            r = cli.get(f"/proyectos/{pid}")
            if r.status_code != 200:
                print(f"{i:<3} {pid:<35} ✗ NO ENCONTRADO ({r.status_code})")
                not_found += 1
                issues.append(f"{pid}: NO ENCONTRADO")
                continue
            p = r.json()
        except Exception as e:
            print(f"{i:<3} {pid:<35} ERR: {str(e)[:50]}")
            not_found += 1
            continue
        found += 1
        extra = p.get("extra") or {}
        modelos = extra.get("modelos") or []
        unidades = p.get("unidades") or []
        imgs = p.get("imagenes") or []
        estac = extra.get("estacionamientos_dom") or extra.get("estacionamientos") or []
        bod = extra.get("bodegas_dom") or extra.get("bodegas") or []
        packs = extra.get("packs_dom") or extra.get("packs") or []
        con_pl = sum(1 for m in modelos if m.get("planta_url"))
        pl_unicas = len({m.get("planta_url") for m in modelos if m.get("planta_url")})
        problemas = []
        if not p.get("foto_principal_url"): problemas.append("sin-foto")
        if not p.get("inmobiliaria") or p.get("inmobiliaria").lower() == "bigcapital": problemas.append("inmob-mal")
        # huérfanas
        mnames = {m.get("nombre") for m in modelos}
        huer = sum(1 for u in unidades if u.get("modelo") not in mnames)
        if huer: problemas.append(f"{huer}huer")
        if problemas: issues.append(f"{pid}: {','.join(problemas)}")
        status = "✓" if not problemas else "⚠ " + ",".join(problemas)
        totals["uds"] += len(unidades); totals["est"] += len(estac); totals["bod"] += len(bod); totals["pck"] += len(packs)
        mp = f"{len(modelos)}({con_pl}/{pl_unicas})"
        print(f"{i:<3} {pid[:34]:<35} {(p.get('inmobiliaria') or '?')[:7]:<8} "
              f"{(p.get('comuna') or '?')[:17]:<18} {mp:<14} {len(unidades):<5} "
              f"{len(estac)}/{len(bod)}/{len(packs):<8} {len(imgs):<6} {status}")
    print("═" * 130)
    print(f"\nRESUMEN INGEVEC EN STOCK LOCAL:")
    print(f"  Encontrados: {found}/{len(INGEVEC)}")
    print(f"  NO encontrados: {not_found}")
    print(f"  Totales acumulados: uds={totals['uds']} estac={totals['est']} bodegas={totals['bod']} packs={totals['pck']}")
    if issues:
        print(f"\n  ⚠ Issues ({len(issues)}):")
        for x in issues: print(f"    • {x}")
    else:
        print(f"\n  ✓ Sin issues bloqueantes.")


if __name__ == "__main__":
    main()
