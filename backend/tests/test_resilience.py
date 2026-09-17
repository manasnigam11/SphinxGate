"""
Phase 2 Resilience Engine Test Suite.

Tests are organized to cover every requirement from the Phase 2 spec.
All tests use mocked/fake providers — no real API calls are made.

Test coverage:
  1.  Successful request → no retry
  2.  Retryable provider failure → retry occurs
  3.  Non-retryable failure → no retry
  4.  Retry limit is respected
  5.  Exponential backoff is bounded
  6.  Circuit transitions CLOSED → OPEN
  7.  OPEN circuit blocks normal requests
  8.  Recovery window allows HALF-OPEN
  9.  Successful HALF-OPEN probe → CLOSED
  10. Failed HALF-OPEN probe → OPEN again
  11. Fallback provider is used when appropriate
  12. Fallback not attempted when configuration does not allow it
  13. All providers fail → structured failure
  14. Gateway rate limit rejects excessive requests
  15. Phase 1 successful request path remains functional (integration smoke test)
"""

import asyncio
import pytest
import pytest_asyncio

from app.resilience.classifier import (
    FailureKind,
    classify_status_code,
    classify_exception,
    is_retryable,
    counts_toward_circuit,
)
from app.resilience.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerRegistry
from app.resilience.rate_limiter import GatewayRateLimiter
from app.resilience.engine import ResilienceEngine
from app.resilience.policy import ResiliencePolicy, FallbackConfig
from app.resilience.events import RETRY_ATTEMPTED, RETRY_EXHAUSTED, CIRCUIT_OPENED, FALLBACK_ATTEMPTED

import httpx


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_policy(**overrides) -> ResiliencePolicy:
    """Return a test policy with sensible fast defaults."""
    defaults = dict(
        request_timeout_seconds=5.0,
        retry_enabled=True,
        max_retries=2,
        initial_backoff_seconds=0.01,   # very short for tests
        max_backoff_seconds=0.05,
        circuit_failure_threshold=3,
        circuit_recovery_window_seconds=0.1,  # 100ms for tests
        rate_limit_requests=100,
        rate_limit_window_seconds=1.0,
        fallback_enabled=True,
        fallback_configs={},
    )
    defaults.update(overrides)
    return ResiliencePolicy(**defaults)


class FakeProvider:
    """
    Fake provider that returns preconfigured responses or raises preconfigured errors.

    responses: list of callables or dicts / exceptions to return/raise in order.
    If the list is exhausted the last item is repeated.
    """

    def __init__(self, slug: str, responses: list):
        self.slug = slug
        self.display_name = slug.capitalize()
        self._responses = responses
        self._call_count = 0

    async def chat_completion(self, payload, api_key):
        idx = min(self._call_count, len(self._responses) - 1)
        item = self._responses[idx]
        self._call_count += 1

        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item


def _success_response():
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """Create a fake httpx.HTTPStatusError with the given status code."""
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


async def _run_engine(
    policy: ResiliencePolicy,
    providers: dict,  # slug -> FakeProvider
    primary: str = "primary",
    extra_api_keys: dict | None = None,
):
    """
    Run the ResilienceEngine with fake providers injected.

    Patches app.providers.registry.get_provider to return the fake providers.
    """
    from unittest.mock import patch

    api_keys = {slug: "test-key" for slug in providers}
    if extra_api_keys:
        api_keys.update(extra_api_keys)

    engine = ResilienceEngine(policy)

    with patch("app.resilience.engine.get_provider") as mock_get_provider:
        def _get(slug):
            if slug not in providers:
                raise KeyError(f"Unknown: {slug}")
            return providers[slug]

        mock_get_provider.side_effect = _get

        result = await engine.execute(
            request_id="req_test",
            provider_slug=primary,
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=lambda slug: api_keys.get(slug),
        )
    return result, engine


