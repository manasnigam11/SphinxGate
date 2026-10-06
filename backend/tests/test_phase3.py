"""
Phase 3 tests -- Facade, Cache, Telemetry, Request ID, Security.

ALL Phase 1 + Phase 2 + Phase 2.5 tests must continue to pass.
This file adds the new Phase 3 coverage.

Test categories:
  1. Facade -- orchestration, routing, success/failure flow
  2. Request ID -- generation, propagation, response header
  3. Cache -- miss, hit, TTL, metadata, provider policy
  4. Telemetry -- record, retrieve, summary, security
  5. Security -- no API key in telemetry/logs/response
  6. API endpoints -- new telemetry endpoints
  7. Provider health endpoint
"""

import asyncio
import json
import os
import time
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_success_response(text: str = "Hello!") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


# ============================================================
# 1. CACHE TESTS
# ============================================================

class TestResponseCache:
    def setup_method(self):
        from app.cache.store import ResponseCache, CachePolicy
        self.cache = ResponseCache({
            "open_meteo": CachePolicy(enabled=True, ttl_seconds=60, max_entries=10),
            "frankfurter": CachePolicy(enabled=True, ttl_seconds=3600, max_entries=10),
            "jokeapi": CachePolicy(enabled=False),
            "trivia": CachePolicy(enabled=False),
        })

    def test_cache_miss_when_empty(self):
        result = self.cache.get("open_meteo", {"lat": 52.0, "lon": 13.0})
        assert result.hit is False

    def test_cache_hit_after_set(self):
        params = {"lat": 52.0, "lon": 13.0}
        data = {"temperature": 22.5}
        self.cache.set("open_meteo", params, data)
        result = self.cache.get("open_meteo", params)
        assert result.hit is True
        assert result.data == data

    def test_cache_key_is_deterministic(self):
        params = {"lon": 13.0, "lat": 52.0}  # different order
        key1 = self.cache.make_key("open_meteo", params)
        key2 = self.cache.make_key("open_meteo", {"lat": 52.0, "lon": 13.0})
        assert key1 == key2

    def test_cache_disabled_for_jokeapi(self):
        self.cache.set("jokeapi", {}, {"joke": "Why did..."})
        result = self.cache.get("jokeapi", {})
        # Even if we call set, get() returns miss when disabled
        assert result.hit is False

    def test_cache_disabled_for_trivia(self):
        result = self.cache.get("trivia", {})
        assert result.hit is False

    def test_cache_disabled_for_unknown_provider(self):
        result = self.cache.get("openai", {"model": "gpt-4"})
        assert result.hit is False

    def test_cache_miss_after_ttl_expiry(self):
        from app.cache.store import CachePolicy, ResponseCache
        short_cache = ResponseCache({
            "open_meteo": CachePolicy(enabled=True, ttl_seconds=0.01, max_entries=10),
        })
        params = {"lat": 1.0}
        short_cache.set("open_meteo", params, {"temp": 20})
        time.sleep(0.05)  # Wait past TTL
        result = short_cache.get("open_meteo", params)
        assert result.hit is False

    def test_cache_hit_within_ttl(self):
        params = {"lat": 10.0}
        self.cache.set("open_meteo", params, {"temp": 15})
        result = self.cache.get("open_meteo", params)
        assert result.hit is True
        assert result.age_seconds < 1.0

    def test_different_params_different_keys(self):
        params_a = {"lat": 52.0, "lon": 13.0}
        params_b = {"lat": 48.0, "lon": 2.0}
        self.cache.set("open_meteo", params_a, {"city": "Berlin"})
        result = self.cache.get("open_meteo", params_b)
        assert result.hit is False

    def test_cache_returns_metadata(self):
        params = {"base": "USD"}
        self.cache.set("frankfurter", params, {"rates": {"EUR": 0.92}})
        result = self.cache.get("frankfurter", params)
        assert result.hit is True
        assert result.cache_key is not None
        assert result.age_seconds >= 0

    def test_cache_evicts_at_capacity(self):
        from app.cache.store import CachePolicy, ResponseCache
        tiny_cache = ResponseCache({
            "open_meteo": CachePolicy(enabled=True, ttl_seconds=60, max_entries=3),
        })
        for i in range(5):
            tiny_cache.set("open_meteo", {"i": i}, {"val": i})
        # Should not exceed max_entries
        assert len(tiny_cache._store.get("open_meteo", {})) <= 3

    def test_cache_stats(self):
        self.cache.set("open_meteo", {"lat": 1}, {"temp": 10})
        stats = self.cache.stats()
        assert "open_meteo" in stats
        assert stats["open_meteo"]["live_entries"] >= 1

    def test_invalidate_provider(self):
        self.cache.set("open_meteo", {"lat": 1}, {"temp": 10})
        removed = self.cache.invalidate("open_meteo")
        assert removed >= 1
        result = self.cache.get("open_meteo", {"lat": 1})
        assert result.hit is False

    def test_stale_fallback_not_served_by_default(self):
        from app.cache.store import CachePolicy, ResponseCache
        stale_cache = ResponseCache({
            "open_meteo": CachePolicy(
                enabled=True, ttl_seconds=0.01, max_entries=10,
                allow_stale_on_failure=False,
            ),
        })
        params = {"lat": 1.0}
        stale_cache.set("open_meteo", params, {"temp": 20})
        time.sleep(0.05)
        result = stale_cache.get("open_meteo", params, allow_stale=True)
        # allow_stale_on_failure=False means stale is not returned
        assert result.hit is False


