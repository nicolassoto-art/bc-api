"""rank_pendientes.py — Rankea 58 pendientes JB por stock total (uds+estac+bod+packs)."""
from __future__ import annotations
import asyncio, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS
import httpx

PEND = [
    ("AJ URBANA","Edificio DownTown San Martín","IDLyBU4W"),
    ("AJ URBANA","Edificio Vista Morandé","GMrPAyQt"),
    ("AJ URBANA","Edificio Vista Amunategui","NgBHe0jo"),
    ("AJ URBANA","Edificio Teatinos 750","atUiRS6M"),
    ("AJ URBANA","Vista San Martin","osnL3M1C"),
    ("Vellatrix","Bandera 1060","vWkZk19n"),
    ("Vellatrix","Vivo Rengo","nYjXw5kL"),
    ("Inmob. Origen","Plaza Victoria","hw9SoClo"),
    ("Inmob. Las Palmas","Altos de Collao","dr6uuHkX"),
    ("LARRAIN PRIETO","ZAPADORES 1821","iB3uhp34"),
    ("LARRAIN PRIETO","EDIFICIO ÑUÑOA ZAÑARTU","Sfp8j2Sq"),
    ("LARRAIN PRIETO","EDIFICIO MISSOURI 3885","SUWJ0Rye"),
    ("LARRAIN PRIETO","EDIFICIO CONEXIÓN INDEPENDENCIA","48t1IInf"),
    ("Stitchkin","Eleuterio Ramírez","C0xMpK4K"),
    ("Stitchkin","Las Condes 7039","Ml02Ecl7"),
    ("Stitchkin","Novus Torre E","KvRtrtXK"),
    ("Stitchkin","Novus Torre G","4Kny8VBw"),
    ("Stitchkin","Vicuña Mackenna 1194","sFfaXZIQ"),
    ("Stitchkin","Rodrigo Araya 1410","eHxgQsNq"),
    ("Itrio","Bulnes 138","ksHJwBab"),
    ("Itrio","EDIFICIO SANTA ELENA 236","HvNRYfwm"),
    ("Iroyal","Mirador Chacabuco","W8P6QggB"),
    ("Iroyal","Mirador oceánico","Vw1zOkV6"),
    ("Iroyal","Parque Huertos","ImxDl3nl"),
    ("Iroyal","Condominio Mallorca","f8VQHYVK"),
    ("Iroyal","Edificio Peumayen","3JcwgGZi"),
    ("CISS","Fuentes de Miguel Collao","75PDpryA"),
    ("CISS","Fuentes de Lomas IV","1gaVJbKl"),
    ("CISS","Fuentes de Lomas III","hSeBHnw1"),
    ("CISS","Fuentes de Lomas II","dX4Rddfn"),
    ("Ileon","Edificio B.Come","pkR9sdRb"),
    ("Vitalia","Almanova","q8RwqXao"),
    ("Ecasa","Ferroparque","C8R7VcvH"),
    ("Ecasa","Bosquemar","thmz67c6"),
    ("Ecasa","Urban La Florida","mshykABZ"),
    ("Ecasa","Terratoltén","kUYM4Rl8"),
    ("Ecasa","Terratoltén 2","wHL2AUKl"),
    ("Ecasa","Bezanilla","vWeKp0EM"),
    ("Ecasa","Aires La Florida 2","9YO68rOa"),
    ("Ecasa","Edificio HA","LXXJ9agb"),
    ("Ecasa","Cumbres de Peñuelas","WGfF1Hcm"),
    ("Prohabit","MiraOlas Peñuelas","OHpd4zbx"),
    ("Prohabit","Quinta Park","nmLpNNTD"),
    ("Prohabit","MiraOlas Peñuelas 2º etapa","3Av5Af58"),
    ("Maestra","Jardines de Alvarado","FrOy8Hxr"),
    ("Maestra","Vista Reloncaví","hKtYFYuQ"),
    ("Maestra","Pintor Cicarelli I","Ao8J0BvU"),
    ("Maestra","General Mackenna","4nyJKnq9"),
    ("Maestra","Trinidad III","5d7qpMgc"),
    ("Maestra","Plaza Cervantes torre B","iaEIx5Eo"),
    ("Maestra","Pintor Cicarelli II","RNEqQ6dw"),
    ("Maestra","Cáceres","UAq8pgxr"),
    ("Maestra","Apóstol Santiago","teQxJTnq"),
    ("Maestra","Alto Buzeta","zkp4Z7HH"),
    ("Maestra","Vista Costanera","7qF2CCA7"),
    ("Maestra","Serrano Torre A","LmVJgz7F"),
    ("Inmob. Olimpia","Pionera Parque Cerrillos","m9zXfNHe"),
    ("BigCapital","Edificio Borja Plaza","zOHnfOQJ"),
]


async def probe(imp, jar, inmob, nombre, jid):
    out = {"inmob": inmob, "nombre": nombre, "id": jid, "u": 0, "e": 0, "b": 0, "p": 0, "kind": "?"}
    headers_base = {**JB_HEADERS, "jet-brokers-version": "7.43.1",
                    "Authorization": f"Bearer {imp._jb_token}"}
    # own
    async with httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=15,
        headers={**headers_base, "Referer": f"https://app.jetbrokers.io/projects/detail/{jid}"}) as cli:
        try:
            r = await cli.get(f"/project/{jid}/detail")
            if r.status_code == 200:
                d = r.json()
                out["kind"] = "own"
                out["u"] = d.get("apartmentsTotal") or 0
                out["e"] = d.get("parkingsTotal") or 0
                out["b"] = d.get("storesTotal") or 0
                out["p"] = d.get("packsTotal") or 0
                return out
        except Exception as e:
            out["kind"] = f"exc-own:{e.__class__.__name__}"
    # mkt
    async with httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=15,
        headers={**headers_base, "Referer": f"https://app.jetbrokers.io/marketplace/workview/{jid}"}) as cli:
        try:
            r = await cli.get(f"/marketplace/{jid}/workview")
            if r.status_code == 200:
                d = r.json()
                out["kind"] = "mkt"
                out["u"] = d.get("apartmentsTotal") or 0
                out["e"] = d.get("parkingsTotal") or 0
                out["b"] = d.get("storesTotal") or 0
                out["p"] = d.get("packsTotal") or 0
                return out
            out["kind"] = f"mkt{r.status_code}"
        except Exception as e:
            out["kind"] = f"exc-mkt:{e.__class__.__name__}"
    return out


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base="https://bc-api.178-105-91-29.nip.io", bc_jwt="dummy",
                     imports_dir=Path("imports/_rank"))
    await imp.login()
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}

    # batched para no saturar
    results = []
    sem = asyncio.Semaphore(6)
    async def wrap(row):
        async with sem:
            return await probe(imp, jar, *row)
    results = await asyncio.gather(*[wrap(r) for r in PEND])

    results.sort(key=lambda x: -(x["u"] + x["e"] + x["b"] + x["p"]))
    print(f"\n{'#':>3} {'STOCK':>6} {'U':>5} {'E':>4} {'B':>4} {'P':>3} {'KIND':<8} {'INMOB':<22} NOMBRE  (jb_id)")
    print("─" * 120)
    for i, r in enumerate(results, 1):
        tot = r["u"] + r["e"] + r["b"] + r["p"]
        print(f"{i:>3} {tot:>6} {r['u']:>5} {r['e']:>4} {r['b']:>4} {r['p']:>3} {r['kind']:<8} {r['inmob'][:22]:<22} {r['nombre']}  ({r['id']})")

    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
