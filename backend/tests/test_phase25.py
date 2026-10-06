"""
Phase 2.5 Test Suite — Multi-Provider Architecture.

Tests cover:
  A. Provider base abstraction (ProviderCategory, BaseLLMProvider, BasePublicAPIProvider)
  B. Provider registry (all 7 providers registered, lookup, category filtering)
  C. Groq adapter (normalization, config, error handling)
  D. Open-Meteo adapter (normalization, error handling)
  E. JokeAPI adapter (normalization, twopart, error handling)
  F. Frankfurter adapter (normalization, error handling)
  G. Open Trivia DB adapter (normalization, error codes, HTML decoding)
  H. Resilience integration for public API providers
       - public API provider passes through with api_key=None
       - timeout handling
       - retryable failure / retry
       - circuit breaker
       - rate limiter
       - fallback only within same category
  I. Config — Groq key in settings
  J. Security — no key required for public providers

No real HTTP calls are made.  All upstream calls are mocked.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import httpx

from app.providers.base import (
    BaseProvider,
    BaseLLMProvider,
    BasePublicAPIProvider,
    ProviderCategory,
)
from app.providers.registry import (
    REGISTRY,
    get_provider,
    list_providers,
    list_providers_by_category,
    get_provider_info,
)
from app.providers.groq import GroqProvider, _resolve_model as groq_resolve_model
from app.providers.open_meteo import OpenMeteoProvider, _normalize as meteo_normalize
from app.providers.jokeapi import JokeAPIProvider, _normalize as joke_normalize
from app.providers.frankfurter import FrankfurterProvider, _normalize as fx_normalize
from app.providers.trivia import TriviaProvider, _normalize as trivia_normalize
from app.config import Settings
from app.resilience.policy import ResiliencePolicy, FallbackConfig
from app.resilience.engine import ResilienceEngine
from app.resilience.events import RETRY_ATTEMPTED, CIRCUIT_OPENED, RATE_LIMIT_REJECTED


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_policy(**overrides) -> ResiliencePolicy:
    defaults = dict(
        request_timeout_seconds=5.0,
        retry_enabled=True,
        max_retries=2,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
        circuit_failure_threshold=3,
        circuit_recovery_window_seconds=0.1,
        rate_limit_requests=100,
        rate_limit_window_seconds=1.0,
        fallback_enabled=True,
        fallback_configs={},
    )
    defaults.update(overrides)
    return ResiliencePolicy(**defaults)


class FakePublicAPIProvider(BasePublicAPIProvider):
    """Fake public API provider for testing without real HTTP calls."""
    slug = "fake_public"
    display_name = "Fake Public"

    def __init__(self, responses: list):
        self._responses = responses
        self._call_count = 0

    async def call(self, payload, api_key):
        idx = min(self._call_count, len(self._responses) - 1)
        item = self._responses[idx]
        self._call_count += 1
        if isinstance(item, Exception):
            raise item
        if asyncio.iscoroutinefunction(item):
            return await item()
        if callable(item):
            return item()
        return item


class FakeLLMProvider(BaseLLMProvider):
    """Fake LLM provider for testing."""
    slug = "fake_llm"
    display_name = "Fake LLM"

    def __init__(self, responses: list):
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


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.example.com/v1/data")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=req, response=resp)


async def _run_engine_with_provider(
    policy: ResiliencePolicy,
    provider,
    slug: str,
    payload: dict | None = None,
    api_key: str | None = None,
):
    """Run the ResilienceEngine with a single injected provider."""
    engine = ResilienceEngine(policy)
    providers = {slug: provider}

    with patch("app.resilience.engine.get_provider") as mock_get:
        def _get(s):
            if s not in providers:
                raise KeyError(f"Unknown: {s}")
            return providers[s]
        mock_get.side_effect = _get

        result = await engine.execute(
            request_id="req_test",
            provider_slug=slug,
            payload=payload or {},
            api_key_getter=lambda s: api_key,
        )
    return result, engine


# ══════════════════════════════════════════════════════════════════════════════
# A. Provider base abstraction
# ══════════════════════════════════════════════════════════════════════════════

def test_provider_category_enum_values():
    """ProviderCategory must have LLM and PUBLIC_API values."""
    assert ProviderCategory.LLM.value == "llm"
    assert ProviderCategory.PUBLIC_API.value == "public_api"


def test_base_llm_provider_category():
    """BaseLLMProvider subclasses should have category=LLM and requires_api_key=True."""
    p = FakeLLMProvider([{}])
    assert p.category == ProviderCategory.LLM
    assert p.requires_api_key is True


def test_base_public_api_provider_category():
    """BasePublicAPIProvider subclasses should have category=PUBLIC_API and requires_api_key=False."""
    p = FakePublicAPIProvider([{}])
    assert p.category == ProviderCategory.PUBLIC_API
    assert p.requires_api_key is False


@pytest.mark.asyncio
async def test_base_llm_provider_call_delegates_to_chat_completion():
    """BaseLLMProvider.call() must delegate to chat_completion() with the same args."""
    expected = {"id": "test", "choices": []}
    p = FakeLLMProvider([expected])
    result = await p.call({"model": "test"}, "test-key")
    assert result == expected


@pytest.mark.asyncio
async def test_base_public_api_provider_call_direct():
    """BasePublicAPIProvider.call() is implemented directly (no chat_completion)."""
    expected = {"data": "weather-data"}
    p = FakePublicAPIProvider([expected])
    result = await p.call({}, None)
    assert result == expected


# ══════════════════════════════════════════════════════════════════════════════
# B. Provider registry
# ══════════════════════════════════════════════════════════════════════════════

def test_all_seven_providers_registered():
    """All 7 providers must be present in the registry."""
    expected = {"openai", "gemini", "groq", "open_meteo", "jokeapi", "frankfurter", "trivia"}
    assert expected.issubset(set(REGISTRY.keys()))


def test_groq_registered():
    """'groq' must be in the registry."""
    assert "groq" in REGISTRY


def test_open_meteo_registered():
    assert "open_meteo" in REGISTRY


def test_jokeapi_registered():
    assert "jokeapi" in REGISTRY


def test_frankfurter_registered():
    assert "frankfurter" in REGISTRY


def test_trivia_registered():
    assert "trivia" in REGISTRY


def test_existing_providers_still_registered():
    """Adding new providers must not break openai and gemini registration."""
    assert "openai" in REGISTRY
    assert "gemini" in REGISTRY


def test_get_provider_groq():
    """get_provider('groq') must return a GroqProvider instance."""
    provider = get_provider("groq")
    
    # If fault injection is enabled, it's wrapped
    from app.fault_injection.middleware import FaultAwareProvider
    if isinstance(provider, FaultAwareProvider):
        provider = provider._inner
        
    assert isinstance(provider, GroqProvider)
    assert provider.slug == "groq"


def test_unknown_provider_raises():
    """get_provider with unknown slug must raise KeyError."""
    with pytest.raises(KeyError):
        get_provider("nonexistent_provider_xyz")


def test_list_providers_by_category_llm():
    """list_providers_by_category(LLM) must include openai, gemini, groq."""
    llm_providers = list_providers_by_category(ProviderCategory.LLM)
    assert "openai" in llm_providers
    assert "gemini" in llm_providers
    assert "groq" in llm_providers
    # Must NOT include public API providers
    assert "open_meteo" not in llm_providers
    assert "jokeapi" not in llm_providers


def test_list_providers_by_category_public_api():
    """list_providers_by_category(PUBLIC_API) must include all 4 public API providers."""
    public_providers = list_providers_by_category(ProviderCategory.PUBLIC_API)
    assert "open_meteo" in public_providers
    assert "jokeapi" in public_providers
    assert "frankfurter" in public_providers
    assert "trivia" in public_providers
    # Must NOT include LLM providers
    assert "openai" not in public_providers
    assert "groq" not in public_providers


def test_get_provider_info_includes_all():
    """get_provider_info() must return metadata for all 7 providers."""
    info = get_provider_info()
    slugs = {p["slug"] for p in info}
    assert {"openai", "gemini", "groq", "open_meteo", "jokeapi", "frankfurter", "trivia"} == slugs


def test_public_providers_do_not_require_api_key():
    """Public API providers must have requires_api_key=False in registry."""
    for slug in ("open_meteo", "jokeapi", "frankfurter", "trivia"):
        provider = get_provider(slug)
        assert provider.requires_api_key is False, f"{slug} should not require an API key"


def test_llm_providers_require_api_key():
    """LLM providers must have requires_api_key=True."""
    for slug in ("openai", "gemini", "groq"):
        provider = get_provider(slug)
        assert provider.requires_api_key is True, f"{slug} should require an API key"


# ══════════════════════════════════════════════════════════════════════════════
# C. Groq adapter
# ══════════════════════════════════════════════════════════════════════════════

def test_groq_api_key_in_settings():
    """Settings must load GROQ_API_KEY."""
    s = Settings(GROQ_API_KEY="gsk_test_key_123")
    assert s.get_provider_api_key("groq") == "gsk_test_key_123"


def test_groq_api_key_returns_none_when_absent():
    """get_provider_api_key('groq') returns None when key is not set."""
    s = Settings.model_construct(groq_api_key=None)
    assert s.get_provider_api_key("groq") is None


def test_groq_model_resolution_openai_names():
    """OpenAI model names must be mapped to Groq equivalents."""
    assert groq_resolve_model("gpt-4o") == "llama-3.3-70b-versatile"
    assert groq_resolve_model("gpt-4o-mini") == "llama-3.1-8b-instant"
    assert groq_resolve_model("gpt-3.5-turbo") == "llama-3.1-8b-instant"


def test_groq_model_resolution_native_names():
    """Groq-native model names must pass through unchanged."""
    assert groq_resolve_model("llama-3.3-70b-versatile") == "llama-3.3-70b-versatile"
    assert groq_resolve_model("mixtral-8x7b-32768") == "mixtral-8x7b-32768"


def test_groq_model_resolution_unknown_falls_back():
    """Unknown model names must fall back to the default Groq model."""
    result = groq_resolve_model("some-unknown-model")
    assert result == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_groq_adapter_success():
    """Groq adapter must parse a successful chat completion response."""
    groq_response = {
        "id": "chatcmpl-groq-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.3-70b-versatile",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    mock_response = MagicMock()
    mock_response.json.return_value = groq_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    provider = GroqProvider()

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.chat_completion(
            payload={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            api_key="gsk_test_key",
        )

    assert result["id"] == "chatcmpl-groq-test"
    assert result["choices"][0]["message"]["content"] == "Hello"
    assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_groq_api_key_sent_in_auth_header_not_url():
    """Groq API key must be in Authorization header, never in the URL."""
    captured_headers = {}

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "test", "object": "chat.completion", "created": 0,
        "model": "llama-3.3-70b-versatile", "choices": [], "usage": {}
    }
    mock_response.raise_for_status = MagicMock()

    async def fake_post(url, headers=None, json=None, **kwargs):
        captured_headers.update(headers or {})
        # URL must NOT contain the key
        assert "gsk_test" not in url
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    provider = GroqProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await provider.chat_completion(
            payload={"model": "gpt-4o", "messages": []},
            api_key="gsk_test_key_secret",
        )

    assert "Authorization" in captured_headers
    assert "gsk_test_key_secret" in captured_headers["Authorization"]
    # Bearer scheme
    assert captured_headers["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_groq_upstream_error_raises():
    """Groq adapter must raise HTTPStatusError on non-2xx, allowing the engine to classify."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _http_error(500)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    provider = GroqProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat_completion(
                payload={"model": "gpt-4o", "messages": []},
                api_key="gsk_test",
            )


