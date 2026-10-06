"""
Incident Detector — Phase 4.

Evaluates telemetry/resilience signals and creates/updates incidents
when meaningful failure patterns are detected.

Design decisions:
  - Called from the Facade AFTER the request completes — NOT on the hot path
    of the actual provider call.  It runs as a non-blocking background task
    so it never adds latency to the user response.
  - No AI — incidents are created based on deterministic thresholds.
  - Deduplication is built in: one ongoing incident per (provider, failure_category).
  - The detector consumes the RequestResult from the existing engine — it does
    NOT re-read the database for every request.
  - Circuit-open events are treated as high-priority incident triggers regardless
    of threshold.
  - No duplicate incidents: if an active incident already exists, it is updated.

Thresholds (simple, tuneable):
  INCIDENT_THRESHOLD_ERRORS: int = 3
      Minimum consecutive failures to trigger an incident (for non-circuit events).

  INCIDENT_THRESHOLD_ERROR_RATE: float = 0.5
      Not used per-request — reserved for future batch/window detection.

Phase 5 note:
  The incident metadata dict is deliberately structured to make it easy for
  an AI copilot to consume the evidence and produce root-cause analysis.
"""

import asyncio
import logging
import time
from typing import Optional

from app.incidents.models import (
    FailureCategory,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentTimelineEntry,
    classify_failure_category,
)
from app.incidents.store import IncidentStore, get_incident_store
from app.resilience.events import (
    CIRCUIT_OPENED,
    FALLBACK_ATTEMPTED,
    PROVIDER_FAILURE,
    TIMEOUT_OCCURRED,
    RequestResult,
)

logger = logging.getLogger("sphinxgate.incidents")

# Minimum failures before an incident is raised (non-circuit events).
INCIDENT_THRESHOLD_ERRORS: int = 3

# Consecutive errors tracked per provider (in-memory, lightweight).
# Resets on success.
_error_streaks: dict[str, int] = {}  # provider_slug → consecutive_error_count

# error_types that say nothing about upstream provider health.
_NON_PROVIDER_ERRORS = frozenset({"gateway_rate_limit", "invalid_request"})


def _primary_from_events(result: RequestResult) -> Optional[str]:
    for e in result.events:
        if e.event_type == FALLBACK_ATTEMPTED:
            primary = (e.data or {}).get("primary")
            if primary:
                return primary
    return None


def _primary_failure_kind(result: RequestResult, primary: str) -> Optional[str]:
    """Last observed failure kind for `primary` in this request's events."""
    kind: Optional[str] = None
    for e in result.events:
        if e.provider_slug != primary:
            continue
        if e.event_type == TIMEOUT_OCCURRED:
            kind = "timeout"
        elif e.event_type == PROVIDER_FAILURE:
            kind = (e.data or {}).get("failure_kind") or kind or "unknown"
    if kind is None:
        # Primary produced no failure events: it was skipped (open circuit).
        kind = "circuit_open"
    return kind


def _display_name_for(slug: str) -> str:
    try:
        from app.providers.registry import REGISTRY
        prov = REGISTRY.get(slug)
        return getattr(prov, "display_name", None) or slug
    except Exception:
        return slug


def _primary_circuit_state(slug: str, default: str) -> str:
    try:
        from app.gateway.router import get_engine
        for snap in get_engine().get_circuit_snapshots():
            if snap.get("provider") == slug:
                return snap.get("state", default)
        return "closed"
    except Exception:
        return default


