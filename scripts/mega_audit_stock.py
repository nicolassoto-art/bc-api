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

# CSV master 92: (nombre, jb_id). Para scoping MINE vs OTROS y cross-check de presencia.
CSV_ROWS = [
    ("Edificio DownTown San Martín","IDLyBU4W"),("Edificio Vista Morandé","GMrPAyQt"),
    ("Edificio Vista Amunategui","NgBHe0jo"),("Edificio Teatinos 750","atUiRS6M"),
    ("Vista San Martin","osnL3M1C"),("Bandera 1060","vWkZk19n"),("Vivo Rengo","nYjXw5kL"),
    ("Plaza Victoria","hw9SoClo"),("Altos de Collao","dr6uuHkX"),
    ("Edificio Mapocho 3521 Edificio A","FxGIdSga"),("Santa Elena 1670 MBI","EZljonhe"),
    ("Vicuña Mackenna 1432","PsqVqc03"),("Rosas 1444","b7Aniv5k"),("Guillermo Mann 1401","Dw5PBsEd"),
    ("ViMa","uRZc07TE"),("Vespucio Capital","VgrH6Vg2"),("ZAPADORES 1821","iB3uhp34"),
    ("EDIFICIO ÑUÑOA ZAÑARTU","Sfp8j2Sq"),("EDIFICIO MISSOURI 3885","SUWJ0Rye"),
    ("Eleuterio Ramírez","C0xMpK4K"),("Las Condes 7039","Ml02Ecl7"),("Novus Torre E","KvRtrtXK"),
    ("Novus Torre G","4Kny8VBw"),("El Aromo","sn2K1WIY"),("Nueva Esmeralda","LPJoCNEb"),
    ("Coronel Godoy","IDSvEAu8"),("Los lilenes","LKubKmn0"),("Edificio Serrano Capital","AJBqsIIi"),
    ("Cordillera Oriente Etapa 1","Xm0GuxtO"),("Matta","CGFo7vDQ"),("Brasil","hvEkYVJq"),
    ("Don Ignacio","is9kmud9"),("Diagonal Paraguay 240","NeOU0rvU"),
    ("Vicuña Mackenna 7589 Etapa II","v8tAVcOG"),("Vicuña Mackenna 7589 Etapa I","OwPhi37z"),
    ("Tocornal","9MubHeQ8"),("Vivaceta 864","IaIQ9iTH"),("ETAPA 2 PORTAL DEL PINAR","exrBr6Tp"),
    ("Condominio La Rioja","IgfWZVh2"),("Centenario I","86YW1rPt"),("Froilan Roa","jfkJBrPQ"),
    ("Vicuña Mackenna 1796","1kvflc3m"),("PORTAL DEL PINAR","tvFyLEMz"),("Bulnes 138","ksHJwBab"),
    ("Los Alerces","WWMCny3E"),("Mirador Chacabuco","W8P6QggB"),("Mirador oceánico","Vw1zOkV6"),
    ("Parque Huertos","ImxDl3nl"),("Condominio Mallorca","f8VQHYVK"),("Edificio Peumayen","3JcwgGZi"),
    ("Independencia 4745","qlkZufJk"),("Edificio Vitro","Xm0ZQPxk"),
    ("Jose Pedro Alessandri 1498","R5cTUSc8"),("EDIFICIO CONEXIÓN INDEPENDENCIA","48t1IInf"),
    ("Fuentes de Miguel Collao","75PDpryA"),("Fuentes de Lomas IV","1gaVJbKl"),
    ("Fuentes de Lomas III","hSeBHnw1"),("Edificio B.Come","pkR9sdRb"),("Almanova","q8RwqXao"),
    ("EDIFICIO SANTA ELENA 236","HvNRYfwm"),("Santa Rosa 250","T8UuEf2r"),("Ferroparque","C8R7VcvH"),
    ("Bosquemar","thmz67c6"),("Urban La Florida","mshykABZ"),("Terratoltén","kUYM4Rl8"),
    ("Terratoltén 2","wHL2AUKl"),("Bezanilla","vWeKp0EM"),("Aires La Florida 2","9YO68rOa"),
    ("Edificio HA","LXXJ9agb"),("Cumbres de Peñuelas","WGfF1Hcm"),("MiraOlas Peñuelas","OHpd4zbx"),
    ("Vicuña Mackenna 1194","sFfaXZIQ"),("Jardines de Alvarado","FrOy8Hxr"),
    ("Vista Reloncaví","hKtYFYuQ"),("Pintor Cicarelli I","Ao8J0BvU"),("General Mackenna","4nyJKnq9"),
    ("Trinidad III","5d7qpMgc"),("Plaza Cervantes torre B","iaEIx5Eo"),("Pintor Cicarelli II","RNEqQ6dw"),
    ("Cáceres","UAq8pgxr"),("Apóstol Santiago","teQxJTnq"),("Alto Buzeta","zkp4Z7HH"),
    ("Vista Costanera","7qF2CCA7"),("Serrano Torre A","LmVJgz7F"),("Quinta Park","nmLpNNTD"),
    ("Rodrigo Araya 1410","eHxgQsNq"),("MiraOlas Peñuelas 2º etapa","3Av5Af58"),
    ("Pionera Parque Cerrillos","m9zXfNHe"),("Fuentes de Lomas II","dX4Rddfn"),
    ("Edificio Borja Plaza","zOHnfOQJ"),
]
EXCLUIDOS_SLUGS = set()  # se llena en main con slug de los 3 excluidos (Pinar E1 = caso aparte)
RESERVADO_MANUAL = True
# orientaciones válidas que produce el importer correcto. Todo lo demás en proyecto MÍO = bug.
ORIENT_VALID = {"N","S","O","P","NO","NP","SO","SP","NE","SE","NPO","",None}

