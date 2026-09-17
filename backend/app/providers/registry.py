"""
Provider registry.

Maps provider slugs to their adapter instances.
The gateway router calls get_provider(slug) and gets back a BaseProvider.

To add a new provider (e.g. Anthropic):
  1. Implement app/providers/anthropic.py
  2. Import it here and add it to REGISTRY
"""

from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider

# Add new providers to this dict.
# Key = slug used in X-Provider header and DEFAULT_PROVIDER env var.
REGISTRY: dict[str, BaseProvider] = {
    "openai": OpenAIProvider(),
}


def get_provider(slug: str) -> BaseProvider:
    """
    Return the provider adapter for a given slug.

    Raises
    ------
    KeyError
        If the slug does not match any registered provider.
        The gateway router turns this into a 400 response.
    """
    provider = REGISTRY.get(slug)
    if provider is None:
        raise KeyError(f"Unknown provider: '{slug}'. Available: {list(REGISTRY)}")
    return provider


def list_providers() -> list[str]:
    """Return all registered provider slugs."""
    return list(REGISTRY.keys())