class IncidentDetector:
    """
    Evaluates each completed request and maintains incident state.

    This is intentionally simple — no ML, no complex pattern matching,
    no expensive database scans.  Phase 5 will add AI-assisted analysis.
    """

    def __init__(self, store: Optional[IncidentStore] = None) -> None:
        self._store = store or get_incident_store()

    async def evaluate(
        self,
        result: RequestResult,
        fault_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate a completed request result and update incident state.

        Parameters
        ----------
        result:
            The RequestResult from the ResilienceEngine (via Facade).
        fault_id:
            If this request was affected by fault injection, the fault ID.
        """
        try:
            await self._evaluate_internal(result, fault_id)
        except Exception:
            # Incident detection must NEVER break a user request.
            logger.exception("IncidentDetector.evaluate failed silently")

    async def _evaluate_internal(
        self,
        result: RequestResult,
        fault_id: Optional[str],
    ) -> None:
        provider_slug = result.provider_slug
        provider_display = result.provider_display_name or provider_slug
        underlying_kind: Optional[str] = result.underlying_failure_kind
        circuit_state = result.circuit_state
        primary_failed_behind_fallback = False

        # On success: reset error streak
        if result.success:
            if _error_streaks.get(provider_slug, 0) > 0:
                logger.info(
                    "Provider %s recovered — resetting error streak (was %d)",
                    provider_slug, _error_streaks[provider_slug],
                )
                _error_streaks[provider_slug] = 0
                # Optionally: auto-resolve incidents that were tied to this provider
                # (not done automatically — operator confirmation is better UX).

            if not result.fallback_used:
                return

            # A fallback served the request: the *primary* still failed.  Without
            # this the outage would be invisible to incident detection exactly
            # when fallback is working — so evaluate it as a primary failure.
            primary = _primary_from_events(result)
            if primary is None:
                return
            primary_failure = _primary_failure_kind(result, primary)
            if primary_failure is None:
                return
            provider_slug = primary
            provider_display = _display_name_for(primary)
            underlying_kind = primary_failure
            circuit_state = _primary_circuit_state(primary, default="unknown")
            primary_failed_behind_fallback = True
        elif result.error_type in _NON_PROVIDER_ERRORS:
            # Gateway rate-limit rejections and caller errors (HTTP 400) say
            # nothing about provider health — never count them.
            return

        # On failure: increment error streak
        streak = _error_streaks.get(provider_slug, 0) + 1
        _error_streaks[provider_slug] = streak

        # Determine whether circuit opened during this request
        if primary_failed_behind_fallback:
            circuit_opened = any(
                e.event_type == CIRCUIT_OPENED and e.provider_slug == provider_slug
                for e in result.events
            )
        else:
            circuit_opened = any(e.event_type == CIRCUIT_OPENED for e in result.events)
        if circuit_opened:
            circuit_state = "open"

        # Classify failure.  Prefer the engine's real cause (timeout,
        # rate_limited, …) over the generic "no_healthy_provider" error_type.
        failure_type = underlying_kind or result.error_type or "unknown"
        failure_category = classify_failure_category(failure_type)

        # ── Check if we should create/update an incident ───────────────────────
        # Triggers:
        #  1. Circuit breaker opened (immediate, regardless of streak)
        #  2. Error streak >= INCIDENT_THRESHOLD_ERRORS
        #  3. Provider is rate-limited (429 stream)
        should_create = (
            circuit_opened
            or streak >= INCIDENT_THRESHOLD_ERRORS
            or failure_category == FailureCategory.RATE_LIMITED and streak >= 2
        )

        if not should_create:
            logger.debug(
                "IncidentDetector: provider=%s streak=%d (below threshold %d) — no incident",
                provider_slug, streak, INCIDENT_THRESHOLD_ERRORS,
            )
            return

        # ── Determine severity ─────────────────────────────────────────────────
        if circuit_opened or circuit_state == "open":
            severity = IncidentSeverity.CRITICAL
        elif streak >= INCIDENT_THRESHOLD_ERRORS * 2:
            severity = IncidentSeverity.HIGH
        elif failure_category == FailureCategory.RATE_LIMITED:
            severity = IncidentSeverity.HIGH
        else:
            severity = IncidentSeverity.MEDIUM

        # ── Deduplication: look for an existing active incident ────────────────
        dedup_key = f"{provider_slug}:{failure_category.value}"
        existing = await self._store.get_active_by_dedup_key(dedup_key)

        if existing is not None:
            # Update existing incident instead of creating a duplicate.
            existing.update_from_new_failure(
                request_id=result.request_id,
                retry_count=result.retry_count,
                fallback_used=result.fallback_used,
                circuit_state=circuit_state,
                circuit_opened=circuit_opened,
            )
            if fault_id and not existing.fault_injected:
                existing.fault_injected = True
                existing.fault_id = fault_id
            await self._store.update(existing)
            logger.info(
                "Incident %s updated: provider=%s errors=%d",
                existing.incident_id, provider_slug, existing.error_count,
            )
            return

        # ── Create a new incident ──────────────────────────────────────────────
        fault_injected = fault_id is not None
        title = _build_title(
            provider_display=provider_display,
            failure_category=failure_category,
            failure_type=failure_type,
            circuit_opened=circuit_opened,
            fault_injected=fault_injected,
        )
        summary = _build_summary(
            provider_display=provider_display,
            failure_type=failure_type,
            streak=streak,
            circuit_opened=circuit_opened,
            fault_injected=fault_injected,
            fault_id=fault_id,
        )

        incident = Incident(
            provider_slug=provider_slug,
            provider_display_name=provider_display,
            failure_category=failure_category,
            failure_type=failure_type,
            severity=severity,
            title=title,
            error_count=streak,
            circuit_state=circuit_state,
            circuit_opened=circuit_opened,
            fault_injected=fault_injected,
            fault_id=fault_id,
            summary=summary,
            metadata={
                # Structured for Phase 5 AI consumption.
                "trigger": "circuit_opened" if circuit_opened else "error_threshold",
                "streak_at_creation": streak,
                "failure_type":       failure_type,
                "failure_category":   failure_category.value,
                "circuit_state":      circuit_state,
                "fault_injected":     fault_injected,
                "fault_id":           fault_id,
                "error_type":         result.error_type,
                "underlying_failure_kind": underlying_kind,
                "served_by_fallback": primary_failed_behind_fallback,
                "first_request_id":   result.request_id,
            },
        )
        incident.add_affected_request(result.request_id)
        if result.retry_count > 0:
            incident.retry_count = result.retry_count
        if result.fallback_used:
            incident.fallback_count = 1

        # Initial timeline entry.
        trigger_event = (
            f"Circuit breaker opened for {provider_display}"
            if circuit_opened
            else f"{streak} consecutive failures detected for {provider_display}"
        )
        incident.timeline.append(IncidentTimelineEntry(
            timestamp=time.time(),
            event=trigger_event,
            event_type="detection",
        ))

        await self._store.create(incident)


def _build_title(
    *,
    provider_display: str,
    failure_category: FailureCategory,
    failure_type: str,
    circuit_opened: bool,
    fault_injected: bool,
) -> str:
    prefix = "[FAULT INJECTED] " if fault_injected else ""
    if circuit_opened:
        return f"{prefix}{provider_display} — Circuit Breaker Opened"
    if failure_category == FailureCategory.AVAILABILITY:
        return f"{prefix}{provider_display} — Availability Degraded"
    if failure_category == FailureCategory.RATE_LIMITED:
        return f"{prefix}{provider_display} — Rate Limit Sustained"
    return f"{prefix}{provider_display} — {failure_type.replace('_', ' ').title()}"


def _build_summary(
    *,
    provider_display: str,
    failure_type: str,
    streak: int,
    circuit_opened: bool,
    fault_injected: bool,
    fault_id: Optional[str],
) -> str:
    parts = []
    if fault_injected:
        parts.append(f"This incident was triggered by fault injection (fault_id={fault_id}).")
    parts.append(
        f"{streak} consecutive failures observed for {provider_display}."
    )
    parts.append(f"Failure type: {failure_type.replace('_', ' ')}.")
    if circuit_opened:
        parts.append(
            "The circuit breaker has opened — requests to this provider are being blocked "
            "until the recovery window elapses."
        )
    return " ".join(parts)


# ── Singleton ──────────────────────────────────────────────────────────────────

_incident_detector: Optional["IncidentDetector"] = None


def get_incident_detector() -> IncidentDetector:
    global _incident_detector
    if _incident_detector is None:
        _incident_detector = IncidentDetector()
    return _incident_detector


def _reset_incident_detector() -> None:
    """Test helper."""
    global _incident_detector, _error_streaks
    _incident_detector = None
    _error_streaks.clear()
