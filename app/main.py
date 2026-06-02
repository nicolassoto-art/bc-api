"""bc-api · backend privado para Herramientas BigCapital.

Uvicorn entry: `uvicorn app.main:app --host 0.0.0.0 --port 8001`
Docs interactivas: GET /docs (Swagger) y /redoc.
"""
from __future__ import annotations
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import auth, proyectos, imagenes, unidades, importador, inmobiliarias
from .settings import settings

logging.basicConfig(level=settings.log_level)

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
app.include_router(unidades.router)
app.include_router(importador.router)
app.include_router(inmobiliarias.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.env}


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "bc-api",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }
