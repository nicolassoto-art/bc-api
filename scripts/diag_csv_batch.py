"""
diag_csv_batch.py — Diagnóstico read-only de los 20 proyectos del CSV de Ingevec.

Para cada ID:
  - JB:   GET /project/{id}/detail (status, name, dev, locality, totales)
          GET /apartment-model/.../all (modelos + plantas)
          POST /apartment/project-detail-search (unidades, ambos availability)
          GET /parking|/store|/pack /list/0 + /assets (estac/bodegas/packs)
  - bc-api: buscar por nombre sluggificado y por extra.jb_id
            reportar unidades/imagenes/foto/updated_at + "manual?" heurística

Salida: tabla consolidada al final.
NO escribe nada.

Env: JETBROKERS_EMAIL, JETBROKERS_PASS, BC_API_JWT
"""
from __future__ import annotations
import asyncio, json, os, re, sys, time, unicodedata
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.jb_importer import JBImporter, JB_API_BASE, JB_HEADERS  # noqa
import httpx  # noqa

BC = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
OUT = Path("imports/_diag_csv"); OUT.mkdir(parents=True, exist_ok=True)

# Lista del CSV (sin #1 ViMa ni #6 Los Lilenes, según decisión del usuario)
PROYECTOS = [
    ("Vespucio Capital",            "VgrH6Vg2"),
    ("El Aromo",                    "sn2K1WIY"),
    ("Nueva Esmeralda",             "LPJoCNEb"),
    ("Coronel Godoy",               "IDSvEAu8"),
    ("Edificio Serrano Capital",    "AJBqsIIi"),
    ("Matta",                       "CGFo7vDQ"),
    ("Terrazzo",                    "72GkWnlW"),
    ("Brasil",                      "hvEkYVJq"),
    ("Don Ignacio",                 "is9kmud9"),
    ("Abdón Cifuentes",             "G3jWrRoE"),
    ("Diagonal Paraguay 240",       "NeOU0rvU"),
    ("V. Mackenna 7589 Etapa II",   "v8tAVcOG"),
    ("V. Mackenna 7589 Etapa I",    "OwPhi37z"),
    ("Tocornal",                    "9MubHeQ8"),
    ("Vivaceta 864",                "IaIQ9iTH"),
    ("Centenario I",                "86YW1rPt"),
    ("Froilán Roa",                 "jfkJBrPQ"),
    ("V. Mackenna 1796",            "1kvflc3m"),
    ("Los Alerces",                 "WWMCny3E"),
    ("Santa Rosa 250",              "T8UuEf2r"),
]


