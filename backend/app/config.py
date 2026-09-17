"""
SphinxGate configuration.

All settings are loaded from environment variables (or a .env file).
Provider API keys are never hardcoded here.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Provider credentials ─────────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # ── Gateway ──────────────────────────────────────────────────────────────
    # Which provider to route to when the client does not specify one.
    default_provider: str = Field(default="openai", alias="DEFAULT_PROVIDER")

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins.
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="ALLOWED_ORIGINS",
    )

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def get_provider_api_key(self, provider_slug: str) -> Optional[str]:
        """Return the API key for a given provider slug, or None if not configured."""
        key_map = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return key_map.get(provider_slug)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance (loaded once at startup)."""
    return Settings()