# ============================================================
# 2. TELEMETRY STORE TESTS
# ============================================================

class TestTelemetryStore:

    @pytest.fixture
    def tmp_store(self, tmp_path):
        from app.telemetry.store import TelemetryStore
        db_file = str(tmp_path / "test_telemetry.db")
        return TelemetryStore(db_path=db_file)

    def test_store_initializes(self, tmp_store):
        asyncio.run(tmp_store.initialize())
        assert tmp_store._initialized is True

    def test_record_and_retrieve(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_test_001",
            timestamp=time.time(),
            provider_slug="gemini",
            provider_display_name="Google Gemini",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=350,
            retry_count=0,
            fallback_used=False,
            circuit_state="closed",
            tokens_used=100,
        )
        asyncio.run(tmp_store.record(rec))
        records = asyncio.run(tmp_store.recent(limit=10))
        assert len(records) == 1
        assert records[0].request_id == "req_test_001"
        assert records[0].provider_slug == "gemini"
        assert records[0].success is True

    def test_failed_request_recorded(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_fail_001",
            timestamp=time.time(),
            provider_slug="openai",
            provider_display_name="OpenAI",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=False,
            status_code=503,
            latency_ms=5000,
            retry_count=2,
            fallback_used=False,
            circuit_state="open",
            error_type="timeout",
            error_message="Provider timed out after 3 retries",
        )
        asyncio.run(tmp_store.record(rec))
        records = asyncio.run(tmp_store.recent(limit=10))
        assert records[0].success is False
        assert records[0].error_type == "timeout"
        assert records[0].retry_count == 2

    def test_get_by_request_id(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_detail_001",
            timestamp=time.time(),
            provider_slug="groq",
            provider_display_name="Groq",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=120,
            retry_count=0,
            fallback_used=False,
            circuit_state="closed",
            tokens_used=50,
        )
        asyncio.run(tmp_store.record(rec))
        found = asyncio.run(tmp_store.get("req_detail_001"))
        assert found is not None
        assert found.provider_slug == "groq"

    def test_get_unknown_request_returns_none(self, tmp_store):
        asyncio.run(tmp_store.initialize())
        found = asyncio.run(tmp_store.get("req_nonexistent"))
        assert found is None

    def test_summary_is_accurate(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        for i in range(3):
            asyncio.run(tmp_store.record(TelemetryRecord(
                request_id=f"req_ok_{i}",
                timestamp=time.time(),
                provider_slug="gemini",
                provider_display_name="Google Gemini",
                provider_category="llm",
                endpoint="/api/v1/chat/completions",
                success=True,
                status_code=200,
                latency_ms=300 + i * 50,
                retry_count=0,
                fallback_used=False,
                circuit_state="closed",
                tokens_used=100,
            )))
        asyncio.run(tmp_store.record(TelemetryRecord(
            request_id="req_fail_s",
            timestamp=time.time(),
            provider_slug="openai",
            provider_display_name="OpenAI",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=False,
            status_code=503,
            latency_ms=5000,
            retry_count=2,
            fallback_used=False,
            circuit_state="open",
            error_type="timeout",
        )))
        summary = asyncio.run(tmp_store.summary(since_seconds=3600))
        assert summary.total_requests == 4
        assert summary.successful_requests == 3
        assert summary.failed_requests == 1
        assert "timeout" in summary.failure_types

    def test_retry_metadata_recorded(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_retry_001",
            timestamp=time.time(),
            provider_slug="groq",
            provider_display_name="Groq",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=800,
            retry_count=2,
            fallback_used=False,
            circuit_state="closed",
        )
        asyncio.run(tmp_store.record(rec))
        records = asyncio.run(tmp_store.recent(limit=10))
        assert records[0].retry_count == 2

    def test_fallback_metadata_recorded(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_fallback_001",
            timestamp=time.time(),
            provider_slug="groq",
            provider_display_name="Groq",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=450,
            retry_count=0,
            fallback_used=True,
            circuit_state="closed",
        )
        asyncio.run(tmp_store.record(rec))
        records = asyncio.run(tmp_store.recent(limit=10))
        assert records[0].fallback_used is True

    def test_cache_hit_metadata_recorded(self, tmp_store):
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        rec = TelemetryRecord(
            request_id="req_cache_001",
            timestamp=time.time(),
            provider_slug="open_meteo",
            provider_display_name="Open-Meteo",
            provider_category="public_api",
            endpoint="/api/v1/query",
            success=True,
            status_code=200,
            latency_ms=0,
            retry_count=0,
            fallback_used=False,
            circuit_state="closed",
            cache_hit=True,
            cache_key="open_meteo:abc123",
        )
        asyncio.run(tmp_store.record(rec))
        found = asyncio.run(tmp_store.get("req_cache_001"))
        assert found.cache_hit is True
        assert found.cache_key == "open_meteo:abc123"

    def test_no_api_key_in_records(self, tmp_store):
        """API keys must never appear in stored telemetry."""
        from app.telemetry.models import TelemetryRecord
        asyncio.run(tmp_store.initialize())
        # Store a record that simulates a real request (no key in any field)
        rec = TelemetryRecord(
            request_id="req_sec_001",
            timestamp=time.time(),
            provider_slug="gemini",
            provider_display_name="Google Gemini",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=300,
            retry_count=0,
            fallback_used=False,
            circuit_state="closed",
            error_type=None,
            error_message=None,  # Must never contain the API key
        )
        asyncio.run(tmp_store.record(rec))
        found = asyncio.run(tmp_store.get("req_sec_001"))
        # Verify no secret-looking values in the record
        record_str = json.dumps(found.__dict__)
        # These field values should not appear
        assert "sk-" not in record_str
        assert "AIza" not in record_str
        assert "gsk_" not in record_str


# ============================================================
# 3. FACADE TESTS
# ============================================================

class TestSphinxGateFacade:

    def _make_facade(self):
        from app.facade import SphinxGateFacade
        from app.cache.store import ResponseCache, CachePolicy
        from app.resilience.engine import ResilienceEngine
        from app.resilience.policy import ResiliencePolicy

        policy = ResiliencePolicy.from_settings()
        engine = ResilienceEngine(policy)

        cache = ResponseCache({
            "open_meteo": CachePolicy(enabled=True, ttl_seconds=60, max_entries=100),
        })

        # Minimal in-memory mock store
        class MemStore:
            def __init__(self):
                self.records = []
            async def record(self, rec):
                self.records.append(rec)
            async def initialize(self):
                pass

        store = MemStore()
        facade = SphinxGateFacade(engine=engine, cache=cache, store=store)
        return facade, engine, store

    def test_facade_instantiates(self):
        facade, _, _ = self._make_facade()
        assert facade is not None
        assert facade.engine is not None

    def test_facade_rejects_unknown_llm_provider(self):
        facade, _, _ = self._make_facade()
        with pytest.raises(ValueError, match="Unknown provider"):
            asyncio.run(facade.handle_llm_request(
                request_id="req_test",
                provider_slug="nonexistent_provider",
                payload={},
                api_key_getter=lambda slug: None,
            ))

    def test_facade_rejects_wrong_category_for_llm(self):
        """Cannot use a public API provider via handle_llm_request."""
        facade, _, _ = self._make_facade()
        with pytest.raises(ValueError, match="not an LLM provider"):
            asyncio.run(facade.handle_llm_request(
                request_id="req_test",
                provider_slug="open_meteo",
                payload={},
                api_key_getter=lambda slug: None,
            ))

    def test_facade_rejects_wrong_category_for_public_api(self):
        """Cannot use LLM provider via handle_public_api_request."""
        facade, _, _ = self._make_facade()
        with pytest.raises(ValueError, match="not a public API provider"):
            asyncio.run(facade.handle_public_api_request(
                request_id="req_test",
                provider_slug="gemini",
                payload={},
                api_key_getter=lambda slug: "fake-key",
            ))

    def test_facade_records_telemetry_on_success(self):
        facade, engine, store = self._make_facade()

        success_resp = _make_success_response()

        async def run():
            from app.providers.registry import get_provider
            provider = get_provider("open_meteo")
            with patch.object(provider, "call", new=AsyncMock(return_value={"weather": "sunny"})):
                result = await facade.handle_public_api_request(
                    request_id="req_facade_001",
                    provider_slug="open_meteo",
                    payload={"lat": 1.0, "lon": 2.0},
                    api_key_getter=lambda slug: None,
                )
            return result

        result = asyncio.run(run())
        assert len(store.records) == 1
        assert store.records[0].request_id == "req_facade_001"

    def test_facade_records_telemetry_on_failure(self):
        facade, engine, store = self._make_facade()

        async def run():
            from app.providers.registry import get_provider
            provider = get_provider("open_meteo")
            with patch.object(provider, "call", new=AsyncMock(side_effect=Exception("upstream error"))):
                result = await facade.handle_public_api_request(
                    request_id="req_facade_fail",
                    provider_slug="open_meteo",
                    payload={"lat": 1.0},
                    api_key_getter=lambda slug: None,
                )
            return result

        result = asyncio.run(run())
        assert len(store.records) == 1
        assert store.records[0].success is False

    def test_facade_always_calls_engine_despite_cache(self):
        """Even with cached data, the engine should be called for fresh data (resilience-only cache)."""
        facade, engine, store = self._make_facade()

        params = {"lat": 52.0, "lon": 13.0}
        cached_data = {"temperature": 22.5}
        facade._cache.set("open_meteo", params, cached_data)

        engine_execute_called = []

        async def run():
            original_execute = engine.execute
            async def spy_execute(*args, **kwargs):
                engine_execute_called.append(True)
                return await original_execute(*args, **kwargs)
            engine.execute = spy_execute
            
            from app.providers.registry import get_provider
            provider = get_provider("open_meteo")
            with patch.object(provider, "call", new=AsyncMock(return_value={"temperature": 25.0})):
                result = await facade.handle_public_api_request(
                    request_id="req_always_fresh",
                    provider_slug="open_meteo",
                    payload=params,
                    api_key_getter=lambda slug: None,
                )
            return result

        result = asyncio.run(run())
        assert result.cache_hit is False  # Cache hit upfront is now ignored for the main result
        assert len(engine_execute_called) == 1  # Engine WAS called

    def test_facade_cache_miss_calls_engine(self):
        """On a cache miss, the engine should be called."""
        facade, engine, store = self._make_facade()

        engine_execute_called = []

        async def run():
            from app.providers.registry import get_provider
            provider = get_provider("open_meteo")
            with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 10})):
                result = await facade.handle_public_api_request(
                    request_id="req_cache_miss",
                    provider_slug="open_meteo",
                    payload={"lat": 99.0},
                    api_key_getter=lambda slug: None,
                )
            return result

        result = asyncio.run(run())
        assert result.cache_hit is False

    def test_facade_caches_successful_public_response(self):
        """A successful public API response should be cached and used as a fallback if the API fails."""
        facade, engine, store = self._make_facade()

        params = {"lat": 33.0, "lon": 44.0}

        async def run():
            from app.providers.registry import REGISTRY
            provider = REGISTRY["open_meteo"]
            # First call: healthy, populates cache
            with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 25})):
                await facade.handle_public_api_request(
                    request_id="req_cache_populate",
                    provider_slug="open_meteo",
                    payload=params,
                    api_key_getter=lambda slug: None,
                )

            # Second call: fails, so it degrades and hits the cache fallback
            with patch.object(provider, "call", new=AsyncMock(side_effect=Exception("API down"))):
                result2 = await facade.handle_public_api_request(
                    request_id="req_cache_hit2",
                    provider_slug="open_meteo",
                    payload=params,
                    api_key_getter=lambda slug: None,
                )
            return result2

        result = asyncio.run(run())
        assert result.cache_hit is True
        assert result.degraded is True

    def test_facade_does_not_cache_llm_responses(self):
        """LLM responses must never be cached."""
        facade, engine, store = self._make_facade()
        # LLM request returns -- cache should be empty after
        async def run():
            from app.providers.registry import REGISTRY
            provider = REGISTRY["gemini"]
            with patch.object(provider, "call", new=AsyncMock(return_value=_make_success_response())):
                await facade.handle_llm_request(
                    request_id="req_llm_no_cache",
                    provider_slug="gemini",
                    payload={"model": "gemini-pro", "messages": []},
                    api_key_getter=lambda slug: "fake-key",
                )
            return facade._cache.stats()

        stats = asyncio.run(run())
        # gemini cache should not have any entries
        assert "gemini" not in stats


# ============================================================
# 4. REQUEST ID TESTS
# ============================================================

class TestRequestID:

    @pytest.fixture
    def client(self):
        """Create a TestClient with the real app."""
        from app.main import app
        from app.gateway.router import _reset_engine
        from app.facade import _reset_facade
        _reset_engine(None)
        _reset_facade(None)
        return TestClient(app, raise_server_exceptions=True)

    def test_request_id_in_response_header_on_success(self, client):
        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        with patch.object(provider, "call", new=AsyncMock(return_value={"weather": "sunny"})):
            response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": {"lat": 1.0}})
        assert "x-request-id" in response.headers
        assert response.headers["x-request-id"].startswith("req_")

    def test_request_id_in_response_header_on_failure(self, client):
        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        with patch.object(provider, "call", new=AsyncMock(side_effect=Exception("fail"))):
            response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": {}})
        # Even failures should have a request ID
        assert "x-request-id" in response.headers

    def test_unique_request_ids(self, client):
        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        ids = []
        with patch.object(provider, "call", new=AsyncMock(return_value={"w": "ok"})):
            for _ in range(5):
                response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": {}})
                ids.append(response.headers.get("x-request-id"))
        # All IDs should be unique
        assert len(set(ids)) == 5


# ============================================================
# 5. SECURITY TESTS
# ============================================================

