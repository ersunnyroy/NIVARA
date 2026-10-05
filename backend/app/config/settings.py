"""Application settings loaded from environment variables.

All secrets come from the environment (see ../../.env.example). Nothing here is
hard-coded for production; defaults are safe for local development only.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "NIVARA"
    environment: str = Field("development", description="development | test | production")
    debug: bool = False
    api_prefix: str = "/api"
    secret_key: str = Field("dev-insecure-change-me-please-use-a-long-random-value", description="Signs session tokens. MUST be overridden in production.")
    encryption_key: str | None = Field(None, description="Fernet key for encrypting provider secrets stored in DB.")
    allowed_origins: list[str] = ["http://localhost:3000"]
    session_ttl_minutes: int = 60 * 12
    cookie_secure: bool = False
    timezone: str = "Asia/Kolkata"

    # --- infra ---
    database_url: str = "postgresql+psycopg://nivara:nivara@localhost:5442/nivara"
    redis_url: str = "redis://localhost:6381/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    data_cache_dir: Path = BACKEND_DIR / "var" / "cache"
    use_timescale: bool = True

    # --- rate limiting ---
    rate_limit_per_minute: int = 240
    login_rate_limit_per_minute: int = 10

    # --- data providers ---
    nse_enabled: bool = True
    nse_website_api_enabled: bool = Field(
        True, description="Use www.nseindia.com JSON endpoints (FII/DII, corporate actions, results, shareholding)."
    )
    nse_min_request_interval_sec: float = 1.0
    nse_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36 NIVARA-research/0.1"
    )
    upstox_access_token: str | None = None
    kite_api_key: str | None = None
    kite_access_token: str | None = None
    news_rss_feeds: list[str] = Field(default_factory=list, description="Extra reputable RSS feeds (secondary sources).")

    # --- AI ---
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
    ai_enabled: bool = True

    # --- notifications ---
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    alert_webhook_url: str | None = None

    # --- observability ---
    sentry_dsn: str | None = None
    log_level: str = "INFO"
    log_json: bool = True

    # --- bootstrap ---
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("allowed_origins", "news_rss_feeds", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key.startswith("dev-insecure"):
        raise RuntimeError("SECRET_KEY must be set in production")
    return s
