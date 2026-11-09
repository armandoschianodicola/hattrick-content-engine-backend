from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://hattrick:hattrick@localhost:5434/hattrick"
    )
    api_key: SecretStr = SecretStr("local-development-key-change-me")
    retrieval_provider: Literal["fake", "pgvector"] = "fake"
    ai_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_temperature: float | None = Field(default=None, ge=0, le=2)
    openai_max_output_tokens: int = Field(default=2500, ge=256, le=16000)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=2000)
    retrieval_limit: int = Field(default=8, ge=1, le=20)
    retrieval_min_similarity: float = Field(default=0.25, ge=-1, le=1)
    allow_illustrative_evidence: bool = True
    assets_directory: Path = Path("data/assets")
    font_path: Path | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: SecretStr | None = None
    http_timeout_seconds: float = Field(default=30, gt=0, le=120)

    @model_validator(mode="after")
    def production_settings(self):
        if self.environment == "production":
            if len(
                self.api_key.get_secret_value()
            ) < 32 or self.api_key.get_secret_value().startswith("local-development"):
                raise ValueError("Production requires a unique API_KEY of at least 32 characters")
            if self.ai_provider == "fake" or self.retrieval_provider == "fake":
                raise ValueError("Fake providers are restricted to development and tests")
            if self.allow_illustrative_evidence:
                raise ValueError("Disable illustrative evidence in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
