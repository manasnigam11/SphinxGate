"""
Google Gemini provider adapter.

Forwards chat completion requests to the Google Gemini API
(generativelanguage.googleapis.com).

Gemini uses a different request/response format from OpenAI, so this adapter
translates in both directions:

  Incoming (OpenAI-compatible format from the gateway)
    │
    ▼
  translate_to_gemini_request()
    │
    ▼
  POST /v1beta/models/{model}:generateContent
    │
    ▼
  translate_to_openai_response()
    │
    ▼
  OpenAI-compatible response returned to the gateway router

The resilience layer (timeout, retry, circuit breaker, rate limiting) is
applied by the ResilienceEngine — NOT inside this adapter.  This adapter
is intentionally a thin HTTP + translation layer only.

Model naming:
  When the client sends X-Provider: gemini and specifies a model, SphinxGate
  passes that model name through.  Supported Gemini model names:
    gemini-2.0-flash      (recommended default — fast, cheap)
    gemini-1.5-pro
    gemini-1.5-flash
    gemini-1.0-pro

  If the client sends an OpenAI model name (e.g. "gpt-4o"), we map it to a
  sensible Gemini default so the Playground still works without manual changes.

API reference:
  https://ai.google.dev/api/generate-content
"""

from typing import Any

import httpx

from app.providers.base import BaseLLMProvider


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Maps common OpenAI model names to their closest Gemini equivalents.
# This lets the Playground work without requiring the user to change the model
# field when switching providers.
_OPENAI_TO_GEMINI_MODEL: dict[str, str] = {
    "gpt-4o":               "gemini-2.5-flash",
    "gpt-4o-mini":          "gemini-2.5-flash",
    "gpt-4-turbo":          "gemini-1.5-pro",
    "gpt-4":                "gemini-1.5-pro",
    "gpt-3.5-turbo":        "gemini-1.5-flash",
    "gpt-3.5-turbo-16k":    "gemini-1.5-flash",
}

# Default model when no mapping exists and the client hasn't specified a native one.
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _resolve_model(requested: str) -> str:
    """
    Resolve the model name to a valid Gemini model identifier.

    If the client passed an OpenAI model name, map it.
    If it already looks like a Gemini model name, pass it through.
    """
    if requested in _OPENAI_TO_GEMINI_MODEL:
        return _OPENAI_TO_GEMINI_MODEL[requested]
    # Accept any string that starts with "gemini" as a native Gemini model.
    if requested.startswith("gemini"):
        return requested
    # Unknown model name — fall back to the default.
    return _DEFAULT_GEMINI_MODEL


