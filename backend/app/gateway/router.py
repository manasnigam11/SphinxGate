"""
Gateway router — core of Phase 1.

This module owns the /api/v1/chat/completions endpoint.

Request lifecycle (Phase 1):
  1. Validate the incoming request (Pydantic).
  2. Decide which provider to use (X-Provider header or DEFAULT_PROVIDER).
  3. Retrieve the provider's API key from config (never from the client).
  4. Forward the request to the provider adapter.
  5. Measure end-to-end latency.
  6. Return the provider's response with gateway metadata headers attached.

No resilience logic (retry, circuit breaker, fallback) is implemented here.
Those belong to Phase 2.
"""

import logging
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import ChatCompletionRequest
from app.providers.registry import get_provider

logger = logging.getLogger("sphinxgate.gateway")

router = APIRouter(prefix="/api/v1", tags=["gateway"])


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_environment: str | None = Header(default=None, alias="X-Environment"),
) -> Response:
    """
    Proxy a chat completion request through SphinxGate to an upstream provider.

    The client may optionally specify a provider via the X-Provider header.
    If not specified, the DEFAULT_PROVIDER environment variable is used.

    Response headers added by the gateway:
      X-Request-ID     — unique ID for this gateway request
      X-Provider       — which provider was used
      X-Latency-Ms     — total end-to-end latency in milliseconds
      X-Retry-Count    — always 0 in Phase 1
      X-Circuit-State  — always "closed" in Phase 1
      X-Tokens-Used    — total tokens from the provider's usage field
    """
    settings = get_settings()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # ── 1. Select provider ────────────────────────────────────────────────────
    provider_slug = (x_provider or settings.default_provider).lower().strip()

    try:
        provider = get_provider(provider_slug)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 2. Get API key from config (never from client) ────────────────────────
    api_key = settings.get_provider_api_key(provider_slug)
    if not api_key:
        logger.error(
            "No API key configured for provider '%s'. "
            "Set %s_API_KEY in your .env file.",
            provider_slug,
            provider_slug.upper(),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{provider_slug}' is not configured on this gateway. "
                   f"Add {provider_slug.upper()}_API_KEY to the server's .env file.",
        )

    # ── 3. Forward to provider ────────────────────────────────────────────────
    payload = body.model_dump(exclude_none=True)

    start_time = time.perf_counter()
    try:
        result: dict[str, Any] = await provider.chat_completion(payload, api_key)
    except httpx.HTTPStatusError as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(
            "[%s] provider=%s status=%s latency=%dms",
            request_id, provider_slug, exc.response.status_code, elapsed_ms,
        )
        # Surface the provider's error body to the client so the Playground
        # can show a meaningful error message.
        try:
            error_body = exc.response.json()
        except Exception:
            error_body = {"error": {"message": exc.response.text, "type": "provider_error"}}

        return JSONResponse(
            status_code=exc.response.status_code,
            content=error_body,
            headers=_build_headers(
                request_id=request_id,
                provider=provider.display_name,
                latency_ms=elapsed_ms,
                tokens_used=0,
            ),
        )
    except httpx.TimeoutException:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning(
            "[%s] provider=%s timeout latency=%dms",
            request_id, provider_slug, elapsed_ms,
        )
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "Provider did not respond in time.", "type": "timeout"}},
            headers=_build_headers(
                request_id=request_id,
                provider=provider.display_name,
                latency_ms=elapsed_ms,
                tokens_used=0,
            ),
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.exception("[%s] Unexpected error from provider '%s'", request_id, provider_slug)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": "Unexpected gateway error.", "type": "gateway_error"}},
            headers=_build_headers(
                request_id=request_id,
                provider=provider.display_name,
                latency_ms=elapsed_ms,
                tokens_used=0,
            ),
        )

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # ── 4. Extract token usage ────────────────────────────────────────────────
    usage = result.get("usage") or {}
    tokens_used = usage.get("total_tokens", 0)

    logger.info(
        "[%s] provider=%s model=%s status=200 latency=%dms tokens=%d env=%s",
        request_id,
        provider_slug,
        body.model,
        elapsed_ms,
        tokens_used,
        x_environment or "unknown",
    )

    # ── 5. Return response with gateway metadata headers ─────────────────────
    return JSONResponse(
        content=result,
        headers=_build_headers(
            request_id=request_id,
            provider=provider.display_name,
            latency_ms=elapsed_ms,
            tokens_used=tokens_used,
        ),
    )


def _build_headers(
    *,
    request_id: str,
    provider: str,
    latency_ms: int,
    tokens_used: int,
) -> dict[str, str]:
    """
    Build the gateway metadata headers that the frontend Playground reads.
    All values are strings because HTTP headers must be strings.
    """
    return {
        "X-Request-ID": request_id,
        "X-Provider": provider,
        "X-Latency-Ms": str(latency_ms),
        "X-Retry-Count": "0",         # Phase 1: no retry engine
        "X-Circuit-State": "closed",  # Phase 1: no circuit breaker
        "X-Tokens-Used": str(tokens_used),
        # Expose headers to the browser (required for JS to read custom headers)
        "Access-Control-Expose-Headers": (
            "X-Request-ID, X-Provider, X-Latency-Ms, "
            "X-Retry-Count, X-Circuit-State, X-Tokens-Used"
        ),
    }
