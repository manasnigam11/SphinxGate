"""
Provider registry — Phase 2.5.

Maps provider slugs to their adapter instances.
The gateway router calls get_provider(slug) and gets back a BaseProvider.

Phase 2.5 additions:
  - GroqProvider           (LLM — requires GROQ_API_KEY)
  - OpenMeteoProvider      (Public API — no key)
  - JokeAPIProvider        (Public API — no key)
  - FrankfurterProvider    (Public API — no key)
  - TriviaProvider         (Public API — no key)

To add a new provider:
  1. Implement app/providers/<name>.py
  2. Import and add to REGISTRY below
"""

from app.providers.base import BaseProvider, ProviderCategory
from app.providers.frankfurter import FrankfurterProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.jokeapi import JokeAPIProvider
from app.providers.open_meteo import OpenMeteoProvider
from app.providers.openai import OpenAIProvider
from app.providers.trivia import TriviaProvider
from app.providers.local_llm import LocalLLMProvider
from app.config import get_settings

# Add new providers to this dict.
# Key = slug used in X-Provider header, DEFAULT_PROVIDER env var, and
#       the PublicAPIRequest.provider field.
REGISTRY: dict[str, BaseProvider] = {
    # ── LLM providers ───────────────────────────────────────────────────────
    "openai":   OpenAIProvider(),
    "gemini":   GeminiProvider(),
    "groq":     GroqProvider(),
    # ── Public API providers ─────────────────────────────────────────────────
    "open_meteo":   OpenMeteoProvider(),
    "jokeapi":      JokeAPIProvider(),
    "frankfurter":  FrankfurterProvider(),
    "trivia":       TriviaProvider(),
}

if get_settings().local_llm_enabled:
    REGISTRY["local"] = LocalLLMProvider()

def get_provider(slug: str) -> BaseProvider:
    """
    Return the provider adapter for a given slug.

    When fault injection is enabled (FAULT_INJECTION_ENABLED=true, honouring
    the production guard) the adapter is wrapped in FaultAwareProvider so an
    injected fault is raised from inside the real provider call and handled by
    the unmodified ResilienceEngine (timeout/retry/circuit/fallback).  The
    check happens on every call, so enabling/disabling needs no restart and no
    module patching.

    Raises
    ------
    KeyError
        If the slug does not match any registered provider.
        The gateway router turns this into a 400 response.
    """
    provider = REGISTRY.get(slug)
    if provider is None:
        raise KeyError(f"Unknown provider: '{slug}'. Available: {list(REGISTRY)}")

    # Lazy import: the fault-injection package imports provider base classes.
    from app.fault_injection.resolver import wrap_if_fault_injection_enabled
    return wrap_if_fault_injection_enabled(provider)


def list_providers() -> list[str]:
    """Return all registered provider slugs."""
    return list(REGISTRY.keys())


def list_providers_by_category(category: ProviderCategory) -> list[str]:
    """Return provider slugs filtered by category."""
    return [slug for slug, p in REGISTRY.items() if p.category == category]


# Example request params per public API provider.  Served through /providers so
# the frontend Playground never hardcodes provider-specific defaults.
_EXAMPLE_PARAMS: dict[str, dict] = {
    "open_meteo":  {"latitude": 51.5074, "longitude": -0.1278},
    "jokeapi":     {"category": "Programming", "safe_mode": True},
    "frankfurter": {"base": "USD", "to": "EUR,GBP,JPY"},
    "trivia":      {"amount": 3, "difficulty": "easy", "type": "multiple"},
}

# Model name the gateway accepts for every LLM provider (each adapter maps
# OpenAI-style names onto its own native models).
DEFAULT_LLM_MODEL = "gpt-4o-mini"


def get_provider_info() -> list[dict]:
    """
    Return metadata about every registered provider.
    Used by the /api/v1/providers endpoint.
    """
    info = []
    for slug, p in REGISTRY.items():
        entry = {
            "slug":             slug,
            "display_name":     p.display_name,
            "category":         p.category.value,
            "requires_api_key": p.requires_api_key,
        }
        if p.category == ProviderCategory.PUBLIC_API:
            entry["example_params"] = _EXAMPLE_PARAMS.get(slug, {})
        else:
            entry["default_model"] = DEFAULT_LLM_MODEL
        info.append(entry)
    return info
