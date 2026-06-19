"""
patch_orientacion.py — Normaliza orientaciones almacenadas a abreviatura ES (N/S/O/P/NO/...).

NO-DESTRUCTIVO: por cada unidad con orientación en palabra completa ('Norte','Nor-Oriente'),
mayúscula ('NORTE') o basura ('-1','SN','EAS'), reescribe SOLO el campo `orientacion`
vía PUT puntual. No toca modelo, precios ni otros campos. No hace wipe.

Basura (nivel '-1', códigos) → orientación se deja vacía (mejor que mostrar '-2' al cliente).

Env: BC_API_JWT
Uso (workflow): patch-orientacion.yml -f pids="brasil,tocornal,..."  (vacío = TODOS los míos)
"""
import os, re, httpx

BC = "https://bc-api.178-105-91-29.nip.io"
VALID = re.compile(r"^[NSOP]{1,3}$")


def facing_es(f):
    if not f:
        return None
    k = str(f).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    m = {"north":"N","south":"S","east":"O","west":"P",
         "northeast":"NO","northwest":"NP","southeast":"SO","southwest":"SP",
         "norte":"N","sur":"S","oriente":"O","poniente":"P","este":"O","oeste":"P",
         "nororiente":"NO","norponiente":"NP","suroriente":"SO","surponiente":"SP",
         "orientenorte":"NO","ponientenorte":"NP","orientesur":"SO","ponientesur":"SP"}
    if k in m:
        return m[k]
    parts = []
    for full, ab in (("norte","N"),("sur","S"),("oriente","O"),("poniente","P"),("este","O"),("oeste","P")):
        if full in k and ab not in parts:
            parts.append(ab)
    if parts:
        return "".join(parts)
    up = str(f).strip().upper()
    return up if VALID.match(up) else None


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=60)
    pids_env = os.environ.get("PIDS", "").strip()
    if pids_env:
        pids = [p.strip() for p in pids_env.split(",") if p.strip()]
    else:
        pids = [p["id"] for p in cli.get("/proyectos").json()]

    tot_fix = tot_clear = tot_ok = 0
    for pid in pids:
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"❌ {pid}: {e}"); continue
        unidades = p.get("unidades") or []
        cambios = []
        for u in unidades:
            cur = u.get("orientacion")
            if cur is None or cur == "" or VALID.match(str(cur)):
                tot_ok += 1; continue
            nuevo = facing_es(cur)
            if nuevo != cur:
                cambios.append((u, cur, nuevo))
        if not cambios:
            continue
        ok = 0
        for u, cur, nuevo in cambios:
            body = {k: u.get(k) for k in (
                "numero","modelo","tipologia","tipo","orientacion","sup_total","sup_interior",
                "sup_terraza","sup_logia","sup_jardin","precio_lista_uf","precio_final_uf",
                "descuento_pct","bono_pie_pct","estac_flag","bodega_flag","pack_flag",
                "disponible","id_externo") if u.get(k) is not None}
            body["orientacion"] = nuevo or ""
            body["descuento_pct"] = u.get("descuento_pct") or 0
            body["bono_pie_pct"] = u.get("bono_pie_pct") or 0
            try:
                r = cli.put(f"/proyectos/{pid}/unidades/{u['id']}", json=body)
                if r.status_code in (200, 201):
                    ok += 1
                    if nuevo: tot_fix += 1
                    else: tot_clear += 1
            except Exception:
                pass
        print(f"▸ {p.get('nombre')!r} ({pid}): {ok}/{len(cambios)} orientaciones normalizadas")
    print(f"\n{'='*60}\n  ✓ {tot_fix} normalizadas · {tot_clear} basura→vacío · {tot_ok} ya OK\n{'='*60}")


if __name__ == "__main__":
    main()
