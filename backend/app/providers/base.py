"""
Abstract provider interface — Phase 2.5.

Every provider adapter must implement this base class.
The gateway router works entirely against this interface.

Phase 2.5 changes:
  - Added provider_category to distinguish LLM vs. public-API providers.
  - The single entry point is now call() instead of chat_completion().
  - LLM providers implement call() via chat_completion() for backwards compat.
  - Public API providers implement call() directly.
  - The resilience engine calls call() — it never distinguishes by category.

To add a new provider:
  1. Create a new file in app/providers/  (e.g. groq.py)
  2. Subclass BaseLLMProvider or BasePublicAPIProvider
  3. Register it in app/providers/registry.py
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class InvalidProviderRequest(ValueError):
    """
    Raised by an adapter when the *caller's* request is malformed
    (e.g. missing required parameters).  This is not an upstream failure:
    the engine returns HTTP 400, does not retry, does not fall back, does not
    touch the circuit breaker and does not create an incident.
    """


class ProviderCategory(str, Enum):
    """Top-level provider kind.  Used for routing and fallback decisions."""
    LLM        = "llm"          # Providers that respond to chat/text completion
    PUBLIC_API = "public_api"   # Key-free public REST APIs (weather, jokes, …)


class BaseProvider(ABC):
    """
    Minimal interface every provider adapter must implement.

    Attributes
    ----------
    slug : str
        Short identifier used in routing and response headers (e.g. "openai").
    display_name : str
        Human-readable name shown in the frontend (e.g. "OpenAI").
    category : ProviderCategory
        Whether this is an LLM or a public API.
    requires_api_key : bool
        True for providers that need a secret key; False for public APIs.
    """

    slug: str
    display_name: str
    category: ProviderCategory
    requires_api_key: bool = True
    timeout_override: float | None = None

    @abstractmethod
    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        """
        Execute the provider-specific upstream request.

        Parameters
        ----------
        payload:
            The validated request body dict.  Shape varies by provider:
            - LLM providers expect OpenAI-compatible chat completion fields.
            - Public API providers receive a simple params dict.
        api_key:
            The provider API key retrieved from config, or None for keyless APIs.
            Adapters must NEVER accept keys from the client request.

        Returns
        -------
        dict
            Normalized response.
            - LLM providers return an OpenAI-compatible chat completion dict.
            - Public API providers return a PublicAPIResponse-shaped dict.

        Raises
        ------
        httpx.HTTPStatusError
            If the upstream returns a non-2xx response.
        httpx.TimeoutException
            If the upstream does not respond in time.
        """
        ...

    async def health_check(self, api_key: str | None) -> bool | None:
        """
        Perform a lightweight active health check.
        Return True if healthy, False if unhealthy.
        Return None if active health checking is not supported by this provider.
        """
        return None



class BaseLLMProvider(BaseProvider):
    """
    Convenience base for LLM providers.

    Implements call() by delegating to chat_completion() so existing
    OpenAI and Gemini adapters work without changes.
    """

    category = ProviderCategory.LLM
    requires_api_key = True

    async def call(
        self,
        payload: dict[str, Any],
        api_key: str | None,
    ) -> dict[str, Any]:
        return await self.chat_completion(payload, api_key or "")

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        Forward a chat completion request to the upstream provider.

        The gateway router normalizes the result into a ChatCompletionResponse.
        Timeout is controlled by the ResilienceEngine — do not set it here.
        """
        ...


class BasePublicAPIProvider(BaseProvider):
    """
    Convenience base for key-free public REST API providers.

    Public APIs do not need an API key, so requires_api_key is False.
    The engine will pass api_key=None for these providers.
    """

    category = ProviderCategory.PUBLIC_API
    requires_api_key = False
