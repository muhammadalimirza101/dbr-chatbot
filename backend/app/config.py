"""Application settings loaded from the repo-root .env via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root: backend/app/config.py -> backend/app -> backend -> <root>
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    openai_api_key: str
    jwt_secret: str
    dashboard_origin: str
    connector_shared_secret: str
    # consumed by the connector only; optional here so the backend can be
    # deployed without it
    whatsapp_session_dir: str = ""

    # optional, sensible local defaults
    connector_url: str = "http://127.0.0.1:3001"
    media_storage_dir: str = "media_storage"
    # spend guard: per conversation per UTC day, across all models
    daily_token_cap_per_conversation: int = 25000


@lru_cache
def get_settings() -> Settings:
    return Settings()
