"""Centralized settings loaded from environment via pydantic-settings."""
from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Lee .env (BD, JWT, etc.) y además .env.smtp (solo SMTP, lo escribe el deploy
    # desde el secreto SMTP_PASS de GitHub) — separados para no tocar nunca el .env
    # con credenciales sensibles. El segundo pisa al primero si hay choque.
    model_config = SettingsConfigDict(env_file=(".env", ".env.smtp"), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://bcapi:bcapi@localhost:5432/bcapi"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 24
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10
    cors_origins: str = "http://localhost:8765"
    super_admins: str = "nicolas.soto@bigcapital.cl"
    legacy_api_url: str = "http://127.0.0.1/backend/api.php"
    # Token de servicio para el Cloudflare Worker (catálogo público).
    # Vacío = endpoint /proyectos/public deshabilitado (devuelve 503).
    bc_api_service_token: str = ""
    env: str = "development"
    log_level: str = "INFO"

    # SMTP para notificaciones de cambios de stock (Fase 2). Reusa las MISMAS
    # credenciales del dashboard de brokers (mismos nombres de env): basta copiar
    # el bloque SMTP_* del .env del dashboard al .env de bc-api. Si están vacías,
    # el envío es no-op (no rompe nada). El "from" sale como sistemas@bigcapital.cl.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""  # vacío → usa smtp_user (Gmail exige from = cuenta autenticada)
    smtp_from_name: str = "BigCapital · Stock"
    notify_to: str = "nicolas.soto@bigcapital.cl"  # destinatario admin de las notificaciones

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def super_admins_list(self) -> List[str]:
        return [e.strip().lower() for e in self.super_admins.split(",") if e.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
