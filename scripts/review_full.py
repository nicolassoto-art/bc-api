"""review_full.py — Revisión EXHAUSTIVA de un proyecto importado v2.
Combina: datos crudos + integridad + visual + cross-check JB.
"""
import os, json, httpx
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
PID = os.environ.get("PID_BC", "vespucio-capital")


def gp(o, *path):
    for k in path:
        if not isinstance(o, dict): return None
        o = o.get(k)
    return o


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    p = cli.get(f"/proyectos/{PID}").json()
    extra = p.get("extra") or {}
    modelos = extra.get("modelos") or []
    unidades = p.get("unidades") or []
    imgs = p.get("imagenes") or []
    estac = extra.get("estacionamientos_dom") or extra.get("estacionamientos") or []
    bod = extra.get("bodegas_dom") or extra.get("bodegas") or []
    packs = extra.get("packs_dom") or extra.get("packs") or []

    print(f"\n{'═'*80}")
    print(f"REVISIÓN COMPLETA — {p.get('nombre')} ({PID})")
    print(f"{'═'*80}\n")

    # 1. FICHA GENERAL
    print("📋 [1] FICHA GENERAL")
    print(f"   nombre:         {p.get('nombre')!r}")
    print(f"   inmobiliaria:   {p.get('inmobiliaria')!r}")
    print(f"   comuna/región:  {p.get('comuna')!r} / {p.get('region')!r}")
    print(f"   dirección:      {p.get('direccion')!r}")
    print(f"   GPS:            {p.get('gps_lat')}, {p.get('gps_lon')}")
    print(f"   fase:           {p.get('fase')!r}")
    print(f"   modalidad:      {p.get('modalidad')!r}")
    print(f"   entrega:        {p.get('fecha_entrega')!r} / {p.get('ano_entrega')!r}")
    print(f"   foto_principal: {'sí ✓' if p.get('foto_principal_url') else 'NO ✗'}")
    print(f"   disponible:     {p.get('disponible')}")
    print(f"   created/updated:{p.get('created_at')} / {p.get('updated_at')}")

    # 2. FÍSICOS
    fis = extra.get("fisicos") or {}
    print(f"\n🏗️  [2] DATOS FÍSICOS")
    print(f"   pisos:                  {fis.get('pisos')!r}")
    print(f"   unidades_totales:       {fis.get('unidades_totales')!r}")
    print(f"   unidades_por_piso:      {fis.get('unidades_por_piso')!r}")
    print(f"   estac_totales (decl):   {fis.get('estacionamientos_totales') or fis.get('estac_totales')!r}  · REAL: {len(estac)}")
    print(f"   bodegas_totales (decl): {fis.get('bodegas_totales')!r}  · REAL: {len(bod)}")
    print(f"   ascensores:             {fis.get('ascensores')!r}")
    print(f"   constructora:           {fis.get('constructora')!r}")
    print(f"   permiso construcción:   {fis.get('permiso_construccion')!r} / nº {fis.get('numero_permiso')!r}")
    print(f"   acepta cesión:          {fis.get('acepta_cesion')!r}")

    # 3. COMERCIAL
    com = extra.get("comercial") or {}
    print(f"\n💰 [3] CONDICIONES COMERCIALES")
    print(f"   pie %:           {com.get('pie_pct')!r}  · tipo: {com.get('tipo_pie')!r}")
    print(f"   cuotón inicial:  {com.get('cuoton_inicial_pct')!r}%  · final: {com.get('cuoton_final_pct')!r}%")
    print(f"   tipo descuento:  {com.get('tipo_descuento')!r}")
    print(f"   tipo bono pie:   {com.get('tipo_bono_pie')!r}")
    print(f"   reserva:         CLP {com.get('valor_reserva_clp')!r} · tipo: {com.get('tipo_reserva')!r} · destino: {com.get('destino_reserva')!r}")
    print(f"   valor cuota:     CLP {com.get('valor_cuota_clp')!r}")

    # 4. FORMAS DE PAGO PIE
    fpp = extra.get("formas_pago_pie") or {}
    print(f"\n💳 [4] FORMAS DE PAGO PIE")
    print(f"   cuotas pre-entrega:  {fpp.get('cuotas_pre_entrega')!r}  · método: {fpp.get('pago_pre_entrega')!r}")
    print(f"   cuotas post-entrega: {fpp.get('cuotas_post_entrega')!r}  · método: {fpp.get('pago_post_entrega')!r}")
    print(f"   pago cuotón inicial: {fpp.get('pago_cuoton_inicial')!r}")

    # 5. CUENTA RESERVA
    cta = extra.get("cuenta_reserva") or {}
    print(f"\n🏦 [5] CUENTA RESERVA")
    print(f"   titular:      {cta.get('titular_nombre')!r}  · RUT: {cta.get('titular_rut')!r}")
    print(f"   banco:        {cta.get('banco')!r}")
    print(f"   tipo cuenta:  {cta.get('tipo_cuenta')!r}")
    print(f"   nº cuenta:    {cta.get('numero_cuenta')!r}")
    print(f"   link pago:    {cta.get('link_pago')!r}")

    # 6. SPA
    spa = extra.get("spa_proyecto") or {}
    print(f"\n📄 [6] SPA DEL PROYECTO")
    print(f"   nombre:    {spa.get('nombre')!r}")
    print(f"   RUT:       {spa.get('rut')!r}")
    print(f"   dirección: {spa.get('direccion')!r}")

    # 7. PROMOCIONES + DESCRIPCIÓN
    print(f"\n🎁 [7] PROMOCIONES Y CONTENIDO")
    print(f"   promoción broker:   {(extra.get('promocion_broker') or '')[:80]!r}")
    print(f"   promoción cliente:  {(extra.get('promocion_cliente') or '')[:80]!r}")
    print(f"   descripción:        {(extra.get('descripcion') or '')[:80]!r} ({len(extra.get('descripcion') or '')}c)")
    print(f"   notas HTML:         {len(extra.get('notas_html') or '')}c")
    print(f"   condiciones espec.: {(extra.get('condiciones_especiales') or '')[:80]!r}")
    print(f"   stock_type:         {extra.get('stock_type')!r}")
    print(f"   solicita preap.:    {extra.get('solicita_preaprobacion')!r}")
    print(f"   etiquetas:          {extra.get('etiquetas')}")
    print(f"   equipamiento ({len(extra.get('equipamiento') or [])}): {(extra.get('equipamiento') or [])[:6]}")
    print(f"   áreas comunes ({len(extra.get('areas_comunes') or [])}): {(extra.get('areas_comunes') or [])[:6]}")
    print(f"   entorno ({len(extra.get('entorno') or [])}): {(extra.get('entorno') or [])[:6]}")

    # 8. MODELOS
    print(f"\n🏠 [8] MODELOS ({len(modelos)})")
    plantas_set = {m.get("planta_url") for m in modelos if m.get("planta_url")}
    print(f"   con planta_url: {sum(1 for m in modelos if m.get('planta_url'))}/{len(modelos)} · plantas DISTINTAS: {len(plantas_set)}")
    for m in modelos:
        flags = f"bod={m.get('cotiza_bodega')}/est={m.get('cotiza_estac')}/pack={m.get('cotiza_pack')}"
        print(f"   • {m.get('nombre')!r:30} {m.get('dormitorios')}D/{m.get('banos')}B  planta={'sí' if m.get('planta_url') else 'NO'}  {flags}")

    # 9. UNIDADES — detalle
    print(f"\n🚪 [9] UNIDADES ({len(unidades)})")
    disp = sum(1 for u in unidades if u.get("disponible"))
    print(f"   disponibles: {disp}/{len(unidades)}")
    orient = Counter(u.get("orientacion") for u in unidades if u.get("orientacion"))
    print(f"   orientaciones: {dict(orient)}")
    by_modelo = Counter(u.get("modelo") for u in unidades)
    print(f"   por modelo: {dict(by_modelo)}")
    # rango sup/precios
    sups = [u.get("sup_total") for u in unidades if u.get("sup_total")]
    precios = [u.get("precio_lista_uf") for u in unidades if u.get("precio_lista_uf")]
    if sups: print(f"   sup_total: min={min(sups)} max={max(sups)} promedio={sum(sups)/len(sups):.1f}")
    if precios: print(f"   precio UF: min={min(precios)} max={max(precios)} promedio={sum(precios)/len(precios):.1f}")
    # 5 superficies
    sup_int = sum(1 for u in unidades if u.get("sup_interior"))
    sup_terr = sum(1 for u in unidades if u.get("sup_terraza"))
    sup_log = sum(1 for u in unidades if u.get("sup_logia"))
    sup_jar = sum(1 for u in unidades if u.get("sup_jardin"))
    print(f"   con sup_interior: {sup_int}/{len(unidades)} · terraza: {sup_terr} · logia: {sup_log} · jardín: {sup_jar}")
    # huérfanas
    mnames = {m.get("nombre") for m in modelos}
    huer = [u.get("numero") for u in unidades if u.get("modelo") not in mnames]
    if huer:
        print(f"   ⚠ huérfanas (modelo no existe): {huer}")
    else:
        print(f"   ✓ 0 huérfanas")
    # ejemplo unidad
    if unidades:
        u0 = unidades[0]
        print(f"\n   Ejemplo unidad #0:")
        for k in ("numero","modelo","tipologia","tipo","orientacion","sup_total","sup_interior",
                  "sup_terraza","sup_logia","sup_jardin","precio_lista_uf","precio_final_uf",
                  "descuento_pct","bono_pie_pct","estac_flag","bodega_flag","pack_flag","disponible","id_externo"):
            print(f"      {k}: {u0.get(k)!r}")

    # 10. ESTACIONAMIENTOS
    print(f"\n🚗 [10] ESTACIONAMIENTOS ({len(estac)})")
    nivs = Counter()
    precios_e = []
    disp_e = 0
    for e in estac:
        c = e.get("cells") or [None, e.get("numero"), e.get("precio_uf"), e.get("nivel")]
        if len(c) > 3 and c[3]: nivs[str(c[3])] += 1
        if len(c) > 2 and c[2]:
            try: precios_e.append(float(c[2]))
            except: pass
        if e.get("disponible", True): disp_e += 1
    print(f"   disponibles: {disp_e}/{len(estac)}")
    print(f"   niveles: {dict(nivs)}")
    if precios_e: print(f"   precio UF: min={min(precios_e)} max={max(precios_e)} promedio={sum(precios_e)/len(precios_e):.1f}")

    # 11. BODEGAS
    print(f"\n📦 [11] BODEGAS ({len(bod)})")
    disp_b = 0
    sups_b = []
    precios_b = []
    for b in bod:
        c = b.get("cells") or [None, b.get("numero"), b.get("precio_uf"), b.get("superficie")]
        if b.get("disponible", True): disp_b += 1
        if len(c) > 2 and c[2]:
            try: precios_b.append(float(c[2]))
            except: pass
        if len(c) > 3 and c[3]:
            try: sups_b.append(float(c[3]))
            except: pass
    print(f"   disponibles: {disp_b}/{len(bod)}")
    if precios_b: print(f"   precio UF: min={min(precios_b)} max={max(precios_b)} promedio={sum(precios_b)/len(precios_b):.1f}")
    if sups_b: print(f"   superficie m²: min={min(sups_b)} max={max(sups_b)} promedio={sum(sups_b)/len(sups_b):.1f}")
    else: print(f"   ⚠ ninguna bodega tiene superficie")

    # 12. PACKS
    print(f"\n📦 [12] PACKS ({len(packs)})")
    if not packs: print(f"   (sin packs)")
    for pk in packs[:5]:
        print(f"   • nº={pk.get('numero')!r} precio={pk.get('precio_uf')!r} estac={pk.get('estacionamientos')} bodegas={pk.get('bodegas')}")

    # 13. IMÁGENES
    print(f"\n📷 [13] IMÁGENES ({len(imgs)})")
    cats = Counter(i.get("categoria") for i in imgs)
    print(f"   por categoría: {dict(cats)}")
    principal = [i for i in imgs if i.get("es_principal")]
    pri_cat = repr(principal[0].get("categoria")) if principal else "—"
    print(f"   principal: {len(principal)} ({pri_cat})")
    # plantas únicas
    planta_cats = [c for c in cats if c and c.startswith("jb-planta-")]
    print(f"   plantas: {len(planta_cats)} (debe ser = a #modelos con planta)")

    # 14. VERIFICACIÓN HTTP de URLs
    print(f"\n🌐 [14] VERIFICACIÓN URLs (HEAD)")
    if p.get("foto_principal_url"):
        u = p["foto_principal_url"]
        full = u if u.startswith("http") else BC + u
        try:
            r = cli.head(full)
            print(f"   foto_principal_url: HTTP {r.status_code}")
        except Exception as e:
            print(f"   foto_principal_url: ERR {e}")
    print(f"   plantas de modelos (muestra 3):")
    for m in modelos[:3]:
        u = m.get("planta_url")
        if u:
            full = u if u.startswith("http") else BC + u
            try:
                r = cli.head(full)
                print(f"     {m.get('nombre')!r:8} → HTTP {r.status_code} · {full}")
            except Exception as e:
                print(f"     {m.get('nombre')!r}: ERR {e}")

    # 15. VEREDICTO
    print(f"\n{'═'*80}")
    print(f"VEREDICTO")
    print(f"{'═'*80}")
    issues = []
    if not p.get("inmobiliaria") or p["inmobiliaria"].lower() == "bigcapital":
        issues.append("inmobiliaria mal")
    if len(modelos) > 0 and len(plantas_set) < sum(1 for m in modelos if m.get("planta_url")):
        issues.append("plantas colapsadas")
    if huer: issues.append(f"{len(huer)} huérfanas")
    if not principal: issues.append("sin foto principal")
    if not issues:
        print(f"   ✓ TODO OK · sin issues bloqueantes")
    else:
        for i in issues: print(f"   🔴 {i}")


if __name__ == "__main__":
    main()