# ══════════════════════════════════════════════════════════════════════════════
# 1. Successful request — no retry
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_successful_request_no_retry():
    """A successful first-attempt response must not trigger any retries."""
    provider = FakeProvider("primary", [_success_response()])
    result, engine = await _run_engine(
        make_policy(),
        {"primary": provider},
    )

    assert result.success is True
    assert result.retry_count == 0
    assert provider._call_count == 1
    assert result.tokens_used == 15


# ══════════════════════════════════════════════════════════════════════════════
# 2. Retryable failure → retry occurs
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_retryable_failure_triggers_retry():
    """A 503 failure on attempt 1 must cause at least one retry."""
    provider = FakeProvider("primary", [
        _http_error(503),        # attempt 1 → fail (retryable)
        _success_response(),     # attempt 2 → success
    ])
    result, _ = await _run_engine(make_policy(), {"primary": provider})

    assert result.success is True
    assert provider._call_count == 2
    assert result.retry_count == 1
    retry_events = [e for e in result.events if e.event_type == RETRY_ATTEMPTED]
    assert len(retry_events) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. Non-retryable failure → no retry
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_non_retryable_failure_no_retry():
    """A 401 authentication error must NOT trigger any retries."""
    provider = FakeProvider("primary", [_http_error(401)])
    result, _ = await _run_engine(
        make_policy(fallback_enabled=False),
        {"primary": provider},
    )

    assert result.success is False
    assert provider._call_count == 1   # only one call — no retry
    assert result.retry_count == 0


@pytest.mark.asyncio
async def test_quota_exhausted_not_retried():
    """A quota-exhaustion error (via 429) must NOT be retried."""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(
        429,
        json={"error": {"type": "insufficient_quota", "code": "insufficient_quota", "message": "Quota exceeded"}},
        request=request,
    )
    exc = httpx.HTTPStatusError("429", request=request, response=response)
    provider = FakeProvider("primary", [exc])

    result, _ = await _run_engine(
        make_policy(fallback_enabled=False),
        {"primary": provider},
    )

    assert result.success is False
    assert provider._call_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# 4. Retry limit is respected
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_retry_limit_respected():
    """With max_retries=2, a provider that always fails must be called exactly 3 times."""
    provider = FakeProvider("primary", [_http_error(503)])  # always fails
    result, _ = await _run_engine(
        make_policy(max_retries=2, fallback_enabled=False),
        {"primary": provider},
    )

    assert result.success is False
    assert provider._call_count == 3  # 1 initial + 2 retries
    assert result.retry_count == 2

    exhausted = [e for e in result.events if e.event_type == RETRY_EXHAUSTED]
    assert len(exhausted) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. Exponential backoff is bounded
# ══════════════════════════════════════════════════════════════════════════════

def test_backoff_is_bounded():
    """Computed backoff must never exceed max_backoff_seconds."""
    policy = make_policy(
        initial_backoff_seconds=0.5,
        max_backoff_seconds=2.0,
        max_retries=10,
    )
    engine = ResilienceEngine(policy)

    for attempt in range(1, 11):
        backoff = engine._compute_backoff(attempt)
        assert backoff <= policy.max_backoff_seconds, (
            f"Attempt {attempt}: backoff {backoff} exceeds max {policy.max_backoff_seconds}"
        )


def test_backoff_increases():
    """Backoff must grow with each successive retry (until capped)."""
    policy = make_policy(initial_backoff_seconds=0.1, max_backoff_seconds=100.0)
    engine = ResilienceEngine(policy)

    b1 = engine._compute_backoff(1)
    b2 = engine._compute_backoff(2)
    b3 = engine._compute_backoff(3)

    assert b1 < b2 < b3


