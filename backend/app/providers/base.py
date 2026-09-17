"""
Abstract provider interface.

Every upstream AI provider must implement this base class.
The gateway router works entirely against this interface — it never knows
which concrete provider it is talking to.

To add a new provider in a later phase:
  1. Create a new file in app/providers/ (e.g. anthropic.py)
  2. Subclass BaseProvider
  3. Register it in app/providers/registry.py
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """
    Minimal interface that every provider adapter must implement.

    Attributes
    ----------
    slug : str
        Short identifier used in routing and response headers (e.g. "openai").
    display_name : str
        Human-readable name shown in the frontend (e.g. "OpenAI").
    """

    slug: str
    display_name: str

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        Forward a chat completion request to the upstream provider.

        Parameters
        ----------
        payload:
            The raw request body (already validated by Pydantic).
        api_key:
            The provider API key (retrieved from config, never from the client).

        Returns
        -------
        dict
            The raw JSON response from the upstream provider.
            The gateway router normalises this into a ChatCompletionResponse.

        Raises
        ------
        httpx.HTTPStatusError
            If the upstream provider returns a non-2xx response.
        httpx.TimeoutException
            If the upstream provider does not respond in time.
        """
        ...