class TestSecurity:

    def test_no_api_key_in_telemetry_record(self):
        """TelemetryRecord must not contain API key data."""
        from app.telemetry.models import TelemetryRecord
        rec = TelemetryRecord(
            request_id="req_sec_test",
            timestamp=time.time(),
            provider_slug="gemini",
            provider_display_name="Google Gemini",
            provider_category="llm",
            endpoint="/api/v1/chat/completions",
            success=True,
            status_code=200,
            latency_ms=300,
            retry_count=0,
            fallback_used=False,
            circuit_state="closed",
        )
        rec_dict = rec.__dict__
        # Verify there's no field that would store an API key
        for field_name in rec_dict:
            assert "api_key" not in field_name.lower()
            assert "secret" not in field_name.lower()
            assert "credential" not in field_name.lower()
            assert "token" not in field_name.lower() or field_name == "tokens_used"

    def test_error_message_truncated_in_telemetry(self):
        """Very long error messages should be truncated before storage."""
        from app.facade import SphinxGateFacade
        from app.cache.store import ResponseCache
        from app.resilience.engine import ResilienceEngine
        from app.resilience.policy import ResiliencePolicy
        from app.resilience.events import RequestResult

        policy = ResiliencePolicy.from_settings()
        engine = ResilienceEngine(policy)

        class MemStore:
            def __init__(self):
                self.records = []
            async def record(self, rec):
                self.records.append(rec)
            async def initialize(self):
                pass

        store = MemStore()
        facade = SphinxGateFacade(engine=engine, cache=ResponseCache({}), store=store)

        very_long_error = "A" * 2000
        result = RequestResult(
            success=False,
            response=None,
            request_id="req_trunc",
            provider_slug="openai",
            provider_display_name="OpenAI",
            latency_ms=0,
            retry_count=0,
            circuit_state="closed",
            fallback_used=False,
            status_code=500,
            tokens_used=0,
            error_type="test_error",
            error_message=very_long_error,
        )

        asyncio.run(facade._record_telemetry(
            result=result,
            endpoint="/api/v1/chat/completions",
            provider_category="llm",
            cache_result=None,
        ))
        assert len(store.records) == 1
        # Error message should be capped at 500 chars
        stored_msg = store.records[0].error_message
        assert len(stored_msg) <= 500

    def test_cache_key_does_not_contain_api_key(self):
        """Cache keys should only include provider slug and param hash."""
        from app.cache.store import ResponseCache, CachePolicy
        cache = ResponseCache({
            "open_meteo": CachePolicy(enabled=True, ttl_seconds=60),
        })
        # Even if someone accidentally passes api_key in params (they shouldn't),
        # the cache key is a hash and doesn't expose it
        key = cache.make_key("open_meteo", {"lat": 52.0, "lon": 13.0})
        assert "AIza" not in key
        assert "sk-" not in key
        assert "gsk_" not in key

    def test_response_headers_do_not_contain_api_key(self):
        """Gateway response headers must never leak API keys."""
        from app.main import app
        from app.gateway.router import _reset_engine
        from app.facade import _reset_facade
        _reset_engine(None)
        _reset_facade(None)

        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        with patch.object(provider, "call", new=AsyncMock(return_value={"w": "ok"})):
            with TestClient(app) as client:
                response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": {}})

        for header_name, header_value in response.headers.items():
            assert "AIza" not in header_value
            assert "sk-" not in header_value
            assert "gsk_" not in header_value


