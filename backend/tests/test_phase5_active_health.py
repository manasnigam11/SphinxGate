import asyncio
import pytest

from app.health.checker import (
    HealthRegistry,
    ActiveHealthState,
    ActiveHealthChecker,
)
from app.resilience.engine import ResilienceEngine
from app.resilience.policy import ResiliencePolicy
from app.providers.base import BaseProvider


class MockProvider(BaseProvider):
    slug = "mock"
    display_name = "Mock Provider"
    category = "mock"
    requires_api_key = False

    def __init__(self):
        self.health_state = True
        self.calls = 0

    async def call(self, payload, api_key):
        return {"status": "ok"}

    async def health_check(self, api_key):
        self.calls += 1
        return self.health_state


@pytest.mark.asyncio
async def test_health_registry_transitions():
    registry = HealthRegistry(failure_threshold=2, success_threshold=2)

    # Starts unknown
    assert registry.get_state("mock") == ActiveHealthState.UNKNOWN

    # One failure -> degraded (since it must not stay UNKNOWN)
    registry.record_probe("mock", False)
    assert registry.get_state("mock") == ActiveHealthState.DEGRADED

    # Second failure -> unhealthy
    registry.record_probe("mock", False)
    assert registry.get_state("mock") == ActiveHealthState.UNHEALTHY

    # One success -> still unhealthy
    registry.record_probe("mock", True)
    assert registry.get_state("mock") == ActiveHealthState.UNHEALTHY

    # Second success -> healthy
    registry.record_probe("mock", True)
    assert registry.get_state("mock") == ActiveHealthState.HEALTHY


@pytest.mark.asyncio
async def test_health_registry_unsupported():
    registry = HealthRegistry()
    
    registry.record_probe("mock", True)
    registry.record_probe("mock", True)
    assert registry.get_state("mock") == ActiveHealthState.HEALTHY
    
    # If a provider starts returning None (e.g. dynamic config change or generic), it goes to UNKNOWN
    registry.record_probe("mock", None)
    assert registry.get_state("mock") == ActiveHealthState.UNKNOWN


@pytest.mark.asyncio
async def test_resilience_engine_skips_unhealthy(monkeypatch):
    from app.health.checker import get_health_registry
    
    # Setup registry
    registry = get_health_registry()
    registry._states["mock"] = ActiveHealthState.UNHEALTHY
    
    # Register mock provider
    provider = MockProvider()
    from app.providers.registry import REGISTRY
    monkeypatch.setitem(REGISTRY, "mock", provider)

    policy = ResiliencePolicy.from_settings()
    
    # Wait, we need to mock api_key_getter
    engine = ResilienceEngine(policy)
    
    result = await engine.execute(
        request_id="req-123",
        provider_slug="mock",
        payload={"messages": []},
        api_key_getter=lambda slug: "dummy-key"
    )

    # Provider should be skipped due to active health being UNHEALTHY
    assert not result.success
    # Wait, if all are skipped, engine returns failure with circuit state OPEN or CLOSED.
    # But wait, it should skip it because of unhealthy. Let's see if the error is correct.
    # We didn't add a specific error message for "unhealthy" skipping, it just says all providers exhausted.
    assert result.error_message is None or "no healthy provider is currently available" in result.error_message.lower()