def _translate_to_gemini_request(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert an OpenAI-compatible chat completion payload into a Gemini
    generateContent request body.

    OpenAI format:
      {
        "model": "gpt-4o",
        "messages": [
          {"role": "system", "content": "You are helpful."},
          {"role": "user",   "content": "Hello"}
        ],
        "temperature": 0.7,
        "max_tokens": 512
      }

    Gemini format:
      {
        "contents": [
          {"role": "user", "parts": [{"text": "You are helpful.\n\nHello"}]}
        ],
        "generationConfig": {
          "temperature": 0.7,
          "maxOutputTokens": 512
        }
      }

    Key differences handled here:
      - "system" role → prepended to first user message (Gemini has no system role)
      - "assistant" → "model" (Gemini's role name)
      - message content string → parts list
      - max_tokens → maxOutputTokens
    """
    messages: list[dict] = payload.get("messages", [])

    # Collect any system messages and prepend their text to the first user turn.
    system_text_parts: list[str] = []
    non_system_messages: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_text_parts.append(content)
            elif isinstance(content, list):
                # Content blocks — extract text parts only.
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_text_parts.append(block.get("text", ""))
        else:
            non_system_messages.append(msg)

    system_prefix = "\n\n".join(system_text_parts)

    contents: list[dict] = []
    for i, msg in enumerate(non_system_messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Map OpenAI roles to Gemini roles.
        gemini_role = "model" if role == "assistant" else "user"

        # Flatten content to a single text string.
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            text = "\n".join(text_parts)
        else:
            text = str(content)

        # Prepend system instruction to the very first user message only.
        if i == 0 and system_prefix and gemini_role == "user":
            text = f"{system_prefix}\n\n{text}" if text else system_prefix

        contents.append({
            "role": gemini_role,
            "parts": [{"text": text}],
        })

    # Build generationConfig from supported OpenAI parameters.
    generation_config: dict[str, Any] = {}
    if "temperature" in payload and payload["temperature"] is not None:
        generation_config["temperature"] = payload["temperature"]
    if "max_tokens" in payload and payload["max_tokens"] is not None:
        generation_config["maxOutputTokens"] = payload["max_tokens"]
    if "top_p" in payload and payload["top_p"] is not None:
        generation_config["topP"] = payload["top_p"]
    if "stop" in payload and payload["stop"] is not None:
        stop = payload["stop"]
        generation_config["stopSequences"] = [stop] if isinstance(stop, str) else stop

    gemini_body: dict[str, Any] = {"contents": contents}
    if generation_config:
        gemini_body["generationConfig"] = generation_config

    return gemini_body


def _translate_to_openai_response(
    gemini_response: dict[str, Any],
    model: str,
    request_id: str,
) -> dict[str, Any]:
    """
    Convert a Gemini generateContent response into an OpenAI-compatible
    chat completion response so the gateway router and frontend Playground
    can process it without any changes.

    Gemini response shape (simplified):
      {
        "candidates": [{
          "content": {"parts": [{"text": "Hello!"}], "role": "model"},
          "finishReason": "STOP"
        }],
        "usageMetadata": {
          "promptTokenCount": 10,
          "candidatesTokenCount": 5,
          "totalTokenCount": 15
        }
      }
    """
    import time

    candidates = gemini_response.get("candidates", [])
    choices = []

    for i, candidate in enumerate(candidates):
        content_block = candidate.get("content", {})
        parts = content_block.get("parts", [])
        text = " ".join(p.get("text", "") for p in parts if "text" in p)

        finish_reason_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "stop",
        }
        raw_finish = candidate.get("finishReason", "STOP")
        finish_reason = finish_reason_map.get(raw_finish, "stop")

        choices.append({
            "index": i,
            "message": {"role": "assistant", "content": text},
            "finish_reason": finish_reason,
        })

    usage_meta = gemini_response.get("usageMetadata", {})
    usage = {
        "prompt_tokens": usage_meta.get("promptTokenCount", 0),
        "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
        "total_tokens": usage_meta.get("totalTokenCount", 0),
    }

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": usage,
    }


class GeminiProvider(BaseLLMProvider):
    """
    Provider adapter for Google Gemini.

    Translates between the OpenAI-compatible request/response format used
    by the SphinxGate gateway and the Gemini generateContent API.

    The ResilienceEngine handles all timeout, retry, circuit breaker, and
    rate limiting concerns.  This class only performs HTTP communication
    and format translation.
    """

    slug = "gemini"
    display_name = "Google Gemini"

    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        Translate the request, call the Gemini API, translate the response.

        The api_key is passed securely via the 'x-goog-api-key' HTTP header.
        It is never included in response bodies or URL parameters to prevent logging leaks.
        """
        requested_model = payload.get("model", _DEFAULT_GEMINI_MODEL)
        gemini_model = _resolve_model(requested_model)

        url = f"{GEMINI_BASE_URL}/{gemini_model}:generateContent"
        gemini_body = _translate_to_gemini_request(payload)

        # Generate a stable request ID for the OpenAI-compatible response.
        import uuid
        response_id = f"chatcmpl-gemini-{uuid.uuid4().hex[:12]}"

        # Socket-level backstop timeout (generous, engine policy takes priority).
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                json=gemini_body,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key
                },
            )
            # Raise for 4xx/5xx so the ResilienceEngine classifier handles it.
            response.raise_for_status()
            gemini_data = response.json()

        return _translate_to_openai_response(gemini_data, gemini_model, response_id)

    async def health_check(self, api_key: str | None) -> bool | None:
        if not api_key:
            return None
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            response = await client.get(url, headers={"x-goog-api-key": api_key})
            response.raise_for_status()
            return True