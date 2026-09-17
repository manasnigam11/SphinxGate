"""
Per-provider Circuit Breaker — Phase 2.

Implements the standard three-state circuit breaker pattern:

  CLOSED  → Normal operation.  Failures are counted.
            Once consecutive failures hit the threshold, transition → OPEN.

  OPEN    → Provider is assumed failing.  Requests are rejected immediately
            without hitting the upstream.  After the recovery window expires,
            transition → HALF-OPEN.

  HALF-OPEN → One probe request is allowed through.
              Success → CLOSED.
              Failure → OPEN (timer resets).

Implementation notes:
  - State is stored in-memory per process.  For the hackathon (modular monolith)
    this is the correct scope — no Redis needed.
  - asyncio.Lock ensures async-safe state transitions.
  - Only failures that count_toward_circuit() contribute to the failure counter
    (see classifier.py).  Auth errors and quota exhaustion do NOT trip the breaker.
  - The circuit stores basic state that Phase 3 can expose for dashboards.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("sphinxgate.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half-open"


@dataclass
class CircuitBreakerState:
    """
    Mutable state for a single provider's circuit breaker.

    This is the data Phase 3 will surface on the Circuit Breakers dashboard.
    """
    provider_slug: str
    state: CircuitState = CircuitState.CLOSED

    # Consecutive failure counter — resets to 0 on any success
    failure_count: int = 0

    # Timestamp (epoch float) when the circuit last transitioned to OPEN.
    # Used to determine when to allow a HALF-OPEN probe.
    opened_at: Optional[float] = None

    # Human-readable info about the most recent failure.
    last_failure_kind: Optional[str] = None
    last_failure_at: Optional[float] = None

    # History of transitions for Phase 3 dashboards.
    # Each entry: {"timestamp": float, "from": str, "to": str, "reason": str}
    transition_history: list[dict] = field(default_factory=list)

    def record_transition(self, from_state: CircuitState, to_state: CircuitState, reason: str) -> None:
        self.transition_history.append({
            "timestamp": time.time(),
            "from": from_state.value,
            "to": to_state.value,
            "reason": reason,
        })
        # Keep only the last 50 transitions to bound memory.
        if len(self.transition_history) > 50:
            self.transition_history = self.transition_history[-50:]


class CircuitBreaker:
    """
    Circuit breaker for a single provider.

    Usage:
        cb = CircuitBreaker(provider_slug="openai", failure_threshold=5, recovery_window=30.0)

        if not cb.allow_request():
            # circuit is OPEN — skip this provider
            ...

        try:
            result = await provider.chat_completion(...)
            await cb.record_success()
        except SomeRetryableError:
            await cb.record_failure(kind)
    """

    def __init__(
        self,
        provider_slug: str,
        failure_threshold: int,
        recovery_window_seconds: float,
    ) -> None:
        self._slug = provider_slug
        self._threshold = failure_threshold
        self._recovery_window = recovery_window_seconds
        self._state = CircuitBreakerState(provider_slug=provider_slug)
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def allow_request(self) -> bool:
        """
        Return True if a request may be sent to this provider right now.

        CLOSED  → always True
        OPEN    → True only if the recovery window has elapsed (probe allowed)
        HALF-OPEN → True (the probe is already in-flight or about to be)

        This is NOT async — it only reads state and checks the clock,
        which is safe without the lock in CPython due to the GIL.
        The transition to HALF-OPEN happens inside record_failure / allow_request
        but is guarded by _maybe_transition_to_half_open.
        """
        if self._state.state == CircuitState.CLOSED:
            return True

        if self._state.state == CircuitState.HALF_OPEN:
            # A probe is in-flight.  Block additional requests until the probe
            # resolves.  (We only allow ONE concurrent probe.)
            return False

        # OPEN — check whether the recovery window has elapsed.
        if self._state.opened_at is not None:
            elapsed = time.time() - self._state.opened_at
            if elapsed >= self._recovery_window:
                # Optimistically transition; the actual write is protected by
                # the lock in _maybe_transition_to_half_open.
                return True   # caller will trigger record_success/failure which finalises

        return False

    def _check_half_open_transition(self) -> bool:
        """
        Check (without lock) if we should be entering HALF-OPEN.
        Returns True if the circuit is OPEN and the window has passed.
        """
        return (
            self._state.state == CircuitState.OPEN
            and self._state.opened_at is not None
            and (time.time() - self._state.opened_at) >= self._recovery_window
        )

    async def maybe_enter_half_open(self) -> bool:
        """
        If the circuit is OPEN and the recovery window has elapsed,
        transition to HALF-OPEN and return True.
        Returns False if no transition occurred.
        """
        async with self._lock:
            if self._check_half_open_transition():
                old = self._state.state
                self._state.state = CircuitState.HALF_OPEN
                self._state.record_transition(old, CircuitState.HALF_OPEN, "recovery window elapsed")
                logger.info("[%s] circuit → HALF-OPEN (recovery probe allowed)", self._slug)
                return True
        return False

    async def record_success(self) -> None:
        """
        Record a successful upstream response.

        CLOSED   → stay CLOSED, reset failure counter.
        HALF-OPEN → transition to CLOSED (probe succeeded).
        OPEN     → should not happen in normal flow; reset anyway.
        """
        async with self._lock:
            old = self._state.state
            self._state.failure_count = 0
            self._state.last_failure_kind = None

            if old == CircuitState.HALF_OPEN:
                self._state.state = CircuitState.CLOSED
                self._state.opened_at = None
                self._state.record_transition(old, CircuitState.CLOSED, "probe succeeded")
                logger.info("[%s] circuit → CLOSED (probe succeeded)", self._slug)
            # If already CLOSED, nothing changes.

    async def record_failure(self, failure_kind: str) -> None:
        """
        Record a failure that counts toward the circuit-breaker threshold.

        CLOSED    → increment counter; if threshold reached → OPEN.
        HALF-OPEN → probe failed → back to OPEN (reset timer).
        OPEN      → already open; update failure info.
        """
        async with self._lock:
            old = self._state.state
            self._state.failure_count += 1
            self._state.last_failure_kind = failure_kind
            self._state.last_failure_at = time.time()

            if old == CircuitState.HALF_OPEN:
                # Probe failed — reopen.
                self._state.state = CircuitState.OPEN
                self._state.opened_at = time.time()
                self._state.record_transition(
                    old, CircuitState.OPEN,
                    f"probe failed ({failure_kind})",
                )
                logger.warning(
                    "[%s] circuit → OPEN (probe failed: %s)", self._slug, failure_kind
                )

            elif old == CircuitState.CLOSED:
                if self._state.failure_count >= self._threshold:
                    self._state.state = CircuitState.OPEN
                    self._state.opened_at = time.time()
                    self._state.record_transition(
                        old, CircuitState.OPEN,
                        f"{self._state.failure_count} consecutive failures ({failure_kind})",
                    )
                    logger.warning(
                        "[%s] circuit → OPEN (%d consecutive failures: %s)",
                        self._slug, self._state.failure_count, failure_kind,
                    )
                else:
                    logger.debug(
                        "[%s] failure %d/%d (%s)",
                        self._slug, self._state.failure_count, self._threshold, failure_kind,
                    )
            # If already OPEN, just update the failure info (already logged).

    # ── State introspection (for Phase 3 / health endpoint) ───────────────────

    @property
    def state(self) -> CircuitState:
        return self._state.state

    @property
    def failure_count(self) -> int:
        return self._state.failure_count

    @property
    def last_failure_kind(self) -> Optional[str]:
        return self._state.last_failure_kind

    @property
    def last_failure_at(self) -> Optional[float]:
        return self._state.last_failure_at

    def get_snapshot(self) -> dict:
        """
        Return a serializable snapshot of circuit state.
        Phase 3 will expose this through the /api/v1/providers/state endpoint.
        """
        return {
            "provider": self._slug,
            "state": self._state.state.value,
            "failure_count": self._state.failure_count,
            "failure_threshold": self._threshold,
            "last_failure_kind": self._state.last_failure_kind,
            "last_failure_at": self._state.last_failure_at,
            "opened_at": self._state.opened_at,
            "recovery_window_seconds": self._recovery_window,
            "transition_history": self._state.transition_history[-10:],  # last 10
        }


# ── Registry of per-provider circuit breakers ─────────────────────────────────

class CircuitBreakerRegistry:
    """
    Holds one CircuitBreaker per provider slug.

    The registry is created once at startup (by the ResilienceEngine) with
    the resolved policy, and lives for the lifetime of the process.
    """

    def __init__(
        self,
        failure_threshold: int,
        recovery_window_seconds: float,
    ) -> None:
        self._threshold = failure_threshold
        self._recovery_window = recovery_window_seconds
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get(self, provider_slug: str) -> CircuitBreaker:
        """Return the CircuitBreaker for a provider, creating it if needed."""
        async with self._lock:
            if provider_slug not in self._breakers:
                self._breakers[provider_slug] = CircuitBreaker(
                    provider_slug=provider_slug,
                    failure_threshold=self._threshold,
                    recovery_window_seconds=self._recovery_window,
                )
            return self._breakers[provider_slug]

    def get_all_snapshots(self) -> list[dict]:
        """Return snapshots of all known circuit breakers."""
        return [cb.get_snapshot() for cb in self._breakers.values()]
