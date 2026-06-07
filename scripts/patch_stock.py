"""
patch_stock.py — Refresca estac/bodegas/packs de un proyecto SIN wipe.
Trae el merge nuevo /list+/assets de JB y actualiza solo extra.estacionamientos_dom etc.
Preserva unidades, fotos, ediciones manuales.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS, BC_API_JWT, PID_JB, PID_BC
"""
from __future__ import annotations
import asyncio, json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS
import httpx

PID_JB = os.environ["PID_JB"]
PID_BC = os.environ["PID_BC"]
BC = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")


def asset_num(s): return str(s or "").split("[")[0].strip()
def _fnum(v):
    try: return float(str(v).replace(",", "."))
    except: return None
def asset_uf(s):
    m = re.search(r"\[\s*([\d.,]+)\s*UF", str(s or ""))
    return _fnum(m.group(1)) if m else None
def asset_m2(s):
    m = re.search(r"\[\s*([\d.,]+)\s*m2", str(s or ""))
    return _fnum(m.group(1)) if m else None


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base=BC, bc_jwt=os.environ["BC_API_JWT"], imports_dir=Path("imports/_patch"))
    await imp.login()
    await imp._page.goto(f"https://app.jetbrokers.io/projects/detail/{PID_JB}", wait_until="networkidle", timeout=50_000)
    await imp._page.wait_for_timeout(3_000)
    cookies = await imp._ctx.cookies()
    jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
    cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": f"https://app.jetbrokers.io/projects/detail/{PID_JB}"})

    async def gj(ep):
        r = await cli.get(ep)
        return r.json() if r.status_code == 200 else None

    pk_l = ((await gj(f"/parking/project/{PID_JB}/list/0")) or {}).get("parkings", [])
    st_l = ((await gj(f"/store/project/{PID_JB}/list/0")) or {}).get("stores", [])
    pc_l = ((await gj(f"/pack/project/{PID_JB}/list/0")) or {}).get("packs", [])
    # assets
    acli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=30,
        headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                 "Authorization": f"Bearer {imp._jb_token}",
                 "Referer": "https://app.jetbrokers.io/quotes"})
    a = await (await acli.get(f"/project/{PID_JB}/assets")).aread() if False else None
    ar = await acli.get(f"/project/{PID_JB}/assets")
    assets = ar.json() if ar.status_code == 200 else {}
    await acli.aclose(); await cli.aclose()
    pk_a = assets.get("parkings", [])
    st_a = assets.get("stores", [])
    pc_a = assets.get("packs", [])

    def merge(list_, assets_):
        base = list_ if len(list_) >= len(assets_) else assets_
        other = assets_ if base is list_ else list_
        other_by_num = {asset_num(o.get("number")): o for o in other if o.get("number")}
        out = []
        for it in base:
            num = asset_num(it.get("number"))
            merged = dict(it)
            comp = other_by_num.get(num)
            if comp:
                for k, v in comp.items():
                    if not merged.get(k) and v is not None:
                        merged[k] = v
            out.append(merged)
        return out

    parkings = merge(pk_l, pk_a)
    stores = merge(st_l, st_a)
    packs = merge(pc_l, pc_a)
    print(f"JB: {len(parkings)} estac · {len(stores)} bodegas · {len(packs)} packs "
          f"(list:{len(pk_l)}/{len(st_l)}/{len(pc_l)} + assets:{len(pk_a)}/{len(st_a)}/{len(pc_a)})", flush=True)

    estacionamientos_dom = [
        {"cells": [None, asset_num(pk.get("number")),
                   pk.get("price") or asset_uf(pk.get("number")),
                   str(pk.get("level")) if pk.get("level") is not None else "",
                   (",".join(pk.get("type")) if isinstance(pk.get("type"), list) else str(pk.get("type") or ""))],
         "disponible": bool(pk.get("available", True))}
        for pk in parkings if pk.get("number")]
    bodegas_dom = [
        {"cells": [None, asset_num(st.get("number")),
                   st.get("price") or asset_uf(st.get("number")),
                   str(st.get("surface") or asset_m2(st.get("number")) or "")],
         "disponible": bool(st.get("available", True))}
        for st in stores if st.get("number")]
    packs_dom = [
        {"numero": asset_num(pk.get("number")),
         "precio_uf": pk.get("price") or asset_uf(pk.get("number")),
         "estacionamientos": [asset_num(p.get("number")) for p in (pk.get("parkings") or [])],
         "bodegas": [asset_num(s.get("number")) for s in (pk.get("stores") or [])],
         "disponible": bool(pk.get("available", True))}
        for pk in packs if pk.get("number")]

    # GET proyecto actual de bc-api → PUT con solo estos 3 campos del extra reemplazados.
    bcc = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {os.environ['BC_API_JWT']}"}, timeout=30)
    p = bcc.get(f"/proyectos/{PID_BC}").json()
    extra_old = p.get("extra") or {}
    # eliminar arrays "shaped" antiguos (post-edit) y *_dom para que mande solo el nuevo
    for k in ("estacionamientos", "bodegas", "packs",
              "estacionamientos_dom", "bodegas_dom", "packs_dom",
              "_estacionamientos_dom", "_bodegas_dom", "_packs_dom"):
        extra_old.pop(k, None)
    extra_new = {**extra_old,
                 "estacionamientos_dom": estacionamientos_dom,
                 "bodegas_dom": bodegas_dom,
                 "packs_dom": packs_dom}
    body = {k: p[k] for k in p
            if k not in ("id", "unidades", "imagenes", "documentos", "created_at", "updated_at", "timeline")}
    body["extra"] = extra_new
    r = bcc.put(f"/proyectos/{PID_BC}", json=body)
    print(f"PUT → {r.status_code}", flush=True)
    if r.status_code != 200:
        print(f"ERROR: {r.text[:500]}", flush=True)
    else:
        print(f"✓ patch OK: {len(estacionamientos_dom)} estac · {len(bodegas_dom)} bodegas · {len(packs_dom)} packs", flush=True)
    await imp.close()


if __name__ == "__main__":
    asyncio.run(main())