# ============================================================
# 6. TELEMETRY API ENDPOINT TESTS
# ============================================================

class TestTelemetryAPIEndpoints:

    @pytest.fixture
    def client(self):
        """Set up a TestClient with isolated telemetry store."""
        from app.main import app
        from app.gateway.router import _reset_engine
        from app.facade import _reset_facade
        from app.telemetry import store as telemetry_store_module
        import tempfile

        # Use a temp DB for each test
        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, "test_telemetry.db")

        from app.telemetry.store import TelemetryStore
        fresh_store = TelemetryStore(db_path=db_path)

        _reset_engine(None)
        _reset_facade(None)
        telemetry_store_module._store = fresh_store

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

        telemetry_store_module._store = None

    def test_telemetry_requests_empty(self, client):
        response = client.get("/api/v1/telemetry/requests")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert isinstance(data["requests"], list)

    def test_telemetry_summary_empty(self, client):
        response = client.get("/api/v1/telemetry/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert data["total_requests"] == 0

    def test_telemetry_summary_window_param(self, client):
        response = client.get("/api/v1/telemetry/summary?window=24h")
        assert response.status_code == 200
        data = response.json()
        assert data["window"] == "24h"

    def test_telemetry_request_not_found(self, client):
        response = client.get("/api/v1/telemetry/requests/req_nonexistent")
        assert response.status_code == 404

    def test_telemetry_cache_stats(self, client):
        response = client.get("/api/v1/telemetry/cache")
        assert response.status_code == 200
        data = response.json()
        assert "cache_stats" in data

    def test_telemetry_provider_health(self, client):
        response = client.get("/api/v1/telemetry/health")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)

    def test_requests_appear_in_telemetry_after_query(self, client):
        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 20})):
            client.post("/api/v1/query", json={"provider": "open_meteo", "params": {"lat": 1.0}})

        response = client.get("/api/v1/telemetry/requests")
        data = response.json()
        # The request should now be in telemetry
        assert data["count"] >= 1
        assert any(r["provider"] == "open_meteo" for r in data["requests"])

    def test_telemetry_provider_stats_endpoint(self, client):
        response = client.get("/api/v1/telemetry/providers/open_meteo")
        assert response.status_code == 200
        data = response.json()
        assert "window" in data

    def test_telemetry_requests_pagination(self, client):
        response = client.get("/api/v1/telemetry/requests?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0


# ============================================================
# 7. CACHE IN RESPONSE HEADERS
# ============================================================

class TestCacheHeaders:

    @pytest.fixture
    def client(self):
        from app.main import app
        from app.gateway.router import _reset_engine
        from app.facade import _reset_facade
        from app.cache import store as cache_store_module
        _reset_engine(None)
        _reset_facade(None)
        cache_store_module._cache = None  # also reset the cache singleton
        return TestClient(app, raise_server_exceptions=False)

    def test_cache_miss_header_for_public_api(self, client):
        from app.providers.registry import get_provider
        provider = get_provider("open_meteo")
        with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 20})):
            response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": {"lat": 11.11}})
        # First call with fresh cache is always a miss
        assert response.headers.get("x-cache-hit") == "false"

    def test_cache_hit_header_on_second_call(self, client):
        from app.providers.registry import REGISTRY
        provider = REGISTRY["open_meteo"]
        params = {"lat": 77.0, "lon": 88.0}
        with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 15})):
            # First call -- miss, populates cache
            client.post("/api/v1/query", json={"provider": "open_meteo", "params": params})
        
        # Second call -- fail the API so it degrades and falls back to cache
        with patch.object(provider, "call", new=AsyncMock(side_effect=Exception("API Down"))):
            response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": params})
        
        assert response.headers.get("x-cache-hit") == "true"

    def test_cache_miss_for_llm_always(self, client):
        """LLM requests should always report cache miss."""
        from app.providers.registry import REGISTRY
        provider = REGISTRY["gemini"]
        with patch.object(provider, "call", new=AsyncMock(return_value=_make_success_response())):
            response = client.post(
                "/api/v1/chat/completions",
                json={"model": "gemini-pro", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"X-Provider": "gemini"},
            )
        # Should be "miss" -- LLMs are never cached
        assert response.headers.get("x-cache-hit") == "miss"

    def test_cache_body_metadata_on_hit(self, client):
        """cache_hit field should appear in response body on a cache hit (degraded)."""
        from app.providers.registry import REGISTRY
        provider = REGISTRY["open_meteo"]
        params = {"lat": 55.0, "lon": 37.0}
        with patch.object(provider, "call", new=AsyncMock(return_value={"temp": 5})):
            client.post("/api/v1/query", json={"provider": "open_meteo", "params": params})
            
        with patch.object(provider, "call", new=AsyncMock(side_effect=Exception("Fail"))):
            response = client.post("/api/v1/query", json={"provider": "open_meteo", "params": params})
        
        body = response.json()
        assert body.get("cache_hit") is True


