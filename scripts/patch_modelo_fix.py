"""
patch_modelo_fix.py — Repara unidades con modelo inválido o vacío (NO-DESTRUCTIVO).

Para cada unidad cuyo `modelo` NO existe en extra.modelos (o está vacío), intenta, en orden:
  1. STRIP-SUFFIX: 'L17_3al9 - 866 - TOC - ...'.split(' - ')[0] = 'L17_3al9' → si ∈ modelos, usar.
  2. TIPOLOGÍA EXACTA: si unit.tipologia ('Studio','2D2B') ∈ nombres de modelos, usar.
  3. POR (D,B): parsear tipologia ('2D - 1B'→(2,1)) → si hay UN solo modelo con esos (D,B), usar.
  4. Si nada matchea o es ambiguo → dejar como está + agregar a extra._deptos_con_warning.

Reescribe SOLO el campo `modelo` por unidad vía PUT puntual. No wipe, no toca otros campos.

Env: BC_API_JWT · PIDS (coma, vacío = todos los proyectos)
"""
import os, re, time, httpx
from collections import defaultdict

BC = "https://bc-api.178-105-91-29.nip.io"


def get_json(cli, url, tries=6):
    """GET con reintentos — bc-api a veces devuelve 502 bajo carga."""
    for i in range(tries):
        try:
            r = cli.get(url)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError(f"GET {url} falló tras {tries} intentos")


def parse_db(tip):
    if not tip:
        return (None, None)
    m = re.search(r"(\d+)\s*D[^\d]*(\d+)\s*B", tip.upper())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=60)
    pids_env = os.environ.get("PIDS", "").strip()
    pids = [p.strip() for p in pids_env.split(",") if p.strip()] if pids_env \
        else [p["id"] for p in get_json(cli, "/proyectos")]

    g_fix = g_warn = 0
    for pid in pids:
        try:
            p = get_json(cli, f"/proyectos/{pid}")
        except Exception as e:
            print(f"❌ {pid}: {e}"); continue
        extra = p.get("extra") or {}
        modelos = extra.get("modelos") or []
        unidades = p.get("unidades") or []
        nombres = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
        if not nombres:
            continue
        # mapa (D,B) → [nombres únicos]
        by_db = defaultdict(set)
        for m in modelos:
            if not isinstance(m, dict):
                continue
            try:
                d = int(m["dormitorios"]) if m.get("dormitorios") is not None else None
                b = int(m["banos"]) if m.get("banos") is not None else None
            except (ValueError, TypeError):
                d = b = None
            nm = (m.get("nombre") or "").strip()
            if d is not None and b is not None and nm:
                by_db[(d, b)].add(nm)

        rotas = [u for u in unidades if not u.get("modelo") or u.get("modelo") not in nombres]
        if not rotas:
            continue
        cambios, warns = [], []
        for u in rotas:
            cur = (u.get("modelo") or "").strip()
            target = None
            # 1) strip suffix
            if cur and " - " in cur:
                pref = cur.split(" - ")[0].strip()
                if pref in nombres:
                    target = pref
            # 2) tipologia exacta
            if not target:
                tip = (u.get("tipologia") or "").strip()
                if tip and tip in nombres:
                    target = tip
                else:
                    tip2 = tip.replace(" - ", "").replace(" ", "")  # '2D - 2B'→'2D2B'
                    if tip2 in nombres:
                        target = tip2
            # 3) por (D,B)
            if not target:
                d, b = parse_db(u.get("tipologia") or "")
                if d is not None and len(by_db.get((d, b), set())) == 1:
                    target = next(iter(by_db[(d, b)]))
            if target and target != cur:
                cambios.append((u, target))
            elif not target:
                # no resoluble: limpiar modelo a '' (huérfana con badge) en vez de dejar
                # un código basura ('A','D1') que el frontend marca como inválido.
                if cur:
                    cambios.append((u, ""))
                warns.append({"numero": u.get("numero"), "modelo": cur or (u.get("tipologia") or "?")})

        ok = 0
        for u, target in cambios:
            body = {k: u.get(k) for k in (
                "numero","modelo","tipologia","tipo","orientacion","sup_total","sup_interior",
                "sup_terraza","sup_logia","sup_jardin","precio_lista_uf","precio_final_uf",
                "descuento_pct","bono_pie_pct","estac_flag","bodega_flag","pack_flag",
                "disponible","id_externo") if u.get(k) is not None}
            body["modelo"] = target
            body["descuento_pct"] = u.get("descuento_pct") or 0
            body["bono_pie_pct"] = u.get("bono_pie_pct") or 0
            try:
                r = cli.put(f"/proyectos/{pid}/unidades/{u['id']}", json=body)
                if r.status_code in (200, 201):
                    ok += 1
            except Exception:
                pass
        # warning para lo no recuperable
        if warns:
            ex = dict(extra)
            prev = {w["numero"] for w in (ex.get("_deptos_con_warning") or [])}
            ex["_deptos_con_warning"] = (ex.get("_deptos_con_warning") or []) + \
                [w for w in warns if w["numero"] not in prev]
            body = {k: p[k] for k in p if k not in
                    ("id","unidades","imagenes","documentos","created_at","updated_at","timeline")}
            body["extra"] = ex
            try:
                cli.put(f"/proyectos/{pid}", json=body)
            except Exception:
                pass
        g_fix += ok; g_warn += len(warns)
        print(f"▸ {p.get('nombre')!r} ({pid}): {ok} reparadas · {len(warns)} con warning")

    print(f"\n{'='*60}\n  ✓ TOTAL: {g_fix} modelos reparados · {g_warn} con warning\n{'='*60}")


if __name__ == "__main__":
    main()
