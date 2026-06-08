"""
patch_modelo_huerfanas.py — Repara unidades con modelo="" en proyectos afectados.

Estrategia:
  • Para 5 proyectos seguros (Los Lilenes, Vespucio, Brasil, Vivaceta 864, Serrano):
    auto-asignar modelo basado en (dormitorios, baños) de la tipología, matcheando
    contra extra.modelos. Si (D,B) es único → asigna. Si es ambiguo → deja vacío.
  • Para Don Ignacio: agregar extra._deptos_con_warning con los 100 deptos sin modelo
    (el frontend ya lee esto y muestra badge rojo en la vista pública).

Solo escribe:
  • PUT /proyectos/{id}/unidades/{u_id} para cada unidad recuperable
  • PUT /proyectos/{id} solo en Don Ignacio para agregar el warning a extra

Env: BC_API_JWT
"""
import os, re, httpx
from collections import defaultdict, Counter

BC = "https://bc-api.178-105-91-29.nip.io"
SEGUROS = ["los-lilenes", "vespucio-capital", "brasil", "edificio-serrano-capital", "vivaceta-864"]
WARNING_ONLY = ["don-ignacio"]


def parse_db(tip):
    """'2D - 1B' → (2, 1)."""
    if not tip:
        return (None, None)
    m = re.search(r"(\d+)\s*D[^\d]*(\d+)\s*B", tip.upper())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=40)
    print(f"{'═'*72}\n   PATCH DE UNIDADES HUÉRFANAS — MODO NO-DESTRUCTIVO\n{'═'*72}\n")

    # ───── A) Proyectos seguros: auto-asignar modelo ─────
    for pid in SEGUROS:
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"❌ {pid}: error cargando ({e})\n")
            continue
        modelos = (p.get("extra") or {}).get("modelos") or []
        unidades = p.get("unidades") or []
        # mapa (D,B) → [nombres]
        by_db = defaultdict(list)
        for m in modelos:
            if not isinstance(m, dict): continue
            try:
                d = int(m.get("dormitorios")) if m.get("dormitorios") is not None else None
                b = int(m.get("banos")) if m.get("banos") is not None else None
            except (ValueError, TypeError):
                d = b = None
            n = (m.get("nombre") or "").strip()
            if d is not None and b is not None and n:
                by_db[(d, b)].append(n)
        ambiguos = {k for k, v in by_db.items() if len(v) > 1}
        unicos = {k: v[0] for k, v in by_db.items() if len(v) == 1}

        sin_modelo = [u for u in unidades if not u.get("modelo")]
        cambios = []
        no_match = []
        ambig = []
        for u in sin_modelo:
            d, b = parse_db(u.get("tipologia") or "")
            if d is None:
                no_match.append((u.get("numero"), u.get("tipologia"), "tipología no parseable"))
                continue
            if (d, b) in ambiguos:
                ambig.append((u.get("numero"), (d, b), by_db[(d, b)]))
                continue
            target = unicos.get((d, b))
            if not target:
                no_match.append((u.get("numero"), (d, b), "sin modelo (D,B) en proyecto"))
                continue
            cambios.append((u, target))

        print(f"▸ {p.get('nombre')!r} ({pid})")
        print(f"   huérfanas: {len(sin_modelo)} · recuperables: {len(cambios)} · ambiguas: {len(ambig)} · sin_match: {len(no_match)}")
        ok = 0
        errors = []
        for u, target in cambios:
            # PUT con TODOS los campos de la unidad (formato que espera el endpoint).
            body = {k: u.get(k) for k in (
                "numero", "modelo", "tipologia", "tipo", "orientacion",
                "sup_total", "sup_interior", "sup_terraza", "sup_logia", "sup_jardin",
                "precio_lista_uf", "precio_final_uf", "descuento_pct", "bono_pie_pct",
                "estac_flag", "bodega_flag", "pack_flag", "disponible", "id_externo",
            ) if u.get(k) is not None}
            body["modelo"] = target
            body["descuento_pct"] = u.get("descuento_pct") or 0
            body["bono_pie_pct"] = u.get("bono_pie_pct") or 0
            try:
                r = cli.put(f"/proyectos/{pid}/unidades/{u['id']}", json=body)
                if r.status_code in (200, 201):
                    ok += 1
                else:
                    errors.append((u.get("numero"), r.status_code, r.text[:120]))
            except Exception as e:
                errors.append((u.get("numero"), "ERR", str(e)[:80]))
        print(f"   ✓ asignadas: {ok}/{len(cambios)}")
        if errors[:3]:
            print(f"   errores (primeros 3): {errors[:3]}")
        print()

    # ───── B) Don Ignacio: warning en extra (sin asignar modelo) ─────
    for pid in WARNING_ONLY:
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"❌ {pid}: error cargando ({e})\n"); continue
        unidades = p.get("unidades") or []
        sin_modelo = [u for u in unidades if not u.get("modelo")]
        # construir lista de warnings
        warnings = [{"numero": u.get("numero"), "modelo": u.get("tipologia") or "?"} for u in sin_modelo]
        extra = dict(p.get("extra") or {})
        extra["_deptos_con_warning"] = warnings
        # PUT proyecto con solo el extra actualizado (no toca unidades ni imagenes)
        body = {k: p[k] for k in p
                if k not in ("id", "unidades", "imagenes", "documentos", "created_at", "updated_at", "timeline")}
        body["extra"] = extra
        r = cli.put(f"/proyectos/{pid}", json=body)
        print(f"▸ {p.get('nombre')!r} ({pid})")
        print(f"   huérfanas (sin modelo): {len(sin_modelo)}")
        print(f"   ✓ warning agregado a extra._deptos_con_warning · PUT {r.status_code}")
        if r.status_code != 200:
            print(f"   error body: {r.text[:200]}")
        print()

    print(f"{'═'*72}\n   ✓ PATCH COMPLETO. Verificar con review-ingevec o debug-general.\n{'═'*72}")


if __name__ == "__main__":
    main()
