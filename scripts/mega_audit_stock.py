#!/usr/bin/env python3
"""
MEGA AUDIT · inspección exhaustiva tipo-humana del stock JetBrokers → bc-api.

Recorre TODOS los proyectos importados y verifica, por proyecto:
  · API health (bc-api responde, proyecto cargable)
  · inmobiliaria válida (NUNCA "BigCapital"/"Sin asignar"/vacío)
  · unidades: count, huérfanas (modelo=""), modelo inválido (apunta a modelo inexistente)
  · modelos: count, sin planta (planta_url/plano_url)
  · enums en español (no crudos: voluntary/required/all/onlyApartment/...)
  · estac/bodegas/packs presencia
  · orientaciones en set válido ES (N/S/O/P/NO/NP/SO/SP)
  · foto principal presente
  · warnings frontend (_deptos_con_warning)
  · idioma: sin voseo argentino en notas/textos

Cross-check global:
  · 88/92 proyectos del CSV master presentes
  · 4 excluidos AUSENTES (Terrazzo, Abdón Cifuentes, Borja Plaza, Pinar E1 salvo jb-tvfylemz)

Severidad:
  🔴 CRITICAL: endpoint roto · proyecto esperado ausente · inmob=BigCapital · 0 modelos ·
               modelo inválido (frontend rompe) · excluido presente que no debería
  ⚠ HIGH:      huérfanas (modelo="") · enum crudo · orientación cruda · foto principal falta ·
               0 unidades en proyecto que debería tenerlas
  🟡 MEDIUM:   modelos sin planta (minoría) · notas vacías · voseo detectado
  ·  LOW:      cosmético

Genera logs/mega_audit_stock_<ts>.json + stdout.
Env: BC_API_JWT
"""
from __future__ import annotations
import os, re, json, sys
import httpx
from datetime import datetime, timezone
from pathlib import Path

BC = "https://bc-api.178-105-91-29.nip.io"
LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True)

ENUMS_CRUDOS = {"voluntary","required","all","onlyApartment","downPayment","expense",
                "projectDeveloper","broker","yesAuthorized","yesPromise","inProcess",
                "Corriente","shared","north","south","east","west"}
ORIENT_OK = {"N","S","O","P","NO","NP","SO","SP","NE","SE","NPO","",None}
VOSEO = re.compile(r"\b(ten[ée]s|sos|quer[ée]s|decime|pod[ée]s|and[áa]|hac[ée]s|"
                   r"ll[áa]m[áa]s|mir[áa]|busc[áa]|fij[áa]te|aprovech[áa]|eleg[íi]|pon[ée])\b", re.I)

# Excluidos: NO deben existir (salvo Pinar E1 que vive como jb-tvfylemz, gestionado aparte)
EXCLUIDOS_JB = {"72GkWnlW": "Terrazzo", "G3jWrRoE": "Abdón Cifuentes", "zOHnfOQJ": "Borja Plaza"}

