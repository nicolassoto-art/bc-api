"""bc-api · backend privado para Herramientas BigCapital.

Uvicorn entry: `uvicorn app.main:app --host 0.0.0.0 --port 8001`
Docs interactivas: GET /docs (Swagger) y /redoc.
"""
from __future__ import annotations
import logging
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import auth, proyectos, imagenes, unidades, importador, inmobiliarias, documentos, tickets, capacitaciones
from .settings import settings
from .deps.auth import super_admin
from fastapi.responses import HTMLResponse, Response
from .services import email_service
from .services.daily_report import (
    send_daily_report, build_daily_report, _build_html,
    _pendientes_pdf_bytes, migrar_snapshot_viejo,
)
from .services.stock_emails import (
    build_sin_revisar, html_sin_revisar, asunto_sin_revisar, send_sin_revisar,
    build_fallas, html_fallas_acotado, asunto_fallas, pdf_fallas, send_fallas,
)
from .services.inbox_processor import process_inbox
from .models import Usuario
from .models.proyecto import Proyecto
from .db import SessionLocal

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(
    title="BigCapital API",
    description="Backend privado de Herramientas BC. Auth: bearer JWT.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir uploads estáticos (también lo puede hacer Caddy/nginx delante con mejor rendimiento)
app.mount("/uploads", StaticFiles(directory=str(settings.upload_path)), name="uploads")

app.include_router(auth.router)
app.include_router(proyectos.router)
app.include_router(imagenes.router)
app.include_router(documentos.router)
app.include_router(unidades.router)
app.include_router(importador.router)
app.include_router(inmobiliarias.router)
app.include_router(tickets.router)
app.include_router(capacitaciones.router)   # compresión de videos (taller, no bodega)


# ── Scheduler · informe diario L-V 09am Chile ─────────────────────────────
# Reemplaza los emails por cada cambio (notify_change quedó silenciado).
# Si daily_report_enabled=False, no se registra el job → cero overhead.
_scheduler = None
_scheduler_lock_fd = None  # se mantiene abierto toda la vida del proceso ganador del lock


def _acquire_scheduler_lock() -> bool:
    """True solo en UN worker. uvicorn con >1 worker = N procesos, cada uno corre el
    startup → N schedulers → el job dispara N veces (el daily_report salía DUPLICADO y
    process_inbox corría 2×; max_instances/coalesce solo dedup DENTRO de un scheduler, no
    entre procesos). Lock de archivo exclusivo no-bloqueante: solo el worker que lo toma
    arranca el scheduler; si el proceso muere, el SO libera el flock y otro lo toma al
    reiniciar."""
    global _scheduler_lock_fd
    try:
        import fcntl
        # Fuera de /tmp: systemd-tmpfiles puede borrar el archivo por edad y un
        # worker respawneado tomaría un lock sobre un inode NUEVO → doble scheduler
        # y emails duplicados. upload_path es persistente y escribible.
        _lock_path = os.path.join(str(settings.upload_path), ".scheduler.lock")
        fd = os.open(_lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        _scheduler_lock_fd = fd  # NO cerrar: mantener el lock mientras viva el proceso
        return True
    except Exception as e:
        # Si fcntl no está disponible (no-unix), no bloqueamos el arranque.
        log.warning("Scheduler lock no disponible (%s) · sigo sin guard multi-worker", e)
        return True


def _registrar_jobs(scheduler) -> list:
    """Registra los jobs del programador según los flags. Devuelve los ids registrados.

    L-V, hora de Chile: 09:00 informe diario · 09:02 «proyectos sin revisar» · 09:04
    «fallas en fichas» (2026-10-05) · inbox cada N min. El de las 13:00 se eliminó.
    """
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    comunes = dict(replace_existing=True, max_instances=1, coalesce=True)
    ids = []

    def _cron(func, hora, minuto, job_id):
        scheduler.add_job(
            func,
            CronTrigger(day_of_week="mon-fri", hour=hora, minute=minuto, timezone="America/Santiago"),
            id=job_id, misfire_grace_time=3600, **comunes,
        )
        ids.append(job_id)
        log.info("Scheduler · %s L-V %02d:%02d America/Santiago", job_id, hora, minuto)

    if settings.daily_report_enabled:
        _cron(send_daily_report, 9, 0, "daily_stock_report")
    if settings.stock_sin_revisar_enabled:
        _cron(send_sin_revisar, 9, 2, "stock_sin_revisar")
    if settings.fallas_fichas_enabled:
        _cron(send_fallas, 9, 4, "fallas_fichas")
    # Inbox processor: cada N minutos lee emails con Excel adjunto y los aplica.
    if settings.inbox_processor_enabled:
        scheduler.add_job(
            process_inbox,
            IntervalTrigger(minutes=max(1, settings.inbox_poll_minutes)),
            id="inbox_processor", **comunes,
        )
        ids.append("inbox_processor")
        log.info("Scheduler · inbox_processor cada %d min", settings.inbox_poll_minutes)
    return ids


@app.on_event("startup")
def _start_scheduler():
    global _scheduler
    # Cada job tiene su PROPIO flag: daily_report_enabled solo apaga el informe de
    # las 09:00 — NO el de las 13:00 ni el inbox processor (antes un early-return
    # apagaba el scheduler entero y todos los jobs caían juntos).
    if not (settings.daily_report_enabled or settings.inbox_processor_enabled
            or settings.stock_sin_revisar_enabled or settings.fallas_fichas_enabled):
        log.info("Scheduler: todos los jobs deshabilitados, no se inicia.")
        return
    if not _acquire_scheduler_lock():
        log.info("Scheduler: otro worker ya tiene el lock · este worker NO inicia scheduler.")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        # Solo el dueño del candado: la foto del informe sale de uploads/ (público).
        migrar_snapshot_viejo()
        _scheduler = BackgroundScheduler(timezone="America/Santiago")
        _registrar_jobs(_scheduler)
        _scheduler.start()
        log.info("Scheduler iniciado.")
    except Exception as e:
        log.error("No se pudo iniciar scheduler: %s", e, exc_info=True)
        # Liberar el flock: si este worker falló al arrancar el scheduler y retiene
        # el lock, NINGÚN worker programa los informes (cero emails en silencio).
        global _scheduler_lock_fd
        if _scheduler_lock_fd is not None:
            try:
                os.close(_scheduler_lock_fd)
            except Exception:
                pass
            _scheduler_lock_fd = None


@app.on_event("shutdown")
def _stop_scheduler():
    if _scheduler:
        try: _scheduler.shutdown(wait=False)
        except Exception: pass


@app.post("/admin/daily-report/test", tags=["meta"])
def trigger_daily_report(semana: bool = False, usuario: Usuario = Depends(super_admin)):
    """Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA SOLO A QUIEN
    LO PIDE (2026-10-05: antes iba a los destinatarios reales). Para revisar el
    contenido sin enviar nada, usar GET /admin/daily-report/preview.
    semana=true fuerza la sección 'Resumen de la semana anterior' (normalmente solo lunes).
    NO guarda el snapshot del cruce ni anota el resultado del día."""
    para = [usuario.email]
    estado = send_daily_report(forzar_semana=semana, guardar_snapshot=False, para=para)
    return {"ok": estado == "enviado", "estado": estado, "sent_to": para, "forzar_semana": semana}


@app.get("/admin/daily-report/preview", response_class=HTMLResponse, tags=["meta"])
def preview_daily_report(semana: bool = False, _: Usuario = Depends(super_admin)):
    """Devuelve el HTML del informe diario con los datos REALES de prod, SIN enviarlo
    (solo super_admin). semana=true fuerza el resumen semanal (normalmente solo lunes)."""
    with SessionLocal() as db:
        data = build_daily_report(db, forzar_semana=semana)
    return HTMLResponse(_build_html(data))


@app.get("/admin/daily-report/pendientes-pdf", tags=["meta"])
def preview_pendientes_pdf(_: Usuario = Depends(super_admin)):
    """PDF con el listado COMPLETO de pendientes vigentes (críticos, sin cortar —
    persisten + nuevos), con datos REALES de prod, SIN enviar ningún email. Es el
    mismo PDF que se adjunta al informe diario; expuesto aparte para poder revisarlo
    antes de que salga el correo real. Solo super_admin."""
    with SessionLocal() as db:
        data = build_daily_report(db)
    cruce = data.get("cruce", {})
    items = (cruce.get("persisten") or []) + (cruce.get("nuevos") or [])
    pdf_bytes = _pendientes_pdf_bytes(items, data["fecha_cl"])
    return Response(content=pdf_bytes, media_type="application/pdf")


# ── Correos "Stock interno" (2026-10-05): vistas previas de SOLO LECTURA ────────
# No envían nada ni escriben el estado (NUEVA, resueltas): sirven para revisar el
# contenido y medir cuántas fichas toca cada regla antes de encender los correos.

@app.get("/admin/stock-sin-revisar/preview", response_class=HTMLResponse, tags=["meta"])
def preview_stock_sin_revisar(_: Usuario = Depends(super_admin)):
    """HTML del correo «proyectos sin revisar» con datos reales, SIN enviarlo."""
    with SessionLocal() as db:
        data = build_sin_revisar(db)
    return HTMLResponse(html_sin_revisar(data))


@app.get("/admin/fallas-fichas/preview", response_class=HTMLResponse, tags=["meta"])
def preview_fallas_fichas(_: Usuario = Depends(super_admin)):
    """HTML del correo «fallas en fichas» con datos reales, SIN enviarlo ni guardar estado."""
    with SessionLocal() as db:
        data = build_fallas(db)
    return HTMLResponse(html_fallas_acotado(data))


@app.get("/admin/fallas-fichas/pdf", tags=["meta"])
def preview_fallas_pdf(_: Usuario = Depends(super_admin)):
    """PDF completo del correo «fallas en fichas», SIN enviarlo ni guardar estado."""
    with SessionLocal() as db:
        data = build_fallas(db)
    return Response(content=pdf_fallas(data), media_type="application/pdf")


@app.get("/admin/stock-interno/conteo", tags=["meta"])
def conteo_stock_interno(_: Usuario = Depends(super_admin)):
    """Números para decidir el encendido: fichas por regla (y % del total), fallas por
    sección, proyectos sin revisar por categoría, peso de cada correo y asuntos."""
    with SessionLocal() as db:
        f = build_fallas(db)
        s = build_sin_revisar(db)
    return {
        "fallas": {
            "asunto": asunto_fallas(f), "n_fichas": f["n_fichas"], "n_criticas": f["n_criticas"],
            "por_seccion": {sec["clave"]: {"fichas": len(sec["proyectos"]), "fallas": sec["n_fallas"]}
                            for sec in f["secciones"]},
            "por_regla": f["conteo_por_regla"], "textos": f["resumen_textos"],
            "bytes_correo": len(html_fallas_acotado(f).encode("utf-8")),
        },
        "sin_revisar": {
            "asunto": asunto_sin_revisar(s), "n": s["n"], "por_categoria": s["cuenta"],
            "n_urgentes": s["n_urgentes"], "bytes_correo": len(html_sin_revisar(s).encode("utf-8")),
        },
        "encendidos": {"stock_sin_revisar": settings.stock_sin_revisar_enabled,
                       "fallas_fichas": settings.fallas_fichas_enabled},
    }


@app.post("/admin/inmobiliarias/normalize", tags=["meta"])
def normalize_inmobiliarias(apply: bool = False, _: Usuario = Depends(super_admin)):
    """Unifica EN EL SISTEMA las inmobiliarias que son la misma con distinto tipeo
    (case/espacios): p.ej. 'AJ Urbana' → 'AJ URBANA'. Canoniza a la grafía más
    frecuente. Dry-run por defecto; ?apply=true escribe. Solo super_admin."""
    from collections import Counter, defaultdict
    with SessionLocal() as db:
        proys = db.query(Proyecto).filter(Proyecto.deleted_at.is_(None)).all()
        grupos = defaultdict(list)
        for p in proys:
            raw = (p.inmobiliaria or "").strip()
            if raw:
                grupos[raw.casefold()].append(p)
        cambios = []
        for _norm, ps in grupos.items():
            spellings = Counter((p.inmobiliaria or "").strip() for p in ps)
            if len(spellings) <= 1:
                continue  # ya uniforme, nada que hacer
            canonical = spellings.most_common(1)[0][0]
            for p in ps:
                cur = (p.inmobiliaria or "").strip()
                if cur != canonical:
                    cambios.append({"id": p.id, "de": cur, "a": canonical})
                    if apply:
                        p.inmobiliaria = canonical
        if apply and cambios:
            db.commit()
        return {"apply": apply, "n_cambios": len(cambios),
                "variantes_detectadas": sorted({(c["de"], c["a"]) for c in cambios}),
                "cambios": cambios}


@app.get("/admin/diag/usuario", tags=["meta"])
def diag_usuario(email: str, _: Usuario = Depends(super_admin)):
    """Estado de la fila bc-api de un usuario (solo super_admin). Para diagnosticar
    el caso 'tengo el permiso pero me pide clave': si activo=false, el exchange daba
    401. Desde 2026-06-17 el exchange reactiva a quien tenga acceso legacy válido."""
    em = (email or "").strip().lower()
    with SessionLocal() as db:
        u = db.query(Usuario).filter(Usuario.email == em).first()
        if not u:
            return {"email": em, "existe_en_bcapi": False,
                    "nota": "No tiene fila en bc-api; se crea (activa) en el próximo exchange."}
        return {"email": em, "existe_en_bcapi": True, "activo": u.activo,
                "is_admin": u.is_admin, "nombre": u.nombre,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


@app.post("/admin/inbox/poll", tags=["meta"])
def trigger_inbox_poll(_: Usuario = Depends(super_admin)):
    """Dispara el procesador de inbox manualmente (solo super_admin). Lee emails con
    Excel adjunto, los aplica al proyecto identificado y responde con confirmación.
    Útil para probar sin esperar al cron de cada N min."""
    return process_inbox()


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.env}


@app.get("/diag/email", tags=["meta"])
def diag_email(send: bool = False, _: Usuario = Depends(super_admin)):
    """Diagnóstico SMTP (solo super admin). Sin args: estado de config.
    Con ?send=1: envía un correo de prueba a notify_to y devuelve ok/error."""
    return email_service.test_send() if send else email_service.status()


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "bc-api",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }
