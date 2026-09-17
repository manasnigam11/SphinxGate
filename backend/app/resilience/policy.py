"""
Centralized Resilience Policy — Phase 2.

All configurable resilience parameters live here.  Nothing in the codebase
should hardcode timeout values, retry counts, backoff parameters, etc.

The policy can be read from environment variables so it is overridable in
different deployment environments without code changes.

Compatible with the frontend's ResiliencePolicy type shape so Phase 3
can expose these values through a /api/v1/policy endpoint.
"""

from dataclasses import dataclass, field
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Fallback chain configuration ───────────────────────────────────────────────

@dataclass
class FallbackConfig:
    """
    Ordered list of fallback provider slugs for a primary provider.

    When the primary provider fails (or its circuit is OPEN), the engine
    will attempt each fallback in order, stopping at the first success.

    Fallbacks must be explicitly configured — the engine never blindly tries
    all registered providers.
    """
    primary: str
    fallbacks: list[str] = field(default_factory=list)


# ── Policy settings (environment-configurable) ─────────────────────────────────

class ResiliencePolicySettings(BaseSettings):
    """
    Resilience policy loaded from environment variables.

    All variables are prefixed with RESILIENCE_ to avoid clashes with the
    main gateway settings.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Timeout ───────────────────────────────────────────────────────────────
    # How long to wait for a provider before declaring a timeout failure.
    # Applies to each individual attempt (including retries).
    request_timeout_seconds: float = Field(default=30.0, alias="RESILIENCE_TIMEOUT_SECONDS")

    # ── Retry ─────────────────────────────────────────────────────────────────
    retry_enabled: bool = Field(default=True, alias="RESILIENCE_RETRY_ENABLED")
    max_retries: int = Field(default=2, alias="RESILIENCE_MAX_RETRIES")

    # Exponential backoff: wait = min(initial * 2^attempt, max) seconds
    initial_backoff_seconds: float = Field(default=0.5, alias="RESILIENCE_INITIAL_BACKOFF_SECONDS")
    max_backoff_seconds: float = Field(default=5.0, alias="RESILIENCE_MAX_BACKOFF_SECONDS")

    # ── Circuit breaker ───────────────────────────────────────────────────────
    # Number of consecutive failures before the circuit opens.
    circuit_failure_threshold: int = Field(default=5, alias="RESILIENCE_CIRCUIT_FAILURE_THRESHOLD")
    # How long (seconds) to wait in OPEN state before probing (HALF-OPEN).
    circuit_recovery_window_seconds: float = Field(default=30.0, alias="RESILIENCE_CIRCUIT_RECOVERY_WINDOW_SECONDS")

    # ── Gateway rate limiter ───────────────────────────────────────────────────
    # Maximum number of requests allowed per time window (across all clients).
    rate_limit_requests: int = Field(default=100, alias="RESILIENCE_RATE_LIMIT_REQUESTS")
    # Time window in seconds for the rate limit.
    rate_limit_window_seconds: float = Field(default=1.0, alias="RESILIENCE_RATE_LIMIT_WINDOW_SECONDS")

    # ── Fallback ──────────────────────────────────────────────────────────────
    fallback_enabled: bool = Field(default=True, alias="RESILIENCE_FALLBACK_ENABLED")
    # Comma-separated fallback chain: "openai:anthropic" means
    # if openai fails, try anthropic.  Multiple pairs separated by pipe:
    # "openai:anthropic|anthropic:openai"
    # Format: primary1:fallback1a,fallback1b|primary2:fallback2a
    fallback_chains: str = Field(default="", alias="RESILIENCE_FALLBACK_CHAINS")

    def get_fallback_configs(self) -> dict[str, FallbackConfig]:
        """
        Parse the RESILIENCE_FALLBACK_CHAINS env var into a dict of FallbackConfig.

        Format: "primary1:fb1a,fb1b|primary2:fb2a"
        Returns a mapping from primary slug → FallbackConfig.
        """
        result: dict[str, FallbackConfig] = {}
        if not self.fallback_chains.strip():
            return result

        for chain in self.fallback_chains.split("|"):
            chain = chain.strip()
            if ":" not in chain:
                continue
            primary, fallbacks_str = chain.split(":", 1)
            primary = primary.strip()
            fallbacks = [f.strip() for f in fallbacks_str.split(",") if f.strip()]
            result[primary] = FallbackConfig(primary=primary, fallbacks=fallbacks)

        return result


# ── Consolidated policy object ─────────────────────────────────────────────────

@dataclass
class ResiliencePolicy:
    """
    Resolved resilience policy used throughout the engine.

    Constructed once from ResiliencePolicySettings so the engine always
    works against a plain dataclass rather than a settings object.
    """
    request_timeout_seconds: float
    retry_enabled: bool
    max_retries: int
    initial_backoff_seconds: float
    max_backoff_seconds: float
    circuit_failure_threshold: int
    circuit_recovery_window_seconds: float
    rate_limit_requests: int
    rate_limit_window_seconds: float
    fallback_enabled: bool
    fallback_configs: dict[str, FallbackConfig]

    @classmethod
    def from_settings(cls, s: Optional[ResiliencePolicySettings] = None) -> "ResiliencePolicy":
        """Build a ResiliencePolicy from environment settings (or defaults)."""
        if s is None:
            s = ResiliencePolicySettings()
        return cls(
            request_timeout_seconds=s.request_timeout_seconds,
            retry_enabled=s.retry_enabled,
            max_retries=s.max_retries,
            initial_backoff_seconds=s.initial_backoff_seconds,
            max_backoff_seconds=s.max_backoff_seconds,
            circuit_failure_threshold=s.circuit_failure_threshold,
            circuit_recovery_window_seconds=s.circuit_recovery_window_seconds,
            rate_limit_requests=s.rate_limit_requests,
            rate_limit_window_seconds=s.rate_limit_window_seconds,
            fallback_enabled=s.fallback_enabled,
            fallback_configs=s.get_fallback_configs(),
        )

    def to_dict(self) -> dict:
        """Serialize for the /api/v1/policy endpoint (Phase 3 will call this)."""
        return {
            "id": "default",
            "name": "Default Policy",
            "enabled": True,
            "timeout": int(self.request_timeout_seconds * 1000),      # ms (matches frontend)
            "maxRetries": self.max_retries,
            "initialBackoff": int(self.initial_backoff_seconds * 1000),
            "maxBackoff": int(self.max_backoff_seconds * 1000),
            "circuitBreakerThreshold": self.circuit_failure_threshold,
            "circuitBreakerWindow": int(self.circuit_recovery_window_seconds),
            "fallbackEnabled": self.fallback_enabled,
            "rateLimitRps": self.rate_limit_requests,
        }
