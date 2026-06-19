"""diag_modelo_invalido.py — Dump de proyectos con uds que apuntan a modelo inexistente.
Solo lectura. Para diseñar el patch correcto."""
import os, httpx, json
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = ["edificio-vista-amunategui","vista-san-martin","edificio-vista-morande",
        "guillermo-mann-1401","independencia-4745","don-ignacio","los-alerces",
        "tocornal","vicu-a-mackenna-1796","froilan-roa"]


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=60)
    # resolver slugs reales por nombre si no existen
    lst = cli.get("/proyectos").json()
    import unicodedata, re
    def slug(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+","-",s).strip("-")
    by_slug = {slug(p.get("id") or ""): p["id"] for p in lst}
    by_name = {slug(p.get("nombre") or ""): p["id"] for p in lst}

    for want in PIDS:
        pid = by_slug.get(want) or by_name.get(want) or want
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"❌ {want}: {e}"); continue
        extra = p.get("extra") or {}
        modelos = extra.get("modelos") or []
        unidades = p.get("unidades") or []
        nombres = {(m.get("nombre") or "").strip() for m in modelos if isinstance(m, dict)}
        print(f"\n{'='*78}\n  {p.get('nombre')!r}  ({pid})  · {len(unidades)} uds · {len(modelos)} modelos")
        print(f"{'='*78}")
        # modelos disponibles
        print("  extra.modelos (nombre · D/B · tipologia):")
        for m in modelos[:30]:
            if isinstance(m, dict):
                print(f"    · {m.get('nombre')!r:30} D={m.get('dormitorios')} B={m.get('banos')} "
                      f"tip={m.get('tipologia')!r} plano={'sí' if (m.get('planta_url') or m.get('plano_url')) else 'no'}")
        # unidades huérfanas/inválidas
        bad = [u for u in unidades if u.get("modelo") and u.get("modelo") not in nombres]
        vac = [u for u in unidades if not u.get("modelo")]
        print(f"\n  INVÁLIDAS ({len(bad)}) · VACÍAS ({len(vac)}):")
        cnt = Counter(u.get("modelo") for u in bad)
        for modelo_val, c in cnt.most_common(15):
            # muestra una unidad de ejemplo
            ej = next(u for u in bad if u.get("modelo") == modelo_val)
            print(f"    modelo={modelo_val!r} ×{c} · ej: numero={ej.get('numero')!r} "
                  f"tip={ej.get('tipologia')!r} ST={ej.get('sup_total')} D={ej.get('dormitorios')} B={ej.get('banos')}")
        if vac:
            ejv = vac[0]
            print(f"    [vacías] ej: numero={ejv.get('numero')!r} tip={ejv.get('tipologia')!r} "
                  f"ST={ejv.get('sup_total')} D={ejv.get('dormitorios')} B={ejv.get('banos')}")


if __name__ == "__main__":
    main()
