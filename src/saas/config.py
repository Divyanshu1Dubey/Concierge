"""SaaS configuration and environment management."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH, override=False)


class Settings(BaseModel):
    app_env: str = Field(default=os.getenv("APP_ENV", "development"), alias="APP_ENV")
    app_url: str = Field(default=os.getenv("APP_URL", "http://localhost:8000"), alias="APP_URL")
    api_url: str = Field(default=os.getenv("API_URL", "http://localhost:8000"), alias="API_URL")
    widget_url: str = Field(default=os.getenv("WIDGET_URL", "http://localhost:8000"), alias="WIDGET_URL")
    jwt_secret: str = Field(default=os.getenv("JWT_SECRET", "change-me"), alias="JWT_SECRET")
    jwt_algorithm: str = Field(default=os.getenv("JWT_ALGORITHM", "HS256"), alias="JWT_ALGORITHM")
    jwt_expires_minutes: int = Field(default=int(os.getenv("JWT_EXPIRES_MINUTES", "1440")), alias="JWT_EXPIRES_MINUTES")
    encryption_key: SecretStr = Field(default=SecretStr(os.getenv("ENCRYPTION_KEY", "change-me")), alias="ENCRYPTION_KEY")
    database_url: str = Field(default=os.getenv("DATABASE_URL", str(ROOT / "data" / "saas.db")), alias="DATABASE_URL")
    cors_origins: str = Field(default=os.getenv("CORS_ORIGINS", "*"), alias="CORS_ORIGINS")
    rate_limit_per_minute: int = Field(default=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")), alias="RATE_LIMIT_PER_MINUTE")
    default_smtp_host: str | None = Field(default=os.getenv("DEFAULT_SMTP_HOST") or os.getenv("SMTP_HOST") or "smtp.gmail.com", alias="DEFAULT_SMTP_HOST")
    default_smtp_port: int | None = Field(default=int(os.getenv("DEFAULT_SMTP_PORT") or os.getenv("SMTP_PORT") or "465"), alias="DEFAULT_SMTP_PORT")
    default_smtp_user: str | None = Field(default=os.getenv("DEFAULT_SMTP_USER") or os.getenv("SMTP_USER") or os.getenv("FRONT_DESK_EMAIL"), alias="DEFAULT_SMTP_USER")
    default_smtp_password: SecretStr | None = Field(
        default=SecretStr(os.getenv("DEFAULT_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD") or "") if (os.getenv("DEFAULT_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD")) else None,
        alias="DEFAULT_SMTP_PASSWORD"
    )
    default_smtp_from: str | None = Field(default=os.getenv("DEFAULT_SMTP_FROM") or os.getenv("FRONT_DESK_EMAIL") or os.getenv("SMTP_USER"), alias="DEFAULT_SMTP_FROM")
    default_smtp_reply_to: str | None = Field(default=os.getenv("DEFAULT_SMTP_REPLY_TO") or os.getenv("FRONT_DESK_EMAIL") or os.getenv("SMTP_USER"), alias="DEFAULT_SMTP_REPLY_TO")

    model_config = {
        "populate_by_name": True,
    }

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_list(self) -> list[str]:
        if self.cors_origins.strip() in ("*", ""):
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
