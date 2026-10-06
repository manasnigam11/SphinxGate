"""
Local LLM Provider Tests.

Covers:
  1. Provider registration when enabled/disabled
  2. Adapter success response parsing
  3. Model name override
  4. Health check
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.providers.local_llm import LocalLLMProvider
from app.providers.base import ProviderCategory
from app.config import Settings


# ══════════════════════════════════════════════════════════════════════════════
# 1. Configuration & Registration
# ══════════════════════════════════════════════════════════════════════════════

def test_local_provider_attributes():
    with patch("app.providers.local_llm.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(LOCAL_LLM_ENABLED=True, LOCAL_LLM_TIMEOUT=45)
        provider = LocalLLMProvider()
        
        assert provider.slug == "local"
        assert provider.category == ProviderCategory.LLM
        assert not provider.requires_api_key
        assert provider.timeout_override == 45.0


def test_registry_includes_local_when_enabled():
    with patch("app.config.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(LOCAL_LLM_ENABLED=True)
        # Import inside the mocked context
        import importlib
        import app.providers.registry
        importlib.reload(app.providers.registry)
        
        from app.providers.registry import REGISTRY
        assert "local" in REGISTRY


def test_registry_excludes_local_when_disabled():
    with patch("app.config.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(LOCAL_LLM_ENABLED=False)
        
        import importlib
        import app.providers.registry
        importlib.reload(app.providers.registry)
        
        from app.providers.registry import REGISTRY
        assert "local" not in REGISTRY


# ══════════════════════════════════════════════════════════════════════════════
# 2. HTTP Adapter logic
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_local_llm_adapter_success():
    fake_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"message": {"content": "Local model says hello"}}],
    }

    with patch("app.providers.local_llm.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(
            LOCAL_LLM_ENABLED=True, 
            LOCAL_LLM_BASE_URL="http://localhost:11434/v1"
        )
        provider = LocalLLMProvider()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = fake_response

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client_cls.return_value = mock_client

            result = await provider.chat_completion(
                payload={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                api_key=None,
            )

    assert result["choices"][0]["message"]["content"] == "Local model says hello"
    # Ensure URL is correct
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "http://localhost:11434/v1/chat/completions"


@pytest.mark.asyncio
async def test_local_llm_model_override():
    fake_response = {"choices": []}

    with patch("app.providers.local_llm.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(
            LOCAL_LLM_ENABLED=True, 
            LOCAL_LLM_MODEL="llama3-local"
        )
        provider = LocalLLMProvider()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = fake_response

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client_cls.return_value = mock_client

            await provider.chat_completion(
                payload={"model": "gpt-4o", "messages": []},
                api_key=None,
            )

    args, kwargs = mock_client.post.call_args
    # The payload model should be overridden
    assert kwargs["json"]["model"] == "llama3-local"


@pytest.mark.asyncio
async def test_local_llm_health_check_success():
    with patch("app.providers.local_llm.get_settings") as mock_get_settings:
        mock_get_settings.return_value = Settings(LOCAL_LLM_ENABLED=True)
        provider = LocalLLMProvider()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            mock_client_cls.return_value = mock_client

            healthy = await provider.health_check(api_key=None)

    assert healthy is True
    mock_client.get.assert_called_once()
