"""
registrar_eventos.py — Registra eventos anómalos detectados para revisión manual.

Eventos que registra:
  - Proyectos sin unidades (esperadas vs reales)
  - Proyectos con inmobiliaria placeholder ("Sin asignar", "BigCapital")
  - Runs de workflow fuera de ventana esperada (L-V 10-18 Chile)
  - Runs cancelados
  - Failures en cualquier workflow relacionado
  - Importaciones que se quedan sin data (0 fotos, 0 modelos, 0 unidades)

Salida: eventos_anomalos.jsonl (append-only) + EVENTOS.md (regenerated).
"""
from __future__ import annotations
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import timezone, timedelta

import httpx

LOG_JSONL = Path("eventos_anomalos.jsonl")
LOG_MD = Path("EVENTOS.md")
CHILE_TZ = timezone(timedelta(hours=-4))


def now_iso() -> str:
    return datetime.datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_chile() -> datetime.datetime:
    return datetime.datetime.now(CHILE_TZ)


def load_existing() -> list[dict]:
    if not LOG_JSONL.exists():
        return []
    out = []
    for line in LOG_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def append_event(events: list[dict], evt: dict) -> bool:
    """Append solo si no existe un evento equivalente reciente (dedup 24h)."""
    key = (evt.get("type"), evt.get("subject"), evt.get("detail", "")[:80])
    cutoff = (datetime.datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for e in events:
        if e.get("ts", "") < cutoff:
            continue
        k = (e.get("type"), e.get("subject"), e.get("detail", "")[:80])
        if k == key:
            return False
    events.append(evt)
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    return True


def detect_bc_anomalies(bc_base: str, jwt: str) -> list[dict]:
    """Inspecciona bc-api y devuelve lista de eventos anómalos."""
    out = []
    cli = httpx.Client(base_url=bc_base, headers={"Authorization": f"Bearer {jwt}"}, timeout=30.0)
    r = cli.get("/proyectos")
    if r.status_code != 200:
        out.append({
            "ts": now_iso(), "type": "BC_UNREACHABLE", "severity": "high",
            "subject": "GET /proyectos",
            "detail": f"HTTP {r.status_code} {r.text[:200]}",
        })
        return out
    listing = r.json()
    for p in listing:
        pid = p.get("id") or ""
        nombre = p.get("nombre") or ""
        inmo = (p.get("inmobiliaria") or "").strip()

        # Inmobiliaria placeholder
        if inmo.lower() in ("bigcapital", "sin asignar", ""):
            out.append({
                "ts": now_iso(), "type": "INMOBILIARIA_PLACEHOLDER", "severity": "medium",
                "subject": pid, "nombre": nombre,
                "detail": f"inmobiliaria='{inmo}' — JB no devolvió la real",
            })
        # Stub name no actualizado
        if nombre.startswith("JB-") and len(nombre) <= 15:
            out.append({
                "ts": now_iso(), "type": "STUB_NAME", "severity": "medium",
                "subject": pid, "nombre": nombre,
                "detail": "Nombre quedó como JB-{id} (no se sobreescribió desde JB)",
            })

        # Full fetch para chequear contenido
        try:
            full = cli.get(f"/proyectos/{pid}").json()
        except Exception:
            continue
        extra = full.get("extra") or {}
        unidades = full.get("unidades") or []
        modelos = (extra.get("modelos") or extra.get("modelos_dom") or [])
        imagenes = full.get("imagenes") or []
        fotos = sum(1 for i in imagenes if (i.get("categoria") or "") != "plano")
        plantas = sum(1 for i in imagenes if (i.get("categoria") or "") == "plano")
        if extra.get("jb_id"):
            # Tiene jb_id pero 0 todo → proyecto totalmente huérfano
            if not unidades and not modelos and not imagenes:
                out.append({
                    "ts": now_iso(), "type": "JB_VACIO_TOTAL", "severity": "medium",
                    "subject": pid, "nombre": nombre,
                    "detail": "0 unidades, 0 modelos, 0 imágenes — JB no expone data para este proyecto",
                })
            elif modelos and not unidades:
                out.append({
                    "ts": now_iso(), "type": "MODELOS_SIN_UNIDADES", "severity": "high",
                    "subject": pid, "nombre": nombre,
                    "detail": f"{len(modelos)} modelos pero 0 unidades — Excel JB vacío",
                    "modelos_count": len(modelos), "fotos": fotos, "plantas": plantas,
                })
    return out


def detect_workflow_anomalies() -> list[dict]:
    """Inspecciona últimos 20 runs de cada workflow clave y registra rarezas."""
    out = []
    workflows = ["batch-import-jb.yml", "import-jb.yml", "monitor-health.yml"]
    for wf in workflows:
        try:
            data = subprocess.check_output([
                "gh", "-R", "nicolassoto-art/bc-api", "run", "list",
                "--workflow", wf, "--limit", "20",
                "--json", "databaseId,createdAt,conclusion,status,event,name",
            ]).decode()
            runs = json.loads(data)
        except Exception as e:
            out.append({
                "ts": now_iso(), "type": "GH_CLI_ERROR", "severity": "low",
                "subject": wf, "detail": str(e)[:200],
            })
            continue
        for r in runs:
            created = r.get("createdAt", "")
            try:
                created_dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                created_chile = created_dt.astimezone(CHILE_TZ)
            except Exception:
                continue
            run_id = r.get("databaseId")
            conclusion = r.get("conclusion") or ""
            status = r.get("status") or ""

            # Failed
            if conclusion == "failure":
                out.append({
                    "ts": now_iso(), "type": "WORKFLOW_FAILURE", "severity": "high",
                    "subject": f"{wf}#{run_id}",
                    "detail": f"created={created_chile.strftime('%a %d/%m %H:%M')} Chile · trigger={r.get('event')}",
                    "url": f"https://github.com/nicolassoto-art/bc-api/actions/runs/{run_id}",
                })
            elif conclusion == "cancelled":
                out.append({
                    "ts": now_iso(), "type": "WORKFLOW_CANCELLED", "severity": "low",
                    "subject": f"{wf}#{run_id}",
                    "detail": f"created={created_chile.strftime('%a %d/%m %H:%M')} Chile · trigger={r.get('event')}",
                    "url": f"https://github.com/nicolassoto-art/bc-api/actions/runs/{run_id}",
                })

            # Batch fuera de ventana esperada (L-V 10-18 Chile)
            if wf == "batch-import-jb.yml":
                weekday = created_chile.weekday()
                hour = created_chile.hour
                if weekday > 4 or hour < 10 or hour >= 18:
                    out.append({
                        "ts": now_iso(), "type": "BATCH_FUERA_VENTANA", "severity": "low",
                        "subject": f"{wf}#{run_id}",
                        "detail": f"corrió @ {created_chile.strftime('%a %d/%m %H:%M')} Chile (fuera de L-V 10-18) · trigger={r.get('event')}",
                        "url": f"https://github.com/nicolassoto-art/bc-api/actions/runs/{run_id}",
                    })
    return out


def render_md(events: list[dict]) -> str:
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e.get("type", "?"), []).append(e)

    sections_order = [
        ("WORKFLOW_FAILURE", "🚨 Fallos de workflow"),
        ("BC_UNREACHABLE", "🚨 bc-api no responde"),
        ("MODELOS_SIN_UNIDADES", "⚠ Proyectos con modelos pero sin unidades"),
        ("JB_VACIO_TOTAL", "⚠ Proyectos huérfanos (JB sin data)"),
        ("INMOBILIARIA_PLACEHOLDER", "ℹ Inmobiliaria sin asignar"),
        ("STUB_NAME", "ℹ Nombre stub no actualizado"),
        ("WORKFLOW_CANCELLED", "ℹ Workflows cancelados"),
        ("BATCH_FUERA_VENTANA", "ℹ Batches fuera de ventana L-V 10-18"),
        ("GH_CLI_ERROR", "ℹ Errores leyendo GH CLI"),
    ]

    lines = [
        "# Eventos anómalos — registro automático",
        "",
        f"Última actualización: {now_chile().strftime('%a %d/%m/%Y %H:%M')} Chile · {len(events)} eventos totales",
        "",
        "Este archivo se regenera automáticamente desde `eventos_anomalos.jsonl`.",
        "Los eventos están deduplicados en ventanas de 24h.",
        "",
    ]
    for key, title in sections_order:
        items = by_type.get(key, [])
        if not items:
            continue
        # Ordenar por timestamp desc, top 30
        items_sorted = sorted(items, key=lambda x: x.get("ts", ""), reverse=True)[:30]
        lines.append(f"## {title} ({len(items)} en total, mostrando últimos {len(items_sorted)})")
        lines.append("")
        lines.append("| Fecha (UTC) | Subject | Detalle |")
        lines.append("|---|---|---|")
        for e in items_sorted:
            ts = e.get("ts", "")[:19].replace("T", " ")
            subj = (e.get("subject") or "")[:50]
            nm = e.get("nombre")
            if nm:
                subj = f"{subj} · _{nm[:30]}_"
            det = (e.get("detail") or "").replace("|", "\\|")[:120]
            url = e.get("url")
            if url:
                det = f"{det} · [run]({url})"
            lines.append(f"| {ts} | `{subj}` | {det} |")
        lines.append("")
    return "\n".join(lines)


def main():
    bc_base = os.environ.get("BC_API_BASE", "https://bc-api.178-105-91-29.nip.io")
    jwt = os.environ.get("BC_API_JWT", "")
    if not jwt:
        print("ERROR: BC_API_JWT no seteado")
        sys.exit(1)

    print("📋 Cargando eventos previos...")
    events = load_existing()
    initial = len(events)
    print(f"   {initial} eventos en log")

    print("🔍 Detectando anomalías bc-api...")
    bc_events = detect_bc_anomalies(bc_base, jwt)
    print(f"   {len(bc_events)} candidatos bc-api")

    print("🔍 Detectando anomalías workflows...")
    wf_events = detect_workflow_anomalies()
    print(f"   {len(wf_events)} candidatos workflows")

    added = 0
    for e in bc_events + wf_events:
        if append_event(events, e):
            added += 1
    print(f"➕ {added} nuevos (resto deduplicado por 24h)")

    LOG_MD.write_text(render_md(events), encoding="utf-8")
    print(f"📄 Renderizado {LOG_MD} ({len(events)} eventos)")


if __name__ == "__main__":
    main()
