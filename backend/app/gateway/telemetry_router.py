"""
Telemetry & Observability API router — Phase 3.

Read-only endpoints for the frontend dashboards and operational inspection.

Endpoints:
  GET /api/v1/telemetry/requests           — recent requests (paginated)
  GET /api/v1/telemetry/requests/{id}      — single request detail
  GET /api/v1/telemetry/summary            — aggregate statistics
  GET /api/v1/telemetry/providers/{slug}   — per-provider stats
  GET /api/v1/telemetry/cache              — cache statistics

Security:
  - These endpoints expose operational telemetry only.
  - No API keys, credentials, or secrets are returned.
  - Response bodies are bounded and sanitized by the TelemetryRecord schema.
  - In Phase 3, these endpoints have no authentication.
    NOTE: In a production deployment these endpoints MUST be behind
    authentication/authorization.  This limitation is documented.
"""

import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.telemetry.store import get_telemetry_store
from app.facade import get_facade
from app.security.redaction import redact_text, redact_value

logger = logging.getLogger("sphinxgate.telemetry_api")

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


# ── Recent requests ────────────────────────────────────────────────────────────

@router.get("/requests")
async def list_requests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Return the most recent gateway requests (newest first).

    Query params:
      limit  — number of records to return (1–200, default 50)
      offset — pagination offset
    """
    store = get_telemetry_store()
    records = await store.recent(limit=limit, offset=offset)
    return {
        "requests": [_format_record(r, include_events=True) for r in records],
        "count": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.get("/requests/{request_id}")
async def get_request(request_id: str) -> dict[str, Any]:
    """Return full detail for a single request by its request_id."""
    store = get_telemetry_store()
    record = await store.get(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return _format_record(record, include_events=True)


# ── Summary / analytics ────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    window: str = Query(default="1h", pattern=r"^\d+[mhd]$"),
) -> dict[str, Any]:
    """
    Aggregate statistics for a time window.

    window: e.g. "1h" (1 hour), "24h" (24 hours), "7d" (7 days).
    Supports m (minutes), h (hours), d (days).
    """
    seconds = _parse_window(window)
    store = get_telemetry_store()
    summary = await store.summary(since_seconds=seconds)

    success_rate = (
        round(summary.successful_requests / summary.total_requests * 100, 1)
        if summary.total_requests > 0
        else None
    )
    error_rate = (
        round(summary.failed_requests / summary.total_requests * 100, 1)
        if summary.total_requests > 0
        else None
    )
    cache_hit_rate = None
    total_cache = summary.cache_hits + summary.cache_misses
    if total_cache > 0:
        cache_hit_rate = round(summary.cache_hits / total_cache * 100, 1)

    return {
        "window": window,
        "since_seconds": seconds,
        "total_requests": summary.total_requests,
        "successful_requests": summary.successful_requests,
        "failed_requests": summary.failed_requests,
        "success_rate": success_rate,
        "error_rate": error_rate,
        "avg_latency_ms": summary.avg_latency_ms,
        "p95_latency_ms": summary.p95_latency_ms,
        "total_tokens_used": summary.total_tokens_used,
        "total_retries": summary.total_retries,
        "total_fallbacks": summary.total_fallbacks,
        "cache_hits": summary.cache_hits,
        "cache_misses": summary.cache_misses,
        "cache_hit_rate": cache_hit_rate,
        "provider_stats": summary.provider_stats,
        "failure_types": summary.failure_types,
    }


# ── Per-provider stats ─────────────────────────────────────────────────────────

@router.get("/providers/{provider_slug}")
async def get_provider_telemetry(
    provider_slug: str,
    window: str = Query(default="24h", pattern=r"^\d+[mhd]$"),
) -> dict[str, Any]:
    """Return per-provider telemetry statistics."""
    seconds = _parse_window(window)
    store = get_telemetry_store()
    stats = await store.provider_stats(provider_slug=provider_slug, since_seconds=seconds)
    return {"window": window, **stats}


# ── Provider health (circuit + telemetry combined) ─────────────────────────────

@router.get("/health")
async def get_provider_health() -> dict[str, Any]:
    """
    Combined provider health view: circuit state + recent telemetry.

    Returns a list of providers with their live circuit state and recent
    stats — suitable for the Provider Health and Dashboard pages.
    """
    from app.providers.registry import get_provider_info
    from app.gateway.router import get_engine
    from app.config import get_settings

    engine = get_engine()
    circuit_snaps = {s["provider"]: s for s in engine.get_circuit_snapshots()}
    store = get_telemetry_store()
    settings = get_settings()

    from app.health.checker import get_health_registry, ActiveHealthState
    health_registry = get_health_registry()

    providers = []
    for info in get_provider_info():
        slug = info["slug"]
        snap = circuit_snaps.get(slug) or engine.default_circuit_snapshot(slug)
        stats = await store.provider_stats(slug, since_seconds=3600)
        active_health = health_registry.get_state(slug)
        health_details = health_registry.get_details(slug)

        circuit_state = snap.get("state", "closed")
        
        # Determine health_status based on circuit state and active health
        if circuit_state == "open":
            health_status = "down"
        elif active_health == ActiveHealthState.UNHEALTHY:
            health_status = "down"
        elif circuit_state == "half-open" or active_health == ActiveHealthState.DEGRADED:
            health_status = "degraded"
        elif active_health == ActiveHealthState.HEALTHY:
            health_status = "healthy"
        elif stats.get("total_requests", 0) == 0:
            health_status = "unknown"
        else:
            success_r = stats.get("successful_requests", 0)
            total_r = stats.get("total_requests", 1)
            success_pct = success_r / total_r * 100
            health_status = "healthy" if success_pct >= 95 else "degraded"

        # `configured` never reveals the key — only whether one exists.
        configured = (
            bool(settings.get_provider_api_key(slug)) if info.get("requires_api_key") else True
        )
        providers.append({
            **info,
            "configured": configured,
            "circuit_state": circuit_state,
            "failure_count": snap.get("failure_count", 0),
            "failure_threshold": snap.get("failure_threshold"),
            "health_status": health_status,
            "active_health": health_details,
            "recent_stats": stats,
        })

    return {"providers": providers}


# ── Cache statistics ───────────────────────────────────────────────────────────

@router.get("/cache")
async def get_cache_stats() -> dict[str, Any]:
    """Return cache statistics for all providers."""
    facade = get_facade()
    return {
        "cache_stats": facade.cache_stats(),
        "note": "In-process cache — stats reset on server restart.",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_window(window: str) -> float:
    """Parse a window string like '1h', '24h', '7d', '30m' to seconds."""
    unit = window[-1]
    value = int(window[:-1])
    multipliers = {"m": 60, "h": 3600, "d": 86400}
    return float(value * multipliers.get(unit, 3600))


def service_state_for(success: bool, fallback_used: bool, error_type: Optional[str]) -> str:
    """Truthful service state for a stored request (mirrors facade.compute_service_state)."""
    if error_type == "degraded_stale_cache":
        return "degraded"
    if success:
        return "fallback" if fallback_used else "normal"
    if error_type in ("gateway_rate_limit", "invalid_request"):
        return "normal"
    return "unavailable"


def _format_record(rec, *, include_events: bool = False) -> dict[str, Any]:
    """Serialize a TelemetryRecord to a dict safe for API responses."""
    d = {
        "request_id": rec.request_id,
        "timestamp": rec.timestamp,
        "timestamp_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(rec.timestamp)
        ),
        "provider": rec.provider_slug,
        "provider_display_name": rec.provider_display_name,
        "provider_category": rec.provider_category,
        "endpoint": rec.endpoint,
        "success": rec.success,
        "status_code": rec.status_code,
        "latency_ms": rec.latency_ms,
        "retry_count": rec.retry_count,
        "fallback_used": rec.fallback_used,
        "circuit_state": rec.circuit_state,
        "tokens_used": rec.tokens_used,
        "cache_hit": rec.cache_hit,
        "error_type": rec.error_type,
        "service_state": service_state_for(rec.success, rec.fallback_used, rec.error_type),
        # Redacted on read as well as on write (defence in depth).
        "error_message": redact_text(rec.error_message) if rec.error_message else None,
    }
    if include_events:
        try:
            d["events"] = redact_value(json.loads(rec.events_json))
        except Exception:
            d["events"] = []
    return d
