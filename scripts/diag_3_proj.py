import os, httpx
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url="https://bc-api.178-105-91-29.nip.io",
                   headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
for pid in ["jb-b7aniv5k"]:
    r = cli.get(f"/proyectos/{pid}")
    print(f"GET /proyectos/{pid} → HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  body: {r.text[:200]}")
        # buscar en listing
        lst = cli.get("/proyectos").json()
        cand = [q for q in lst if "b7aniv5k" in (q.get("id") or "") or "b7aniv5k" in (q.get("jb_id") or "")]
        if not cand:
            cand = [q for q in lst if (q.get("extra") or {}).get("jb_id") == "b7aniv5k"]
        for q in cand: print(f"  candidato: id={q.get('id')} nombre={q.get('nombre')}")
        continue
    p = r.json()
    extra = p.get("extra") or {}
    modelos = extra.get("modelos") or []
    print(f"\n=== {pid} · {p.get('nombre')} ===")
    print(f"modelos: {len(modelos)} · unidades: {len(p.get('unidades') or [])} · imgs: {len(p.get('imagenes') or [])}")
    cp, sp = 0, 0
    for m in modelos:
        if not isinstance(m, dict): continue
        n = m.get("nombre") or "?"
        u = m.get("planta_url") or ""
        t = m.get("planta_thumb_src") or ""
        if u or t: cp += 1
        else: sp += 1
        flag = "✓" if (u or t) else "✗"
        print(f"  {flag} '{n}' url={u[:50]!r:55s} thumb={t[:30]!r}")
    print(f"  TOTAL con planta: {cp}/{len(modelos)} · sin: {sp}")
