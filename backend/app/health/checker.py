"""
Active Provider Health Checker.

Continuously probes all registered providers in the background to detect
outages before a user request fails. Updates a thread-safe registry of health
states that the routing engine can use.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional, Any

from app.config import get_settings
from app.providers.registry import get_provider_info, get_provider

logger = logging.getLogger("sphinxgate.health")

class ActiveHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

import time

class HealthRegistry:
    def __init__(self, failure_threshold: int = 2, success_threshold: int = 2):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self._states: dict[str, ActiveHealthState] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._consecutive_successes: dict[str, int] = {}
        self._last_checked: dict[str, float] = {}
        self._last_success: dict[str, float] = {}
        self._last_failure: dict[str, float] = {}
        self._latency: dict[str, float] = {}
        self._last_failure_reason: dict[str, str] = {}

    def get_state(self, slug: str) -> ActiveHealthState:
        return self._states.get(slug, ActiveHealthState.UNKNOWN)
        
    def get_details(self, slug: str) -> dict:
        return {
            "state": self.get_state(slug).value,
            "last_checked_at": self._last_checked.get(slug),
            "last_success_at": self._last_success.get(slug),
            "last_failure_at": self._last_failure.get(slug),
            "last_failure_reason": self._last_failure_reason.get(slug),
            "probe_latency_ms": self._latency.get(slug),
            "consecutive_failures": self._consecutive_failures.get(slug, 0),
            "consecutive_successes": self._consecutive_successes.get(slug, 0),
        }

    def record_probe(self, slug: str, success: bool | None, latency_ms: float = 0.0, reason: str | None = None):
        now = time.time()
        self._last_checked[slug] = now
        self._latency[slug] = latency_ms
        
        if success is None:
            # Provider does not support active checks
            self._states[slug] = ActiveHealthState.UNKNOWN
            return

        current_state = self.get_state(slug)
        if success:
            self._last_success[slug] = now
            self._consecutive_failures[slug] = 0
            self._consecutive_successes[slug] = self._consecutive_successes.get(slug, 0) + 1
            if self._consecutive_successes[slug] >= self.success_threshold:
                if current_state != ActiveHealthState.HEALTHY:
                    logger.info(f"Provider {slug} recovered -> HEALTHY")
                self._states[slug] = ActiveHealthState.HEALTHY
            elif current_state == ActiveHealthState.UNKNOWN:
                self._states[slug] = ActiveHealthState.DEGRADED
        else:
            self._last_failure[slug] = now
            if reason:
                self._last_failure_reason[slug] = reason
            self._consecutive_successes[slug] = 0
            self._consecutive_failures[slug] = self._consecutive_failures.get(slug, 0) + 1
            if self._consecutive_failures[slug] >= self.failure_threshold:
                if current_state != ActiveHealthState.UNHEALTHY:
                    logger.warning(f"Provider {slug} active check failed -> UNHEALTHY. Reason: {reason}")
                self._states[slug] = ActiveHealthState.UNHEALTHY
            elif current_state == ActiveHealthState.UNKNOWN or current_state == ActiveHealthState.HEALTHY:
                self._states[slug] = ActiveHealthState.DEGRADED

    def record_passive(self, slug: str, success: bool, reason: str | None = None):
        """Update health state purely from real traffic observations."""
        now = time.time()
        current_state = self.get_state(slug)
        if success:
            self._last_success[slug] = now
            self._consecutive_failures[slug] = 0
            if current_state != ActiveHealthState.HEALTHY:
                logger.info(f"Provider {slug} passive recovery -> HEALTHY")
            self._states[slug] = ActiveHealthState.HEALTHY
            self._last_failure_reason.pop(slug, None)
        else:
            self._last_failure[slug] = now
            if reason:
                self._last_failure_reason[slug] = reason
            self._consecutive_successes[slug] = 0
            # A single real failure immediately degrades the provider,
            # but we leave it to the circuit breaker to mark it fully DOWN/UNHEALTHY
            # unless the failure is a complete outage.
            if current_state in (ActiveHealthState.UNKNOWN, ActiveHealthState.HEALTHY):
                self._states[slug] = ActiveHealthState.DEGRADED
                logger.warning(f"Provider {slug} passively marked DEGRADED. Reason: {reason}")


class ActiveHealthChecker:
    def __init__(self, registry: HealthRegistry):
        self.registry = registry
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def start(self):
        settings = get_settings()
        if not settings.health_check_enabled:
            logger.info("Active Health Checker is DISABLED via configuration")
            return
            
        if self._task is None:
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._loop(settings.health_check_interval_seconds))

    async def stop(self):
        if self._task is not None:
            if hasattr(self, '_stop_event') and getattr(self, '_stop_event', None):
                self._stop_event.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, interval_seconds: int):
        while not self._stop_event.is_set():
            await self._check_all()
            try:
                # Wait for interval or stop event
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass  # expected, proceed to next check

    async def _force_open_circuit(self, slug: str, reason: str):
        try:
            from app.gateway.router import get_engine
            engine = get_engine()
            if engine:
                cb = await engine._circuit_breakers.get(slug)
                await cb.force_open(f"active health probe failed: {reason}")
        except Exception as e:
            logger.error(f"Failed to force open circuit breaker for {slug}: {str(e)}")

    async def _check_provider(self, slug: str, provider: Any, api_key: Optional[str], timeout: int):
        start_state = self.registry.get_state(slug)
        applied_reason = None

        if provider.requires_api_key and not api_key:
            logger.warning(f"Skipping active health check for {slug}: API key missing (recording as UNHEALTHY)")
            applied_reason = "API key missing"
            self.registry.record_probe(slug, False, latency_ms=0.0, reason=applied_reason)
        else:
            start_time = time.perf_counter()
            try:
                # Wrap the provider's health_check with the configured timeout
                is_healthy = await asyncio.wait_for(
                    provider.health_check(api_key), 
                    timeout=timeout
                )
                latency_ms = (time.perf_counter() - start_time) * 1000
                if is_healthy is False:
                    applied_reason = "Provider returned unhealthy status"
                    self.registry.record_probe(slug, False, latency_ms=latency_ms, reason=applied_reason)
                else:
                    self.registry.record_probe(slug, is_healthy, latency_ms=latency_ms)
            except asyncio.TimeoutError:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(f"Health check timed out for {slug} after {timeout}s")
                applied_reason = "Probe timeout"
                self.registry.record_probe(slug, False, latency_ms=latency_ms, reason=applied_reason)
            except Exception as e:
                import httpx
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(f"Error checking health for {slug}: {str(e)}")
                reason = str(e)
                if isinstance(e, httpx.HTTPStatusError):
                    reason = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                    if e.response.status_code == 429:
                        reason = "Quota exhausted / Rate limited"
                elif isinstance(e, httpx.RequestError):
                    reason = "Network/connection error"
                elif not reason:
                    reason = e.__class__.__name__
                applied_reason = reason
                self.registry.record_probe(slug, False, latency_ms=latency_ms, reason=applied_reason)

        end_state = self.registry.get_state(slug)
        if start_state != ActiveHealthState.UNHEALTHY and end_state == ActiveHealthState.UNHEALTHY:
            if applied_reason:
                await self._force_open_circuit(slug, applied_reason)

    async def _check_all(self):
        settings = get_settings()
        timeout = settings.health_check_timeout_seconds
        
        tasks = []
        for info in get_provider_info():
            slug = info["slug"]
            
            # Hybrid / Event-driven health model: 
            # Only run active probes for providers that are UNHEALTHY, DEGRADED, or UNKNOWN.
            # Do not waste quota polling HEALTHY providers.
            state = self.registry.get_state(slug)
            if state == ActiveHealthState.HEALTHY:
                continue

            try:
                provider = get_provider(slug)
                
                from app.providers.base import ProviderCategory
                # Skip unnecessary startup probes for LLM providers to save quota.
                # Public APIs are cheap and can be probed at startup.
                if state == ActiveHealthState.UNKNOWN and provider.category == ProviderCategory.LLM:
                    continue

                api_key = settings.get_provider_api_key(slug)
                # Startup optimization: If no api_key and requires it, mark unhealthy without network call
                if provider.requires_api_key and not api_key:
                    start_state = self.registry.get_state(slug)
                    self.registry.record_probe(slug, False, reason="API key missing")
                    if start_state != ActiveHealthState.UNHEALTHY and self.registry.get_state(slug) == ActiveHealthState.UNHEALTHY:
                        tasks.append(asyncio.create_task(self._force_open_circuit(slug, "API key missing")))
                    continue
                    
                tasks.append(self._check_provider(slug, provider, api_key, timeout))
            except Exception as e:
                logger.error(f"Failed to prepare health check for {slug}: {str(e)}")
                self.registry.record_probe(slug, False, reason=str(e))
                
        # Run all provider checks concurrently to prevent a slow provider from blocking others
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

_REGISTRY = HealthRegistry()
_CHECKER = ActiveHealthChecker(_REGISTRY)

def get_health_registry() -> HealthRegistry:
    return _REGISTRY

def get_health_checker() -> ActiveHealthChecker:
    return _CHECKER