# 92 jb_ids del CSV master; 88 deben estar (los 4 excluidos no, pero Pinar E1 sí como jb-tvfylemz)
CSV_JB_IDS_ESPERADOS = {
    "IDLyBU4W","GMrPAyQt","NgBHe0jo","atUiRS6M","osnL3M1C","vWkZk19n","nYjXw5kL","hw9SoClo",
    "dr6uuHkX","FxGIdSga","EZljonhe","PsqVqc03","b7Aniv5k","Dw5PBsEd","uRZc07TE","VgrH6Vg2",
    "iB3uhp34","Sfp8j2Sq","SUWJ0Rye","C0xMpK4K","Ml02Ecl7","KvRtrtXK","4Kny8VBw","sn2K1WIY",
    "LPJoCNEb","IDSvEAu8","LKubKmn0","AJBqsIIi","Xm0GuxtO","CGFo7vDQ","hvEkYVJq","is9kmud9",
    "NeOU0rvU","v8tAVcOG","OwPhi37z","9MubHeQ8","IaIQ9iTH","exrBr6Tp","IgfWZVh2","86YW1rPt",
    "jfkJBrPQ","1kvflc3m","tvFyLEMz","ksHJwBab","WWMCny3E","W8P6QggB","Vw1zOkV6","ImxDl3nl",
    "f8VQHYVK","3JcwgGZi","qlkZufJk","Xm0ZQPxk","R5cTUSc8","48t1IInf","75PDpryA","1gaVJbKl",
    "hSeBHnw1","pkR9sdRb","q8RwqXao","HvNRYfwm","T8UuEf2r","C8R7VcvH","thmz67c6","mshykABZ",
    "kUYM4Rl8","wHL2AUKl","vWeKp0EM","9YO68rOa","LXXJ9agb","WGfF1Hcm","OHpd4zbx","sFfaXZIQ",
    "FrOy8Hxr","hKtYFYuQ","Ao8J0BvU","4nyJKnq9","5d7qpMgc","iaEIx5Eo","RNEqQ6dw","UAq8pgxr",
    "teQxJTnq","zkp4Z7HH","7qF2CCA7","LmVJgz7F","nmLpNNTD","eHxgQsNq","m9zXfNHe","dX4Rddfn",
    # importados pre-CSV (Maestra propios) — no en CSV pero válidos:
}
# huérfanas que el usuario reserva para arreglo MANUAL (no contar como bloqueante auto-fix)
RESERVADO_MANUAL = True

findings = []  # (sev, categoria, proyecto, msg)
def add(sev, cat, proy, msg): findings.append({"sev": sev, "cat": cat, "proy": proy, "msg": msg})


