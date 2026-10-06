"""
Local LLM provider adapter.

Forwards requests to a local OpenAI-compatible model server (e.g., Ollama).
Supports configurable timeouts and custom models.
"""

from typing import Any
import httpx

from app.providers.base import BaseLLMProvider
from app.config import get_settings


class LocalLLMProvider(BaseLLMProvider):
    slug = "local"
    display_name = "Local LLM"
    # Local models do not require a cloud API key.
    # The resilience engine will pass api_key=None.
    requires_api_key = False

    def __init__(self):
        settings = get_settings()
        self.timeout_override = float(settings.local_llm_timeout)

    async def chat_completion(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        """
        POST the payload to the local model server.
        """
        settings = get_settings()

        # Copy payload so we don't mutate the caller's dict
        req_payload = payload.copy()
        
        # Override the model if configured
        if settings.local_llm_model:
            req_payload["model"] = settings.local_llm_model
        # If not explicitly configured, we fall back to the default LLM model name
        # passed in by the frontend, which the local server may or may not support.

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Timeout is handled by ResilienceEngine using self.timeout_override
        # We just add a generous safety backstop.
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.local_llm_base_url}/chat/completions",
                headers=headers,
                json=req_payload,
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self, api_key: str | None) -> bool | None:
        """
        Active health check: Verify if the local model server is reachable.
        """
        settings = get_settings()
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Most OpenAI-compatible servers (like Ollama) expose /models
            response = await client.get(
                f"{settings.local_llm_base_url}/models",
                headers=headers
            )
            response.raise_for_status()
            return True
