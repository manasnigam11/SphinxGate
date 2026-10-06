"""
Fault Injection Middleware — Phase 4.

This is where the fault is actually applied to the provider call.

Key design decision:
  The fault injection intercepts the provider.call() inside the
  ResilienceEngine's _attempt_with_retries loop by wrapping the provider
  object.  This means:

  - The ResilienceEngine is NOT modified.
  - The fault raises the SAME exception types the engine already handles.
  - The engine's retry/circuit/fallback logic fires exactly as it would
    for a real failure.
  - Telemetry captures the failure as if it were real.

How it works:
  1. FaultAwareProvider wraps a BaseProvider.
  2. When .call() is invoked, it first checks the FaultStore.
  3. If an effective fault is found, it raises the appropriate exception.
  4. Otherwise, it delegates to the wrapped provider unchanged.

Security:
  - Only exceptions from a closed allowlist are raised.
  - No arbitrary Python code is executed.
  - LATENCY fault adds asyncio.sleep() — bounded by MAX_LATENCY_MS.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.fault_injection.models import FaultConfig, FaultType
from app.fault_injection.store import FaultStore, is_fault_injection_enabled
from app.providers.base import BaseProvider, ProviderCategory

logger = logging.getLogger("sphinxgate.fault_injection")


class FaultAwareProvider(BaseProvider):
    """
    A thin wrapper around any BaseProvider that applies an injected fault
    before delegating to the real provider.

    This wrapper is created per-request inside the engine's provider lookup
    so that fault state is always checked fresh.
    """

    def __init__(self, inner: BaseProvider, fault_store: FaultStore) -> None:
        self._inner = inner
        self._fault_store = fault_store
        # Forward provider metadata transparently.
        self.slug = inner.slug
        self.display_name = inner.display_name
        self.category = inner.category
        self.requires_api_key = inner.requires_api_key

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Check for an active fault, apply it if present, otherwise delegate.
        """
        # Fast path: if injection is globally disabled, skip store lookup.
        if not is_fault_injection_enabled():
            return await self._inner.call(payload, api_key)

        fault = await self._fault_store.get_effective_for_provider(self._inner.slug)
        if fault is None:
            return await self._inner.call(payload, api_key)

        logger.warning(
            "FAULT INJECTED: provider=%s type=%s fault_id=%s",
            self._inner.slug,
            fault.fault_type.value,
            fault.fault_id,
        )

        await _apply_fault(fault)
        # _apply_fault raises for every failure-type fault.  It only returns
        # for LATENCY, which delays the call but must still reach the real
        # provider (a latency fault slows requests; it does not fail them).
        return await self._inner.call(payload, api_key)

    async def health_check(self, api_key: str | None) -> bool | None:
        """Delegate active health probes to the real provider."""
        return await self._inner.health_check(api_key)

    # BaseProvider requires this abstract method.  FaultAwareProvider delegates.
    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:  # pragma: no cover
        return await self._inner.call(payload, api_key)


async def _apply_fault(fault: FaultConfig) -> None:
    """
    Raise the appropriate exception for the given fault type.

    LATENCY is the only non-raising fault — it delays then lets the call proceed
    via the caller (FaultAwareProvider.call resumes the real provider after this).

    All other faults raise an exception that the ResilienceEngine already knows
    how to handle via its existing exception handlers and classifier.

    Security: this is a closed switch/match — no user-controlled code paths.
    """
    ft = fault.fault_type

    if ft == FaultType.TIMEOUT:
        # asyncio.TimeoutError is what asyncio.wait_for raises.
        # The engine catches this as FailureKind.TIMEOUT.
        raise asyncio.TimeoutError(
            f"[fault-injected] Simulated timeout for provider '{fault.provider_slug}'"
        )

    if ft == FaultType.CONNECTION_ERROR:
        # httpx.ConnectError → FailureKind.CONNECTION_ERROR in classifier.
        raise httpx.ConnectError(
            f"[fault-injected] Simulated connection error for provider '{fault.provider_slug}'"
        )

    if ft == FaultType.HTTP_429:
        raise _make_http_status_error(429, fault.provider_slug)

    if ft == FaultType.HTTP_500:
        raise _make_http_status_error(500, fault.provider_slug)

    if ft == FaultType.HTTP_502:
        raise _make_http_status_error(502, fault.provider_slug)

    if ft == FaultType.HTTP_503:
        raise _make_http_status_error(503, fault.provider_slug)

    if ft == FaultType.LATENCY:
        delay_seconds = min(fault.latency_ms, 30_000) / 1000.0
        await asyncio.sleep(delay_seconds)
        # For LATENCY, we do NOT raise — the real call proceeds after the delay.
        # FaultAwareProvider.call must NOT call apply_fault then call the inner
        # provider again; it handles LATENCY specially.
        return

    # Should never reach here given the closed enum, but guard defensively.
    raise RuntimeError(f"Unknown FaultType: {ft!r}")  # pragma: no cover


def _make_http_status_error(status_code: int, provider_slug: str) -> httpx.HTTPStatusError:
    """
    Build a minimal httpx.HTTPStatusError that the classifier can process.

    The response is constructed with the exact structure the classifier checks.
    """
    request = httpx.Request("POST", f"https://fault-injected-{provider_slug}.internal/")
    response = httpx.Response(
        status_code=status_code,
        content=f'{{"error": {{"message": "[fault-injected] HTTP {status_code} for {provider_slug}", "type": "injected_fault"}}}}'.encode(),
        request=request,
    )
    return httpx.HTTPStatusError(
        f"[fault-injected] HTTP {status_code} for provider '{provider_slug}'",
        request=request,
        response=response,
    )


async def apply_fault_if_active(
    provider: BaseProvider,
    fault_store: FaultStore,
) -> None:
    """
    Standalone helper for cases where wrapping is not practical.
    Checks for an effective fault and applies it, or does nothing.
    """
    if not is_fault_injection_enabled():
        return
    fault = await fault_store.get_effective_for_provider(provider.slug)
    if fault is None:
        return
    await _apply_fault(fault)