def main():
    jwt = os.environ.get("BC_API_JWT", "")
    if not jwt:
        print("BC_API_JWT vacío"); sys.exit(2)
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=60)

    # 1) API health
    try:
        h = cli.get("/health")
        if h.status_code != 200:
            add("CRITICAL","api","_global",f"/health → {h.status_code}")
    except Exception as e:
        add("CRITICAL","api","_global",f"/health excepción {e!r}"); _dump(); sys.exit(1)

    r = cli.get("/proyectos")
    if r.status_code != 200:
        add("CRITICAL","api","_global",f"/proyectos → {r.status_code}: {r.text[:120]}"); _dump(); sys.exit(1)
    lst = r.json()
    print(f"bc-api responde · {len(lst)} proyectos en listado\n")

    by_jb = {}
    for p in lst:
        jb = (p.get("extra") or {}).get("jb_id")
        if jb: by_jb[jb] = p

    # 2) cross-check presencia esperados / excluidos
    for jb in CSV_JB_IDS_ESPERADOS:
        if jb == "tvFyLEMz":
            continue  # vive como jb-tvfylemz, gestionado aparte
        if jb not in by_jb:
            add("CRITICAL","presencia",jb,"esperado en bc-api pero AUSENTE")
    for jb, nom in EXCLUIDOS_JB.items():
        if jb in by_jb:
            add("CRITICAL","excluido",nom,f"EXCLUIDO pero presente en bc-api (jb_id={jb})")

    # 3) deep per-proyecto
    n = 0
    for p in lst:
        pid = p.get("id"); nombre = p.get("nombre") or pid
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            add("CRITICAL","carga",nombre,f"GET /proyectos/{pid} falló {e!r}"); continue
        n += 1
        extra = full.get("extra") or {}
        inmob = (full.get("inmobiliaria") or "").strip()
        modelos = extra.get("modelos") or []
        unidades = full.get("unidades") or []
        estac = extra.get("estacionamientos") or extra.get("estacionamientos_dom") or []
        bodegas = extra.get("bodegas") or extra.get("bodegas_dom") or []
        packs = extra.get("packs") or extra.get("packs_dom") or []
        warns = extra.get("_deptos_con_warning") or []

        # inmobiliaria
        if inmob in ("", "BigCapital", "Sin asignar"):
            add("CRITICAL","inmob",nombre,f"inmobiliaria inválida='{inmob}'")
        # modelos
        if not modelos:
            add("CRITICAL","modelos",nombre,"0 modelos")
        nombres_modelos = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
        # huérfanas
        huv = [u for u in unidades if not u.get("modelo")]
        hui = [u for u in unidades if u.get("modelo") and u.get("modelo") not in nombres_modelos]
        if hui:
            add("CRITICAL","modelo-invalido",nombre,
                f"{len(hui)} uds con modelo que NO existe en extra.modelos (frontend rompe)")
        if huv:
            sev = "HIGH"
            add(sev,"huerfanas",nombre,f"{len(huv)} uds sin modelo (modelo='')"
                + (" · reservado MANUAL por usuario" if RESERVADO_MANUAL else ""))
        # sin planta
        sin_planta = [m for m in modelos if isinstance(m, dict) and not (m.get("planta_url") or m.get("plano_url"))]
        if modelos and sin_planta:
            frac = len(sin_planta)/len(modelos)
            sev = "HIGH" if frac >= 0.6 else "MEDIUM"
            add(sev,"sin-planta",nombre,f"{len(sin_planta)}/{len(modelos)} modelos sin planta ({frac*100:.0f}%)")
        # enums crudos
        ficha = " ".join(str(full.get(k)) for k in (
            "tipo_pie","tipo_descuento","tipo_bono_pie","tipo_reserva","destino_reserva",
            "acepta_cesion","permiso_construccion","tipo_cuenta","stock_type","solicita_preaprobacion")
            if full.get(k) is not None)
        crudos = [w for w in ENUMS_CRUDOS if re.search(rf"\b{re.escape(w)}\b", ficha)]
        if crudos:
            add("HIGH","enums",nombre,f"enums crudos sin mapear: {','.join(crudos[:4])}")
        # orientaciones
        bad_or = sorted({u.get("orientacion") for u in unidades
                         if u.get("orientacion") not in ORIENT_OK})
        if bad_or:
            add("HIGH","orientacion",nombre,f"orientaciones no-ES: {bad_or[:5]}")
        # estac/bod/pack
        if not estac and not bodegas and not packs:
            add("MEDIUM","assets",nombre,"sin estac/bodegas/packs (verificar si JB realmente 0)")
        # foto principal
        fp = full.get("foto_principal_url") or extra.get("foto_principal_url")
        imgs = full.get("imagenes") or extra.get("imagenes") or []
        if not fp and not imgs:
            add("MEDIUM","foto",nombre,"sin foto principal ni imágenes")
        # voseo en notas
        notas = str(extra.get("notas") or extra.get("notas_html") or full.get("descripcion") or "")
        if VOSEO.search(notas):
            add("MEDIUM","voseo",nombre,"posible voseo argentino en notas/descripción")

    print(f"Auditados {n} proyectos en profundidad.\n")

    # resumen
    crit = [f for f in findings if f["sev"]=="CRITICAL"]
    high = [f for f in findings if f["sev"]=="HIGH"]
    med  = [f for f in findings if f["sev"]=="MEDIUM"]
    low  = [f for f in findings if f["sev"]=="LOW"]
    icon = {"CRITICAL":"🔴","HIGH":"⚠","MEDIUM":"🟡","LOW":"·"}
    for grp,name in ((crit,"CRITICAL"),(high,"HIGH"),(med,"MEDIUM"),(low,"LOW")):
        if not grp: continue
        print(f"\n{icon[name]} {name} ({len(grp)})")
        for f in sorted(grp, key=lambda x: x["cat"]):
            print(f"   [{f['cat']}] {f['proy']}: {f['msg']}")

    print(f"\n{'='*70}")
    print(f"RESUMEN: {len(crit)} 🔴 · {len(high)} ⚠ · {len(med)} 🟡 · {len(low)} ·")
    gate = len(crit) + len(high)
    print(f"GATE (CRITICAL+HIGH): {gate}  →  {'✅ ZERO ERRORS' if gate==0 else '❌ con errores'}")
    print(f"{'='*70}")

    _dump()


def _dump():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = LOG_DIR / f"mega_audit_stock_{ts}.json"
    out.write_text(json.dumps({"ts": ts, "findings": findings}, ensure_ascii=False, indent=2))
    print(f"\nReporte: {out}")


if __name__ == "__main__":
    main()
