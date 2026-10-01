from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from the environment. Nothing secret lives in the DB."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    database_url: str = "postgresql+psycopg://radar:radar@localhost:5432/radar"
    public_base_url: str = "http://localhost:3000"
    environment: str = "development"
    log_level: str = "INFO"

    # --- auth ---
    business_password: str = "noma-radar"
    ops_token: str = "change-me-ops-token"
    session_secret: str = "dev-session-secret-change-me"
    encryption_key: str | None = None  # Fernet key; derived from session_secret when unset

    # --- LLM ---
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_daily_budget_usd: float = 5.0
    llm_input_cost_per_1m: float = 0.40
    llm_output_cost_per_1m: float = 1.60
    embedding_cost_per_1m: float = 0.02

    # --- ingestion ---
    default_source_interval_minutes: int = 60
    page_watch_interval_minutes: int = 360
    backfill_days: int = 7
    max_items_per_run: int = 40
    fetch_timeout_seconds: float = 20.0
    per_host_min_delay_seconds: float = 2.0
    user_agent: str = "RadarBot/0.1 (+competitor monitoring; contact ops@noma.security)"
    # 0.92 collapsed distinct boilerplate-heavy news pages into one item in practice; 0.95 still catches
    # the same announcement syndicated across a blog and a press room.
    dedup_similarity_threshold: float = 0.95
    page_change_min_chars: int = 200
    raw_html_retention_days: int = 30
    snapshot_retention_days: int = 90

    # --- worker ---
    worker_tick_seconds: int = 30
    worker_concurrency: int = 4
    healthcheck_url: str | None = None
    ops_slack_webhook: str | None = None

    # --- eval ---
    eval_max_items: int = 60
    eval_hour_utc: int = 3

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
