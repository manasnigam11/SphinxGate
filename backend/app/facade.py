"""
SphinxGate Facade — Phase 3.

The Facade is the single coordination point for all gateway requests.
It answers the question: "How does a request move through SphinxGate?"

What the Facade does (orchestration only):
  1. Assigns / validates the request ID.
  2. Selects and validates the target provider.
  3. Consults the cache (public API providers only).
  4. Delegates to the ResilienceEngine (which owns retry/circuit/rate-limit).
  5. Writes a TelemetryRecord to the store.
  6. Returns a structured FacadeResult to the router.

What the Facade does NOT do:
  - Implement retry/backoff/circuit-breaker logic  (that stays in ResilienceEngine).
  - Implement provider-specific HTTP calls          (that stays in provider adapters).
  - Parse/validate request bodies                  (that stays in Pydantic models).
  - Persist or query telemetry                     (that stays in TelemetryStore).

Design:
  - The router imports only the Facade — it no longer calls the engine directly.
  - The Facade is stateless: all state lives in its injected components.
  - Telemetry failures are silently absorbed; they never break user requests.
  - Cache failures are silently absorbed; the request falls through to the engine.

Security:
  - The api_key_getter callable is provided by the router (from Settings).
  - The Facade never receives raw API key values — it passes the getter through.
  - Nothing sensitive is written to telemetry (enforced by TelemetryRecord shape).
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.cache.store import CacheResult, ResponseCache, get_cache
from app.providers.base import ProviderCategory
from app.providers.registry import get_provider
from app.resilience.engine import ResilienceEngine
from app.resilience.events import (
    DEGRADED_RESPONSE_SERVED,
    RequestResult,
    ResilienceEvent,
)
from app.security.redaction import redact_text, redact_value
from app.telemetry.models import TelemetryRecord
from app.telemetry.store import TelemetryStore, get_telemetry_store

logger = logging.getLogger("sphinxgate.facade")

# Service states communicated to clients (Phase 5)
STATE_NORMAL = "normal"            # served by the requested provider
STATE_FALLBACK = "fallback"        # served by a configured fallback provider
STATE_DEGRADED = "degraded"        # served from stale cache; explicitly NOT live data
STATE_UNAVAILABLE = "unavailable"  # no provider could serve the request

# Keep strong references to fire-and-forget tasks so they are not GC'd mid-flight.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def compute_service_state(result: RequestResult, degraded: bool = False) -> str:
    """Derive the truthful service state of a finished request."""
    if degraded:
        return STATE_DEGRADED
    if result.success:
        return STATE_FALLBACK if result.fallback_used else STATE_NORMAL
    if result.error_type == "no_healthy_provider":
        return STATE_UNAVAILABLE
    # gateway_rate_limit / invalid_request: the service itself is not degraded.
    return STATE_NORMAL


@dataclass
class FacadeResult:
    """
    Everything the router needs to build an HTTP response.

    Extends RequestResult with cache metadata so the router can
    include cache information in headers and response bodies.
    """
    # Delegate fields from RequestResult
    result: RequestResult
    # Cache metadata
    cache_hit: bool = False
    cache_key: Optional[str] = None
    cache_age_seconds: float = 0.0
    is_stale_cache: bool = False
    # Phase 4 — fault injection traceability
    fault_id: Optional[str] = None
    # Phase 5 — truthful service state + degradation detail
    service_state: str = STATE_NORMAL
    degraded: bool = False
    degraded_reason: Optional[str] = None


class SphinxGateFacade:
    """
    Orchestrates the full SphinxGate request pipeline.

    Instantiate once per process (singleton); inject into the router.
    """

    def __init__(
        self,
        engine: ResilienceEngine,
        cache: Optional[ResponseCache] = None,
        store: Optional[TelemetryStore] = None,
    ) -> None:
        self._engine = engine
        self._cache = cache or get_cache()
        self._store = store or get_telemetry_store()

    # ── Main entry points ──────────────────────────────────────────────────────

    async def handle_llm_request(
        self,
        *,
        request_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        api_key_getter: Callable[[str], Optional[str]],
        endpoint: str = "/api/v1/chat/completions",
    ) -> FacadeResult:
        """
        Process an LLM chat-completion request through the full pipeline.

        No cache is consulted for LLM requests — LLM responses are not
        deterministic and caching them would be incorrect.
        """
        # 1. Validate provider
        try:
            provider_obj = get_provider(provider_slug)
        except KeyError:
            raise ValueError(f"Unknown provider: {provider_slug!r}")

        if provider_obj.category != ProviderCategory.LLM:
            raise ValueError(
                f"Provider {provider_slug!r} is not an LLM provider. "
                "Use /api/v1/query for public API providers."
            )

        # 2. Execute through the Resilience Engine
        engine_result = await self._engine.execute(
            request_id=request_id,
            provider_slug=provider_slug,
            payload=payload,
            api_key_getter=api_key_getter,
        )

        # 3. Determine if a fault is active (for traceability)
        fault_id = await self._get_active_fault_id(provider_slug)

        facade_result = FacadeResult(
            result=engine_result,
            fault_id=fault_id,
            service_state=compute_service_state(engine_result),
        )

        # 4. Record telemetry (fire-and-forget; never raises to the caller)
        await self._record_telemetry(
            result=engine_result,
            endpoint=endpoint,
            provider_category=ProviderCategory.LLM.value,
            cache_result=None,
        )

        # 5. Incident detection (fire-and-forget background task)
        _spawn_background(
            self._detect_incident(result=engine_result, fault_id=fault_id)
        )

        return facade_result

    async def handle_public_api_request(
        self,
        *,
        request_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        api_key_getter: Callable[[str], Optional[str]],
        endpoint: str = "/api/v1/query",
    ) -> FacadeResult:
        """
        Process a public API request through the cache → resilience pipeline.

        Cache lookup:
          HIT  → return cached response immediately (no engine call)
          MISS → call through engine → cache successful response
        """
        # 1. Validate provider
        try:
            provider_obj = get_provider(provider_slug)
        except KeyError:
            raise ValueError(f"Unknown provider: {provider_slug!r}")

        if provider_obj.category != ProviderCategory.PUBLIC_API:
            raise ValueError(
                f"Provider {provider_slug!r} is not a public API provider. "
                "Use /api/v1/chat/completions for LLM providers."
            )

        # 2. Get cache metadata (do not return early; always fetch fresh data)
        cache_result = self._safe_cache_get(provider_slug, payload)

        # 3. Always go through the resilience engine for fresh data
        engine_result = await self._engine.execute(
            request_id=request_id,
            provider_slug=provider_slug,
            payload=payload,
            api_key_getter=api_key_getter,
        )

        # 4. Cache the successful response
        cache_key: Optional[str] = cache_result.cache_key
        if engine_result.success and engine_result.response is not None:
            cache_key = self._safe_cache_set(provider_slug, payload, engine_result.response)

        # 5. Fault traceability
        fault_id = await self._get_active_fault_id(provider_slug)

        # 5b. Graceful degradation (policy-driven, explicit, never fabricated):
        #     only when every provider genuinely failed AND a previously cached
        #     real response exists within the policy's max stale age.
        degraded_result: Optional[RequestResult] = None
        degraded_age = 0.0
        if not engine_result.success:
            degraded_result, degraded_age = self._try_degraded_response(
                engine_result, provider_slug, provider_obj.display_name, payload
            )

        if degraded_result is not None:
            facade_result = FacadeResult(
                result=degraded_result,
                cache_hit=True,
                cache_key=cache_key,
                cache_age_seconds=degraded_age,
                is_stale_cache=True,
                fault_id=fault_id,
                service_state=STATE_DEGRADED,
                degraded=True,
                degraded_reason=engine_result.underlying_failure_kind or engine_result.error_type,
            )
            final_result = degraded_result
        else:
            facade_result = FacadeResult(
                result=engine_result,
                cache_hit=False,
                cache_key=cache_key,
                fault_id=fault_id,
                service_state=compute_service_state(engine_result),
            )
            final_result = engine_result

        # 6. Telemetry (records the degraded outcome truthfully — see _record_telemetry)
        await self._record_telemetry(
            result=final_result,
            endpoint=endpoint,
            provider_category=ProviderCategory.PUBLIC_API.value,
            cache_result=cache_result,
        )

        # 7. Incident detection (fire-and-forget).  Always evaluates the ORIGINAL
        #    engine outcome so an outage is never masked by a degraded response.
        _spawn_background(
            self._detect_incident(result=engine_result, fault_id=fault_id)
        )

        return facade_result

    # ── Graceful degradation ──────────────────────────────────────────────

    def _try_degraded_response(
        self,
        engine_result: RequestResult,
        provider_slug: str,
        display_name: str,
        payload: dict[str, Any],
    ) -> tuple[Optional[RequestResult], float]:
        """
        Return (degraded RequestResult, stale_age) or (None, 0.0).

        Conditions (all required):
          - the engine failed because no provider was available (a 400 or a
            gateway rate-limit is NOT an outage and is never masked);
          - the active policy has degradation enabled;
          - the provider's cache policy opted in to stale-on-failure;
          - a real cached response younger than the policy's max stale age exists.
        """
        if engine_result.error_type != "no_healthy_provider":
            return None, 0.0
        policy = self._engine.policy
        if not getattr(policy, "degradation_enabled", False):
            return None, 0.0
        try:
            stale = self._cache.get(
                provider_slug,
                payload,
                allow_stale=True,
                max_stale_age=getattr(policy, "degradation_max_stale_seconds", None),
            )
        except Exception:
            logger.warning("Stale cache lookup failed for %s", provider_slug)
            return None, 0.0
        if not stale.hit:
            return None, 0.0

        reason = engine_result.underlying_failure_kind or engine_result.error_type
        events = list(engine_result.events)
        events.append(ResilienceEvent(
            event_type=DEGRADED_RESPONSE_SERVED,
            request_id=engine_result.request_id,
            provider_slug=provider_slug,
            data={"stale_age_seconds": round(stale.age_seconds, 1), "reason": reason},
        ))
        logger.warning(
            "[%s] DEGRADED provider=%s serving stale cache age=%.0fs reason=%s",
            engine_result.request_id, provider_slug, stale.age_seconds, reason,
        )
        return RequestResult(
            success=False,                 # provider health: the live call failed
            response=stale.data,           # real previously-cached upstream data
            request_id=engine_result.request_id,
            provider_slug=provider_slug,
            provider_display_name=display_name,
            latency_ms=engine_result.latency_ms,
            retry_count=engine_result.retry_count,
            circuit_state=engine_result.circuit_state,
            fallback_used=engine_result.fallback_used,
            status_code=200,               # what the client actually received
            tokens_used=0,
            error_type="degraded_stale_cache",
            error_message=(
                f"Live provider unavailable ({reason}); "
                f"serving cached data that is {int(stale.age_seconds)}s old."
            ),
            underlying_failure_kind=engine_result.underlying_failure_kind,
            events=events,
        ), stale.age_seconds

    # ── Cache helpers ──────────────────────────────────────────────────────────

    def _safe_cache_get(self, provider_slug: str, params: dict[str, Any]) -> CacheResult:
        try:
            return self._cache.get(provider_slug, params)
        except Exception:
            logger.warning("Cache.get failed for %s — proceeding without cache", provider_slug)
            return CacheResult(hit=False)

    def _safe_cache_set(self, provider_slug: str, params: dict[str, Any], data: Any) -> str:
        try:
            return self._cache.set(provider_slug, params, data)
        except Exception:
            logger.warning("Cache.set failed for %s — result not cached", provider_slug)
            return ""

    # ── Telemetry ──────────────────────────────────────────────────────────────

    async def _record_telemetry(
        self,
        result: RequestResult,
        endpoint: str,
        provider_category: str,
        cache_result: Optional[CacheResult],
    ) -> None:
        """Write a TelemetryRecord to the store. Never raises."""
        try:
            # Serialize events — redact anything that could contain a secret
            events = []
            for ev in result.events:
                events.append({
                    "event_type": ev.event_type,
                    "provider_slug": ev.provider_slug,
                    "timestamp": ev.timestamp,
                    "data": redact_value(ev.data),
                })

            rec = TelemetryRecord(
                request_id=result.request_id,
                timestamp=time.time(),
                provider_slug=result.provider_slug,
                provider_display_name=result.provider_display_name,
                provider_category=provider_category,
                endpoint=endpoint,
                success=result.success,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                retry_count=result.retry_count,
                fallback_used=result.fallback_used,
                circuit_state=result.circuit_state,
                error_type=result.error_type,
                # Redact, then truncate, so large/credentialed provider payloads never persist
                error_message=redact_text(result.error_message)[:500] if result.error_message else None,
                tokens_used=result.tokens_used,
                cache_hit=bool(cache_result and cache_result.hit),
                cache_key=cache_result.cache_key if cache_result else None,
                events_json=json.dumps(events),
            )
            await self._store.record(rec)
        except Exception:
            logger.exception("Telemetry recording failed (non-fatal)")

    # ── Result builder for cache hits ─────────────────────────────────────────

    @staticmethod
    def _build_cache_hit_result(
        request_id: str,
        provider_slug: str,
        provider_display_name: str,
        data: Any,
    ) -> RequestResult:
        """
        Build a synthetic RequestResult for a cache hit.
        Latency is ~0, no retries, no circuit events.
        """
        from app.resilience.events import RequestResult as RR
        return RR(
            success=True,
            response=data,
            request_id=request_id,
            provider_slug=provider_slug,
            provider_display_name=provider_display_name,
            latency_ms=0,
            retry_count=0,
            circuit_state="closed",
            fallback_used=False,
            status_code=200,
            tokens_used=0,
        )

    # ── Phase 4 helpers ────────────────────────────────────────────────────────

    async def _get_active_fault_id(self, provider_slug: str) -> Optional[str]:
        """Return the active fault ID for a provider, or None."""
        try:
            from app.fault_injection.store import get_fault_store, is_fault_injection_enabled
            if not is_fault_injection_enabled():
                return None
            store = get_fault_store()
            fault = await store.get_effective_for_provider(provider_slug)
            return fault.fault_id if fault else None
        except Exception:
            return None

    async def _detect_incident(
        self,
        result: RequestResult,
        fault_id: Optional[str],
    ) -> None:
        """Run the incident detector. Never raises — called as background task."""
        try:
            from app.incidents.detector import get_incident_detector
            detector = get_incident_detector()
            await detector.evaluate(result=result, fault_id=fault_id)
        except Exception:
            logger.exception("Incident detection failed silently")

    # ── Introspection ─────────────────────────────────────────────────────────

    def cache_stats(self) -> dict[str, Any]:
        """Return current cache statistics."""
        return self._cache.stats()

    @property
    def engine(self) -> ResilienceEngine:
        return self._engine


# ── Singleton helpers ─────────────────────────────────────────────────────────
_facade: Optional[SphinxGateFacade] = None


def get_facade(engine: Optional[ResilienceEngine] = None) -> SphinxGateFacade:
    """
    Return (or create) the process-level singleton Facade.

    Pass `engine` only on first call; subsequent calls ignore it.
    """
    global _facade
    if _facade is None:
        if engine is None:
            # Lazy import to avoid circular deps
            from app.gateway.router import get_engine
            engine = get_engine()
        _facade = SphinxGateFacade(engine=engine)
    return _facade


def _reset_facade(facade: Optional[SphinxGateFacade] = None) -> None:
    """Replace the facade singleton — used by tests."""
    global _facade
    _facade = facade