# ══════════════════════════════════════════════════════════════════════════════
# D. Open-Meteo adapter
# ══════════════════════════════════════════════════════════════════════════════

def test_open_meteo_normalize_basic():
    """meteo_normalize() must produce location/current/units keys."""
    raw = {
        "latitude": 51.5,
        "longitude": -0.1,
        "timezone": "Europe/London",
        "timezone_abbreviation": "GMT",
        "elevation": 5.0,
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
        "current": {"time": "2024-01-01T12:00", "temperature_2m": 10.5, "wind_speed_10m": 20.0},
    }
    params = {"latitude": 51.5, "longitude": -0.1}
    result = meteo_normalize(raw, params)

    assert result["location"]["latitude"] == 51.5
    assert result["location"]["timezone"] == "Europe/London"
    assert result["current"]["temperature_2m"] == 10.5
    assert result["units"]["temperature_2m"] == "°C"


@pytest.mark.asyncio
async def test_open_meteo_requires_lat_lon():
    """Open-Meteo adapter must raise ValueError if lat/lon are missing."""
    provider = OpenMeteoProvider()
    with pytest.raises(ValueError, match="latitude"):
        await provider.call({}, None)


@pytest.mark.asyncio
async def test_open_meteo_upstream_error_raises():
    """Open-Meteo adapter must propagate HTTP errors for the engine to handle."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _http_error(503)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = OpenMeteoProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.call({"latitude": 51.5, "longitude": -0.1}, None)


@pytest.mark.asyncio
async def test_open_meteo_successful_response():
    """Open-Meteo adapter must return normalized data on success."""
    raw_response = {
        "latitude": 51.51,
        "longitude": -0.13,
        "timezone": "Europe/London",
        "timezone_abbreviation": "GMT",
        "elevation": 10.0,
        "current_units": {"temperature_2m": "°C"},
        "current": {"time": "2024-01-01T12:00", "temperature_2m": 8.3},
    }

    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = OpenMeteoProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.call({"latitude": 51.51, "longitude": -0.13}, None)

    assert result["location"]["latitude"] == 51.51
    assert result["current"]["temperature_2m"] == 8.3


# ══════════════════════════════════════════════════════════════════════════════
# E. JokeAPI adapter
# ══════════════════════════════════════════════════════════════════════════════

def test_joke_normalize_single():
    """joke_normalize() must handle single delivery jokes."""
    raw = {
        "type": "single",
        "joke": "Why do programmers prefer dark mode? Because light attracts bugs.",
        "category": "Programming",
        "id": 42,
        "safe": True,
        "lang": "en",
        "flags": {"nsfw": False},
        "error": False,
    }
    result = joke_normalize(raw)
    assert result["joke"]["text"] == raw["joke"]
    assert result["joke"]["delivery"] is None
    assert result["joke"]["category"] == "Programming"
    assert result["error"] is False


def test_joke_normalize_twopart():
    """joke_normalize() must handle two-part jokes."""
    raw = {
        "type": "twopart",
        "setup": "Why was the JavaScript developer sad?",
        "delivery": "Because he didn't know how to 'null' his feelings.",
        "category": "Programming",
        "id": 1,
        "safe": True,
        "lang": "en",
        "flags": {},
        "error": False,
    }
    result = joke_normalize(raw)
    assert result["joke"]["text"] == raw["setup"]
    assert result["joke"]["delivery"] == raw["delivery"]


@pytest.mark.asyncio
async def test_jokeapi_successful_response():
    """JokeAPI adapter must return normalized data on success."""
    raw_response = {
        "type": "single",
        "joke": "Test joke",
        "category": "Any",
        "id": 1,
        "safe": True,
        "lang": "en",
        "flags": {},
        "error": False,
    }

    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = JokeAPIProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.call({"category": "Any"}, None)

    assert result["joke"]["text"] == "Test joke"
    assert result["error"] is False


@pytest.mark.asyncio
async def test_jokeapi_upstream_error_raises():
    """JokeAPI adapter must propagate HTTP errors."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _http_error(500)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = JokeAPIProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.call({}, None)


