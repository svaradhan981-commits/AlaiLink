
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default pricing per million tokens in USD
DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-3.5-flash-lite": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-flash-8b": {"input_per_million": 0.0375, "output_per_million": 0.15},
    "gemini-1.5-pro": {"input_per_million": 1.25, "output_per_million": 5.00},
    "gemini-2.0-flash": {"input_per_million": 0.10, "output_per_million": 0.40},
}


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

    # Cost and pricing configuration (USD per 1,000,000 tokens)
    llm_default_input_cost_per_million: float = Field(default=0.075, ge=0)
    llm_default_output_cost_per_million: float = Field(default=0.30, ge=0)
    llm_pricing_json: str | None = None

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
