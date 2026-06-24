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
    # (2026-06-10) Default al api.php RAÍZ público (mismo del login). El exchange
    # igual prueba varias rutas como fallback (auth.py), pero el default correcto
    # evita depender de la copia vieja /backend/api.php (sesiones separadas).
    legacy_api_url: str = "https://herramientas.bigcapital.cl/api.php"
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
    notify_to: str = "nicolas.soto@bigcapital.cl"  # admin (To): TODO (stock + tickets + diag + test)
    # CC ('en copia') de las notificaciones de STOCK (crear · publicar · subir Excel) —
    # coma-separado. Override por NOTIFY_STOCK_CC. (2026-06-08) Vacío: solo nicolas.soto recibe.
    # Pamela y Álvaro fueron retirados a pedido del usuario (recibían demasiados emails de stock).
    notify_stock_cc: str = ""
    # (2026-06-08) Pedido del usuario: dejar de enviar email por CADA actualización de stock
    # (crear · publicar · subir Excel). En su lugar, un INFORME ÚNICO diario a las 10:00 AM
    # Chile, L-V. Si algo falla, sí se envía email aparte.
    emails_per_change: bool = False  # False → notify_change es no-op silencioso
    daily_report_enabled: bool = True  # Informe diario L-V 09:00 AM America/Santiago
    # Destinatarios del INFORME DIARIO (2026-06-17, pedido del usuario):
    #   To = Cristopher Jaramillo (responsable de la carga de stock SBC).
    #   Cc = Nicolás Soto.
    # Override por DAILY_REPORT_TO / DAILY_REPORT_CC en el .env del VPS. Si
    # daily_report_to queda vacío, cae a notify_to (nicolas.soto) por seguridad.
    daily_report_to: str = "cristopher.jaramillo@bigcapital.cl"
    daily_report_cc: str = "nicolas.soto@bigcapital.cl"
    # Nombre del operador para la sección "Los avances de X el día anterior".
    # Si queda vacío se deriva del email (primer segmento, title-case).
    daily_report_operator_name: str = "Cristofer"

    # ── Inbox processor · 2026-06-08 ─────────────────────────────────────────
    # Lee adjuntos Excel reenviados desde nicolas.soto@bigcapital.cl al buzón
    # sistema@bigcapital.cl, identifica el proyecto destino y aplica el stock
    # automáticamente, respondiendo por email con confirmación.
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""  # vacío → usa smtp_user (sistema@bigcapital.cl)
    imap_pass: str = ""  # vacío → usa smtp_pass (mismo App Password de Gmail)
    inbox_processor_enabled: bool = True
    inbox_allowed_senders: str = "nicolas.soto@bigcapital.cl"  # coma-separado
    inbox_poll_minutes: int = 10
    # El processor usa bc_api_service_token (ya existente arriba) para llamar al
    # endpoint subir_excel sin JWT — mismo token que usa el worker.

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
