"""
Gateway router — Phase 3.

Phase 3 changes vs Phase 2:
  - Requests now go through the SphinxGate Facade (app.facade) instead of
    calling the ResilienceEngine directly.
  - The Facade adds:
      - Cache lookup/store for eligible public API providers
      - Telemetry persistence per request
      - A clean orchestration boundary separating routing from resilience
  - X-Cache-Hit response header added ("true" / "false" / "miss").
  - New GET /api/v1/telemetry/* endpoints (mounted via telemetry_router).
  - Phase 2 endpoints, headers, and behavior are fully preserved.

Phase 1 and Phase 2 behavior is fully preserved:
  - POST /api/v1/chat/completions -- unchanged from the client's perspective.
  - POST /api/v1/query -- unchanged.
  - GET  /api/v1/policy, /providers, /providers/state -- unchanged.
  - All gateway metadata headers are still returned.

Request lifecycle (Phase 3):
  1. Validate the incoming request (Pydantic) -- unchanged.
  2. Decide which provider was requested -- unchanged.
  3. Hand off to the Facade, which:
       a. Validates and resolves the provider.
       b. Checks the cache (public API only).
       c. Calls the ResilienceEngine if cache miss.
       d. Caches successful responses (public API, where policy permits).
       e. Records telemetry.
  4. Return the response with enriched gateway metadata headers.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.facade import SphinxGateFacade, get_facade, _reset_facade
from app.models import ChatCompletionRequest, PublicAPIRequest
from app.providers.base import ProviderCategory
from app.providers.registry import get_provider_info
from app.resilience.engine import ResilienceEngine
from app.resilience.policy import ResiliencePolicy

logger = logging.getLogger("sphinxgate.gateway")

router = APIRouter(prefix="/api/v1", tags=["gateway"])

# Resilience engine (singleton -- lives for the process lifetime)
# Loaded lazily on first request so tests can replace it easily.
_engine: ResilienceEngine | None = None


def get_engine() -> ResilienceEngine:
    """Return the shared ResilienceEngine, creating it on first call."""
    global _engine
    if _engine is None:
        policy = ResiliencePolicy.from_settings()
        _engine = ResilienceEngine(policy)
        logger.info(
            "ResilienceEngine initialised -- timeout=%.1fs retries=%d "
            "cb_threshold=%d cb_window=%.0fs rate_limit=%d/%.1fs fallback=%s",
            policy.request_timeout_seconds,
            policy.max_retries,
            policy.circuit_failure_threshold,
            policy.circuit_recovery_window_seconds,
            policy.rate_limit_requests,
            policy.rate_limit_window_seconds,
            policy.fallback_enabled,
        )
    return _engine


def _reset_engine(engine: ResilienceEngine | None = None) -> None:
    """
    Replace the engine singleton.  Used by tests to inject a custom engine
    (or reset state between test cases).
    """
    global _engine
    _engine = engine
    # Also reset the facade so it picks up the new engine on next call
    _reset_facade(None)


def _get_facade() -> SphinxGateFacade:
    """Return the Facade singleton, initialising it with the engine on first call."""
    return get_facade(engine=get_engine())


# Chat completions endpoint

@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_environment: str | None = Header(default=None, alias="X-Environment"),
) -> Response:
    """
    Proxy a chat completion request through SphinxGate to an upstream provider.

    The Facade coordinates: provider validation, resilience engine, telemetry.

    Response headers:
      X-Request-ID      -- unique ID for this gateway request
      X-Provider        -- which provider actually served the response
      X-Latency-Ms      -- total end-to-end latency in milliseconds
      X-Retry-Count     -- how many retries were made
      X-Circuit-State   -- circuit state of the final provider used
      X-Tokens-Used     -- total tokens from the provider's usage field
      X-Fallback-Used   -- "true" if a fallback provider was used
      X-Cache-Hit       -- always "miss" for LLM requests
    """
    settings = get_settings()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # 1. Select primary provider
    provider_slug = (x_provider or settings.default_provider).lower().strip()

    # Validate provider slug exists before handing to facade (fast fail for typos).
    from app.providers.registry import get_provider as _get_provider
    try:
        _get_provider(provider_slug)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. Execute through the Facade
    payload = body.model_dump(exclude_none=True)
    facade = _get_facade()

    try:
        facade_result = await facade.handle_llm_request(
            request_id=request_id,
            provider_slug=provider_slug,
            payload=payload,
            api_key_getter=settings.get_provider_api_key,
            endpoint="/api/v1/chat/completions",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = facade_result.result

    # 3. Log the outcome
    if result.success:
        logger.info(
            "[%s] provider=%s model=%s status=200 latency=%dms tokens=%d "
            "retries=%d circuit=%s fallback=%s env=%s",
            request_id,
            result.provider_slug,
            body.model,
            result.latency_ms,
            result.tokens_used,
            result.retry_count,
            result.circuit_state,
            result.fallback_used,
            x_environment or "unknown",
        )
    else:
        logger.warning(
            "[%s] provider=%s status=%d error=%s latency=%dms retries=%d",
            request_id,
            result.provider_slug,
            result.status_code,
            result.error_type,
            result.latency_ms,
            result.retry_count,
        )

    # 4. Build response headers
    headers = _build_headers(
        request_id=result.request_id,
        provider=result.provider_display_name,
        latency_ms=result.latency_ms,
        tokens_used=result.tokens_used,
        retry_count=result.retry_count,
        circuit_state=result.circuit_state,
        fallback_used=result.fallback_used,
        cache_hit="miss",
        service_state=facade_result.service_state,
        fault_id=facade_result.fault_id,
    )

    # 5. Return response
    if result.success:
        return JSONResponse(content=result.response, headers=headers)

    # Structured failure -- never fabricate a success response.
    error_content: dict[str, Any]
    if result.error_type == "gateway_rate_limit":
        error_content = {
            "error": {
                "message": result.error_message,
                "type": "gateway_rate_limit",
                "code": "rate_limit_exceeded",
                "service_state": facade_result.service_state,
            }
        }
    else:
        error_content = {
            "error": {
                "message": result.error_message,
                "type": result.error_type or "gateway_error",
                "code": result.error_type or "gateway_error",
                "retry_after": None,
                "service_state": facade_result.service_state,
            }
        }

    return JSONResponse(
        status_code=result.status_code,
        content=error_content,
        headers=headers,
    )


# Resilience policy endpoint

@router.get("/policy", tags=["resilience"])
async def get_resilience_policy() -> dict:
    """
    Return the active resilience policy.

    The frontend Resilience Policies page calls this to show live settings.
    """
    engine = get_engine()
    return engine.policy.to_dict()


# Provider circuit state endpoint

@router.get("/providers/state", tags=["resilience"])
async def get_provider_states() -> dict:
    """
    Return the current circuit-breaker state for all known providers.

    Phase 3 Circuit Breakers dashboard polls this endpoint.  Phase 5: lists
    EVERY registered provider (closed defaults for providers with no traffic
    yet) so the dashboard never silently omits one.
    """
    from app.providers.registry import list_providers
    engine = get_engine()
    return {"providers": engine.get_all_circuit_snapshots(list_providers())}


# Provider metadata endpoint

@router.get("/providers", tags=["providers"])
async def list_providers_endpoint() -> dict:
    """
    Return metadata about every registered provider.

    Response includes slug, display_name, category, requires_api_key, and
    whether the provider is currently configured (has an API key if needed).
    """
    settings = get_settings()
    providers = []
    for info in get_provider_info():
        slug = info["slug"]
        if info["requires_api_key"]:
            configured = bool(settings.get_provider_api_key(slug))
        else:
            configured = True  # public APIs are always "configured"
        providers.append({**info, "configured": configured})
    return {"providers": providers}


# Public API query endpoint

@router.post("/query", tags=["gateway"])
async def public_api_query(
    body: PublicAPIRequest,
    x_environment: str | None = Header(default=None, alias="X-Environment"),
) -> Response:
    """
    Route a request to a public API provider through SphinxGate.

    Phase 3 additions:
      - Eligible providers (open_meteo, frankfurter) are served from cache on hit.
      - X-Cache-Hit header indicates "true" (hit) or "false" (miss).
      - Telemetry is persisted per request.

    All resilience features (timeout, retry, circuit breaker, rate limiting)
    apply on cache misses exactly as they did in Phase 2.
    """
    settings = get_settings()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    provider_slug = body.provider.lower().strip()

    # Validate provider exists and is a public API provider.
    from app.providers.registry import get_provider as _get_provider
    try:
        provider_obj = _get_provider(provider_slug)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if provider_obj.category != ProviderCategory.PUBLIC_API:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider_slug}' is an LLM provider. "
                f"Use POST /api/v1/chat/completions instead."
            ),
        )

    payload = dict(body.params)
    facade = _get_facade()

    try:
        facade_result = await facade.handle_public_api_request(
            request_id=request_id,
            provider_slug=provider_slug,
            payload=payload,
            api_key_getter=settings.get_provider_api_key,
            endpoint="/api/v1/query",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = facade_result.result

    if result.success:
        logger.info(
            "[%s] provider=%s status=200 latency=%dms retries=%d circuit=%s cache=%s env=%s",
            request_id,
            result.provider_slug,
            result.latency_ms,
            result.retry_count,
            result.circuit_state,
            "hit" if facade_result.cache_hit else "miss",
            x_environment or "unknown",
        )
    else:
        logger.warning(
            "[%s] provider=%s status=%d error=%s latency=%dms",
            request_id,
            result.provider_slug,
            result.status_code,
            result.error_type,
            result.latency_ms,
        )

    cache_hit_str = "true" if facade_result.cache_hit else "false"
    headers = _build_headers(
        request_id=result.request_id,
        provider=result.provider_display_name,
        latency_ms=result.latency_ms,
        tokens_used=result.tokens_used,
        retry_count=result.retry_count,
        circuit_state=result.circuit_state,
        fallback_used=result.fallback_used,
        cache_hit=cache_hit_str,
        service_state=facade_result.service_state,
        fault_id=facade_result.fault_id,
    )

    if result.success or facade_result.degraded:
        response_body = {
            "provider":      result.provider_slug,
            "display_name":  result.provider_display_name,
            "category":      ProviderCategory.PUBLIC_API.value,
            "data":          result.response,
            "request_id":    result.request_id,
            "latency_ms":    result.latency_ms,
            "circuit_state": result.circuit_state,
            "retry_count":   result.retry_count,
            "fallback_used": result.fallback_used,
            "cache_hit":     facade_result.cache_hit,
            "cache_age_seconds": facade_result.cache_age_seconds if facade_result.cache_hit else None,
            "service_state": facade_result.service_state,
            "degraded":      facade_result.degraded,
        }
        if facade_result.degraded:
            # Explicit and truthful: this is previously cached real data, NOT a live answer.
            response_body["degraded_reason"] = facade_result.degraded_reason
            response_body["stale_age_seconds"] = round(facade_result.cache_age_seconds, 1)
            response_body["warning"] = (
                "The live provider is unavailable. This response was served from cache "
                f"and is {int(facade_result.cache_age_seconds)}s old."
            )
        return JSONResponse(content=response_body, headers=headers)

    # Structured failure -- never fabricate a response.
    if result.error_type == "gateway_rate_limit":
        error_content: dict[str, Any] = {
            "error": {
                "message": result.error_message,
                "type": "gateway_rate_limit",
                "code": "rate_limit_exceeded",
                "service_state": facade_result.service_state,
            }
        }
    else:
        error_content = {
            "error": {
                "message": result.error_message,
                "type": result.error_type or "gateway_error",
                "code": result.error_type or "gateway_error",
                "service_state": facade_result.service_state,
            }
        }
    return JSONResponse(
        status_code=result.status_code,
        content=error_content,
        headers=headers,
    )


# Header builder

def _build_headers(
    *,
    request_id: str,
    provider: str,
    latency_ms: int,
    tokens_used: int,
    retry_count: int = 0,
    circuit_state: str = "closed",
    fallback_used: bool = False,
    cache_hit: str = "miss",
    service_state: str = "operational",
    fault_id: str | None = None,
) -> dict[str, str]:
    """
    Build the gateway metadata headers that the frontend Playground reads.
    All values are strings because HTTP headers must be strings.
    """
    exposed = (
        "X-Request-ID, X-Provider, X-Latency-Ms, "
        "X-Retry-Count, X-Circuit-State, X-Tokens-Used, X-Fallback-Used, X-Cache-Hit, "
        "X-Service-State, X-Fault-ID"
    )
    headers = {
        "X-Request-ID":    request_id,
        "X-Provider":      provider,
        "X-Latency-Ms":    str(latency_ms),
        "X-Retry-Count":   str(retry_count),
        "X-Circuit-State": circuit_state,
        "X-Tokens-Used":   str(tokens_used),
        "X-Fallback-Used": "true" if fallback_used else "false",
        "X-Cache-Hit":     cache_hit,
        "X-Service-State": service_state,
        "Access-Control-Expose-Headers": exposed,
    }
    if fault_id:
        headers["X-Fault-ID"] = fault_id
    return headers
