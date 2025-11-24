from functools import lru_cache
from pathlib import Path
import os

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/"


def _find_env_file() -> Path | None:
    """Find .env file in project root."""
    # Try to find project root by looking for .env file
    # Start from current file location and go up
    current = Path(__file__).parent
    for _ in range(3):  # Check up to 3 levels up
        env_file = current / ".env"
        if env_file.exists():
            return env_file
        current = current.parent
    # Try current working directory
    cwd_env = Path(".env")
    if cwd_env.exists():
        return cwd_env
    return None


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    api_key: str = Field(alias="MLIT_API_KEY")
    base_url: HttpUrl | str = Field(default=DEFAULT_BASE_URL, alias="MLIT_BASE_URL")
    http_timeout: float = Field(default=15.0, alias="HTTP_TIMEOUT")
    max_concurrency: int = Field(default=4, alias="MAX_CONCURRENCY")

    model_config = SettingsConfigDict(
        env_file=_find_env_file() or ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def set_api_key_from_env(cls, values: dict) -> dict:
        """Support HUDOUSAN_API_KEY as fallback for MLIT_API_KEY."""
        if isinstance(values, dict):
            # If MLIT_API_KEY is not set, try HUDOUSAN_API_KEY
            if "MLIT_API_KEY" not in values or not values.get("MLIT_API_KEY"):
                hudousan_key = os.getenv("HUDOUSAN_API_KEY")
                if hudousan_key:
                    values["MLIT_API_KEY"] = hudousan_key
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()

