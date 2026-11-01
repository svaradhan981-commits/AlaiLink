
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlaiLink"
    environment: str = "local"

    llm_provider: Literal["openai_compatible"] = "openai_compatible"

    # Primary and fallback models
    llm_model: str = "gemini-3.5-flash-lite"
    llm_fallback_model: str | None = None

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: SecretStr | None = None

    # Reliability settings
    llm_timeout_seconds: float = Field(default=90.0, gt=0)
    llm_max_retries: int = Field(default=1, ge=0, le=5)
    llm_retry_delay_seconds: float = Field(default=1.0, ge=0)

    database_url: SecretStr | None = None
    embedding_provider: Literal["gemini", "openai_compatible"] = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    embedding_api_key: SecretStr | None = None
    embedding_dimensions: int = Field(default=768, gt=0)
    embedding_timeout_seconds: float = Field(default=60.0, gt=0)
    rag_top_k: int = Field(default=5, gt=0, le=20)
    rag_max_distance: float = Field(default=0.65, ge=0, le=2)
    pages_directory: Path = Path("data/raw/pages")
    pdfs_directory: Path = Path("data/raw/pdfs")


@lru_cache
def get_settings() -> Settings:
    return Settings()
