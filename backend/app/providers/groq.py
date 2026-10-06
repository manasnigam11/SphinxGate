"""
Groq provider adapter — Phase 2.5.

Forwards chat completion requests to the Groq API
(api.groq.com/openai/v1/chat/completions).

Groq's API is OpenAI-compatible, so the request format requires no translation.
The response is already OpenAI-shaped, so we return it directly.

Security:
  - The API key is passed via the Authorization: Bearer header.
  - It is never included in the URL, query parameters, or logs.
  - The adapter never accepts keys from client requests.

Model naming:
  Common Groq model identifiers (as of 2025):
    llama-3.3-70b-versatile   (default — strong open-weight model)
    llama-3.1-8b-instant      (fast, lower latency)
    llama-3.2-90b-text-preview
    mixtral-8x7b-32768
    gemma2-9b-it

  OpenAI model names are mapped to sensible Groq equivalents so the
  Playground works without manual changes.

API reference:
  https://console.groq.com/docs/openai
"""

from typing import Any

import httpx

from app.providers.base import BaseLLMProvider


GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Map common OpenAI model names to Groq equivalents.
_OPENAI_TO_GROQ_MODEL: dict[str, str] = {
    "gpt-4o":            "llama-3.3-70b-versatile",
    "gpt-4o-mini":       "llama-3.1-8b-instant",
    "gpt-4-turbo":       "llama-3.3-70b-versatile",
    "gpt-4":             "llama-3.3-70b-versatile",
    "gpt-3.5-turbo":     "llama-3.1-8b-instant",
    "gpt-3.5-turbo-16k": "llama-3.1-8b-instant",
}

_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Groq-native model prefixes — pass these through unchanged.
_GROQ_NATIVE_PREFIXES = ("llama", "mixtral", "gemma", "whisper", "qwen")


def _resolve_model(requested: str) -> str:
    """
    Resolve the model name to a valid Groq model identifier.

    If the client passed an OpenAI model name, map it.
    If it already looks like a Groq-native model name, pass it through.
    """
    if requested in _OPENAI_TO_GROQ_MODEL:
        return _OPENAI_TO_GROQ_MODEL[requested]
    if any(requested.lower().startswith(pfx) for pfx in _GROQ_NATIVE_PREFIXES):
        return requested
    return _DEFAULT_GROQ_MODEL


class GroqProvider(BaseLLMProvider):
    """
    Provider adapter for Groq.

    Groq's API is OpenAI-compatible, which means:
    - The request body passes through directly (with model name remapping).
    - The response body is already in OpenAI chat.completion format.
    - No request/response translation is needed.

    The ResilienceEngine handles all timeout, retry, circuit breaker, and
    rate limiting concerns.  This class only performs HTTP communication
    and model-name remapping.
    """

    slug = "groq"
    display_name = "Groq"

    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        POST the payload to Groq's /v1/chat/completions and return the JSON.

        The api_key is passed via Authorization: Bearer — never in the URL
        or query parameters to prevent accidental logging.
        """
        requested_model = payload.get("model", _DEFAULT_GROQ_MODEL)
        groq_model = _resolve_model(requested_model)

        # Replace the model in the payload with the resolved Groq model name.
        groq_payload = {**payload, "model": groq_model}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Socket-level backstop timeout (generous; engine policy takes priority).
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=headers,
                json=groq_payload,
            )
            # Raise for 4xx/5xx so the ResilienceEngine classifier handles it.
            response.raise_for_status()
            return response.json()

    async def health_check(self, api_key: str | None) -> bool | None:
        if not api_key:
            return None
        
        headers = {"Authorization": f"Bearer {api_key}"}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{GROQ_BASE_URL}/models", headers=headers)
            response.raise_for_status()
            return True

