"""
debug_general.py — Debug exhaustivo de todos los proyectos importados v2.
Detecta inconsistencias entre lo que bc-api tiene y lo que el frontend espera.
"""
import os, json, httpx
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = [os.environ.get("PID_BC", "vespucio-capital")]

# Valores válidos según data/datasets.js
VALID_ENUMS = {
    "tipo_pie": {"Obligatorio", "Opcional", ""},
    "tipo_descuento": {"Todo", "Solo Unidad", ""},
    "tipo_bono_pie": {"Todo", "No", "Solo Unidad", ""},
    "tipo_reserva": {"Pie", "Gastos operacionales", "A devolver", ""},
    "destino_reserva": {"Broker", "Inmobiliaria", ""},
    "tipo_cuenta": {"Cuenta Corriente", "Cuenta Vista", "Cuenta de Ahorro", "CuentaRUT", ""},
    "permiso_construccion": {"1", "0", "tramite", ""},
    "stock_type": {"Compartido", "Exclusivo", "Propio", ""},
}


def gp(o, *path):
    for k in path:
        if not isinstance(o, dict): return None
        o = o.get(k)
    return o


def check(p):
    """Devuelve lista de (nivel, mensaje) — nivel: ERROR/WARN/INFO."""
    out = []
    extra = p.get("extra") or {}
    pid = p.get("id")
    nombre = p.get("nombre") or pid

    # ── 1. Inmobiliaria ──
    inmob = p.get("inmobiliaria")
    if not inmob:
        out.append(("ERROR", "inmobiliaria vacía"))
    elif inmob.lower() == "bigcapital":
        out.append(("ERROR", f"inmobiliaria='BigCapital' (debe ser desarrolladora real)"))

    # ── 2. Modelos ──
    modelos = extra.get("modelos") or []
    if not modelos:
        out.append(("ERROR", "0 modelos en extra"))
    else:
        sin_nombre = sum(1 for m in modelos if not m.get("nombre"))
        if sin_nombre:
            out.append(("ERROR", f"{sin_nombre} modelos sin nombre"))
        # nombres duplicados
        nombres = [m.get("nombre") for m in modelos if m.get("nombre")]
        dup = [n for n, c in Counter(nombres).items() if c > 1]
        if dup:
            out.append(("WARN", f"nombres de modelo DUPLICADOS: {dup[:5]}"))
        # plantas: si hay varios sin planta_url
        sin_planta = sum(1 for m in modelos if not m.get("planta_url"))
        if sin_planta and sin_planta < len(modelos):
            out.append(("INFO", f"{sin_planta}/{len(modelos)} modelos sin planta_url (dato JB)"))
        elif sin_planta == len(modelos):
            out.append(("WARN", f"TODOS los {len(modelos)} modelos sin planta_url"))
        # plantas colapsadas (misma planta para varios modelos)
        plantas = [m.get("planta_url") for m in modelos if m.get("planta_url")]
        plantas_dup = [pl for pl, c in Counter(plantas).items() if c > 1]
        if plantas_dup:
            out.append(("ERROR", f"PLANTA COLAPSADA: misma planta_url para varios modelos: {plantas_dup[:2]}"))

    # ── 3. Unidades ──
    unidades = p.get("unidades") or []
    if not unidades:
        out.append(("INFO", "0 unidades (JB no publica detalle de stock)"))
    else:
        # huérfanas
        mnames = {m.get("nombre") for m in modelos}
        huer = [u.get("numero") for u in unidades if u.get("modelo") not in mnames]
        if huer:
            out.append(("ERROR", f"{len(huer)} unidades huérfanas (modelo no existe): muestra {huer[:5]}"))
        # sin sup_total
        sin_sup = sum(1 for u in unidades if not u.get("sup_total"))
        if sin_sup:
            out.append(("WARN", f"{sin_sup}/{len(unidades)} unidades sin sup_total"))
        # orientaciones crudas (no abreviadas)
        orient = Counter(u.get("orientacion") for u in unidades if u.get("orientacion"))
        crudas = [o for o in orient if o and len(o) > 3]
        if crudas:
            out.append(("WARN", f"orientaciones CRUDAS (no abreviadas): {crudas}"))
        # estac_flag/bodega_flag valores válidos
        flags_invalid = []
        for u in unidades:
            for f in ("estac_flag", "bodega_flag", "pack_flag"):
                v = u.get(f)
                if v and v not in ("optional", "required", "never"):
                    flags_invalid.append(f"{f}={v!r}")
        if flags_invalid:
            out.append(("WARN", f"flags invalid (esperado optional/required/never): {flags_invalid[:3]}"))

    # ── 4. Imágenes ──
    imgs = p.get("imagenes") or []
    if not imgs:
        out.append(("WARN", "0 imágenes"))
    else:
        principal = sum(1 for i in imgs if i.get("es_principal"))
        if principal == 0:
            out.append(("ERROR", "ninguna imagen marcada como principal"))
        elif principal > 1:
            out.append(("ERROR", f"{principal} imágenes marcadas como principal (debe ser 1)"))
        # foto_principal_url consistente
        fp = p.get("foto_principal_url")
        if principal == 1 and not fp:
            out.append(("WARN", "es_principal=true pero foto_principal_url vacío en top-level"))

    # ── 5. Enums (catálogo del frontend) ──
    enum_checks = [
        ("tipo_pie", gp(extra, "comercial", "tipo_pie")),
        ("tipo_descuento", gp(extra, "comercial", "tipo_descuento")),
        ("tipo_bono_pie", gp(extra, "comercial", "tipo_bono_pie")),
        ("tipo_reserva", gp(extra, "comercial", "tipo_reserva")),
        ("destino_reserva", gp(extra, "comercial", "destino_reserva")),
        ("tipo_cuenta", gp(extra, "cuenta_reserva", "tipo_cuenta")),
        ("permiso_construccion", gp(extra, "fisicos", "permiso_construccion")),
        ("stock_type", extra.get("stock_type")),
    ]
    for campo, v in enum_checks:
        if v and str(v) not in VALID_ENUMS.get(campo, set()):
            out.append(("ERROR", f"enum '{campo}'={v!r} NO está en catálogo {sorted(VALID_ENUMS[campo])[:5]}"))

    # ── 6. Físicos: totales vs reales ──
    fis = extra.get("fisicos") or {}
    estac_dec = fis.get("estacionamientos_totales") or fis.get("estac_totales")
    bod_dec = fis.get("bodegas_totales")
    estac_real = len(extra.get("estacionamientos_dom") or extra.get("estacionamientos") or [])
    bod_real = len(extra.get("bodegas_dom") or extra.get("bodegas") or [])
    if estac_dec and estac_dec not in (0, "0") and estac_real and abs(int(estac_dec) - estac_real) > 5:
        out.append(("INFO", f"estac declarado={estac_dec} vs real={estac_real}"))
    if bod_dec and bod_dec not in (0, "0") and bod_real and abs(int(bod_dec) - bod_real) > 5:
        out.append(("INFO", f"bodegas declarado={bod_dec} vs real={bod_real}"))
    if estac_real and (not estac_dec or estac_dec in (0, "0")):
        out.append(("INFO", f"estac.totales=0 pero hay {estac_real} reales (JB no declara totales)"))
    if bod_real and (not bod_dec or bod_dec in (0, "0")):
        out.append(("INFO", f"bodegas.totales=0 pero hay {bod_real} reales"))

    # ── 7. GPS ──
    if not p.get("gps_lat") or not p.get("gps_lon"):
        out.append(("WARN", "sin GPS (lat/lon)"))

    # ── 8. Campos clave ──
    for campo in ("nombre", "comuna", "direccion"):
        if not p.get(campo):
            out.append(("WARN", f"campo top-level '{campo}' vacío"))

    return nombre, out


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    total_errors = total_warns = total_info = 0
    summary = []
    for pid in PIDS:
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"\n### {pid}: ERROR cargando ({e})")
            continue
        nombre, issues = check(p)
        errs = [m for lv, m in issues if lv == "ERROR"]
        warns = [m for lv, m in issues if lv == "WARN"]
        infos = [m for lv, m in issues if lv == "INFO"]
        total_errors += len(errs); total_warns += len(warns); total_info += len(infos)
        print(f"\n### {nombre} ({pid})")
        if not issues:
            print(f"   ✓ sin observaciones")
        for lv, m in issues:
            sym = {"ERROR": "🔴", "WARN": "🟡", "INFO": "ℹ"}[lv]
            print(f"   {sym} {lv}: {m}")
        summary.append((pid, len(errs), len(warns), len(infos)))

    print(f"\n{'═'*70}")
    print(f"RESUMEN GLOBAL")
    print(f"{'═'*70}")
    print(f"{'Proyecto':<35} {'🔴 ERR':<8} {'🟡 WARN':<9} {'ℹ INFO':<8}")
    for pid, e, w, i in summary:
        print(f"{pid:<35} {e:<8} {w:<9} {i:<8}")
    print(f"{'TOTAL':<35} {total_errors:<8} {total_warns:<9} {total_info:<8}")


if __name__ == "__main__":
    main()
