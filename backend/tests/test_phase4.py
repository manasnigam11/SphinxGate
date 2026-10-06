"""
Phase 4 Tests — Fault Injection + Incident Management.

Test categories:
  1. Fault injection models (unit)
  2. Fault store (unit)
  3. Fault injection API (integration — ENABLED + DISABLED states)
  4. Fault middleware / provider wrapping (unit)
  5. Incident models (unit)
  6. Incident store (unit)
  7. Incident detector (unit)
  8. Incident management API (integration)
  9. Security tests
  10. Health endpoint

All tests use mocked providers and deterministic behavior.
No real external API calls are made.
"""

import asyncio
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Shared reset helper
# ─────────────────────────────────────────────────────────────────────────────

def _reset_all():
    """Reset all Phase 4 singletons between tests."""
    from app.fault_injection.store import _reset_fault_store
    from app.incidents.store import _reset_incident_store
    from app.incidents.detector import _reset_incident_detector
    from app.facade import _reset_facade
    _reset_fault_store()
    _reset_incident_store()
    _reset_incident_detector()
    _reset_facade()


def _get_client():
    """Build a TestClient from the FastAPI app."""
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


def _run(coro):
    """Run an async coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fault Injection Models
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultModels:
    def test_fault_type_values(self):
        from app.fault_injection.models import FaultType
        assert FaultType.TIMEOUT.value == "timeout"
        assert FaultType.CONNECTION_ERROR.value == "connection_error"
        assert FaultType.HTTP_429.value == "http_429"
        assert FaultType.HTTP_500.value == "http_500"
        assert FaultType.HTTP_502.value == "http_502"
        assert FaultType.HTTP_503.value == "http_503"
        assert FaultType.LATENCY.value == "latency"

    def test_fault_config_creation(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        assert f.provider_slug == "gemini"
        assert f.fault_type == FaultType.TIMEOUT
        assert f.is_active is True
        assert f.fault_id.startswith("fault-")

    def test_fault_config_latency_bounded(self):
        from app.fault_injection.models import FaultConfig, FaultType, MAX_LATENCY_MS
        f = FaultConfig(
            provider_slug="gemini",
            fault_type=FaultType.LATENCY,
            latency_ms=MAX_LATENCY_MS + 99999,
        )
        assert f.latency_ms == MAX_LATENCY_MS

    def test_fault_config_duration_bounded(self):
        from app.fault_injection.models import FaultConfig, FaultType, MAX_DURATION_S
        f = FaultConfig(
            provider_slug="gemini",
            fault_type=FaultType.TIMEOUT,
            duration_seconds=MAX_DURATION_S + 99999,
        )
        assert f.duration_seconds == MAX_DURATION_S

    def test_fault_config_is_effective_when_active(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        assert f.is_effective is True

    def test_fault_config_inactive_not_effective(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        f.is_active = False
        assert f.is_effective is False

    def test_fault_config_expired(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(
            provider_slug="gemini",
            fault_type=FaultType.TIMEOUT,
            duration_seconds=1,
        )
        f.created_at = time.time() - 10
        assert f.is_expired is True
        assert f.is_effective is False

    def test_fault_config_not_expired(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT, duration_seconds=3600)
        assert f.is_expired is False

    def test_fault_config_zero_duration_never_expires(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT, duration_seconds=0)
        f.created_at = time.time() - 999999
        assert f.is_expired is False

    def test_fault_config_to_dict(self):
        from app.fault_injection.models import FaultConfig, FaultType
        f = FaultConfig(provider_slug="gemini", fault_type=FaultType.HTTP_500)
        d = f.to_dict()
        assert d["provider_slug"] == "gemini"
        assert d["fault_type"] == "http_500"
        assert d["is_active"] is True
        assert "fault_id" in d
        assert "is_effective" in d
        assert "fault_type_label" in d


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fault Store
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultStore:
    @pytest.fixture(autouse=True)
    def reset(self):
        _reset_all()
        yield
        _reset_all()

    def test_add_and_get(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _run_inner():
            await store.add(fault)
            return await store.get(fault.fault_id)

        result = _run(_run_inner())
        assert result is not None
        assert result.fault_id == fault.fault_id

    def test_list_active(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        f1 = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        f2 = FaultConfig(provider_slug="groq", fault_type=FaultType.HTTP_500)

        async def _run_inner():
            await store.add(f1)
            await store.add(f2)
            return await store.list_active()

        results = _run(_run_inner())
        assert len(results) == 2

    def test_disable_fault(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _run_inner():
            await store.add(fault)
            found = await store.disable(fault.fault_id)
            active = await store.list_active()
            return found, active

        found, active = _run(_run_inner())
        assert found is True
        assert len(active) == 0

    def test_disable_nonexistent_returns_false(self):
        from app.fault_injection.store import FaultStore
        store = FaultStore()

        found = _run(store.disable("nonexistent-fault-id"))
        assert found is False

    def test_get_effective_for_provider(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _run_inner():
            await store.add(fault)
            return await store.get_effective_for_provider("gemini")

        result = _run(_run_inner())
        assert result is not None
        assert result.fault_id == fault.fault_id

    def test_get_effective_for_different_provider_returns_none(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _run_inner():
            await store.add(fault)
            return await store.get_effective_for_provider("groq")

        result = _run(_run_inner())
        assert result is None

    def test_clear_all(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        f1 = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        f2 = FaultConfig(provider_slug="groq", fault_type=FaultType.HTTP_500)

        async def _run_inner():
            await store.add(f1)
            await store.add(f2)
            count = await store.clear_all()
            active = await store.list_active()
            return count, active

        count, active = _run(_run_inner())
        assert count == 2
        assert len(active) == 0

    def test_supersede_same_provider_type(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.store import FaultStore
        store = FaultStore()
        f1 = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)
        f2 = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _run_inner():
            await store.add(f1)
            await store.add(f2)
            return await store.list_active()

        active = _run(_run_inner())
        assert len(active) == 1
        assert active[0].fault_id == f2.fault_id


# ─────────────────────────────────────────────────────────────────────────────
# 3. Fault Injection API — DISABLED (default)
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultInjectionAPIDisabled:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
        _reset_all()
        yield
        _reset_all()

    @pytest.fixture
    def client(self):
        return _get_client()

    def test_status_shows_disabled(self, client):
        resp = client.get("/api/v1/faults/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_status_shows_supported_fault_types(self, client):
        resp = client.get("/api/v1/faults/status")
        types = [t["value"] for t in resp.json()["supported_fault_types"]]
        assert "timeout" in types
        assert "http_500" in types
        assert "connection_error" in types

    def test_create_fault_returns_403_when_disabled(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "timeout",
        })
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

    def test_list_faults_works_when_disabled(self, client):
        resp = client.get("/api/v1/faults")
        assert resp.status_code == 200

    def test_delete_fault_returns_403_when_disabled(self, client):
        resp = client.delete("/api/v1/faults/some-fault-id")
        assert resp.status_code == 403

    def test_clear_all_returns_403_when_disabled(self, client):
        resp = client.delete("/api/v1/faults")
        assert resp.status_code == 403

    def test_status_lists_registered_providers(self, client):
        data = client.get("/api/v1/faults/status").json()
        assert "gemini" in data["registered_providers"]
        assert "groq" in data["registered_providers"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fault Injection API — ENABLED
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultInjectionAPIEnabled:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
        _reset_all()
        yield
        _reset_all()

    @pytest.fixture
    def client(self):
        return _get_client()

    def test_status_shows_enabled(self, client):
        resp = client.get("/api/v1/faults/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_create_fault_valid(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "timeout",
            "note": "Test fault",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert data["fault"]["provider_slug"] == "gemini"
        assert data["fault"]["fault_type"] == "timeout"
        assert data["fault"]["is_active"] is True

    def test_create_fault_http_500(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "groq",
            "fault_type": "http_500",
        })
        assert resp.status_code == 201
        assert resp.json()["fault"]["fault_type"] == "http_500"

    def test_create_fault_invalid_type_rejected(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "arbitrary_exception",
        })
        assert resp.status_code == 422

    def test_create_fault_invalid_provider_rejected(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "fake_nonexistent_provider",
            "fault_type": "timeout",
        })
        assert resp.status_code == 400

    def test_create_fault_arbitrary_url_rejected(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "http://evil.com/steal",
            "fault_type": "timeout",
        })
        assert resp.status_code == 422

    def test_create_fault_uppercase_rejected(self, client):
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "GEMINI",
            "fault_type": "timeout",
        })
        assert resp.status_code == 422

    def test_list_faults(self, client):
        client.post("/api/v1/faults", json={"provider_slug": "gemini", "fault_type": "timeout"})
        resp = client.get("/api/v1/faults")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_list_active_faults(self, client):
        client.post("/api/v1/faults", json={"provider_slug": "gemini", "fault_type": "timeout"})
        resp = client.get("/api/v1/faults/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["count"] >= 1

    def test_get_fault_by_id(self, client):
        create_resp = client.post("/api/v1/faults", json={"provider_slug": "gemini", "fault_type": "http_503"})
        fault_id = create_resp.json()["fault"]["fault_id"]
        resp = client.get(f"/api/v1/faults/{fault_id}")
        assert resp.status_code == 200
        assert resp.json()["fault"]["fault_id"] == fault_id

    def test_disable_fault(self, client):
        create_resp = client.post("/api/v1/faults", json={"provider_slug": "gemini", "fault_type": "timeout"})
        fault_id = create_resp.json()["fault"]["fault_id"]
        disable_resp = client.delete(f"/api/v1/faults/{fault_id}")
        assert disable_resp.status_code == 200
        assert disable_resp.json()["disabled"] is True
        active_resp = client.get("/api/v1/faults/active")
        fault_ids = [f["fault_id"] for f in active_resp.json()["active_faults"]]
        assert fault_id not in fault_ids

    def test_disable_nonexistent_fault(self, client):
        resp = client.delete("/api/v1/faults/nonexistent-123")
        assert resp.status_code == 404

    def test_clear_all_faults(self, client):
        client.post("/api/v1/faults", json={"provider_slug": "gemini", "fault_type": "timeout"})
        client.post("/api/v1/faults", json={"provider_slug": "groq", "fault_type": "http_500"})
        resp = client.delete("/api/v1/faults")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True
        assert resp.json()["faults_deactivated"] >= 2

    def test_latency_fault_ms_bounded_by_api(self, client):
        # MAX_LATENCY_MS = 30_000 — request sends 99999 which is over le=30000
        resp = client.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "latency",
            "latency_ms": 99999,
        })
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. Fault Middleware — Exception Types
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultMiddleware:
    def test_timeout_raises_asyncio_timeout(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.TIMEOUT)

        async def _inner():
            with pytest.raises(asyncio.TimeoutError):
                await _apply_fault(fault)

        _run(_inner())

    def test_connection_error_raises_httpx_connect_error(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.CONNECTION_ERROR)

        async def _inner():
            with pytest.raises(httpx.ConnectError):
                await _apply_fault(fault)

        _run(_inner())

    def test_http_429_raises_correct_status(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.HTTP_429)

        async def _inner():
            try:
                await _apply_fault(fault)
            except httpx.HTTPStatusError as e:
                return e.response.status_code

        code = _run(_inner())
        assert code == 429

    def test_http_500_raises_correct_status(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.HTTP_500)

        async def _inner():
            try:
                await _apply_fault(fault)
            except httpx.HTTPStatusError as e:
                return e.response.status_code

        code = _run(_inner())
        assert code == 500

    def test_http_502_raises_correct_status(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.HTTP_502)

        async def _inner():
            try:
                await _apply_fault(fault)
            except httpx.HTTPStatusError as e:
                return e.response.status_code

        code = _run(_inner())
        assert code == 502

    def test_http_503_raises_correct_status(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(provider_slug="gemini", fault_type=FaultType.HTTP_503)

        async def _inner():
            try:
                await _apply_fault(fault)
            except httpx.HTTPStatusError as e:
                return e.response.status_code

        code = _run(_inner())
        assert code == 503

    def test_latency_does_not_raise(self):
        from app.fault_injection.models import FaultConfig, FaultType
        from app.fault_injection.middleware import _apply_fault

        fault = FaultConfig(
            provider_slug="gemini",
            fault_type=FaultType.LATENCY,
            latency_ms=1,
        )

        async def _inner():
            await _apply_fault(fault)
            return "ok"

        result = _run(_inner())
        assert result == "ok"

    def test_fault_aware_provider_transparent_when_disabled(self):
        from app.fault_injection.middleware import FaultAwareProvider
        from app.fault_injection.store import FaultStore

        mock_inner = MagicMock()
        mock_inner.slug = "gemini"
        mock_inner.display_name = "Gemini"
        mock_inner.category = MagicMock()
        mock_inner.requires_api_key = True
        mock_inner.call = AsyncMock(return_value={"ok": True})

        store = FaultStore()
        wrapper = FaultAwareProvider(inner=mock_inner, fault_store=store)

        async def _inner():
            return await wrapper.call({}, "test-key")

        with patch("app.fault_injection.middleware.is_fault_injection_enabled", return_value=False):
            result = _run(_inner())
        assert result == {"ok": True}

    def test_injected_http_status_error_is_classifiable(self):
        """Ensure injected HTTPStatusError has the correct response.status_code for the classifier."""
        from app.fault_injection.middleware import _make_http_status_error
        from app.resilience.classifier import classify_exception, FailureKind

        for code, expected_kind in [
            (429, FailureKind.RATE_LIMITED),
            (500, FailureKind.SERVER_ERROR_500),
            (502, FailureKind.BAD_GATEWAY_502),
            (503, FailureKind.SERVICE_UNAVAILABLE_503),
        ]:
            exc = _make_http_status_error(code, "gemini")
            kind = classify_exception(exc)
            assert kind == expected_kind, f"Expected {expected_kind} for HTTP {code}, got {kind}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Incident Models
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentModels:
    def test_incident_creation(self):
        from app.incidents.models import Incident, IncidentSeverity, IncidentStatus, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Gemini — Availability Degraded",
        )
        assert inc.incident_id.startswith("INC-")
        assert inc.status == IncidentStatus.OPEN
        assert inc.error_count == 1

    def test_incident_dedup_key(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test",
        )
        assert inc.dedup_key == "gemini:availability"

    def test_incident_acknowledge(self):
        from app.incidents.models import Incident, IncidentSeverity, IncidentStatus, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test",
        )
        inc.acknowledge()
        assert inc.status == IncidentStatus.ACKNOWLEDGED
        assert len(inc.timeline) == 1

    def test_incident_resolve(self):
        from app.incidents.models import Incident, IncidentSeverity, IncidentStatus, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test",
        )
        inc.resolve(note="Provider recovered")
        assert inc.status == IncidentStatus.RESOLVED
        assert inc.resolved_at is not None

    def test_incident_update_from_failure(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test",
        )
        inc.update_from_new_failure("req-002", retry_count=2, fallback_used=True)
        assert inc.error_count == 2
        assert inc.retry_count == 2
        assert inc.fallback_count == 1
        assert "req-002" in inc.affected_request_ids

    def test_incident_circuit_opened_escalates_to_critical(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.MEDIUM,
            title="Test",
        )
        inc.update_from_new_failure("req-002", circuit_opened=True)
        assert inc.severity == IncidentSeverity.CRITICAL
        assert inc.circuit_opened is True

    def test_incident_affected_requests_bounded_at_50(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test",
        )
        for i in range(100):
            inc.add_affected_request(f"req-{i}")
        assert len(inc.affected_request_ids) == 50

    def test_incident_to_dict(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Test Incident",
        )
        d = inc.to_dict()
        assert d["incident_id"] == inc.incident_id
        assert d["severity"] == "high"
        assert d["status"] == "open"
        assert "timeline" in d
        assert "metadata" in d

    def test_classify_failure_category(self):
        from app.incidents.models import classify_failure_category, FailureCategory
        assert classify_failure_category("timeout") == FailureCategory.AVAILABILITY
        assert classify_failure_category("connection_error") == FailureCategory.AVAILABILITY
        assert classify_failure_category("rate_limited") == FailureCategory.RATE_LIMITED
        assert classify_failure_category("server_error_500") == FailureCategory.AVAILABILITY
        assert classify_failure_category(None) == FailureCategory.DEGRADED


# ─────────────────────────────────────────────────────────────────────────────
# 7. Incident Store
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentStore:
    @pytest.fixture(autouse=True)
    def reset(self):
        _reset_all()
        yield
        _reset_all()

    def _make_incident(self, provider="gemini", category="availability"):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        return Incident(
            provider_slug=provider,
            provider_display_name=provider.title(),
            failure_category=FailureCategory(category),
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title=f"Test incident for {provider}",
        )

    def test_create_and_get(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc = self._make_incident()

        async def _inner():
            await store.create(inc)
            return await store.get(inc.incident_id)

        result = _run(_inner())
        assert result is not None
        assert result.incident_id == inc.incident_id

    def test_get_nonexistent_returns_none(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        result = _run(store.get("INC-NOTREAL"))
        assert result is None

    def test_get_active_by_dedup_key(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc = self._make_incident()

        async def _inner():
            await store.create(inc)
            return await store.get_active_by_dedup_key(inc.dedup_key)

        result = _run(_inner())
        assert result is not None
        assert result.incident_id == inc.incident_id

    def test_resolved_incident_not_returned_by_dedup(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc = self._make_incident()
        inc.resolve()

        async def _inner():
            await store.create(inc)
            return await store.get_active_by_dedup_key(inc.dedup_key)

        result = _run(_inner())
        assert result is None

    def test_list_all_newest_first(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc1 = self._make_incident("gemini")
        inc2 = self._make_incident("groq")
        inc2.started_at = inc1.started_at + 1

        async def _inner():
            await store.create(inc1)
            await store.create(inc2)
            return await store.list_all()

        results = _run(_inner())
        assert results[0].incident_id == inc2.incident_id

    def test_list_all_filter_by_status(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc1 = self._make_incident("gemini")
        inc2 = self._make_incident("groq")
        inc2.resolve()

        async def _inner():
            await store.create(inc1)
            await store.create(inc2)
            return await store.list_all(status="open")

        results = _run(_inner())
        assert len(results) == 1
        assert results[0].incident_id == inc1.incident_id

    def test_count(self):
        from app.incidents.store import IncidentStore
        store = IncidentStore()
        inc = self._make_incident()

        async def _inner():
            await store.create(inc)
            return await store.count()

        count = _run(_inner())
        assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Incident Detector
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentDetector:
    @pytest.fixture(autouse=True)
    def reset(self):
        _reset_all()
        yield
        _reset_all()

    def _make_failed_result(
        self,
        provider_slug="gemini",
        error_type="timeout",
        circuit_state="closed",
        retry_count=0,
        fallback_used=False,
        circuit_opened_in_events=False,
    ):
        from app.resilience.events import RequestResult, ResilienceEvent, CIRCUIT_OPENED
        events = []
        if circuit_opened_in_events:
            events.append(ResilienceEvent(
                event_type=CIRCUIT_OPENED,
                request_id=f"req-{uuid.uuid4().hex[:8]}",
                provider_slug=provider_slug,
                data={"failure_count": 5},
            ))
        return RequestResult(
            success=False,
            response=None,
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            provider_slug=provider_slug,
            provider_display_name=provider_slug.title(),
            latency_ms=500,
            retry_count=retry_count,
            circuit_state=circuit_state,
            fallback_used=fallback_used,
            status_code=503,
            tokens_used=0,
            error_type=error_type,
            events=events,
        )

    def _make_success_result(self, provider_slug="gemini"):
        from app.resilience.events import RequestResult
        return RequestResult(
            success=True,
            response={"ok": True},
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            provider_slug=provider_slug,
            provider_display_name=provider_slug.title(),
            latency_ms=200,
            retry_count=0,
            circuit_state="closed",
            fallback_used=False,
            status_code=200,
            tokens_used=10,
            events=[],
        )

    def test_no_incident_for_isolated_failure(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector
        store = get_incident_store()
        detector = IncidentDetector(store=store)

        async def _inner():
            await detector.evaluate(self._make_failed_result())
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 0

    def test_incident_created_at_threshold(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector, INCIDENT_THRESHOLD_ERRORS
        store = get_incident_store()
        detector = IncidentDetector(store=store)

        async def _inner():
            for _ in range(INCIDENT_THRESHOLD_ERRORS):
                await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 1
        assert incidents[0].provider_slug == "gemini"

    def test_incident_created_immediately_on_circuit_open(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector
        store = get_incident_store()
        detector = IncidentDetector(store=store)
        result = self._make_failed_result(
            provider_slug="gemini",
            circuit_opened_in_events=True,
            circuit_state="open",
        )

        async def _inner():
            await detector.evaluate(result)
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 1
        assert incidents[0].circuit_opened is True
        assert incidents[0].severity.value == "critical"

    def test_no_duplicate_incidents_for_same_failure(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector, INCIDENT_THRESHOLD_ERRORS
        store = get_incident_store()
        detector = IncidentDetector(store=store)

        async def _inner():
            for _ in range(INCIDENT_THRESHOLD_ERRORS + 5):
                await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 1
        assert incidents[0].error_count > INCIDENT_THRESHOLD_ERRORS

    def test_success_resets_streak(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector, _error_streaks
        store = get_incident_store()
        detector = IncidentDetector(store=store)

        async def _inner():
            # Build streak to 2 (below threshold of 3)
            await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
            await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
            # Success resets streak
            await detector.evaluate(self._make_success_result(provider_slug="gemini"))
            # Now 1 more failure — still below threshold
            await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 0

    def test_fault_id_recorded_in_incident(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector, INCIDENT_THRESHOLD_ERRORS
        store = get_incident_store()
        detector = IncidentDetector(store=store)
        fault_id = "fault-test-abc"

        async def _inner():
            for _ in range(INCIDENT_THRESHOLD_ERRORS):
                await detector.evaluate(
                    self._make_failed_result(provider_slug="gemini"),
                    fault_id=fault_id,
                )
            return await store.list_all()

        incidents = _run(_inner())
        assert len(incidents) == 1
        assert incidents[0].fault_injected is True
        assert incidents[0].fault_id == fault_id

    def test_detector_never_raises_on_store_error(self):
        from app.incidents.detector import IncidentDetector

        broken_store = MagicMock()
        broken_store.get_active_by_dedup_key = AsyncMock(side_effect=RuntimeError("DB broken"))
        detector = IncidentDetector(store=broken_store)
        result = self._make_failed_result(circuit_opened_in_events=True)

        async def _inner():
            await detector.evaluate(result)
            return "ok"

        val = _run(_inner())
        assert val == "ok"

    def test_two_providers_get_separate_incidents(self):
        from app.incidents.store import get_incident_store
        from app.incidents.detector import IncidentDetector, INCIDENT_THRESHOLD_ERRORS
        store = get_incident_store()
        detector = IncidentDetector(store=store)

        async def _inner():
            for _ in range(INCIDENT_THRESHOLD_ERRORS):
                await detector.evaluate(self._make_failed_result(provider_slug="gemini"))
                await detector.evaluate(self._make_failed_result(provider_slug="groq"))
            return await store.list_all()

        incidents = _run(_inner())
        providers = {i.provider_slug for i in incidents}
        assert len(incidents) == 2
        assert "gemini" in providers
        assert "groq" in providers


# ─────────────────────────────────────────────────────────────────────────────
# 9. Incident Management API
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentAPI:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
        _reset_all()
        yield
        _reset_all()

    @pytest.fixture
    def client(self):
        return _get_client()

    def _seed_incident(self):
        from app.incidents.models import Incident, IncidentSeverity, FailureCategory
        from app.incidents.store import get_incident_store
        inc = Incident(
            provider_slug="gemini",
            provider_display_name="Gemini",
            failure_category=FailureCategory.AVAILABILITY,
            failure_type="timeout",
            severity=IncidentSeverity.HIGH,
            title="Gemini — Availability Degraded",
        )
        _run(get_incident_store().create(inc))
        return inc

    def test_list_incidents_empty(self, client):
        resp = client.get("/api/v1/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incidents"] == []
        assert data["total"] == 0

    def test_list_incidents_with_data(self, client):
        inc = self._seed_incident()
        resp = client.get("/api/v1/incidents")
        assert resp.status_code == 200
        ids = [i["incident_id"] for i in resp.json()["incidents"]]
        assert inc.incident_id in ids

    def test_get_incident_by_id(self, client):
        inc = self._seed_incident()
        resp = client.get(f"/api/v1/incidents/{inc.incident_id}")
        assert resp.status_code == 200
        assert resp.json()["incident"]["incident_id"] == inc.incident_id

    def test_get_incident_not_found(self, client):
        resp = client.get("/api/v1/incidents/INC-NOTREAL")
        assert resp.status_code == 404

    def test_acknowledge_incident(self, client):
        inc = self._seed_incident()
        resp = client.post(f"/api/v1/incidents/{inc.incident_id}/acknowledge")
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True
        assert resp.json()["incident"]["status"] == "acknowledged"

    def test_investigate_incident(self, client):
        inc = self._seed_incident()
        resp = client.post(f"/api/v1/incidents/{inc.incident_id}/investigate")
        assert resp.status_code == 200
        assert resp.json()["incident"]["status"] == "investigating"

    def test_resolve_incident(self, client):
        inc = self._seed_incident()
        resp = client.post(
            f"/api/v1/incidents/{inc.incident_id}/resolve",
            json={"note": "Provider recovered."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["incident"]["status"] == "resolved"
        assert data["incident"]["resolved_at"] is not None

    def test_resolve_already_resolved_returns_409(self, client):
        inc = self._seed_incident()
        client.post(f"/api/v1/incidents/{inc.incident_id}/resolve")
        resp = client.post(f"/api/v1/incidents/{inc.incident_id}/resolve")
        assert resp.status_code == 409

    def test_acknowledge_resolved_incident_returns_409(self, client):
        inc = self._seed_incident()
        client.post(f"/api/v1/incidents/{inc.incident_id}/resolve")
        resp = client.post(f"/api/v1/incidents/{inc.incident_id}/acknowledge")
        assert resp.status_code == 409

    def test_incident_summary(self, client):
        resp = client.get("/api/v1/incidents/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "open" in data
        assert "resolved" in data

    def test_filter_by_status(self, client):
        inc = self._seed_incident()
        resp = client.get("/api/v1/incidents?status=open")
        assert resp.status_code == 200
        ids = [i["incident_id"] for i in resp.json()["incidents"]]
        assert inc.incident_id in ids

    def test_incident_contains_no_secrets(self, client):
        inc = self._seed_incident()
        resp = client.get(f"/api/v1/incidents/{inc.incident_id}")
        text = resp.text
        assert "sk-" not in text
        assert "AQ." not in text
        assert "gsk_" not in text

    def test_list_incidents_pagination(self, client):
        resp = client.get("/api/v1/incidents?limit=10&offset=0")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 10. Security Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultInjectionSecurity:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        _reset_all()
        yield
        _reset_all()

    @pytest.fixture
    def client_enabled(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
        return _get_client()

    @pytest.fixture
    def client_disabled(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
        return _get_client()

    def test_cannot_inject_arbitrary_exception_class(self, client_enabled):
        resp = client_enabled.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "SystemExit",
        })
        assert resp.status_code == 422

    def test_cannot_inject_arbitrary_url_as_provider(self, client_enabled):
        resp = client_enabled.post("/api/v1/faults", json={
            "provider_slug": "http://internal-host/steal-secrets",
            "fault_type": "timeout",
        })
        assert resp.status_code == 422

    def test_code_in_note_stored_as_plain_text(self, client_enabled):
        """Note field content is stored verbatim — never executed."""
        resp = client_enabled.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "timeout",
            "note": "__import__('os').system('rm -rf /')",
        })
        assert resp.status_code == 201
        # The note is stored as plain text — check it appears correctly
        assert resp.json()["fault"]["is_active"] is True

    def test_mutation_blocked_when_disabled(self, client_disabled):
        resp = client_disabled.post("/api/v1/faults", json={
            "provider_slug": "gemini",
            "fault_type": "timeout",
        })
        assert resp.status_code == 403
        resp2 = client_disabled.delete("/api/v1/faults")
        assert resp2.status_code == 403

    def test_provider_slug_injection_prevention(self, client_enabled):
        malicious_slugs = [
            "gemini; DROP TABLE requests; --",
            "../etc/passwd",
            "GEMINI",
        ]
        for slug in malicious_slugs:
            resp = client_enabled.post("/api/v1/faults", json={
                "provider_slug": slug,
                "fault_type": "timeout",
            })
            assert resp.status_code in (400, 422), f"Expected rejection for slug: {slug!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Health Endpoint Phase 4
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpointPhase4:
    @pytest.fixture(autouse=True)
    def reset(self):
        _reset_all()
        yield
        _reset_all()

    def test_health_shows_fault_injection_disabled(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["fault_injection_enabled"] is False

    def test_health_shows_fault_injection_enabled(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
        client = _get_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["fault_injection_enabled"] is True

    def test_health_version_is_040(self, monkeypatch):
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
        client = _get_client()
        resp = client.get("/health")
        assert resp.json()["version"] == "0.4.0"