def slugify(s):
    """Sluggify igual que bc-api: minúsculas, sin acentos, espacios → guiones."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


async def main():
    imp = JBImporter(jb_email=os.environ["JETBROKERS_EMAIL"], jb_password=os.environ["JETBROKERS_PASS"],
                     bc_api_base=BC, bc_jwt=os.environ.get("BC_API_JWT", "dummy"),
                     imports_dir=OUT)
    await imp.login()
    page = imp._page

    # bc-api listing (una vez)
    bcc = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {os.environ['BC_API_JWT']}"}, timeout=30)
    bc_list = bcc.get("/proyectos").json()
    bc_by_slug = {p.get("id"): p for p in bc_list}
    bc_by_jbid = {(p.get("extra") or {}).get("jb_id"): p for p in bc_list if (p.get("extra") or {}).get("jb_id")}

    results = []
    for idx, (nombre, jb_id) in enumerate(PROYECTOS, start=1):
        print(f"\n--- [{idx}/20] {nombre} ({jb_id}) ---", flush=True)
        # JB: necesita Referer del proyecto + cookies frescas
        await page.goto(f"https://app.jetbrokers.io/projects/detail/{jb_id}",
                        wait_until="networkidle", timeout=40_000)
        await page.wait_for_timeout(2_500)
        cookies = await imp._ctx.cookies()
        jar = {c["name"]: c["value"] for c in cookies if "jetbrokers" in (c.get("domain") or "")}
        cli = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": f"https://app.jetbrokers.io/projects/detail/{jb_id}"})
        ac = httpx.AsyncClient(base_url=JB_API_BASE, cookies=jar, timeout=25,
            headers={**JB_HEADERS, "jet-brokers-version": "7.43.1",
                     "Authorization": f"Bearer {imp._jb_token}",
                     "Referer": "https://app.jetbrokers.io/quotes"})

        async def gj(c, ep):
            try:
                r = await c.get(ep)
                return r.status_code, (r.json() if r.status_code == 200 else None)
            except Exception:
                return -1, None

        # detail
        det_status, det = await gj(cli, f"/project/{jb_id}/detail")
        # modelos
        mod_status, mods = await gj(cli, f"/apartment-model/project/{jb_id}/all")
        n_mod = len(mods) if isinstance(mods, list) else 0
        n_mod_planta = sum(1 for m in (mods or []) if m.get("blueprint"))
        # unidades — probar ambos availability
        n_uds = 0
        if det_status == 200:
            for av in (None, "available"):
                ts = int(time.time() * 1000)
                body = {"tipologies": [], "type": None, "order": "ASC", "models": [], "facings": [],
                        "projectId": jb_id, "availability": av, "number": None, "element": 0, "elements": 9999}
                try:
                    r = await cli.post(f"/apartment/project-detail-search/{ts}", json=body)
                    if r.status_code in (200, 201):
                        u = (r.json() or {}).get("apartments", [])
                        if len(u) > n_uds: n_uds = len(u)
                except Exception:
                    pass
        # estac/bodegas/packs por fuentes
        _, pk_l = await gj(cli, f"/parking/project/{jb_id}/list/0")
        _, st_l = await gj(cli, f"/store/project/{jb_id}/list/0")
        _, pc_l = await gj(cli, f"/pack/project/{jb_id}/list/0")
        pk_l_n = len((pk_l or {}).get("parkings", [])) if isinstance(pk_l, dict) else 0
        st_l_n = len((st_l or {}).get("stores", [])) if isinstance(st_l, dict) else 0
        pc_l_n = len((pc_l or {}).get("packs", [])) if isinstance(pc_l, dict) else 0
        _, assets = await gj(ac, f"/project/{jb_id}/assets")
        pk_a_n = len((assets or {}).get("parkings", []) or [])
        st_a_n = len((assets or {}).get("stores", []) or [])
        pc_a_n = len((assets or {}).get("packs", []) or [])
        # contar el MAX por tipo (el importer mergea, así que cuenta el merge)
        est = max(pk_l_n, pk_a_n)
        bod = max(st_l_n, st_a_n)
        pck = max(pc_l_n, pc_a_n)
        await cli.aclose(); await ac.aclose()

        # JB resumen
        jb_name = (det or {}).get("name") if det else None
        dev = (det or {}).get("developerName") if det else None
        loc = (det or {}).get("locality") if det else None

        # bc-api lookup
        slug_guess = slugify(jb_name or nombre)
        bc_p = bc_by_jbid.get(jb_id) or bc_by_slug.get(slug_guess)
        bc_state = "—"
        bc_uds = 0
        bc_imgs = 0
        manual = False
        if bc_p:
            try:
                full = bcc.get(f"/proyectos/{bc_p['id']}").json()
                bc_uds = len(full.get("unidades") or [])
                bc_imgs = len(full.get("imagenes") or [])
                ca = full.get("created_at"); ua = full.get("updated_at")
                # heurística manual: updated_at > created_at + 60s
                if ca and ua:
                    try:
                        cdt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        udt = datetime.fromisoformat(ua.replace("Z", "+00:00"))
                        manual = (udt - cdt).total_seconds() > 60
                    except Exception:
                        pass
                if bc_uds == 0 and bc_imgs == 0:
                    bc_state = f"⚠ existe vacío ({bc_p['id']})"
                elif manual:
                    bc_state = f"⚠ editado ({bc_p['id']}, {bc_uds}u/{bc_imgs}i)"
                else:
                    bc_state = f"existe ({bc_p['id']}, {bc_uds}u/{bc_imgs}i)"
            except Exception as e:
                bc_state = f"err: {str(e)[:30]}"
        else:
            bc_state = "no existe"

        result = {
            "n": idx, "nombre": nombre, "jb_id": jb_id,
            "jb_status": det_status, "jb_name": jb_name, "developer": dev, "locality": loc,
            "modelos": n_mod, "modelos_con_planta": n_mod_planta,
            "unidades": n_uds, "estac": est, "bodegas": bod, "packs": pck,
            "list_e_b_p": f"{pk_l_n}/{st_l_n}/{pc_l_n}",
            "assets_e_b_p": f"{pk_a_n}/{st_a_n}/{pc_a_n}",
            "bc_state": bc_state, "bc_uds": bc_uds, "bc_imgs": bc_imgs, "manual_edit": manual,
        }
        results.append(result)
        print(f"   JB[{det_status}] dev={dev!r} loc={loc!r} mod={n_mod}({n_mod_planta}p) "
              f"uds={n_uds} estac={est} bod={bod} pck={pck}", flush=True)
        print(f"   bc-api: {bc_state}", flush=True)

    await imp.close()
    bcc.close()

    # ── Tabla consolidada ──
    print(f"\n{'═'*145}", flush=True)
    print(f"{'N°':<3} {'Proyecto':<32} {'JB ID':<11} {'JB':<4} {'Dev':<10} {'Mod(plt)':<9} {'Uds':<5} "
          f"{'E/B/P':<11} {'bc-api estado'}", flush=True)
    print("═" * 145, flush=True)
    for r in results:
        mp = f"{r['modelos']}({r['modelos_con_planta']})"
        ebp = f"{r['estac']}/{r['bodegas']}/{r['packs']}"
        print(f"{r['n']:<3} {r['nombre'][:31]:<32} {r['jb_id']:<11} {r['jb_status']:<4} "
              f"{(r['developer'] or '?')[:9]:<10} {mp:<9} {r['unidades']:<5} {ebp:<11} {r['bc_state']}", flush=True)
    print("═" * 145, flush=True)

    # Resumen agregado
    print(f"\n=== RESUMEN ===", flush=True)
    ok = sum(1 for r in results if r["jb_status"] == 200)
    fail = sum(1 for r in results if r["jb_status"] != 200)
    print(f"  JB 200: {ok}/20 · errores: {fail}/20", flush=True)
    by_dev = {}
    for r in results:
        d = r.get("developer") or "?"
        by_dev[d] = by_dev.get(d, 0) + 1
    print(f"  inmobiliarias: {by_dev}", flush=True)
    no_existe = sum(1 for r in results if r["bc_state"] == "no existe")
    vacios = sum(1 for r in results if "vacío" in r["bc_state"])
    editados = sum(1 for r in results if "editado" in r["bc_state"])
    print(f"  bc-api: {no_existe} no existen · {vacios} vacíos · {editados} editados", flush=True)
    huerf = [r["nombre"] for r in results if r["jb_status"] == 200 and r["unidades"] == 0]
    if huerf: print(f"  ⚠ 200 pero 0 unidades: {huerf}", flush=True)
    sin_inmob = [r["nombre"] for r in results if r["jb_status"] == 200 and not r["developer"]]
    if sin_inmob: print(f"  ⚠ sin developerName: {sin_inmob}", flush=True)

    (OUT / "diag_csv.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n✓ JSON detallado en imports/_diag_csv/diag_csv.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
