"""
OpenAI provider adapter.

Forwards requests to the OpenAI Chat Completions API.
The request and response format is already OpenAI-compatible, so this adapter
is mostly a thin HTTP wrapper — it passes the payload through and returns the
raw JSON response for the gateway router to normalise.

Any model accessible through api.openai.com/v1 works here (gpt-4o, gpt-4,
gpt-3.5-turbo, etc.).
"""

from typing import Any

import httpx

from app.providers.base import BaseProvider


OPENAI_BASE_URL = "https://api.openai.com/v1"

# How long to wait for OpenAI before giving up.
# Chosen conservatively — long enough for large context windows.
REQUEST_TIMEOUT_SECONDS = 120.0


class OpenAIProvider(BaseProvider):
    slug = "openai"
    display_name = "OpenAI"

    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        POST the payload to OpenAI's /v1/chat/completions and return the JSON.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            # Raise immediately on HTTP 4xx/5xx so the gateway router can
            # translate these into clean error responses for the frontend.
            response.raise_for_status()
            return response.json()
