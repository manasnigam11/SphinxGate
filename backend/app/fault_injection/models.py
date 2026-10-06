"""
Fault Injection models — Phase 4.

Defines the strict typed model for fault configuration.

Security:
  - FaultType is an enum — no arbitrary exception classes can be injected.
  - No URL fields, no arbitrary code paths.
  - Latency is bounded to a maximum safe value.
  - Duration is bounded.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Maximum allowed artificial latency to prevent DoS through fault injection.
MAX_LATENCY_MS = 30_000   # 30 seconds hard cap
MAX_DURATION_S = 3600     # 1 hour maximum fault duration


class FaultType(str, Enum):
    """
    Supported fault types.

    This is a closed enum — users cannot inject arbitrary exceptions
    or arbitrary HTTP responses.  Only these defined fault kinds are
    allowed.
    """
    TIMEOUT            = "timeout"           # Simulates asyncio.TimeoutError
    CONNECTION_ERROR   = "connection_error"  # Simulates httpx.ConnectError
    HTTP_429           = "http_429"          # Upstream rate-limit
    HTTP_500           = "http_500"          # Upstream internal server error
    HTTP_502           = "http_502"          # Bad gateway
    HTTP_503           = "http_503"          # Service unavailable
    LATENCY            = "latency"           # Adds artificial latency (no failure)


# Human-readable labels for the UI / API responses.
FAULT_TYPE_LABELS: dict[FaultType, str] = {
    FaultType.TIMEOUT:          "Timeout",
    FaultType.CONNECTION_ERROR: "Connection Error",
    FaultType.HTTP_429:         "HTTP 429 Rate Limited",
    FaultType.HTTP_500:         "HTTP 500 Server Error",
    FaultType.HTTP_502:         "HTTP 502 Bad Gateway",
    FaultType.HTTP_503:         "HTTP 503 Service Unavailable",
    FaultType.LATENCY:          "Artificial Latency",
}

# Which fault types count toward circuit-breaker failures
# (same semantics as classifier.py's _COUNTS_TOWARD_CIRCUIT).
FAULT_COUNTS_TOWARD_CIRCUIT: frozenset[FaultType] = frozenset({
    FaultType.TIMEOUT,
    FaultType.CONNECTION_ERROR,
    FaultType.HTTP_500,
    FaultType.HTTP_502,
    FaultType.HTTP_503,
    FaultType.HTTP_429,
})


@dataclass
class FaultConfig:
    """
    A single active fault configuration targeting one provider.

    Fields
    ------
    fault_id:
        Auto-generated unique identifier.
    provider_slug:
        The exact provider slug to target (e.g. "gemini", "groq").
    fault_type:
        Which kind of failure to simulate.
    latency_ms:
        Only used when fault_type == LATENCY.  Bounded at MAX_LATENCY_MS.
    duration_seconds:
        How long the fault should remain active after creation.
        0 = unlimited (cleared only by explicit DELETE).
    created_at:
        Unix timestamp of creation.
    created_by:
        Human-readable description of who/what created this fault
        (e.g. "demo-user", "test-suite").  Never stores credentials.
    note:
        Optional operator note.  Free text, stored as-is.
    is_active:
        Whether the fault is currently active.  Faults can be deactivated
        without deleting them, preserving their audit trail.
    """
    provider_slug: str
    fault_type: FaultType
    latency_ms: int = 0              # Used only for LATENCY type
    duration_seconds: int = 0        # 0 = manual clear required
    created_at: float = field(default_factory=time.time)
    created_by: str = "operator"
    note: str = ""
    is_active: bool = True
    fault_id: str = field(default_factory=lambda: f"fault-{uuid.uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        # Enforce bounds — prevent accidental/malicious extreme values.
        if self.latency_ms > MAX_LATENCY_MS:
            self.latency_ms = MAX_LATENCY_MS
        if self.duration_seconds > MAX_DURATION_S:
            self.duration_seconds = MAX_DURATION_S

    @property
    def is_expired(self) -> bool:
        """Return True if this fault has exceeded its configured duration."""
        if self.duration_seconds <= 0:
            return False
        return time.time() > (self.created_at + self.duration_seconds)

    @property
    def is_effective(self) -> bool:
        """Return True if this fault should currently be applied."""
        return self.is_active and not self.is_expired

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for API responses)."""
        return {
            "fault_id":         self.fault_id,
            "provider_slug":    self.provider_slug,
            "fault_type":       self.fault_type.value,
            "fault_type_label": FAULT_TYPE_LABELS[self.fault_type],
            "latency_ms":       self.latency_ms,
            "duration_seconds": self.duration_seconds,
            "created_at":       self.created_at,
            "created_by":       self.created_by,
            "note":             self.note,
            "is_active":        self.is_active,
            "is_expired":       self.is_expired,
            "is_effective":     self.is_effective,
        }
