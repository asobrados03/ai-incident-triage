from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'incidents.db'}"
SUPPORTED_ANALYZER_BACKENDS = {"fake", "ollama"}


class Settings(BaseSettings):
    app_name: str = "Sistema inteligente de triaje de incidencias"
    database_url: str = DEFAULT_DATABASE_URL
    analyzer_backend: str = "fake"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_timeout_seconds: float = 180.0

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


def validate_runtime_settings(settings: Settings) -> None:
    if settings.analyzer_backend not in SUPPORTED_ANALYZER_BACKENDS:
        raise ValueError(
            "ANALYZER_BACKEND must be one of: fake, ollama",
        )
    if settings.analyzer_backend == "ollama":
        parsed_url = urlparse(settings.ollama_base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(
                "OLLAMA_BASE_URL must be an absolute http or https URL",
            )
        if not settings.ollama_model.strip():
            raise ValueError("OLLAMA_MODEL must not be empty")
        if settings.ollama_timeout_seconds <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero")


@lru_cache
def get_settings() -> Settings:
    return Settings()
