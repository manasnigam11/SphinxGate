"""
SphinxGate configuration — Phase 2.5.

All settings are loaded from environment variables (or a .env file).
Provider API keys are never hardcoded here.

Phase 2.5 additions:
  - GROQ_API_KEY added.
  - get_provider_api_key() now returns None (not an error) for providers
    that don't require an API key (public API providers).
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache(maxsize=1)
def _dotenv_values() -> dict[str, str]:
    """Load the local .env file once (values only; never logged)."""
    try:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(".env").items() if v is not None}
    except Exception:
        return {}


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Read a configuration value: real environment first, then the local .env.

    Pydantic's Settings reads .env but does NOT export it into os.environ, so
    plain os.environ lookups silently ignored .env for flags such as
    FAULT_INJECTION_ENABLED.  The real environment always wins (tests and
    deployments override .env).
    """
    value = os.environ.get(name)
    if value is not None:
        return value
    return _dotenv_values().get(name, default)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Provider credentials ─────────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    # Public APIs (no keys needed — fields kept as None for consistency)

    # ── Local LLM Configuration ─────────────────────────────────────────────
    local_llm_enabled: bool = Field(default=False, alias="LOCAL_LLM_ENABLED")
    local_llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LOCAL_LLM_BASE_URL")
    local_llm_model: Optional[str] = Field(default=None, alias="LOCAL_LLM_MODEL")
    # Local LLMs are often slower than cloud APIs, so they need a separate, generous timeout.
    local_llm_timeout: int = Field(default=60, alias="LOCAL_LLM_TIMEOUT")

    # ── Active Health Checking ────────────────────────────────────────────────
    health_check_enabled: bool = Field(default=True, alias="HEALTH_CHECK_ENABLED")
    health_check_interval_seconds: int = Field(default=300, alias="HEALTH_CHECK_INTERVAL_SECONDS")
    health_check_timeout_seconds: int = Field(default=5, alias="HEALTH_CHECK_TIMEOUT_SECONDS")

    # ── Gateway ──────────────────────────────────────────────────────────────
    # Which provider to route to when the client does not specify one.
    default_provider: str = Field(default="openai", alias="DEFAULT_PROVIDER")
    # Deployment label surfaced to the UI (development | staging | production).
    environment: str = Field(default="development", alias="SPHINXGATE_ENV")

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
        """
        Return the API key for a given provider slug, or None.

        For providers that do not require an API key (public APIs like
        open_meteo, jokeapi, frankfurter, trivia), this returns None and
        that is expected — the resilience engine handles it correctly.

        Returns None for unknown slugs as well.
        """
        key_map = {
            "openai":    self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini":    self.gemini_api_key,
            "groq":      self.groq_api_key,
            # Public APIs — no key required; returning None is correct.
            "open_meteo":  None,
            "jokeapi":     None,
            "frankfurter": None,
            "trivia":      None,
        }
        return key_map.get(provider_slug)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance (loaded once at startup)."""
    return Settings()
