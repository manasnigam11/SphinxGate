"""
Structured event types emitted by the Resilience Engine.

Phase 3 (Observability) will consume these events for logging, dashboards,
and incident detection. Phase 2 defines the shape — Phase 3 will persist and
surface them.

Events are plain dataclasses, not database models, so they stay lightweight
and don't pull in any persistence dependencies.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Event type literals ────────────────────────────────────────────────────────

RETRY_ATTEMPTED       = "retry_attempted"
RETRY_EXHAUSTED       = "retry_exhausted"
CIRCUIT_OPENED        = "circuit_opened"
CIRCUIT_CLOSED        = "circuit_closed"
CIRCUIT_HALF_OPEN     = "circuit_half_open"
FALLBACK_ATTEMPTED    = "fallback_attempted"
FALLBACK_SUCCEEDED    = "fallback_succeeded"
FALLBACK_EXHAUSTED    = "fallback_exhausted"
RATE_LIMIT_REJECTED   = "rate_limit_rejected"
TIMEOUT_OCCURRED      = "timeout_occurred"
PROVIDER_FAILURE      = "provider_failure"
REQUEST_SUCCEEDED     = "request_succeeded"
DEGRADED_RESPONSE_SERVED = "degraded_response_served"   # Phase 5


@dataclass
class ResilienceEvent:
    """
    A structured event emitted by the resilience engine.

    All events share this common shape.  The `data` field carries
    event-specific payload that Phase 3 can index or display.
    """
    event_type: str                    # One of the event-type literals above
    request_id: str
    provider_slug: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestResult:
    """
    Final outcome of a request as seen by the resilience engine.

    This is what the gateway router receives back from the engine and uses
    to build the HTTP response + gateway metadata headers.
    """
    success: bool
    response: Optional[dict[str, Any]]   # None on failure

    # Metadata consumed by the frontend via HTTP headers
    request_id: str
    provider_slug: str
    provider_display_name: str
    latency_ms: int
    retry_count: int
    circuit_state: str    # "closed" | "open" | "half-open"
    fallback_used: bool
    status_code: int      # HTTP status code to return to client
    tokens_used: int

    # Error detail (only populated when success=False)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    # Phase 5 — the last *real* failure kind behind a generic error_type such as
    # "no_healthy_provider" (e.g. "timeout", "rate_limited", "circuit_open").
    underlying_failure_kind: Optional[str] = None

    # Events emitted during this request lifecycle (for Phase 3)
    events: list[ResilienceEvent] = field(default_factory=list)
