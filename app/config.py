from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'incidents.db'}"


class Settings(BaseSettings):
    app_name: str = "Sistema inteligente de triaje de incidencias"
    database_url: str = DEFAULT_DATABASE_URL

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