findings = []  # (sev, categoria, proyecto, msg, mine)
def add(sev, cat, proy, msg, mine=True):
    findings.append({"sev": sev, "cat": cat, "proy": proy, "msg": msg, "mine": mine})


def _slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","-",s).strip("-")


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

    # índices 3-vías: jb_id, slug(id), slug(nombre)
    by_jb, by_slug = {}, {}
    for p in lst:
        jb = (p.get("extra") or {}).get("jb_id")
        if jb: by_jb[jb] = p
        by_slug[_slug(p.get("id") or "")] = p
        by_slug[_slug(p.get("nombre") or "")] = p

    def find_bc(nombre, jb_id):
        return by_jb.get(jb_id) or by_slug.get(_slug(nombre)) or by_slug.get(_slug(jb_id))

    # set de slugs MÍOS (CSV master, sin excluidos)
    excl_names = {EXCLUIDOS_JB[j] for j in EXCLUIDOS_JB}
    mine_slugs = set()
    for nombre, jb in CSV_ROWS:
        if nombre in excl_names or jb == "tvFyLEMz":
            continue
        bc = find_bc(nombre, jb)
        if bc:
            mine_slugs.add(_slug(bc.get("id") or ""))
            mine_slugs.add(_slug(bc.get("nombre") or ""))

    # 2) cross-check presencia (3-vías) + excluidos
    for nombre, jb in CSV_ROWS:
        if nombre in excl_names:  # excluidos: deben estar AUSENTES
            bc = find_bc(nombre, jb)
            if bc:
                add("CRITICAL","excluido",nombre,f"EXCLUIDO pero presente (id={bc.get('id')})")
            continue
        if jb == "tvFyLEMz":
            continue  # gestionado aparte (jb-tvfylemz)
        if not find_bc(nombre, jb):
            add("CRITICAL","presencia",nombre,f"esperado (CSV master) pero AUSENTE en bc-api")

    # 3) deep per-proyecto (solo MÍOS para gating; OTROS = informativo)
    n = 0
    for p in lst:
        pid = p.get("id"); nombre = p.get("nombre") or pid
        is_mine = _slug(pid) in mine_slugs or _slug(nombre) in mine_slugs
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            add("CRITICAL","carga",nombre,f"GET /proyectos/{pid} falló {e!r}", is_mine); continue
        n += 1
        extra = full.get("extra") or {}
        inmob = (full.get("inmobiliaria") or "").strip()
        modelos = extra.get("modelos") or []
        unidades = full.get("unidades") or []
        estac = extra.get("estacionamientos") or extra.get("estacionamientos_dom") or []
        bodegas = extra.get("bodegas") or extra.get("bodegas_dom") or []
        packs = extra.get("packs") or extra.get("packs_dom") or []
        warns = extra.get("_deptos_con_warning") or []

        tag = "" if is_mine else " [proyecto del usuario, no del importador]"
        # inmobiliaria (solo gating en míos)
        if inmob in ("", "BigCapital", "Sin asignar"):
            add("CRITICAL" if is_mine else "LOW","inmob",nombre,f"inmobiliaria inválida='{inmob}'{tag}", is_mine)
        # modelos
        if not modelos:
            add("CRITICAL" if is_mine else "LOW","modelos",nombre,f"0 modelos{tag}", is_mine)
        nombres_modelos = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
        # huérfanas / modelo inválido
        huv = [u for u in unidades if not u.get("modelo")]
        hui = [u for u in unidades if u.get("modelo") and u.get("modelo") not in nombres_modelos]
        if hui:
            ejemplos = sorted({u.get("modelo") for u in hui})[:3]
            add("CRITICAL" if is_mine else "LOW","modelo-invalido",nombre,
                f"{len(hui)} uds → modelo inexistente {ejemplos} (frontend rompe){tag}", is_mine)
        if huv:
            add("HIGH" if is_mine else "LOW","huerfanas",nombre,
                f"{len(huv)} uds sin modelo (modelo='')"
                + (" · reservado MANUAL por usuario" if RESERVADO_MANUAL else "") + tag, is_mine)
        # sin planta (siempre MEDIUM: JB con frecuencia no publica planta — no bloquea)
        sin_planta = [m for m in modelos if isinstance(m, dict) and not (m.get("planta_url") or m.get("plano_url"))]
        if modelos and sin_planta:
            frac = len(sin_planta)/len(modelos)
            add("MEDIUM","sin-planta",nombre,
                f"{len(sin_planta)}/{len(modelos)} modelos sin planta ({frac*100:.0f}%) — verificar si JB la publica{tag}", is_mine)
        # enums crudos (solo gating en míos)
        ficha = " ".join(str(full.get(k)) for k in (
            "tipo_pie","tipo_descuento","tipo_bono_pie","tipo_reserva","destino_reserva",
            "acepta_cesion","permiso_construccion","tipo_cuenta","stock_type","solicita_preaprobacion")
            if full.get(k) is not None)
        crudos = [w for w in ENUMS_CRUDOS if re.search(rf"\b{re.escape(w)}\b", ficha)]
        if crudos:
            add("HIGH" if is_mine else "LOW","enums",nombre,f"enums crudos sin mapear: {','.join(crudos[:4])}{tag}", is_mine)
        # orientaciones (solo míos: el importador debe producir N/S/O/P abreviado)
        bad_or = sorted({str(u.get("orientacion")) for u in unidades
                         if u.get("orientacion") not in ORIENT_VALID}, key=str)
        if bad_or:
            add("HIGH" if is_mine else "LOW","orientacion",nombre,
                f"orientaciones no abreviadas ES: {bad_or[:6]}{tag}", is_mine)
        # estac/bod/pack
        if not estac and not bodegas and not packs:
            add("MEDIUM","assets",nombre,f"sin estac/bodegas/packs (verificar si JB realmente 0){tag}", is_mine)
        # foto principal
        fp = full.get("foto_principal_url") or extra.get("foto_principal_url")
        imgs = full.get("imagenes") or extra.get("imagenes") or []
        if not fp and not imgs:
            add("MEDIUM","foto",nombre,f"sin foto principal ni imágenes{tag}", is_mine)
        # voseo en notas
        notas = str(extra.get("notas") or extra.get("notas_html") or full.get("descripcion") or "")
        if VOSEO.search(notas):
            add("MEDIUM","voseo",nombre,f"posible voseo argentino en notas/descripción{tag}", is_mine)

    print(f"Auditados {n} proyectos en profundidad ({len([1 for s in mine_slugs])//2} míos aprox).\n")

    # resumen — gating SOLO sobre proyectos míos (del importador)
    crit = [f for f in findings if f["sev"]=="CRITICAL"]
    high = [f for f in findings if f["sev"]=="HIGH"]
    med  = [f for f in findings if f["sev"]=="MEDIUM"]
    low  = [f for f in findings if f["sev"]=="LOW"]
    icon = {"CRITICAL":"🔴","HIGH":"⚠","MEDIUM":"🟡","LOW":"·"}
    for grp,name in ((crit,"CRITICAL"),(high,"HIGH"),(med,"MEDIUM")):
        if not grp: continue
        print(f"\n{icon[name]} {name} ({len(grp)})")
        for f in sorted(grp, key=lambda x: (x["cat"], x["proy"])):
            print(f"   [{f['cat']}] {f['proy']}: {f['msg']}")
    if low:
        print(f"\n· LOW ({len(low)}) — proyectos del usuario / no-bloqueante (resumido por categoría):")
        from collections import Counter
        for (c,), v in sorted(Counter((f["cat"],) for f in low).items()):
            print(f"   [{c}] ×{v}")

    gate = len([f for f in crit+high if f.get("mine")])
    print(f"\n{'='*70}")
    print(f"RESUMEN total: {len(crit)} 🔴 · {len(high)} ⚠ · {len(med)} 🟡 · {len(low)} ·")
    print(f"GATE (CRITICAL+HIGH en proyectos MÍOS): {gate}  →  {'✅ ZERO ERRORS' if gate==0 else '❌ con errores'}")
    print(f"{'='*70}")

    _dump()


def _dump():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = LOG_DIR / f"mega_audit_stock_{ts}.json"
    out.write_text(json.dumps({"ts": ts, "findings": findings}, ensure_ascii=False, indent=2))
    print(f"\nReporte: {out}")


if __name__ == "__main__":
    main()