# ══════════════════════════════════════════════════════════════════════════════
# 6. Circuit transitions CLOSED → OPEN
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    """After (threshold) consecutive counted failures, circuit must transition to OPEN."""
    cb = CircuitBreaker("test", failure_threshold=3, recovery_window_seconds=60.0)
    assert cb.state == CircuitState.CLOSED

    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    assert cb.state == CircuitState.CLOSED

    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    assert cb.state == CircuitState.CLOSED

    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_engine_emits_circuit_opened_event():
    """ResilienceEngine must emit a CIRCUIT_OPENED event when the breaker opens."""
    # threshold=3, always-failing provider, no fallback
    provider = FakeProvider("primary", [_http_error(503)])
    result, _ = await _run_engine(
        make_policy(
            circuit_failure_threshold=3,
            max_retries=5,           # enough retries to hit the threshold
            fallback_enabled=False,
        ),
        {"primary": provider},
    )
    opened = [e for e in result.events if e.event_type == CIRCUIT_OPENED]
    assert len(opened) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 7. OPEN circuit blocks normal requests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_open_circuit_blocks_requests():
    """A circuit that is OPEN must not allow requests through (allow_request → False)."""
    cb = CircuitBreaker("test", failure_threshold=1, recovery_window_seconds=60.0)
    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)

    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


@pytest.mark.asyncio
async def test_engine_skips_open_circuit_provider():
    """The engine must skip a provider whose circuit is already OPEN."""
    # First, force the circuit open by running failures against it directly.
    provider = FakeProvider("primary", [_http_error(500)])

    result, engine = await _run_engine(
        make_policy(
            circuit_failure_threshold=1,
            max_retries=0,
            fallback_enabled=False,
        ),
        {"primary": provider},
    )
    assert result.success is False

    # Now the circuit should be OPEN. A second request should be immediately rejected.
    from unittest.mock import patch
    with patch("app.resilience.engine.get_provider") as mock_get_provider:
        mock_get_provider.side_effect = lambda s: provider if s == "primary" else (_ for _ in ()).throw(KeyError(s))

        result2 = await engine.execute(
            request_id="req_test2",
            provider_slug="primary",
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=lambda s: "test-key",
        )

    # provider._call_count should still be 1 (not called again)
    assert provider._call_count == 1
    assert result2.success is False


# ══════════════════════════════════════════════════════════════════════════════
# 8. Recovery window allows HALF-OPEN
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_recovery_window_allows_half_open():
    """After the recovery window, the circuit must allow a probe (HALF-OPEN)."""
    cb = CircuitBreaker("test", failure_threshold=1, recovery_window_seconds=0.05)
    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    assert cb.state == CircuitState.OPEN

    # Before window expires: still blocked
    assert cb.allow_request() is False

    # Wait for recovery window
    await asyncio.sleep(0.1)

    # Now a probe should be allowed
    entered = await cb.maybe_enter_half_open()
    assert entered is True
    assert cb.state == CircuitState.HALF_OPEN


# ══════════════════════════════════════════════════════════════════════════════
# 9. Successful HALF-OPEN probe → CLOSED
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_half_open_success_closes_circuit():
    """A successful probe from HALF-OPEN must transition the circuit to CLOSED."""
    cb = CircuitBreaker("test", failure_threshold=1, recovery_window_seconds=0.05)
    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    await asyncio.sleep(0.1)
    await cb.maybe_enter_half_open()
    assert cb.state == CircuitState.HALF_OPEN

    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# ══════════════════════════════════════════════════════════════════════════════
# 10. Failed HALF-OPEN probe → OPEN again
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit():
    """A failed probe from HALF-OPEN must send the circuit back to OPEN."""
    cb = CircuitBreaker("test", failure_threshold=1, recovery_window_seconds=0.05)
    await cb.record_failure(FailureKind.SERVER_ERROR_500.value)
    await asyncio.sleep(0.1)
    await cb.maybe_enter_half_open()
    assert cb.state == CircuitState.HALF_OPEN

    await cb.record_failure(FailureKind.TIMEOUT.value)
    assert cb.state == CircuitState.OPEN


