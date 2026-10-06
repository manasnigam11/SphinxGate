"""
Gemini Provider Tests.

Covers:
  1. Gemini configuration detection (GEMINI_API_KEY present/absent)
  2. Provider registration (gemini slug available in registry)
  3. Successful adapter behavior using mocked HTTP responses
  4. Format translation: OpenAI → Gemini request and Gemini → OpenAI response
  5. Model name mapping (OpenAI model names → Gemini equivalents)
  6. System message handling (prepended to first user turn)
  7. Failure classification / resilience integration (HTTP errors passed through correctly)
  8. Fallback from OpenAI → Gemini using the ResilienceEngine with mocked upstreams
  9. No real external API calls are made anywhere in this file

All tests are isolated — no process-level state leaks between them.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.providers.gemini import (
    GeminiProvider,
    _resolve_model,
    _translate_to_gemini_request,
    _translate_to_openai_response,
    _DEFAULT_GEMINI_MODEL,
)
from app.providers.registry import REGISTRY, get_provider, list_providers
from app.resilience.policy import ResiliencePolicy, FallbackConfig
from app.resilience.engine import ResilienceEngine
from app.resilience.events import FALLBACK_ATTEMPTED, FALLBACK_SUCCEEDED


# ══════════════════════════════════════════════════════════════════════════════
# 1. Configuration detection
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_api_key_read_from_settings_when_present():
    """Settings.get_provider_api_key('gemini') returns the key when configured."""
    from app.config import Settings
    s = Settings(GEMINI_API_KEY="test-gemini-key-123")
    assert s.get_provider_api_key("gemini") == "test-gemini-key-123"


def test_gemini_api_key_returns_none_when_absent():
    """Settings.get_provider_api_key('gemini') returns None when GEMINI_API_KEY is unset."""
    from app.config import Settings
    s = Settings()
    # If no GEMINI_API_KEY is in environment, it must be None.
    # (It may be set in .env during testing; force a clean instance.)
    s_clean = Settings.model_construct(gemini_api_key=None)
    assert s_clean.get_provider_api_key("gemini") is None


def test_gemini_key_never_exposed_in_key_map_for_unknown_slug():
    """get_provider_api_key for an unknown slug returns None, not the Gemini key."""
    from app.config import Settings
    s = Settings(GEMINI_API_KEY="should-not-appear")
    assert s.get_provider_api_key("unknown-provider") is None
    assert s.get_provider_api_key("GEMINI") is None  # case-sensitive


# ══════════════════════════════════════════════════════════════════════════════
# 2. Provider registration
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_registered_in_registry():
    """'gemini' slug must be present in the provider registry."""
    assert "gemini" in REGISTRY


def test_openai_still_registered():
    """Adding Gemini must not break the existing OpenAI registration."""
    assert "openai" in REGISTRY


def test_get_provider_gemini_returns_gemini_instance():
    provider = get_provider("gemini")
    
    # If fault injection is enabled, it's wrapped
    from app.fault_injection.middleware import FaultAwareProvider
    if isinstance(provider, FaultAwareProvider):
        provider = provider._inner
        
    assert isinstance(provider, GeminiProvider)
    assert provider.slug == "gemini"
    assert provider.display_name == "Google Gemini"


def test_list_providers_includes_gemini():
    assert "gemini" in list_providers()


def test_unknown_provider_still_raises():
    with pytest.raises(KeyError, match="Unknown provider"):
        get_provider("nonexistent-provider")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Model name resolution
# ══════════════════════════════════════════════════════════════════════════════

def test_openai_gpt4o_maps_to_gemini_flash():
    assert _resolve_model("gpt-4o") == "gemini-2.5-flash"


def test_openai_gpt4_maps_to_gemini_pro():
    assert _resolve_model("gpt-4") == "gemini-1.5-pro"


def test_openai_gpt35_maps_to_gemini_flash():
    assert _resolve_model("gpt-3.5-turbo") == "gemini-1.5-flash"


def test_native_gemini_model_passed_through():
    assert _resolve_model("gemini-1.5-pro") == "gemini-1.5-pro"
    assert _resolve_model("gemini-2.0-flash") == "gemini-2.0-flash"


def test_unknown_model_falls_back_to_default():
    result = _resolve_model("some-unknown-model-xyz")
    assert result == _DEFAULT_GEMINI_MODEL


# ══════════════════════════════════════════════════════════════════════════════
# 4. Request translation (OpenAI → Gemini)
# ══════════════════════════════════════════════════════════════════════════════

def test_simple_user_message_translated():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello, Gemini!"}],
    }
    result = _translate_to_gemini_request(payload)
    assert "contents" in result
    assert len(result["contents"]) == 1
    assert result["contents"][0]["role"] == "user"
    assert result["contents"][0]["parts"][0]["text"] == "Hello, Gemini!"


def test_system_message_prepended_to_first_user_message():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": "Hi there"},
        ],
    }
    result = _translate_to_gemini_request(payload)
    # System prompt must be merged into the first user turn.
    assert len(result["contents"]) == 1
    text = result["contents"][0]["parts"][0]["text"]
    assert "You are a helpful assistant." in text
    assert "Hi there" in text


def test_assistant_role_mapped_to_model():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user",      "content": "Say hi"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user",      "content": "Say bye"},
        ],
    }
    result = _translate_to_gemini_request(payload)
    assert result["contents"][1]["role"] == "model"


def test_temperature_and_max_tokens_mapped():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "test"}],
        "temperature": 0.5,
        "max_tokens": 256,
    }
    result = _translate_to_gemini_request(payload)
    cfg = result.get("generationConfig", {})
    assert cfg["temperature"] == 0.5
    assert cfg["maxOutputTokens"] == 256


def test_no_generation_config_when_no_optional_params():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "test"}],
    }
    result = _translate_to_gemini_request(payload)
    assert "generationConfig" not in result


def test_stop_string_wrapped_in_list():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "test"}],
        "stop": "END",
    }
    result = _translate_to_gemini_request(payload)
    assert result["generationConfig"]["stopSequences"] == ["END"]


def test_stop_list_passed_through():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "test"}],
        "stop": ["END", "STOP"],
    }
    result = _translate_to_gemini_request(payload)
    assert result["generationConfig"]["stopSequences"] == ["END", "STOP"]


# ══════════════════════════════════════════════════════════════════════════════
# 5. Response translation (Gemini → OpenAI)
# ══════════════════════════════════════════════════════════════════════════════

def _make_gemini_response(text: str = "Hello!", finish: str = "STOP") -> dict:
    return {
        "candidates": [{
            "content": {
                "parts": [{"text": text}],
                "role": "model",
            },
            "finishReason": finish,
        }],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 5,
            "totalTokenCount": 15,
        },
    }


def test_response_has_openai_shape():
    result = _translate_to_openai_response(
        _make_gemini_response("Hi!"),
        model="gemini-2.0-flash",
        request_id="chatcmpl-test-abc",
    )
    assert result["object"] == "chat.completion"
    assert result["model"] == "gemini-2.0-flash"
    assert len(result["choices"]) == 1
    assert result["choices"][0]["message"]["role"] == "assistant"
    assert result["choices"][0]["message"]["content"] == "Hi!"
    assert result["choices"][0]["finish_reason"] == "stop"


def test_usage_tokens_mapped():
    result = _translate_to_openai_response(
        _make_gemini_response(),
        model="gemini-2.0-flash",
        request_id="req-1",
    )
    assert result["usage"]["prompt_tokens"] == 10
    assert result["usage"]["completion_tokens"] == 5
    assert result["usage"]["total_tokens"] == 15


def test_finish_reason_max_tokens_mapped():
    result = _translate_to_openai_response(
        _make_gemini_response(finish="MAX_TOKENS"),
        model="gemini-2.0-flash",
        request_id="req-2",
    )
    assert result["choices"][0]["finish_reason"] == "length"


def test_finish_reason_safety_mapped():
    result = _translate_to_openai_response(
        _make_gemini_response(finish="SAFETY"),
        model="gemini-2.0-flash",
        request_id="req-3",
    )
    assert result["choices"][0]["finish_reason"] == "content_filter"


def test_empty_candidates_returns_empty_choices():
    result = _translate_to_openai_response(
        {"candidates": [], "usageMetadata": {}},
        model="gemini-2.0-flash",
        request_id="req-4",
    )
    assert result["choices"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 6. Successful adapter behavior with mocked HTTP
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_gemini_adapter_success_with_mocked_http():
    """
    The adapter must call the Gemini API, translate the response, and return
    an OpenAI-compatible dict.  No real network call is made.
    """
    fake_gemini_response = _make_gemini_response("Mocked Gemini response")

    provider = GeminiProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = fake_gemini_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await provider.chat_completion(
            payload={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            api_key="test-key",
        )

    assert result["object"] == "chat.completion"
    assert result["choices"][0]["message"]["content"] == "Mocked Gemini response"
    assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_gemini_adapter_raises_on_http_error():
    """
    The adapter must propagate httpx.HTTPStatusError so the ResilienceEngine
    can classify it.  It must not swallow errors.
    """
    provider = GeminiProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        request = httpx.Request("POST", "https://example.com")
        error_response = httpx.Response(500, request=request)
        http_exc = httpx.HTTPStatusError("500", request=request, response=error_response)

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_exc

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat_completion(
                payload={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                api_key="test-key",
            )


@pytest.mark.asyncio
async def test_gemini_api_key_sent_in_header_not_query_param():
    """
    Gemini API key must be sent securely via the x-goog-api-key header.
    It must NOT appear in the URL query parameters to prevent logging leaks.
    """
    fake_gemini_response = _make_gemini_response("ok")
    provider = GeminiProvider()
    captured_call = {}

    async def fake_post(url, **kwargs):
        captured_call["url"] = url
        captured_call["params"] = kwargs.get("params", {})
        captured_call["headers"] = kwargs.get("headers", {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = fake_gemini_response
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = fake_post
        mock_client_cls.return_value = mock_client

        await provider.chat_completion(
            payload={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            api_key="my-secret-key",
        )

    # Key must NOT appear in query parameters
    assert "key" not in captured_call.get("params", {})
    
    # Key MUST appear in headers securely
    # Normalize headers for case-insensitive lookup
    headers = {k.lower(): v for k, v in captured_call.get("headers", {}).items()}
    assert headers.get("x-goog-api-key") == "my-secret-key"


# ══════════════════════════════════════════════════════════════════════════════
# 7. Failure classification integration
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_500_classified_as_server_error():
    from app.resilience.classifier import classify_status_code, FailureKind, is_retryable
    kind = classify_status_code(500)
    assert kind == FailureKind.SERVER_ERROR_500
    assert is_retryable(kind) is True


def test_gemini_503_classified_as_service_unavailable():
    from app.resilience.classifier import classify_status_code, FailureKind, is_retryable
    kind = classify_status_code(503)
    assert kind == FailureKind.SERVICE_UNAVAILABLE_503
    assert is_retryable(kind) is True


def test_gemini_429_classified_as_rate_limited():
    from app.resilience.classifier import classify_status_code, FailureKind, is_retryable
    kind = classify_status_code(429)
    assert kind == FailureKind.RATE_LIMITED
    # We do not retry upstream 429s — provider is asking us to back off
    assert is_retryable(kind) is False


def test_gemini_401_classified_as_client_error():
    from app.resilience.classifier import classify_status_code, FailureKind, is_retryable
    kind = classify_status_code(401)
    assert kind == FailureKind.CLIENT_ERROR_4XX
    assert is_retryable(kind) is False


# ══════════════════════════════════════════════════════════════════════════════
# 8. Fallback: OpenAI → Gemini via ResilienceEngine
# ══════════════════════════════════════════════════════════════════════════════

def make_fast_policy(**overrides) -> ResiliencePolicy:
    defaults = dict(
        request_timeout_seconds=5.0,
        retry_enabled=True,
        max_retries=0,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
        circuit_failure_threshold=3,
        circuit_recovery_window_seconds=0.1,
        rate_limit_requests=1000,
        rate_limit_window_seconds=1.0,
        fallback_enabled=True,
        fallback_configs={
            "openai": FallbackConfig(primary="openai", fallbacks=["gemini"])
        },
    )
    defaults.update(overrides)
    return ResiliencePolicy(**defaults)


def _make_fake_provider(slug: str, responses: list):
    """
    Build a minimal fake provider with a preconfigured call sequence.

    Implements the abstract BaseProvider interface properly so Python 3.13
    ABC enforcement is satisfied.  Returns an AsyncMock for chat_completion
    so call assertions work in tests.
    """
    from app.providers.base import BaseLLMProvider

    # Capture slug/responses in the closure so the inner class can use them.
    _responses = list(responses)
    _call_count = [0]  # mutable container so inner function can mutate it

    async def _chat_completion_impl(payload, api_key):
        idx = min(_call_count[0], len(_responses) - 1)
        item = _responses[idx]
        _call_count[0] += 1
        if isinstance(item, Exception):
            raise item
        return item

    class FakeProvider(BaseLLMProvider):
        async def chat_completion(self, payload, api_key):
            return await _chat_completion_impl(payload, api_key)

    fp = FakeProvider()
    fp.slug = slug
    fp.display_name = slug.capitalize()

    # Wrap with AsyncMock so .assert_not_called() and call inspection work.
    mock = AsyncMock(side_effect=_chat_completion_impl)
    fp.chat_completion = mock
    return fp


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.example.com/")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)


def _success_response(content: str = "Hello from provider") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }


@pytest.mark.asyncio
async def test_fallback_openai_to_gemini_when_openai_fails():
    """
    When OpenAI fails with a retryable error and there are no more retries,
    the engine must fall back to Gemini and succeed.
    """
    openai_provider = _make_fake_provider("openai", [_http_error(503)])
    gemini_provider = _make_fake_provider("gemini", [_success_response("Hello from Gemini")])

    policy = make_fast_policy(max_retries=0)
    engine = ResilienceEngine(policy)

    with patch("app.resilience.engine.get_provider") as mock_get:
        providers = {"openai": openai_provider, "gemini": gemini_provider}
        mock_get.side_effect = lambda slug: providers[slug]

        result = await engine.execute(
            request_id="req_fallback_test",
            provider_slug="openai",
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=lambda slug: "test-key",
        )

    assert result.success is True
    assert result.provider_slug == "gemini"
    assert result.fallback_used is True
    assert result.response["choices"][0]["message"]["content"] == "Hello from Gemini"

    fallback_events = [e for e in result.events if e.event_type == FALLBACK_ATTEMPTED]
    assert len(fallback_events) == 1
    assert fallback_events[0].data["fallback"] == "gemini"

    succeeded_events = [e for e in result.events if e.event_type == FALLBACK_SUCCEEDED]
    assert len(succeeded_events) == 1


@pytest.mark.asyncio
async def test_fallback_not_used_when_openai_succeeds():
    """When OpenAI succeeds, Gemini must not be called at all."""
    openai_provider = _make_fake_provider("openai", [_success_response("Hello from OpenAI")])
    gemini_provider = _make_fake_provider("gemini", [_success_response("Hello from Gemini")])

    policy = make_fast_policy()
    engine = ResilienceEngine(policy)

    with patch("app.resilience.engine.get_provider") as mock_get:
        providers = {"openai": openai_provider, "gemini": gemini_provider}
        mock_get.side_effect = lambda slug: providers[slug]

        result = await engine.execute(
            request_id="req_no_fallback_test",
            provider_slug="openai",
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=lambda slug: "test-key",
        )

    assert result.success is True
    assert result.provider_slug == "openai"
    assert result.fallback_used is False
    # Gemini must not have been called
    gemini_provider.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_both_providers_fail_returns_structured_error():
    """If both OpenAI and Gemini fail, the engine returns a clean structured failure."""
    openai_provider = _make_fake_provider("openai", [_http_error(503)])
    gemini_provider = _make_fake_provider("gemini", [_http_error(503)])

    policy = make_fast_policy(max_retries=0)
    engine = ResilienceEngine(policy)

    with patch("app.resilience.engine.get_provider") as mock_get:
        providers = {"openai": openai_provider, "gemini": gemini_provider}
        mock_get.side_effect = lambda slug: providers[slug]

        result = await engine.execute(
            request_id="req_both_fail",
            provider_slug="openai",
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=lambda slug: "test-key",
        )

    assert result.success is False
    assert result.response is None          # never fabricate a response
    assert result.status_code == 503
    assert result.error_type == "no_healthy_provider"
    assert "openai" in result.error_message
    assert "gemini" in result.error_message


@pytest.mark.asyncio
async def test_gemini_missing_api_key_causes_skip_not_error():
    """
    If no Gemini API key is configured, the engine must skip it gracefully
    and not crash.  It should report failure (no healthy provider) without
    exposing the missing key reason in a stack trace.
    """
    openai_provider = _make_fake_provider("openai", [_http_error(503)])
    gemini_provider = _make_fake_provider("gemini", [_success_response()])

    policy = make_fast_policy(max_retries=0)
    engine = ResilienceEngine(policy)

    def key_getter(slug: str):
        if slug == "openai":
            return "openai-key"
        return None  # No Gemini key — engine should skip it

    with patch("app.resilience.engine.get_provider") as mock_get:
        providers = {"openai": openai_provider, "gemini": gemini_provider}
        mock_get.side_effect = lambda slug: providers[slug]

        result = await engine.execute(
            request_id="req_no_gemini_key",
            provider_slug="openai",
            payload={"model": "gpt-4o", "messages": []},
            api_key_getter=key_getter,
        )

    assert result.success is False
    # Gemini must have been skipped — not called
    gemini_provider.chat_completion.assert_not_called()