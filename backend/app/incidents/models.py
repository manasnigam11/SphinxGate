"""
Incident models — Phase 4.

An Incident represents a meaningful operational problem — NOT every
individual failed request.

Design decisions:
  - Incidents are created by the IncidentDetector when meaningful failure
    patterns are observed (repeated failures, circuit opening, high error rate).
  - Each incident has a deduplication key based on provider + failure category
    + active state, so one ongoing outage creates one incident.
  - The model references telemetry record IDs rather than copying payload data,
    keeping the incident record small and the audit trail clean.
  - No AI-generated content in Phase 4 — incidents are purely evidence-based.
  - Designed so Phase 5 (AI Copilot) can consume this model directly.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.security.redaction import redact_text, redact_value


class IncidentStatus(str, Enum):
    OPEN          = "open"
    ACKNOWLEDGED  = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED      = "resolved"


class IncidentSeverity(str, Enum):
    """
    Severity is determined by failure type and provider category.

    CRITICAL: circuit open on an LLM provider (complete outage)
    HIGH:     repeated failures, sustained error rate > 50%
    MEDIUM:   intermittent failures, error rate 20-50%
    LOW:      isolated degradation, latency spike
    """
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class FailureCategory(str, Enum):
    """
    High-level category that groups related failure kinds for deduplication.
    """
    AVAILABILITY = "availability"   # Provider completely unreachable (connection, timeout, 5xx)
    RATE_LIMITED = "rate_limited"   # Provider rate-limiting (429)
    LATENCY      = "latency"        # Elevated latency, not a hard failure
    DEGRADED     = "degraded"       # Partial failures, mixed success


def classify_failure_category(error_type: Optional[str]) -> FailureCategory:
    """Map an error/failure kind to a FailureCategory for deduplication."""
    if not error_type:
        return FailureCategory.DEGRADED
    if "rate_limit" in error_type:
        return FailureCategory.RATE_LIMITED
    if any(k in error_type for k in (
        "timeout", "connection", "unavailable", "bad_gateway", "server_error",
        "5xx", "circuit_open",
    )):
        return FailureCategory.AVAILABILITY
    if "latency" in error_type:
        return FailureCategory.LATENCY
    return FailureCategory.DEGRADED


@dataclass
class IncidentTimelineEntry:
    """A single timestamped event in an incident's lifecycle."""
    timestamp: float
    event: str
    event_type: str   # "detection" | "action" | "recovery" | "update"

    def to_dict(self) -> dict:
        return {
            "timestamp":     self.timestamp,
            "timestamp_iso": _fmt(self.timestamp),
            "event":         self.event,
            "event_type":    self.event_type,
        }


