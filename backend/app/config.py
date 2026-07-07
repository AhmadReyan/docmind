from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://docmind:docmind@localhost:5432/docmind"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_hours: int = 24
    cookie_secure: bool = False

    embedding_provider: Literal["local", "openai", "hash"] = "local"
    llm_provider: Literal["local", "openai", "anthropic"] = "local"
    embedding_dim: int = 384

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_llm_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    upload_dir: str = "/data/uploads"
    max_upload_bytes: int = 20 * 1024 * 1024

    chat_rate_limit_per_minute: int = 20
    upload_rate_limit_per_hour: int = 10

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
