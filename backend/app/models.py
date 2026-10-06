"""
Pydantic models for the SphinxGate API.

Phase 2.5 additions:
  - PublicAPIRequest  — request model for non-LLM provider calls.
  - PublicAPIResponse — normalized response for weather/joke/currency/trivia.

Existing LLM models are unchanged so the frontend Playground keeps working.
"""

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, list[dict[str, Any]]]
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stream: Optional[bool] = False
    stop: Optional[Union[str, list[str]]] = None
    user: Optional[str] = None
    # Any extra fields the client sends are passed through to the provider.
    model_config = {"extra": "allow"}


# ── Response models ───────────────────────────────────────────────────────────

class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class MessageResponse(BaseModel):
    role: str
    content: str


class Choice(BaseModel):
    index: int
    message: MessageResponse
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Optional[UsageInfo] = None


# ── Gateway metadata ─────────────────────────────────────────────────────────
# Returned in response headers so the frontend can display request lifecycle info.

class GatewayMeta(BaseModel):
    """
    Metadata the gateway attaches to every response as HTTP headers.
    These fields are consumed by the Playground's Timeline and meta-bar.
    """
    request_id: str       # X-Request-ID
    provider: str         # X-Provider
    latency_ms: int       # X-Latency-Ms
    status_code: int      # reflected in X-Status
    tokens_used: int      # X-Tokens-Used
    retry_count: int = 0  # X-Retry-Count  (always 0 in Phase 1, field exists for frontend)
    circuit_state: str = "closed"  # X-Circuit-State (always closed in Phase 1)


# ── Error response ────────────────────────────────────────────────────────────

class GatewayError(BaseModel):
    error: dict[str, Any]


# ── Public API request / response ─────────────────────────────────────────────
# Used by the POST /api/v1/query endpoint for non-LLM providers.

class PublicAPIRequest(BaseModel):
    """
    Generic request for public (key-free) API providers.

    The 'params' dict is forwarded verbatim to the adapter — each provider
    documents its own supported keys in its adapter module.
    """
    provider: str                        # e.g. "open_meteo", "jokeapi"
    params: dict[str, Any] = {}         # provider-specific query parameters
    model_config = {"extra": "ignore"}


class PublicAPIResponse(BaseModel):
    """
    Normalized SphinxGate response for public API providers.

    This is the shape the /api/v1/query endpoint returns.
    Consumers don't need to understand the upstream API's exact shape.
    """
    provider: str                        # slug of the provider that served the response
    display_name: str                    # human-readable provider name
    category: str                        # "public_api"
    data: dict[str, Any]                 # the normalized upstream payload
    request_id: str
    latency_ms: int
    circuit_state: str = "closed"
    retry_count: int = 0
    fallback_used: bool = False