# ══════════════════════════════════════════════════════════════════════════════
# F. Frankfurter adapter
# ══════════════════════════════════════════════════════════════════════════════

def test_frankfurter_normalize():
    """fx_normalize() must produce correct normalized structure."""
    raw = {
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-15",
        "rates": {"EUR": 0.92, "GBP": 0.79},
    }
    result = fx_normalize(raw, 1.0)

    assert result["base"] == "USD"
    assert result["date"] == "2024-01-15"
    assert result["rates"]["EUR"] == 0.92
    assert "description" in result
    assert "EUR" in result["description"]


@pytest.mark.asyncio
async def test_frankfurter_successful_response():
    """Frankfurter adapter must return normalized exchange rate data."""
    raw_response = {
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-15",
        "rates": {"EUR": 0.92, "GBP": 0.79, "JPY": 148.5},
    }

    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = FrankfurterProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.call({"base": "USD", "to": "EUR,GBP,JPY"}, None)

    assert result["base"] == "USD"
    assert "EUR" in result["rates"]


@pytest.mark.asyncio
async def test_frankfurter_upstream_error_raises():
    """Frankfurter adapter must propagate HTTP errors."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _http_error(503)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = FrankfurterProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.call({}, None)


def test_frankfurter_list_currencies_converted():
    """Frankfurter adapter must accept list format for 'to' currencies."""
    raw = {"amount": 1.0, "base": "USD", "date": "2024-01-15", "rates": {"EUR": 0.92}}
    result = fx_normalize(raw, 1.0)
    assert result["rates"] == {"EUR": 0.92}


# ══════════════════════════════════════════════════════════════════════════════
# G. Open Trivia DB adapter
# ══════════════════════════════════════════════════════════════════════════════

def test_trivia_normalize_success():
    """trivia_normalize() must decode HTML entities and structure questions."""
    raw = {
        "response_code": 0,
        "results": [
            {
                "question": "What is 2 &amp; 2?",
                "category": "Math &amp; Science",
                "difficulty": "easy",
                "type": "multiple",
                "correct_answer": "4",
                "incorrect_answers": ["3", "5", "6"],
            }
        ],
    }
    result = trivia_normalize(raw)

    assert result["response_code"] == 0
    assert result["count"] == 1
    q = result["questions"][0]
    assert q["question"] == "What is 2 & 2?"       # HTML decoded
    assert q["category"] == "Math & Science"        # HTML decoded
    assert q["correct_answer"] == "4"
    assert "4" in q["all_answers"]
    assert len(q["all_answers"]) == 4               # 3 incorrect + 1 correct


def test_trivia_normalize_error_code():
    """trivia_normalize() must raise ValueError on non-zero response codes."""
    raw = {"response_code": 1, "results": []}
    with pytest.raises(ValueError, match="Not enough questions"):
        trivia_normalize(raw)


def test_trivia_normalize_all_answers_sorted():
    """trivia_normalize() must sort all_answers so correct isn't always last."""
    raw = {
        "response_code": 0,
        "results": [
            {
                "question": "Q?",
                "category": "C",
                "difficulty": "easy",
                "type": "multiple",
                "correct_answer": "A",
                "incorrect_answers": ["B", "C", "D"],
            }
        ],
    }
    result = trivia_normalize(raw)
    all_answers = result["questions"][0]["all_answers"]
    assert all_answers == sorted(all_answers)


