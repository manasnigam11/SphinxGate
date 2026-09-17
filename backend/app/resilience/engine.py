"""
Top-level Resilience Engine — Phase 2.

This is the single entry point the gateway router calls.
It composes all resilience components:

  Gateway Router
       │
       ▼
  ResilienceEngine.execute(request_id, provider_slug, payload, api_key)
       │
       ├─ GatewayRateLimiter.allow()         → reject if exceeded
       │
       ├─ For primary provider (then fallbacks):
       │    ├─ CircuitBreaker.allow_request() → skip if OPEN
       │    ├─ CircuitBreaker.maybe_enter_half_open()
       │    │
       │    └─ Retry loop (up to max_retries + 1 attempts):
       │         ├─ provider.chat_completion(payload, api_key) [with timeout]
       │         ├─ on success → CircuitBreaker.record_success()
       │         └─ on failure → classify → CircuitBreaker.record_failure()
       │                        → if retryable: exponential backoff, retry
       │                        → if not retryable: break retry loop
       │
       └─ Return RequestResult

Design decisions:
  - The engine holds the circuit-breaker registry and rate limiter as instance
    attributes so they persist across requests (process lifetime).
  - Timeout is applied per-attempt (not total), so retries get their own timeout.
  - Fallback only happens if fallback_enabled AND the primary provider has a
    fallback chain configured in the policy.
  - The engine never fabricates a successful response.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

import httpx

from app.providers.base import BaseProvider
from app.providers.registry import get_provider
from app.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitState
from app.resilience.classifier import (
    FailureKind,
    classify_exception,
    counts_toward_circuit,
    is_retryable,
)
from app.resilience.events import (
    CIRCUIT_OPENED,
    CIRCUIT_CLOSED,
    CIRCUIT_HALF_OPEN,
    FALLBACK_ATTEMPTED,
    FALLBACK_EXHAUSTED,
    FALLBACK_SUCCEEDED,
    PROVIDER_FAILURE,
    RATE_LIMIT_REJECTED,
    REQUEST_SUCCEEDED,
    RETRY_ATTEMPTED,
    RETRY_EXHAUSTED,
    TIMEOUT_OCCURRED,
    RequestResult,
    ResilienceEvent,
)
from app.resilience.policy import ResiliencePolicy
from app.resilience.rate_limiter import GatewayRateLimiter

logger = logging.getLogger("sphinxgate.resilience")


class ResilienceEngine:
    """
    Orchestrates timeout, retry, circuit-breaking, fallback, and rate-limiting
    for every outbound provider request.
    """

    def __init__(self, policy: ResiliencePolicy) -> None:
        self._policy = policy
        self._circuit_breakers = CircuitBreakerRegistry(
            failure_threshold=policy.circuit_failure_threshold,
            recovery_window_seconds=policy.circuit_recovery_window_seconds,
        )
        self._rate_limiter = GatewayRateLimiter(
            max_requests=policy.rate_limit_requests,
            window_seconds=policy.rate_limit_window_seconds,
        )

    # ── Public entry point ─────────────────────────────────────────────────────

    async def execute(
        self,
        request_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        api_key_getter,      # Callable[[str], Optional[str]]
    ) -> RequestResult:
        """
        Execute a request through the full resilience stack.

        Parameters
        ----------
        request_id:
            Unique ID for this gateway request (from the router).
        provider_slug:
            The primary provider the client requested.
        payload:
            The validated request body dict.
        api_key_getter:
            Callable that returns the API key for a given provider slug,
            or None if the provider is not configured.
        """
        events: list[ResilienceEvent] = []

        # ── 1. Gateway rate limit ──────────────────────────────────────────────
        if not await self._rate_limiter.allow():
            events.append(ResilienceEvent(
                event_type=RATE_LIMIT_REJECTED,
                request_id=request_id,
                provider_slug=provider_slug,
                data={"rate_limit": self._policy.rate_limit_requests},
            ))
            return RequestResult(
                success=False,
                response=None,
                request_id=request_id,
                provider_slug=provider_slug,
                provider_display_name=provider_slug,
                latency_ms=0,
                retry_count=0,
                circuit_state=CircuitState.CLOSED.value,
                fallback_used=False,
                status_code=429,
                tokens_used=0,
                error_type="gateway_rate_limit",
                error_message="Gateway rate limit exceeded. Please slow down.",
                events=events,
            )

        # ── 2. Build provider chain [primary, ...fallbacks] ────────────────────
        provider_chain = self._build_provider_chain(provider_slug)

        # ── 3. Try each provider in the chain ─────────────────────────────────
        fallback_used = False
        overall_start = time.perf_counter()

        for chain_index, slug in enumerate(provider_chain):
            if chain_index > 0:
                # This is a fallback attempt — validate it has a key.
                events.append(ResilienceEvent(
                    event_type=FALLBACK_ATTEMPTED,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"primary": provider_slug, "fallback": slug},
                ))
                fallback_used = True
                logger.info(
                    "[%s] fallback → %s (primary %s unavailable)",
                    request_id, slug, provider_slug,
                )

            # ── 3a. Resolve provider adapter ───────────────────────────────────
            try:
                provider = get_provider(slug)
            except KeyError:
                logger.warning("[%s] Unknown provider in chain: %s — skipping", request_id, slug)
                continue

            # ── 3b. Check API key ──────────────────────────────────────────────
            api_key = api_key_getter(slug)
            if not api_key:
                logger.warning("[%s] No API key for %s — skipping", request_id, slug)
                continue

            # ── 3c. Circuit breaker check ──────────────────────────────────────
            cb = await self._circuit_breakers.get(slug)
            half_open_entered = await cb.maybe_enter_half_open()
            if half_open_entered:
                events.append(ResilienceEvent(
                    event_type=CIRCUIT_HALF_OPEN,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"failure_count": cb.failure_count},
                ))

            if not cb.allow_request() and not half_open_entered:
                logger.info(
                    "[%s] circuit OPEN for %s — skipping provider",
                    request_id, slug,
                )
                continue  # Try next in chain

            # ── 3d. Retry loop for this provider ──────────────────────────────
            result = await self._attempt_with_retries(
                request_id=request_id,
                provider=provider,
                slug=slug,
                payload=payload,
                api_key=api_key,
                cb=cb,
                events=events,
            )

            if result is not None:
                # Success
                elapsed_ms = int((time.perf_counter() - overall_start) * 1000)
                if chain_index > 0:
                    events.append(ResilienceEvent(
                        event_type=FALLBACK_SUCCEEDED,
                        request_id=request_id,
                        provider_slug=slug,
                        data={"primary": provider_slug, "fallback": slug},
                    ))
                events.append(ResilienceEvent(
                    event_type=REQUEST_SUCCEEDED,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"latency_ms": elapsed_ms},
                ))
                usage = result.get("usage") or {}
                return RequestResult(
                    success=True,
                    response=result,
                    request_id=request_id,
                    provider_slug=slug,
                    provider_display_name=provider.display_name,
                    latency_ms=elapsed_ms,
                    retry_count=self._count_retries(events, slug),
                    circuit_state=cb.state.value,
                    fallback_used=fallback_used,
                    status_code=200,
                    tokens_used=usage.get("total_tokens", 0),
                    events=events,
                )
            # Provider failed all retries — try next in chain

        # ── 4. All providers exhausted ─────────────────────────────────────────
        elapsed_ms = int((time.perf_counter() - overall_start) * 1000)
        if fallback_used:
            events.append(ResilienceEvent(
                event_type=FALLBACK_EXHAUSTED,
                request_id=request_id,
                provider_slug=provider_slug,
                data={"chain": provider_chain},
            ))
            logger.error(
                "[%s] all providers exhausted: %s", request_id, provider_chain
            )

        # Determine what circuit state to report (use primary provider's CB)
        try:
            primary_cb = await self._circuit_breakers.get(provider_slug)
            final_circuit_state = primary_cb.state.value
        except Exception:
            final_circuit_state = CircuitState.OPEN.value

        return RequestResult(
            success=False,
            response=None,
            request_id=request_id,
            provider_slug=provider_slug,
            provider_display_name=provider_slug,
            latency_ms=elapsed_ms,
            retry_count=self._count_retries(events, provider_slug),
            circuit_state=final_circuit_state,
            fallback_used=fallback_used,
            status_code=503,
            tokens_used=0,
            error_type="no_healthy_provider",
            error_message=(
                "No healthy provider is currently available. "
                f"Tried: {', '.join(provider_chain)}."
            ),
            events=events,
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _build_provider_chain(self, primary_slug: str) -> list[str]:
        """
        Build the ordered list of providers to try: [primary, fallback1, fallback2, …].

        Fallbacks come from the policy's fallback_configs.
        If fallback is disabled or no chain is configured, returns [primary] only.
        """
        chain = [primary_slug]

        if not self._policy.fallback_enabled:
            return chain

        config = self._policy.fallback_configs.get(primary_slug)
        if config:
            for fb in config.fallbacks:
                if fb not in chain:  # prevent duplicates
                    chain.append(fb)

        return chain

    async def _attempt_with_retries(
        self,
        request_id: str,
        provider: BaseProvider,
        slug: str,
        payload: dict[str, Any],
        api_key: str,
        cb,          # CircuitBreaker
        events: list[ResilienceEvent],
    ) -> Optional[dict[str, Any]]:
        """
        Try calling a provider up to (1 + max_retries) times.

        Returns the successful response dict, or None if all attempts failed.
        """
        max_attempts = 1 + (self._policy.max_retries if self._policy.retry_enabled else 0)
        attempt = 0

        while attempt < max_attempts:
            attempt_start = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    provider.chat_completion(payload, api_key),
                    timeout=self._policy.request_timeout_seconds,
                )
                # Success — reset circuit breaker.
                prev_state = cb.state
                await cb.record_success()
                if prev_state == CircuitState.HALF_OPEN:
                    events.append(ResilienceEvent(
                        event_type=CIRCUIT_CLOSED,
                        request_id=request_id,
                        provider_slug=slug,
                        data={"reason": "probe succeeded"},
                    ))
                return result

            except asyncio.TimeoutError:
                failure_kind = FailureKind.TIMEOUT
                error_body = None
                logger.warning(
                    "[%s] attempt %d/%d provider=%s TIMEOUT (%.1fs)",
                    request_id, attempt + 1, max_attempts, slug,
                    self._policy.request_timeout_seconds,
                )
                events.append(ResilienceEvent(
                    event_type=TIMEOUT_OCCURRED,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"attempt": attempt + 1, "timeout_seconds": self._policy.request_timeout_seconds},
                ))

            except httpx.HTTPStatusError as exc:
                try:
                    error_body = exc.response.json()
                except Exception:
                    error_body = None
                failure_kind = classify_exception(exc, error_body)
                logger.warning(
                    "[%s] attempt %d/%d provider=%s status=%d kind=%s",
                    request_id, attempt + 1, max_attempts, slug,
                    exc.response.status_code, failure_kind.value,
                )
                events.append(ResilienceEvent(
                    event_type=PROVIDER_FAILURE,
                    request_id=request_id,
                    provider_slug=slug,
                    data={
                        "attempt": attempt + 1,
                        "status_code": exc.response.status_code,
                        "failure_kind": failure_kind.value,
                    },
                ))

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                error_body = None
                failure_kind = classify_exception(exc)
                logger.warning(
                    "[%s] attempt %d/%d provider=%s network error kind=%s: %s",
                    request_id, attempt + 1, max_attempts, slug,
                    failure_kind.value, exc,
                )
                events.append(ResilienceEvent(
                    event_type=PROVIDER_FAILURE,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"attempt": attempt + 1, "failure_kind": failure_kind.value},
                ))

            except Exception as exc:
                error_body = None
                failure_kind = FailureKind.UNKNOWN
                logger.exception(
                    "[%s] attempt %d/%d provider=%s unexpected error",
                    request_id, attempt + 1, max_attempts, slug,
                )
                events.append(ResilienceEvent(
                    event_type=PROVIDER_FAILURE,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"attempt": attempt + 1, "failure_kind": failure_kind.value, "error": str(exc)},
                ))

            # ── Post-failure handling ──────────────────────────────────────────

            # Update circuit breaker if this failure counts.
            if counts_toward_circuit(failure_kind):
                prev_state = cb.state
                await cb.record_failure(failure_kind.value)
                if cb.state == CircuitState.OPEN and prev_state != CircuitState.OPEN:
                    events.append(ResilienceEvent(
                        event_type=CIRCUIT_OPENED,
                        request_id=request_id,
                        provider_slug=slug,
                        data={
                            "failure_count": cb.failure_count,
                            "threshold": self._policy.circuit_failure_threshold,
                            "failure_kind": failure_kind.value,
                        },
                    ))

            # Non-retryable failures stop immediately — no backoff, no retry.
            if not is_retryable(failure_kind):
                logger.info(
                    "[%s] failure kind %s is not retryable — stopping", request_id, failure_kind.value
                )
                return None

            # If we have more attempts left, apply exponential backoff + jitter.
            attempt += 1
            if attempt < max_attempts:
                backoff = self._compute_backoff(attempt)
                events.append(ResilienceEvent(
                    event_type=RETRY_ATTEMPTED,
                    request_id=request_id,
                    provider_slug=slug,
                    data={
                        "retry_number": attempt,
                        "backoff_seconds": backoff,
                        "failure_kind": failure_kind.value,
                    },
                ))
                logger.info(
                    "[%s] retry %d/%d for %s in %.2fs",
                    request_id, attempt, self._policy.max_retries, slug, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                events.append(ResilienceEvent(
                    event_type=RETRY_EXHAUSTED,
                    request_id=request_id,
                    provider_slug=slug,
                    data={"max_retries": self._policy.max_retries},
                ))
                logger.warning(
                    "[%s] retries exhausted for provider %s", request_id, slug
                )

        return None  # All attempts failed

    def _compute_backoff(self, attempt_number: int) -> float:
        """
        Compute capped exponential backoff.

        backoff = min(initial * 2^(attempt - 1), max)

        No randomized jitter is added — the spec asked for deterministic
        behavior.  The bounded cap prevents excessive waits.
        """
        raw = self._policy.initial_backoff_seconds * (2 ** (attempt_number - 1))
        return min(raw, self._policy.max_backoff_seconds)

    @staticmethod
    def _count_retries(events: list[ResilienceEvent], slug: str) -> int:
        """Count how many RETRY_ATTEMPTED events were emitted for a given slug."""
        return sum(
            1 for e in events
            if e.event_type == RETRY_ATTEMPTED and e.provider_slug == slug
        )

    # ── Introspection (Phase 3 hooks) ──────────────────────────────────────────

    def get_circuit_snapshots(self) -> list[dict]:
        """Return state snapshots for all known circuit breakers."""
        return self._circuit_breakers.get_all_snapshots()

    @property
    def policy(self) -> ResiliencePolicy:
        return self._policy
