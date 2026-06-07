"""review_all.py — Revisión final consolidada de todos los proyectos importados v2."""
from __future__ import annotations
import os, json, httpx
from collections import Counter

BC = "https://bc-api.178-105-91-29.nip.io"
PIDS = os.environ.get("PIDS", "vistamar,etapa-2-portal-del-pinar,vista-llacol-n-torre-b,vista-llacolen-torre-a,cordillera-oriente-etapa-1").split(",")
RAW = {"voluntary","all","onlyapartment","downpayment","projectdeveloper","yesauthorized",
       "yesemergency","yesopen","shared","operationalexpenses","torefund","expense","expenses",
       "refund","corriente","vista","ahorro","checking","savings","atpromise","atreservation",
       "yespromise","yesreservation","developer"}


def gp(o, *path):
    for k in path:
        if not isinstance(o, dict): return None
        o = o.get(k)
    return o


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    print("\n" + "═" * 110, flush=True)
    print(f"{'PROYECTO':<35} {'INMOB':<10} {'MOD/PLT':<8} {'UNI(disp)':<11} {'EST/BOD/PCK':<13} {'FOTOS':<6} {'ENUMS':<8} {'STATUS'}", flush=True)
    print("═" * 110, flush=True)
    issues_total = []
    for pid in PIDS:
        pid = pid.strip()
        if not pid: continue
        try:
            p = cli.get(f"/proyectos/{pid}").json()
        except Exception as e:
            print(f"{pid:<35} ERROR: {str(e)[:60]}", flush=True); continue
        extra = p.get("extra") or {}
        modelos = extra.get("modelos") or []
        unidades = p.get("unidades") or []
        imgs = p.get("imagenes") or []
        # planta_url
        con_planta = sum(1 for m in modelos if m.get("planta_url"))
        plantas_distintas = len({m.get("planta_url") for m in modelos if m.get("planta_url")})
        # unidades
        disp = sum(1 for u in unidades if u.get("disponible"))
        mnames = {m.get("nombre") for m in modelos}
        huer = sum(1 for u in unidades if u.get("modelo") not in mnames)
        # stock — buscar en *_dom (recién importado) Y en arrays planos (post-edit)
        nest = len(extra.get("estacionamientos_dom") or extra.get("estacionamientos") or [])
        nbod = len(extra.get("bodegas_dom") or extra.get("bodegas") or [])
        npck = len(extra.get("packs_dom") or extra.get("packs") or [])
        # enums
        enum_vals = [
            gp(extra,"comercial","tipo_pie"), gp(extra,"comercial","tipo_descuento"),
            gp(extra,"comercial","tipo_bono_pie"), gp(extra,"comercial","tipo_reserva"),
            gp(extra,"comercial","destino_reserva"), gp(extra,"fisicos","acepta_cesion"),
            gp(extra,"fisicos","permiso_construccion"), gp(extra,"cuenta_reserva","tipo_cuenta"),
            gp(extra,"solicita_preaprobacion"), gp(extra,"stock_type")]
        enum_crudos = [v for v in enum_vals if v and str(v).strip().lower() in RAW]
        # principal foto
        principal = sum(1 for i in imgs if i.get("es_principal"))
        # status
        issues = []
        if con_planta < len(modelos): issues.append(f"{len(modelos)-con_planta} sin planta")
        if huer: issues.append(f"{huer} huérfanas")
        if enum_crudos: issues.append(f"enums:{enum_crudos}")
        if not p.get("inmobiliaria") or p["inmobiliaria"].lower() == "bigcapital":
            issues.append("inmob mal")
        if principal == 0: issues.append("sin fachada")
        if not unidades: issues.append("0 unidades")
        status = "✓ OK" if not issues else "⚠ " + "; ".join(issues)
        nombre = (p.get("nombre") or pid)[:34]
        print(f"{nombre:<35} {(p.get('inmobiliaria') or '?')[:9]:<10} "
              f"{con_planta}/{len(modelos)}({plantas_distintas:>2}p) "
              f"{len(unidades):>3}({disp:>3})    "
              f"{nest:>3}/{nbod:>3}/{npck:>3}     {len(imgs):>3}  "
              f"{('OK' if not enum_crudos else 'ERR'):<7} {status}", flush=True)
        if issues:
            issues_total.append((pid, issues))
    print("═" * 110, flush=True)
    print(f"\nResumen: {len(PIDS)} proyectos · {len(issues_total)} con observaciones", flush=True)
    if issues_total:
        for pid, iss in issues_total:
            print(f"  {pid}: {iss}", flush=True)
    else:
        print(f"  ✓ Todos limpios.", flush=True)


if __name__ == "__main__":
    main()
