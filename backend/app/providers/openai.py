"""
OpenAI provider adapter.

Forwards requests to the OpenAI Chat Completions API.
The request and response format is already OpenAI-compatible, so this adapter
is mostly a thin HTTP wrapper — it passes the payload through and returns the
raw JSON response.

Phase 2 change: the timeout is no longer set inside this adapter.
It is controlled by the ResilienceEngine, which wraps the call in
asyncio.wait_for() using the configured request_timeout_seconds from the
resilience policy.  Setting a timeout here as well would create a confusing
double-timeout; the engine-level timeout takes priority.

Any model accessible through api.openai.com/v1 works here (gpt-4o, gpt-4,
gpt-3.5-turbo, etc.).
"""

from typing import Any

import httpx

from app.providers.base import BaseLLMProvider


OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(BaseLLMProvider):
    slug = "openai"
    display_name = "OpenAI"

    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        POST the payload to OpenAI's /v1/chat/completions and return the JSON.

        The timeout is intentionally omitted here — the ResilienceEngine wraps
        this coroutine in asyncio.wait_for() with the policy timeout.
        If you need a hard socket-level timeout as a safety net, set a generous
        value (e.g. 120s) that is larger than the policy timeout.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Use a generous socket-level timeout as a safety backstop only.
        # The primary timeout enforcement is done by the ResilienceEngine.
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            # Raise immediately on HTTP 4xx/5xx so the resilience engine can
            # classify and handle the error.
            response.raise_for_status()
            return response.json()

    async def health_check(self, api_key: str | None) -> bool | None:
        if not api_key:
            return None
        
        headers = {"Authorization": f"Bearer {api_key}"}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OPENAI_BASE_URL}/models", headers=headers)
            response.raise_for_status()
            return True

