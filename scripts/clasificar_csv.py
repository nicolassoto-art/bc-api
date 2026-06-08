"""clasificar_csv.py — Cruza el CSV master (92 proyectos JB) con lo importado en bc-api.

Identifica cuáles del CSV ya están en bc-api (por jb_id en extra.jb_id) y cuáles faltan.
NO escribe nada.
"""
import os, httpx, unicodedata, re
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"

# CSV completo en línea (de /Users/nicolas/Downloads/proyectos_jetbrokers.csv).
CSV = """\
AJ URBANA|Edificio DownTown San Martín|IDLyBU4W
AJ URBANA|Edificio Vista Morandé|GMrPAyQt
AJ URBANA|Edificio Vista Amunategui|NgBHe0jo
AJ URBANA|Edificio Teatinos 750|atUiRS6M
Vellatrix|Bandera 1060|vWkZk19n
Vellatrix|Vivo Rengo|nYjXw5kL
Inmobiliaria Origen|Plaza Victoria|hw9SoClo
Inmobiliaria Las Palmas|Altos de Collao|dr6uuHkX
EuroInmobiliaria|Edificio Mapocho 3521 Edificio A|FxGIdSga
EuroInmobiliaria|Santa Elena 1670 MBI|EZljonhe
EuroInmobiliaria|Vicuña Mackenna 1432|PsqVqc03
EuroInmobiliaria|Rosas 1444|b7Aniv5k
EuroInmobiliaria|Guillermo Mann 1401|Dw5PBsEd
Ingevec|ViMa|uRZc07TE
Ingevec|Vespucio Capital|VgrH6Vg2
INMOBILIARIA LARRAIN PRIETO|ZAPADORES 1821|iB3uhp34
INMOBILIARIA LARRAIN PRIETO|EDIFICIO ÑUÑOA ZAÑARTU|Sfp8j2Sq
INMOBILIARIA LARRAIN PRIETO|EDIFICIO MISSOURI 3885|SUWJ0Rye
Stitchkin|Eleuterio Ramírez|C0xMpK4K
Stitchkin|Las Condes 7039|Ml02Ecl7
Stitchkin|Novus Torre E|KvRtrtXK
Stitchkin|Novus Torre G|4Kny8VBw
Ingevec|El Aromo|sn2K1WIY
Ingevec|Nueva Esmeralda|LPJoCNEb
Ingevec|Coronel Godoy|IDSvEAu8
Ingevec|Los lilenes|LKubKmn0
Ingevec|Edificio Serrano Capital|AJBqsIIi
MNK|Cordillera Oriente Etapa 1|Xm0GuxtO
Ingevec|Matta|CGFo7vDQ
Ingevec|Terrazzo|72GkWnlW
Ingevec|Brasil|hvEkYVJq
Ingevec|Don Ignacio|is9kmud9
Ingevec|Abdón Cifuentes|G3jWrRoE
Ingevec|Diagonal Paraguay 240|NeOU0rvU
Ingevec|Vicuña Mackenna 7589 Etapa II|v8tAVcOG
Ingevec|Vicuña Mackenna 7589 Etapa I|OwPhi37z
Ingevec|Tocornal|9MubHeQ8
Ingevec|Vivaceta 864|IaIQ9iTH
MNK|ETAPA 2 PORTAL DEL PINAR|exrBr6Tp
MNK|Condominio La Rioja|IgfWZVh2
Ingevec|Centenario I|86YW1rPt
Ingevec|Froilan Roa|jfkJBrPQ
Ingevec|Vicuña Mackenna 1796|1kvflc3m
MNK|PORTAL DEL PINAR|tvFyLEMz
Itrio|Bulnes 138|ksHJwBab
Ingevec|Los Alerces|WWMCny3E
Iroyal|Mirador Chacabuco|W8P6QggB
Iroyal|Mirador oceánico|Vw1zOkV6
Iroyal|Parque Huertos|ImxDl3nl
Iroyal|Condominio Mallorca|f8VQHYVK
Iroyal|Edificio Peumayen|3JcwgGZi
EuroInmobiliaria|Independencia 4745|qlkZufJk
EuroInmobiliaria|Edificio Vitro|Xm0ZQPxk
EuroInmobiliaria|Jose Pedro Alessandri 1498|R5cTUSc8
INMOBILIARIA LARRAIN PRIETO|EDIFICIO CONEXIÓN INDEPENDENCIA|48t1IInf
CISS|Fuentes de Miguel Collao|75PDpryA
CISS|Fuentes de Lomas IV|1gaVJbKl
CISS|Fuentes de Lomas III|hSeBHnw1
Ileon|Edificio B.Come|pkR9sdRb
Vitalia|Almanova|q8RwqXao
Itrio|EDIFICIO SANTA ELENA 236|HvNRYfwm
Ingevec|Santa Rosa 250|T8UuEf2r
Ecasa|Ferroparque|C8R7VcvH
Ecasa|Bosquemar|thmz67c6
Ecasa|Urban La Florida|mshykABZ
Ecasa|Terratoltén|kUYM4Rl8
Ecasa|Terratoltén 2|wHL2AUKl
Ecasa|Bezanilla|vWeKp0EM
Ecasa|Aires La Florida 2|9YO68rOa
Ecasa|Edificio HA|LXXJ9agb
Ecasa|Cumbres de Peñuelas|WGfF1Hcm
Prohabit|MiraOlas Peñuelas|OHpd4zbx
Stitchkin|Vicuña Mackenna 1194|sFfaXZIQ
Maestra|Jardines de Alvarado|FrOy8Hxr
Maestra|Vista Reloncaví|hKtYFYuQ
Maestra|Pintor Cicarelli I|Ao8J0BvU
Maestra|General Mackenna|4nyJKnq9
Maestra|Trinidad III|5d7qpMgc
Maestra|Plaza Cervantes torre B|iaEIx5Eo
Maestra|Pintor Cicarelli II|RNEqQ6dw
Maestra|Cáceres|UAq8pgxr
Maestra|Apóstol Santiago|teQxJTnq
Maestra|Alto Buzeta|zkp4Z7HH
Maestra|Vista Costanera|7qF2CCA7
Maestra|Serrano Torre A|LmVJgz7F
Prohabit|Quinta Park|nmLpNNTD
Stitchkin|Rodrigo Araya 1410|eHxgQsNq
AJ URBANA|Vista San Martin|osnL3M1C
Prohabit|MiraOlas Peñuelas 2º etapa|3Av5Af58
Inmobiliaria Olimpia|Pionera Parque Cerrillos|m9zXfNHe
CISS|Fuentes de Lomas II|dX4Rddfn
BigCapital|Edificio Borja Plaza|zOHnfOQJ
"""


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    lst = cli.get("/proyectos").json()
    print(f"Total proyectos en bc-api: {len(lst)}")
    # Indexar bc-api por jb_id (extra.jb_id) y por slug
    by_jb_id = {}
    by_slug = {}
    for p in lst:
        jb_id = (p.get("extra") or {}).get("jb_id")
        if jb_id:
            by_jb_id[jb_id] = p
        if p.get("id"):
            by_slug[p["id"]] = p

    # Parsear CSV
    rows = []
    for line in CSV.strip().split("\n"):
        parts = line.split("|")
        if len(parts) == 3:
            rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

    print(f"Total proyectos en CSV master: {len(rows)}\n")

    importados = []
    pendientes = []
    for inmob, nombre, jb_id in rows:
        bc = by_jb_id.get(jb_id)
        if bc:
            importados.append((inmob, nombre, jb_id, bc.get("id")))
        else:
            pendientes.append((inmob, nombre, jb_id))

    # Agrupar pendientes por inmobiliaria
    by_inmob_pend = {}
    for inmob, nombre, jb_id in pendientes:
        by_inmob_pend.setdefault(inmob, []).append((nombre, jb_id))

    print(f"{'═'*80}\n  IMPORTADOS ({len(importados)})\n{'═'*80}")
    by_inmob_imp = {}
    for inmob, nombre, jb_id, slug in importados:
        by_inmob_imp.setdefault(inmob, []).append((nombre, jb_id, slug))
    for inmob in sorted(by_inmob_imp):
        proyectos = by_inmob_imp[inmob]
        print(f"\n▸ {inmob} ({len(proyectos)})")
        for nombre, jb_id, slug in proyectos:
            print(f"    ✓ {nombre:<40} {jb_id:<12} → {slug}")

    print(f"\n{'═'*80}\n  PENDIENTES ({len(pendientes)})\n{'═'*80}")
    for inmob in sorted(by_inmob_pend):
        proyectos = by_inmob_pend[inmob]
        print(f"\n▸ {inmob} ({len(proyectos)})")
        for nombre, jb_id in proyectos:
            print(f"    ⬜ {nombre:<40} {jb_id}")

    print(f"\n{'═'*80}\n  RESUMEN\n{'═'*80}")
    print(f"  CSV master:    {len(rows)}")
    print(f"  Importados:    {len(importados)}")
    print(f"  Pendientes:    {len(pendientes)}")
    # extras: proyectos en bc-api que NO están en el CSV master (importados antes del CSV)
    csv_jb_ids = {r[2] for r in rows}
    extras = []
    for p in lst:
        jb = (p.get("extra") or {}).get("jb_id")
        if jb and jb not in csv_jb_ids:
            extras.append((p.get("inmobiliaria"), p.get("nombre"), jb, p.get("id")))
    if extras:
        print(f"\n  ⚠ EXTRAS en bc-api (no en CSV master): {len(extras)}")
        for inmob, nombre, jb_id, slug in extras:
            print(f"    {inmob} · {nombre:<35} {jb_id:<12} → {slug}")


if __name__ == "__main__":
    main()
