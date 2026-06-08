"""Verifica ambigüedad de (D,B) para los 6 proyectos afectados. Solo lectura."""
import os, httpx, re
from collections import defaultdict, Counter
BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = ["los-lilenes", "vespucio-capital", "brasil", "edificio-serrano-capital", "vivaceta-864", "don-ignacio"]
jwt = os.environ["BC_API_JWT"]
cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
total_huer = 0
total_recuperables = 0
total_ambig = 0
total_no_match = 0
for pid in PIDS:
    p = cli.get(f"/proyectos/{pid}").json()
    modelos = (p.get("extra") or {}).get("modelos") or []
    unidades = p.get("unidades") or []
    print(f"\n{'='*70}\n  {pid}\n{'='*70}")
    by_db = defaultdict(list)
    for m in modelos:
        d = m.get("dormitorios"); b = m.get("banos"); n = m.get("nombre")
        if d is not None and b is not None and n:
            try:
                by_db[(int(d), int(b))].append(n)
            except (ValueError, TypeError):
                pass
    sin_modelo = [u for u in unidades if not u.get("modelo")]
    tipologias_sin_m = Counter(u.get("tipologia") for u in sin_modelo)
    print(f"  Modelos del proyecto ({len(modelos)}):")
    hay_ambig = False
    for (d, b), names in sorted(by_db.items()):
        if len(names) > 1:
            hay_ambig = True
            print(f"    ({d}D,{b}B) → {names}   ⚠ AMBIGUO")
        else:
            print(f"    ({d}D,{b}B) → '{names[0]}'   ✓")
    print(f"\n  Huérfanas: {len(sin_modelo)} unidades, por tipología:")
    for tip, cnt in tipologias_sin_m.most_common():
        total_huer += cnt
        m = re.search(r"(\d+)\s*D[^\d]*(\d+)\s*B", (tip or "").upper())
        if m:
            d, b = int(m.group(1)), int(m.group(2))
            target = by_db.get((d, b), [])
            if len(target) == 1:
                print(f"    {tip!r:15} × {cnt:>3}   → asignar '{target[0]}' ✓")
                total_recuperables += cnt
            elif len(target) > 1:
                print(f"    {tip!r:15} × {cnt:>3}   ⚠ AMBIGUO {target}")
                total_ambig += cnt
            else:
                print(f"    {tip!r:15} × {cnt:>3}   ✗ no matchea")
                total_no_match += cnt
        else:
            print(f"    {tip!r:15} × {cnt:>3}   ? tipología no parseable")
            total_no_match += cnt

print(f"\n{'='*70}\n  RESUMEN GLOBAL\n{'='*70}")
print(f"  Total huérfanas:        {total_huer}")
print(f"  Recuperables (único):   {total_recuperables}  ✓")
print(f"  Ambiguas (>1 modelo):   {total_ambig}  ⚠")
print(f"  Sin match en proyecto:  {total_no_match}  ✗")
