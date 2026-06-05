"""verify_detail.py — Verifica el import (data + visual) de un proyecto en bc-api."""
from __future__ import annotations
import asyncio, os, sys
from pathlib import Path
from collections import Counter
import httpx
from playwright.async_api import async_playwright

BC = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
PID_BC = os.environ.get("PID_BC", "etapa-2-portal-del-pinar")
OUT = Path("imports/_verify"); OUT.mkdir(parents=True, exist_ok=True)


async def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    p = cli.get(f"/proyectos/{PID_BC}").json()
    extra = p.get("extra") or {}
    modelos = extra.get("modelos") or []
    unidades = p.get("unidades") or []
    imgs = p.get("imagenes") or []

    print(f"=== VERIFICACIÓN: {p.get('nombre')} ({PID_BC}) ===\n", flush=True)
    print(f"[1] FICHA:", flush=True)
    print(f"   inmobiliaria: {p.get('inmobiliaria')!r}  (esperado MNK)", flush=True)
    print(f"   comuna: {p.get('comuna')!r}  foto_principal: {'sí' if p.get('foto_principal_url') else 'NO'}", flush=True)
    print(f"   banco: {(extra.get('cuenta_reserva') or {}).get('banco')!r}  notas_html: {len(extra.get('notas_html') or '')}b", flush=True)

    print(f"\n[2] MODELOS ({len(modelos)}):", flush=True)
    con_planta = [m for m in modelos if m.get("planta_url")]
    plantas_distintas = {m.get("planta_url") for m in con_planta}
    for m in modelos:
        print(f"   {m.get('nombre')!r:8} {m.get('dormitorios')}D{m.get('banos')}B  planta_url={m.get('planta_url')!r}", flush=True)
    print(f"   → con planta_url: {len(con_planta)}/{len(modelos)} · plantas DISTINTAS: {len(plantas_distintas)}", flush=True)
    integridad = "✓ OK" if len(con_planta) == len(modelos) == len(plantas_distintas) else "✗ revisar"
    print(f"   integridad modelo↔planta 1:1: {integridad}", flush=True)

    print(f"\n[3] UNIDADES ({len(unidades)}):", flush=True)
    mnames = {m.get("nombre") for m in modelos}
    huer = sum(1 for u in unidades if u.get("modelo") not in mnames)
    sup = sum(1 for u in unidades if u.get("sup_total"))
    print(f"   enlazadas a modelo: {len(unidades)-huer}/{len(unidades)} huérfanas={huer} · con sup_total: {sup}", flush=True)

    print(f"\n[4] IMÁGENES ({len(imgs)}):", flush=True)
    cats = Counter(i.get("categoria") for i in imgs)
    print(f"   categorías: {dict(cats)}", flush=True)
    print(f"   principal: {sum(1 for i in imgs if i.get('es_principal'))}", flush=True)
    # assets alive
    alive = 0
    for m in con_planta[:3]:
        u = m["planta_url"]
        full = u if u.startswith("http") else BC + u
        try:
            if cli.head(full).status_code == 200:
                alive += 1
        except Exception:
            pass
    print(f"   plantas HTTP 200 (muestra 3): {alive}", flush=True)

    # [5] VISUAL — screenshots vista pública
    print(f"\n[5] VISUAL — capturando vista pública...", flush=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = await b.new_page(viewport={"width": 1440, "height": 1000})
        for tab in ("general", "modelos", "fotos", "stock"):
            try:
                await pg.goto(f"https://herramientas.bigcapital.cl/src/stock-interno/proyecto-vista.html?id={PID_BC}&t={tab}",
                              wait_until="networkidle", timeout=40_000)
                await pg.wait_for_timeout(4_000)
                await pg.screenshot(path=str(OUT / f"vista-{tab}.png"), full_page=True)
                print(f"   ✓ vista-{tab}.png", flush=True)
            except Exception as e:
                print(f"   vista {tab} err: {str(e)[:50]}", flush=True)
        await b.close()
    print(f"\n✓ Verificación completa. Screenshots en imports/_verify/", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
