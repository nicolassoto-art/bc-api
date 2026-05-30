"""
reimport_list.py — Re-importa una lista fija de proyectos que quedaron sin unidades.

Idempotente: salta los jb_ids que YA tienen unidades en bc-api.
Corre dentro de un solo job GitHub Actions (inmune a que el shell local muera).
Si un import falla, sigue con el siguiente.
"""
from __future__ import annotations
import json
import os
import subprocess
import time
import httpx

# Lista de proyectos que estaban vacíos (bug stub-sin-reimport).
# JB SÍ tiene su data — re-importar la trae.
TARGETS = [
    ("q8RwqXao", "Almanova"),
    ("zOHnfOQJ", "Edificio Borja Plaza"),
    ("dX4Rddfn", "Fuentes de Lomas II"),
    ("m9zXfNHe", "Pionera Parque Cerrillos"),
    ("osnL3M1C", "Vista San Martin"),
    ("4Kny8VBw", "Novus Torre G"),
    ("sFfaXZIQ", "Vicuna Mackenna 1194"),
    ("48t1IInf", "EDIFICIO CONEXION INDEPENDENCIA"),
    ("T8UuEf2r", "Santa Rosa 250"),
    ("WWMCny3E", "Los Alerces"),
    ("1kvflc3m", "Vicuna Mackenna 1796"),
    ("jfkJBrPQ", "Froilan Roa"),
]

BC_BASE = "https://bc-api.178-105-91-29.nip.io"


def units_count(cli, jb_id):
    pid = f"jb-{jb_id.lower()}"
    try:
        r = cli.get(f"/proyectos/{pid}")
        if r.status_code != 200:
            return None
        return len(r.json().get("unidades") or [])
    except Exception:
        return None


def trigger_and_wait(jb_id):
    r = subprocess.run(["gh", "workflow", "run", "import-jb.yml", "-f", f"jb_id={jb_id}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "trigger_failed", r.stderr[:200]
    time.sleep(10)
    rid = subprocess.check_output(["gh", "run", "list", "--workflow=import-jb.yml",
                                   "--limit", "1", "--json", "databaseId",
                                   "-q", ".[0].databaseId"]).decode().strip()
    for _ in range(60):  # max 30 min
        time.sleep(30)
        st = subprocess.check_output(["gh", "run", "view", rid, "--json", "status",
                                      "-q", ".status"]).decode().strip()
        if st == "completed":
            break
    concl = subprocess.check_output(["gh", "run", "view", rid, "--json", "conclusion",
                                     "-q", ".conclusion"]).decode().strip()
    return concl, rid


def main():
    jwt = os.environ["BC_API_JWT"]
    cli = httpx.Client(base_url=BC_BASE, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)

    results = []
    for i, (jb_id, nombre) in enumerate(TARGETS, 1):
        # Idempotencia: skip si ya tiene unidades
        n = units_count(cli, jb_id)
        if n and n > 0:
            print(f"[{i}/{len(TARGETS)}] SKIP {jb_id} ({nombre}) — ya tiene {n} unidades")
            results.append({"jb_id": jb_id, "nombre": nombre, "status": "skip", "units": n})
            continue

        print(f"\n[{i}/{len(TARGETS)}] {time.strftime('%H:%M')} — re-importing {jb_id} ({nombre})")
        concl, info = trigger_and_wait(jb_id)
        # Re-chequear unidades post-import
        n2 = units_count(cli, jb_id)
        print(f"  -> {concl} · ahora {n2} unidades (run {info})")
        results.append({"jb_id": jb_id, "nombre": nombre, "status": concl, "units": n2})
        time.sleep(15)

    print("\n========== RESUMEN ==========")
    ok = sum(1 for r in results if (r.get("units") or 0) > 0)
    vacios = [r for r in results if not (r.get("units") or 0)]
    print(f"Con unidades: {ok}/{len(results)}")
    for r in results:
        sym = "✅" if (r.get("units") or 0) > 0 else "⚠"
        print(f"  {sym} {r['jb_id']:12s} {r['nombre'][:35]:35s} {r.get('units')} unidades")
    if vacios:
        print(f"\n⚠ Siguen vacíos ({len(vacios)}) — JB realmente no expone su stock:")
        for r in vacios:
            print(f"    {r['jb_id']} {r['nombre']}")


if __name__ == "__main__":
    main()
