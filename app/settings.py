"""Centralized settings loaded from environment via pydantic-settings."""
from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://bcapi:bcapi@localhost:5432/bcapi"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 24
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10
    cors_origins: str = "http://localhost:8765"
    super_admins: str = "nicolas.soto@bigcapital.cl"
    legacy_api_url: str = "http://127.0.0.1/backend/api.php"
    env: str = "development"
    log_level: str = "INFO"

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