@pytest.mark.asyncio
async def test_trivia_successful_response():
    """Trivia adapter must return normalized questions."""
    raw_response = {
        "response_code": 0,
        "results": [
            {
                "question": "Test question?",
                "category": "General",
                "difficulty": "easy",
                "type": "multiple",
                "correct_answer": "Yes",
                "incorrect_answers": ["No", "Maybe", "Never"],
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = TriviaProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.call({"amount": 1, "difficulty": "easy"}, None)

    assert result["count"] == 1
    assert result["questions"][0]["question"] == "Test question?"


@pytest.mark.asyncio
async def test_trivia_upstream_error_raises():
    """Trivia adapter must propagate HTTP errors."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _http_error(500)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    provider = TriviaProvider()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.call({"amount": 5}, None)


# ══════════════════════════════════════════════════════════════════════════════
# H. Resilience integration — public API providers
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_public_api_provider_passes_through_with_no_key():
    """
    Public API providers must pass through the resilience engine even when
    api_key_getter returns None (requires_api_key=False).
    """
    expected = {"data": "weather"}
    provider = FakePublicAPIProvider([expected])

    result, _ = await _run_engine_with_provider(
        make_policy(),
        provider,
        slug="fake_public",
        payload={"latitude": 51.5, "longitude": -0.1},
        api_key=None,  # keyless
    )

    assert result.success is True
    assert result.response == expected
    assert provider._call_count == 1


@pytest.mark.asyncio
async def test_public_api_retryable_failure_triggers_retry():
    """Public API providers must be retried on transient failures (503)."""
    expected = {"data": "jokes"}
    provider = FakePublicAPIProvider([
        _http_error(503),    # attempt 1 — retryable
        expected,            # attempt 2 — success
    ])

    result, _ = await _run_engine_with_provider(
        make_policy(max_retries=2),
        provider,
        slug="fake_public",
        api_key=None,
    )

    assert result.success is True
    assert provider._call_count == 2
    assert result.retry_count == 1


@pytest.mark.asyncio
async def test_public_api_circuit_breaker_trips():
    """
    The circuit breaker must trip for public API providers after
    enough consecutive failures.
    """
    provider = FakePublicAPIProvider([_http_error(503)])

    policy = make_policy(
        circuit_failure_threshold=3,
        max_retries=5,
        fallback_enabled=False,
    )
    result, engine = await _run_engine_with_provider(
        policy, provider, slug="fake_public", api_key=None,
    )

    opened = [e for e in result.events if e.event_type == CIRCUIT_OPENED]
    assert len(opened) >= 1


@pytest.mark.asyncio
async def test_public_api_rate_limit_applies():
    """The gateway rate limiter must apply to public API providers too."""
    expected = {"data": "currency"}
    provider = FakePublicAPIProvider([expected])

    # rate_limit_requests=0 means every request is rejected immediately
    policy = make_policy(rate_limit_requests=0, rate_limit_window_seconds=10.0)
    result, _ = await _run_engine_with_provider(
        policy, provider, slug="fake_public", api_key=None,
    )

    assert result.success is False
    assert result.status_code == 429
    assert result.error_type == "gateway_rate_limit"
    assert provider._call_count == 0  # provider never called


@pytest.mark.asyncio
async def test_public_api_timeout_handling():
    """Public API provider timeout is handled by the resilience engine."""
    async def slow_call():
        await asyncio.sleep(10)  # Much longer than the test timeout
        return {"data": "never"}

    provider = FakePublicAPIProvider([slow_call])

    result, _ = await _run_engine_with_provider(
        make_policy(
            request_timeout_seconds=0.05,  # very short timeout
            max_retries=0,
            fallback_enabled=False,
        ),
        provider,
        slug="fake_public",
        api_key=None,
    )

    assert result.success is False


@pytest.mark.asyncio
async def test_llm_provider_still_skipped_without_key():
    """LLM providers (requires_api_key=True) must still be skipped if no key."""
    provider = FakeLLMProvider([{"id": "test"}])

    result, _ = await _run_engine_with_provider(
        make_policy(fallback_enabled=False),
        provider,
        slug="fake_llm",
        api_key=None,  # no key for an LLM provider
    )

    assert result.success is False
    assert provider._call_count == 0  # must not have been called


@pytest.mark.asyncio
async def test_no_cross_category_fallback():
    """
    Without a configured fallback chain, a public API provider that fails
    must NOT fall back to a different provider.  This verifies no nonsensical
    weather → jokes fallback happens.
    """
    weather_provider = FakePublicAPIProvider([_http_error(503)])
    joke_provider = FakePublicAPIProvider([{"data": "joke"}])

    engine = ResilienceEngine(make_policy(
        max_retries=0,
        fallback_enabled=True,
        fallback_configs={},  # no chain configured
    ))

    providers = {
        "weather": weather_provider,
        "jokes": joke_provider,
    }

    with patch("app.resilience.engine.get_provider") as mock_get:
        def _get(s):
            if s not in providers:
                raise KeyError(s)
            return providers[s]
        mock_get.side_effect = _get

        result = await engine.execute(
            request_id="req_test",
            provider_slug="weather",
            payload={},
            api_key_getter=lambda s: None,
        )

    assert result.success is False
    # The joke provider must never have been called
    assert joke_provider._call_count == 0


# ══════════════════════════════════════════════════════════════════════════════
# I. Config — security
# ══════════════════════════════════════════════════════════════════════════════

def test_groq_key_never_exposed_for_other_providers():
    """Groq API key must not be returned for other provider slugs."""
    s = Settings(GROQ_API_KEY="gsk_secret")
    assert s.get_provider_api_key("openai") != "gsk_secret"
    assert s.get_provider_api_key("gemini") != "gsk_secret"
    assert s.get_provider_api_key("GROQ") is None   # case-sensitive


def test_public_api_providers_always_return_none_for_key():
    """Public API providers must return None from get_provider_api_key."""
    s = Settings()
    for slug in ("open_meteo", "jokeapi", "frankfurter", "trivia"):
        assert s.get_provider_api_key(slug) is None, f"{slug} should return None"


def test_settings_unknown_provider_returns_none():
    """Settings must not crash on unknown provider slugs — returns None."""
    s = Settings()
    assert s.get_provider_api_key("totally_unknown_provider") is None
