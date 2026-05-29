"""Inspect proyectos con unidades huérfanas — diagnóstico de naming mismatch."""
import os
import httpx

jwt = os.environ['BC_API_JWT']
cli = httpx.Client(
    base_url='https://bc-api.178-105-91-29.nip.io',
    headers={'Authorization': f'Bearer {jwt}'},
    timeout=30,
)
for pid in ['jb-g3jwrroe', 'jb-9mubheq8', 'jb-c0xmpk4k', 'jb-kvrtrtxk', 'jb-86yw1rpt']:
    r = cli.get(f'/proyectos/{pid}').json()
    extra = r.get('extra') or {}
    modelos = extra.get('modelos') or []
    unidades = r.get('unidades') or []
    m_names = sorted({(m.get('nombre') or '').strip() for m in modelos if isinstance(m, dict)})
    u_modelos_counter = {}
    for u in unidades:
        nm = (u.get('modelo') or '').strip()
        u_modelos_counter[nm] = u_modelos_counter.get(nm, 0) + 1
    print(f"\n=== {r.get('nombre')} ({pid}) ===")
    print(f"  Modelos definidos ({len(m_names)}): {m_names[:25]}")
    print(f"  Unidades.modelo distintos ({len(u_modelos_counter)}):")
    for nm, cnt in sorted(u_modelos_counter.items()):
        match = '✓' if nm in {n.lower() for n in m_names} | set(m_names) else '✗'
        print(f"    {match} '{nm}' × {cnt}")