# ══════════════════════════════════════════════════════════════════════════════
# 11. Fallback provider is used when appropriate
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fallback_used_when_primary_fails():
    """When the primary always fails, the engine should fall back to the configured fallback."""
    primary = FakeProvider("primary", [_http_error(503), _http_error(503), _http_error(503)])
    fallback = FakeProvider("fallback", [_success_response()])

    policy = make_policy(
        max_retries=0,
        fallback_enabled=True,
        fallback_configs={"primary": FallbackConfig(primary="primary", fallbacks=["fallback"])},
    )
    result, _ = await _run_engine(policy, {"primary": primary, "fallback": fallback})

    assert result.success is True
    assert result.fallback_used is True
    assert result.provider_slug == "fallback"

    fallback_events = [e for e in result.events if e.event_type == FALLBACK_ATTEMPTED]
    assert len(fallback_events) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 12. Fallback not attempted when configuration does not allow it
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_fallback_when_disabled():
    """When fallback_enabled=False, the engine must not try any fallback provider."""
    primary = FakeProvider("primary", [_http_error(503)])
    fallback = FakeProvider("fallback", [_success_response()])

    policy = make_policy(
        max_retries=0,
        fallback_enabled=False,
        fallback_configs={"primary": FallbackConfig(primary="primary", fallbacks=["fallback"])},
    )
    result, _ = await _run_engine(policy, {"primary": primary, "fallback": fallback})

    assert result.success is False
    assert fallback._call_count == 0
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_no_fallback_when_no_chain_configured():
    """When no fallback chain is configured, only the primary is tried."""
    primary = FakeProvider("primary", [_http_error(503)])
    fallback = FakeProvider("fallback", [_success_response()])

    policy = make_policy(
        max_retries=0,
        fallback_enabled=True,
        fallback_configs={},  # no chain for "primary"
    )
    result, _ = await _run_engine(policy, {"primary": primary, "fallback": fallback})

    assert result.success is False
    assert fallback._call_count == 0


# ══════════════════════════════════════════════════════════════════════════════
# 13. All providers fail → structured failure
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_providers_fail_returns_structured_error():
    """When every provider in the chain fails, the engine must return a clear structured error."""
    primary = FakeProvider("primary", [_http_error(503)])
    fallback = FakeProvider("fallback", [_http_error(503)])

    policy = make_policy(
        max_retries=0,
        fallback_enabled=True,
        fallback_configs={"primary": FallbackConfig(primary="primary", fallbacks=["fallback"])},
    )
    result, _ = await _run_engine(policy, {"primary": primary, "fallback": fallback})

    assert result.success is False
    assert result.response is None   # never fabricate a response
    assert result.error_type == "no_healthy_provider"
    assert "primary" in result.error_message
    assert "fallback" in result.error_message
    assert result.status_code == 503


# ══════════════════════════════════════════════════════════════════════════════
# 14. Gateway rate limit rejects excessive requests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rate_limiter_allows_up_to_limit():
    """Rate limiter must allow exactly max_requests in a window."""
    limiter = GatewayRateLimiter(max_requests=5, window_seconds=10.0)
    results = [await limiter.allow() for _ in range(5)]
    assert all(results)
    # 6th must be rejected
    assert await limiter.allow() is False


@pytest.mark.asyncio
async def test_engine_returns_429_when_rate_limited():
    """The engine must return status_code=429 and the gateway_rate_limit error type."""
    provider = FakeProvider("primary", [_success_response()])
    policy = make_policy(rate_limit_requests=0, rate_limit_window_seconds=10.0)
    result, _ = await _run_engine(policy, {"primary": provider})

    assert result.success is False
    assert result.status_code == 429
    assert result.error_type == "gateway_rate_limit"
    # The provider must never have been called
    assert provider._call_count == 0


# ══════════════════════════════════════════════════════════════════════════════
# 15. Phase 1 request path smoke test
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_phase1_happy_path_still_works():
    """
    End-to-end smoke test: the engine processes a normal successful request
    and returns the provider response with correct metadata.
    """
    provider = FakeProvider("openai", [_success_response()])
    result, _ = await _run_engine(
        make_policy(),
        {"openai": provider},
        primary="openai",
    )

    assert result.success is True
    assert result.response is not None
    assert result.response["object"] == "chat.completion"
    assert result.tokens_used == 15
    assert result.retry_count == 0
    assert result.circuit_state == CircuitState.CLOSED.value
    assert result.fallback_used is False
    assert result.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Classifier unit tests