@dataclass
class Incident:
    """
    A meaningful operational problem observed in the gateway.

    Fields
    ------
    incident_id:
        Auto-generated unique identifier (INC-XXXXXXXX).
    title:
        Human-readable one-liner describing the incident.
    provider_slug:
        The provider that is experiencing the problem.
    provider_display_name:
        Human-readable provider name.
    failure_category:
        High-level failure grouping (used for deduplication).
    failure_type:
        Specific error type from telemetry (e.g. "timeout").
    severity:
        Impact severity.
    status:
        Current lifecycle state.
    started_at:
        Unix timestamp when the incident was created.
    updated_at:
        Unix timestamp of the last update.
    resolved_at:
        Unix timestamp of resolution, or None.
    error_count:
        Number of consecutive/recent failures that triggered/updated this incident.
    affected_request_ids:
        List of request IDs (from telemetry) associated with this incident.
        Kept bounded (max 50) to avoid unbounded memory growth.
    retry_count:
        Total retry attempts observed during this incident.
    fallback_count:
        Number of fallback activations during this incident.
    circuit_state:
        Circuit breaker state at the time of last update.
    circuit_opened:
        True if the circuit breaker opened during this incident.
    fault_injected:
        True if this incident was triggered by fault injection.
    fault_id:
        ID of the injected fault, if applicable.
    summary:
        Brief text summary of the incident (evidence-based, no AI).
    timeline:
        Ordered list of timeline events.
    metadata:
        Additional structured data for Phase 5 AI consumption.
    """
    provider_slug: str
    provider_display_name: str
    failure_category: FailureCategory
    failure_type: str
    severity: IncidentSeverity
    title: str

    # Lifecycle
    status: IncidentStatus = IncidentStatus.OPEN
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None

    # Evidence
    error_count: int = 1
    affected_request_ids: list[str] = field(default_factory=list)  # Bounded at 50
    retry_count: int = 0
    fallback_count: int = 0
    circuit_state: str = "closed"
    circuit_opened: bool = False

    # Fault injection traceability
    fault_injected: bool = False
    fault_id: Optional[str] = None

    # Narrative
    summary: str = ""
    timeline: list[IncidentTimelineEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Auto-generated ID
    incident_id: str = field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:8].upper()}")

    # ── Deduplication key ──────────────────────────────────────────────────────

    @property
    def dedup_key(self) -> str:
        """
        Correlation key for deduplication.
        An active incident with this key blocks creation of a duplicate.
        """
        return f"{self.provider_slug}:{self.failure_category.value}"

    # ── Mutation helpers ───────────────────────────────────────────────────────

    def add_affected_request(self, request_id: str) -> None:
        """Track an affected request, bounded at 50."""
        if request_id not in self.affected_request_ids:
            if len(self.affected_request_ids) < 50:
                self.affected_request_ids.append(request_id)

    def add_timeline_entry(self, event: str, event_type: str = "update") -> None:
        self.timeline.append(IncidentTimelineEntry(
            timestamp=time.time(),
            event=event,
            event_type=event_type,
        ))
        self.updated_at = time.time()

    def update_from_new_failure(
        self,
        request_id: str,
        retry_count: int = 0,
        fallback_used: bool = False,
        circuit_state: str = "closed",
        circuit_opened: bool = False,
    ) -> None:
        """Update incident statistics when a new failure is observed."""
        self.error_count += 1
        self.retry_count += retry_count
        if fallback_used:
            self.fallback_count += 1
        self.circuit_state = circuit_state
        if circuit_opened and not self.circuit_opened:
            self.circuit_opened = True
            self.add_timeline_entry(
                f"Circuit breaker opened for {self.provider_display_name}",
                event_type="detection",
            )
        self.add_affected_request(request_id)
        self.updated_at = time.time()
        # Escalate severity if circuit opened.
        if circuit_opened and self.severity.value not in ("critical",):
            self.severity = IncidentSeverity.CRITICAL

    def acknowledge(self) -> None:
        self.status = IncidentStatus.ACKNOWLEDGED
        self.add_timeline_entry("Incident acknowledged by operator", event_type="action")

    def investigate(self) -> None:
        self.status = IncidentStatus.INVESTIGATING
        self.add_timeline_entry("Investigation started", event_type="action")

    def resolve(self, note: str = "") -> None:
        self.status = IncidentStatus.RESOLVED
        self.resolved_at = time.time()
        # The note is free text typed by an operator — redact and bound it.
        safe_note = redact_text(note).strip()[:500] if note else ""
        msg = f"Incident resolved. {safe_note}".strip() if safe_note else "Incident resolved."
        self.add_timeline_entry(msg, event_type="recovery")

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.resolved_at:
            return self.resolved_at - self.started_at
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        return {
            "incident_id":          self.incident_id,
            "title":                self.title,
            "provider_slug":        self.provider_slug,
            "provider_display_name": self.provider_display_name,
            "failure_category":     self.failure_category.value,
            "failure_type":         self.failure_type,
            "severity":             self.severity.value,
            "status":               self.status.value,
            "started_at":           self.started_at,
            "started_at_iso":       _fmt(self.started_at),
            "updated_at":           self.updated_at,
            "updated_at_iso":       _fmt(self.updated_at),
            "resolved_at":          self.resolved_at,
            "resolved_at_iso":      _fmt(self.resolved_at) if self.resolved_at else None,
            "duration_seconds":     self.duration_seconds,
            "error_count":          self.error_count,
            "affected_request_ids": self.affected_request_ids,
            "affected_count":       len(self.affected_request_ids),
            "retry_count":          self.retry_count,
            "fallback_count":       self.fallback_count,
            "circuit_state":        self.circuit_state,
            "circuit_opened":       self.circuit_opened,
            "fault_injected":       self.fault_injected,
            "fault_id":             self.fault_id,
            "summary":              redact_text(self.summary),
            "timeline":             [redact_value(e.to_dict()) for e in self.timeline],
            "metadata":             redact_value(self.metadata),
        }


def _fmt(ts: float) -> str:
    """Format unix timestamp as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
