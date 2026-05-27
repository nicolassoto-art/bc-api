"""
batch_import_jb.py — Orquestador para importar tandas de N proyectos JB pendientes.

Flujo:
  1. Lee jb_projects.json (descargado por list-jb-projects.yml)
  2. Lista proyectos ya en bc-api → filtra pendientes
  3. Importa los próximos N secuencialmente (uno a uno, regla inviolable)
  4. Reporta estado
  5. Sale con código 0 si quedan más, 1 si terminó todo

Diseñado para correr dentro de batch-import-jb.yml en GitHub Actions.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import httpx


def list_pending(bc_base: str, jwt: str, catalog_path: Path) -> list[dict]:
    """Devuelve proyectos del catálogo JB que NO están en bc-api."""
    catalog = json.loads(catalog_path.read_text())
    print(f"📚 Catálogo JB: {len(catalog)} proyectos")

    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)
    r = cli.get("/proyectos")
    r.raise_for_status()
    bc_proyectos = r.json()
    bc_jb_ids = set()
    for p in bc_proyectos:
        pid = (p.get("id") or "").lower()
        # IDs en bc-api tienen formato "jb-{jbid}" o "edificio-...-{jbid}"
        if pid.startswith("jb-"):
            bc_jb_ids.add(pid[3:])
        # Buscar el sufijo del id (último segmento alfanumérico de 6+ chars)
        for seg in pid.split("-"):
            if len(seg) >= 6 and seg.isalnum():
                bc_jb_ids.add(seg.lower())
    print(f"🗂  bc-api: {len(bc_proyectos)} proyectos importados")

    pending = [p for p in catalog if p["jb_id"].lower() not in bc_jb_ids]
    print(f"⏳ Pendientes: {len(pending)}")
    return pending


def trigger_import(jb_id: str) -> tuple[bool, str]:
    """Dispara import-jb.yml workflow y espera. Retorna (success, run_id)."""
    print(f"\n▶ Importing {jb_id}...")
    # Trigger
    r = subprocess.run(
        ["gh", "workflow", "run", "import-jb.yml", "-f", f"jb_id={jb_id}"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  ✗ trigger error: {r.stderr}")
        return False, ""
    # Pequeña pausa para que aparezca en la API
    time.sleep(8)
    # Get latest run id
    r = subprocess.run(
        ["gh", "run", "list", "--workflow=import-jb.yml", "--limit", "1", "--json", "databaseId", "-q", ".[0].databaseId"],
        capture_output=True, text=True
    )
    run_id = r.stdout.strip()
    if not run_id:
        print(f"  ✗ no run id captured")
        return False, ""
    print(f"  RUN: {run_id}")
    # Wait until completed
    while True:
        time.sleep(30)
        r = subprocess.run(
            ["gh", "run", "view", run_id, "--json", "status,conclusion", "-q", ".status"],
            capture_output=True, text=True
        )
        status = r.stdout.strip()
        if status == "completed":
            r2 = subprocess.run(
                ["gh", "run", "view", run_id, "--json", "conclusion", "-q", ".conclusion"],
                capture_output=True, text=True
            )
            conclusion = r2.stdout.strip()
            print(f"  → {conclusion}")
            return conclusion == "success", run_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--catalog", type=Path, default=Path("jb_projects.json"))
    args = parser.parse_args()

    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ["BC_API_JWT"]

    if not args.catalog.exists():
        print(f"⚠ No existe {args.catalog} — primero corre list-jb-projects.yml")
        sys.exit(2)

    pending = list_pending(bc_base, jwt, args.catalog)
    if not pending:
        print("✅ No hay pendientes — todo importado")
        sys.exit(1)  # Exit 1 para que el workflow sepa que ya no debe re-trigger

    batch = pending[: args.batch_size]
    print(f"\n🚀 Importando tanda de {len(batch)} proyectos:")
    for i, p in enumerate(batch, 1):
        print(f"   {i}. {p['jb_id']:12s} {p.get('inmobiliaria','')[:20]:20s} {p['nombre'][:50]}")

    results = []
    for p in batch:
        ok, run_id = trigger_import(p["jb_id"])
        results.append({"jb_id": p["jb_id"], "nombre": p["nombre"], "ok": ok, "run_id": run_id})

    print("\n📊 Resumen tanda:")
    for r in results:
        sym = "✅" if r["ok"] else "❌"
        print(f"   {sym} {r['jb_id']:12s} {r['nombre'][:50]:50s} (run {r['run_id']})")

    # Total después de la tanda
    remaining = len(pending) - len(batch)
    print(f"\n📈 Quedan {remaining} pendientes para próximas tandas")
    if remaining <= 0:
        print("✅ Importación completa.")
        sys.exit(1)  # 1 = done

    # ── Decisión de encadenamiento ─────────────────────────────────
    # Política: descansar 30 min y luego re-disparar SI seguimos dentro de
    # la ventana L-V 10:00-18:00 Chile (UTC-4). Si caemos fuera, salir y
    # dejar que el próximo cron de las 10:00 AM siguiente día hábil retome.
    from datetime import datetime, timezone, timedelta
    chile_tz = timezone(timedelta(hours=-4))
    now_chile = datetime.now(chile_tz)
    # Tiempo proyectado al despertar (30 min después)
    wake_chile = now_chile + timedelta(minutes=30)
    is_weekday = wake_chile.weekday() < 5  # 0=Mon ... 6=Sun
    in_window = 10 <= wake_chile.hour < 18 and is_weekday
    print(f"\n⏰ Now Chile: {now_chile.strftime('%a %H:%M')}  wake @ {wake_chile.strftime('%a %H:%M')}  in_window={in_window}")

    if not in_window:
        print("🛏  Fuera de ventana L-V 10-18. Salgo, próximo cron de las 10AM L-V retoma.")
        sys.exit(2)  # 2 = pause hasta próximo cron

    print("⏳ Durmiendo 30 minutos antes de encadenar...")
    time.sleep(30 * 60)
    print("🔁 Re-disparando batch-import-jb.yml para la siguiente tanda...")
    r = subprocess.run(
        ["gh", "workflow", "run", "batch-import-jb.yml"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  ✗ no se pudo re-disparar: {r.stderr}")
        sys.exit(3)
    print("  ✓ Disparada. Esta tanda termina; la próxima toma el relevo.")
    sys.exit(0)


if __name__ == "__main__":
    main()