# ══════════════════════════════════════════════════════════════════════════════

def test_classify_timeout_exception():
    exc = httpx.ReadTimeout("timeout", request=httpx.Request("POST", "https://x.com"))
    assert classify_exception(exc) == FailureKind.TIMEOUT


def test_classify_connect_error():
    exc = httpx.ConnectError("refused", request=httpx.Request("POST", "https://x.com"))
    assert classify_exception(exc) == FailureKind.CONNECTION_ERROR


def test_classify_503():
    assert classify_status_code(503) == FailureKind.SERVICE_UNAVAILABLE_503
    assert is_retryable(FailureKind.SERVICE_UNAVAILABLE_503) is True


def test_classify_401():
    assert classify_status_code(401) == FailureKind.CLIENT_ERROR_4XX
    assert is_retryable(FailureKind.CLIENT_ERROR_4XX) is False


def test_classify_429_rate_limited():
    assert classify_status_code(429) == FailureKind.RATE_LIMITED
    assert is_retryable(FailureKind.RATE_LIMITED) is False


def test_classify_429_quota_exhausted():
    body = {"error": {"type": "insufficient_quota", "code": "insufficient_quota"}}
    kind = classify_status_code(429, error_body=body)
    assert kind == FailureKind.QUOTA_EXHAUSTED
    assert is_retryable(FailureKind.QUOTA_EXHAUSTED) is False


def test_retryable_kinds():
    retryable = [
        FailureKind.TIMEOUT,
        FailureKind.CONNECTION_ERROR,
        FailureKind.SERVER_ERROR_500,
        FailureKind.BAD_GATEWAY_502,
        FailureKind.SERVICE_UNAVAILABLE_503,
        FailureKind.GATEWAY_TIMEOUT_504,
        FailureKind.OTHER_5XX,
    ]
    for kind in retryable:
        assert is_retryable(kind), f"{kind} should be retryable"


def test_non_retryable_kinds():
    non_retryable = [
        FailureKind.RATE_LIMITED,
        FailureKind.QUOTA_EXHAUSTED,
        FailureKind.CLIENT_ERROR_4XX,
        FailureKind.PROVIDER_ERROR,
        FailureKind.UNKNOWN,
    ]
    for kind in non_retryable:
        assert not is_retryable(kind), f"{kind} should NOT be retryable"


def test_counts_toward_circuit():
    assert counts_toward_circuit(FailureKind.TIMEOUT) is True
    assert counts_toward_circuit(FailureKind.SERVER_ERROR_500) is True
    assert counts_toward_circuit(FailureKind.RATE_LIMITED) is True
    # Auth errors should NOT trip the circuit
    assert counts_toward_circuit(FailureKind.CLIENT_ERROR_4XX) is False
    assert counts_toward_circuit(FailureKind.QUOTA_EXHAUSTED) is False


# ══════════════════════════════════════════════════════════════════════════════
# Circuit breaker snapshot test
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_circuit_snapshot_shape():
    """Circuit breaker get_snapshot() must return all required fields."""
    cb = CircuitBreaker("test", failure_threshold=5, recovery_window_seconds=30.0)
    snap = cb.get_snapshot()

    assert snap["provider"] == "test"
    assert snap["state"] == "closed"
    assert snap["failure_count"] == 0
    assert snap["failure_threshold"] == 5
    assert snap["recovery_window_seconds"] == 30.0
    assert isinstance(snap["transition_history"], list)


@pytest.mark.asyncio
async def test_circuit_registry_creates_per_provider_instances():
    """Each provider slug must get its own independent circuit breaker."""
    registry = CircuitBreakerRegistry(failure_threshold=5, recovery_window_seconds=30.0)
    cb_a = await registry.get("provider_a")
    cb_b = await registry.get("provider_b")

    await cb_a.record_failure(FailureKind.TIMEOUT.value)
    # provider_b should be unaffected
    assert cb_b.failure_count == 0
    assert cb_a.failure_count == 1
