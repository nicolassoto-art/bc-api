"""bc-api · backend privado para Herramientas BigCapital.

Uvicorn entry: `uvicorn app.main:app --host 0.0.0.0 --port 8001`
Docs interactivas: GET /docs (Swagger) y /redoc.
"""
from __future__ import annotations
import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import auth, proyectos, imagenes, unidades, importador, inmobiliarias, documentos, tickets
from .settings import settings
from .deps.auth import super_admin
from fastapi.responses import HTMLResponse
from .services import email_service
from .services.daily_report import send_daily_report, build_daily_report, _build_html
from .services.inbox_processor import process_inbox
from .models import Usuario
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


# ── Scheduler · informe diario L-V 09am Chile ─────────────────────────────
# Reemplaza los emails por cada cambio (notify_change quedó silenciado).
# Si daily_report_enabled=False, no se registra el job → cero overhead.
_scheduler = None

@app.on_event("startup")
def _start_scheduler():
    global _scheduler
    if not settings.daily_report_enabled:
        log.info("Scheduler: daily_report deshabilitado, no se inicia.")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        _scheduler = BackgroundScheduler(timezone="America/Santiago")
        _scheduler.add_job(
            send_daily_report,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone="America/Santiago"),
            id="daily_stock_report",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Inbox processor: cada N minutos lee emails con Excel adjunto y los aplica.
        if settings.inbox_processor_enabled:
            from apscheduler.triggers.interval import IntervalTrigger
            _scheduler.add_job(
                process_inbox,
                IntervalTrigger(minutes=max(1, settings.inbox_poll_minutes)),
                id="inbox_processor",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            log.info("Scheduler · inbox_processor cada %d min", settings.inbox_poll_minutes)
        _scheduler.start()
        log.info("Scheduler iniciado · daily_stock_report L-V 09:00 America/Santiago")
    except Exception as e:
        log.error("No se pudo iniciar scheduler: %s", e, exc_info=True)


@app.on_event("shutdown")
def _stop_scheduler():
    if _scheduler:
        try: _scheduler.shutdown(wait=False)
        except Exception: pass


@app.post("/admin/daily-report/test", tags=["meta"])
def trigger_daily_report(_: Usuario = Depends(super_admin)):
    """Dispara el informe diario manualmente (solo super_admin) y lo ENVÍA a los
    destinatarios reales (To=daily_report_to, Cc=daily_report_cc). Para revisar el
    contenido SIN enviar, usar GET /admin/daily-report/preview."""
    send_daily_report()
    return {"ok": True, "sent_to": settings.daily_report_to or settings.notify_to,
            "cc": settings.daily_report_cc}


@app.get("/admin/daily-report/preview", response_class=HTMLResponse, tags=["meta"])
def preview_daily_report(_: Usuario = Depends(super_admin)):
    """Devuelve el HTML del informe diario con los datos REALES de prod, SIN enviarlo
    (solo super_admin). Para revisar el formato/agrupación antes de que se mande."""
    with SessionLocal() as db:
        data = build_daily_report(db)
    return HTMLResponse(_build_html(data))


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
