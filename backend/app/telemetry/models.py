"""
Telemetry data models — Phase 3.

Plain dataclasses (not Pydantic/ORM) so they stay fast and dependency-free.
The telemetry store serializes/deserializes them to/from SQLite.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TelemetryRecord:
    """
    One record per gateway request — stored in the telemetry database.

    Every field intentionally avoids storing secrets (no API keys,
    no authorization headers, no request/response bodies beyond what's
    operationally useful).
    """
    # Correlation
    request_id: str
    timestamp: float                    # Unix epoch, seconds

    # Routing
    provider_slug: str                  # Provider that ultimately served the request
    provider_display_name: str
    provider_category: str              # "llm" | "public_api"
    endpoint: str                       # "/api/v1/chat/completions" | "/api/v1/query"

    # Outcome
    success: bool
    status_code: int
    latency_ms: int

    # Resilience metadata
    retry_count: int
    fallback_used: bool
    circuit_state: str                  # "closed" | "open" | "half-open"

    # Error detail (None on success)
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # Token usage (LLM only, 0 for public APIs)
    tokens_used: int = 0

    # Cache metadata (Phase 3)
    cache_hit: bool = False
    cache_key: Optional[str] = None

    # Resilience events snapshot (JSON-serialized list of event dicts)
    events_json: str = "[]"             # serialized list[dict]


@dataclass
class TelemetrySummary:
    """
    Aggregated statistics over a time window.
    Returned by the /api/v1/telemetry/summary endpoint.
    """
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_tokens_used: int = 0
    total_retries: int = 0
    total_fallbacks: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    # Per-provider breakdown: {slug: {total, success, avg_latency_ms}}
    provider_stats: dict[str, Any] = field(default_factory=dict)
    # Recent failure distribution: {error_type: count}
    failure_types: dict[str, int] = field(default_factory=dict)
