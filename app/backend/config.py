"""
Application configuration — loaded once at startup.

All secrets come from environment variables (12-factor app).
PHI_ENCRYPTION_KEY must be a 32-byte base64-encoded key.
Never log this key, never commit it.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://claims:claims@localhost:5432/claimsdb",
        description="Async SQLAlchemy DSN",
    )
    database_url_sync: str = Field(
        default="postgresql://claims:claims@localhost:5432/claimsdb",
        description="Sync DSN for Alembic migrations",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # PHI Encryption (Fernet / AES-128 in CBC)
    phi_encryption_key: str = Field(
        default="",
        description="32-byte base64-encoded key for PHI field encryption. REQUIRED in prod.",
    )

    # Application
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # Kafka (optional — events publish in-memory in dev)
    kafka_bootstrap_servers: str = Field(default="")
    kafka_events_topic: str = Field(default="claims.events")

    # Feature flags
    enable_kafka: bool = Field(default=False)
    enable_redis_cache: bool = Field(default=True)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