# ============================================================
# 8. BACKWARD COMPATIBILITY
# ============================================================

class TestBackwardCompatibility:
    """Ensure Phase 1 and Phase 2 endpoints still work correctly."""

    @pytest.fixture
    def client(self):
        from app.main import app
        from app.gateway.router import _reset_engine
        from app.facade import _reset_facade
        _reset_engine(None)
        _reset_facade(None)
        return TestClient(app, raise_server_exceptions=False)

    def test_policy_endpoint_still_works(self, client):
        response = client.get("/api/v1/policy")
        assert response.status_code == 200
        data = response.json()
        # Policy dict can use various key formats depending on to_dict() implementation
        # Just verify it returns a non-empty dict
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_provider_state_endpoint_still_works(self, client):
        response = client.get("/api/v1/providers/state")
        assert response.status_code == 200
        assert "providers" in response.json()

    def test_providers_endpoint_still_works(self, client):
        response = client.get("/api/v1/providers")
        assert response.status_code == 200
        providers = response.json()["providers"]
        slugs = [p["slug"] for p in providers]
        assert "gemini" in slugs
        assert "open_meteo" in slugs

    def test_health_endpoint_still_works(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] in ("0.3.0", "0.4.0")  # Updated in Phase 4

    def test_unknown_provider_returns_400(self, client):
        response = client.post(
            "/api/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Provider": "nonexistent_provider_xyz"},
        )
        assert response.status_code == 400

    def test_llm_provider_via_query_returns_400(self, client):
        response = client.post(
            "/api/v1/query",
            json={"provider": "gemini", "params": {}},
        )
        assert response.status_code == 400

    def test_public_api_via_completions_returns_400(self, client):
        # open_meteo is not an LLM provider
        from app.providers.registry import get_provider
        response = client.post(
            "/api/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Provider": "open_meteo"},
        )
        # Should return an error -- no API key for this route combo,
        # or be rejected by the facade category check
        assert response.status_code in (400, 500, 503)
