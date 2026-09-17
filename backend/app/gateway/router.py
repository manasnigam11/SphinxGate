"""
Gateway router — Phase 2.

Phase 2 changes vs Phase 1:
  - Requests are now routed through the ResilienceEngine, which adds:
      • Gateway-side rate limiting (HTTP 429 if exceeded)
      • Exponential-backoff retry for retryable failures
      • Per-provider circuit breaking (CLOSED / OPEN / HALF-OPEN)
      • Fallback routing when the primary provider is unavailable
      • Configurable timeout per attempt (no more hardcoded constant in each adapter)
  - Response headers now carry real retry_count, circuit_state, and
    X-Fallback-Used values from the engine.
  - A new GET /api/v1/policy endpoint exposes the active resilience policy.
  - A new GET /api/v1/providers/state endpoint exposes per-provider circuit state.

Phase 1 behavior is fully preserved:
  - POST /api/v1/chat/completions still works unchanged from the client's perspective.
  - X-Provider header and DEFAULT_PROVIDER env var still select the primary provider.
  - All Phase 1 gateway metadata headers are still returned.

Request lifecycle (Phase 2):
  1. Validate the incoming request (Pydantic) — unchanged.
  2. Decide which provider was requested (X-Provider or DEFAULT_PROVIDER) — unchanged.
  3. Hand off to the ResilienceEngine, which handles:
       a. Gateway rate limit check
       b. Provider chain selection (primary + fallbacks)
       c. Circuit breaker check per provider
       d. Retry loop with exponential backoff
  4. Return the response with enriched gateway metadata headers.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import ChatCompletionRequest
from app.resilience.engine import ResilienceEngine
from app.resilience.policy import ResiliencePolicy

logger = logging.getLogger("sphinxgate.gateway")

router = APIRouter(prefix="/api/v1", tags=["gateway"])

# ── Resilience engine (singleton — lives for the process lifetime) ─────────────
# Loaded lazily on first request so tests can replace it easily.
_engine: ResilienceEngine | None = None


def get_engine() -> ResilienceEngine:
    """Return the shared ResilienceEngine, creating it on first call."""
    global _engine
    if _engine is None:
        policy = ResiliencePolicy.from_settings()
        _engine = ResilienceEngine(policy)
        logger.info(
            "ResilienceEngine initialised — timeout=%.1fs retries=%d "
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


# ── Chat completions endpoint ─────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_provider: str | None = Header(default=None, alias="X-Provider"),
    x_environment: str | None = Header(default=None, alias="X-Environment"),
) -> Response:
    """
    Proxy a chat completion request through SphinxGate to an upstream provider.

    The resilience engine handles timeout, retry, circuit breaking, and fallback.

    Response headers:
      X-Request-ID      — unique ID for this gateway request
      X-Provider        — which provider actually served the response
      X-Latency-Ms      — total end-to-end latency in milliseconds
      X-Retry-Count     — how many retries were made
      X-Circuit-State   — circuit state of the final provider used
      X-Tokens-Used     — total tokens from the provider's usage field
      X-Fallback-Used   — "true" if a fallback provider was used
    """
    settings = get_settings()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # ── 1. Select primary provider ─────────────────────────────────────────────
    provider_slug = (x_provider or settings.default_provider).lower().strip()

    # Validate provider slug exists before handing to engine (fast fail for typos).
    from app.providers.registry import get_provider as _get_provider
    try:
        _get_provider(provider_slug)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 2. Execute through the resilience engine ───────────────────────────────
    payload = body.model_dump(exclude_none=True)
    engine = get_engine()

    result = await engine.execute(
        request_id=request_id,
        provider_slug=provider_slug,
        payload=payload,
        api_key_getter=settings.get_provider_api_key,
    )

    # ── 3. Log the outcome ─────────────────────────────────────────────────────
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

    # ── 4. Build response headers ──────────────────────────────────────────────
    headers = _build_headers(
        request_id=result.request_id,
        provider=result.provider_display_name,
        latency_ms=result.latency_ms,
        tokens_used=result.tokens_used,
        retry_count=result.retry_count,
        circuit_state=result.circuit_state,
        fallback_used=result.fallback_used,
    )

    # ── 5. Return response ─────────────────────────────────────────────────────
    if result.success:
        return JSONResponse(content=result.response, headers=headers)

    # Structured failure — never fabricate a success response.
    error_content: dict[str, Any]
    if result.error_type == "gateway_rate_limit":
        error_content = {
            "error": {
                "message": result.error_message,
                "type": "gateway_rate_limit",
                "code": "rate_limit_exceeded",
            }
        }
    else:
        error_content = {
            "error": {
                "message": result.error_message,
                "type": result.error_type or "gateway_error",
                "code": result.error_type or "gateway_error",
                "retry_after": None,
            }
        }

    return JSONResponse(
        status_code=result.status_code,
        content=error_content,
        headers=headers,
    )


# ── Resilience policy endpoint ────────────────────────────────────────────────

@router.get("/policy", tags=["resilience"])
async def get_resilience_policy() -> dict:
    """
    Return the active resilience policy.

    The frontend Resilience Policies page can call this to show live settings
    (Phase 3 will add write support).
    """
    engine = get_engine()
    return engine.policy.to_dict()


# ── Provider circuit state endpoint ───────────────────────────────────────────

@router.get("/providers/state", tags=["resilience"])
async def get_provider_states() -> dict:
    """
    Return the current circuit-breaker state for all known providers.

    Phase 3 Circuit Breakers dashboard will poll this endpoint.
    """
    engine = get_engine()
    return {"providers": engine.get_circuit_snapshots()}


# ── Header builder ────────────────────────────────────────────────────────────

def _build_headers(
    *,
    request_id: str,
    provider: str,
    latency_ms: int,
    tokens_used: int,
    retry_count: int = 0,
    circuit_state: str = "closed",
    fallback_used: bool = False,
) -> dict[str, str]:
    """
    Build the gateway metadata headers that the frontend Playground reads.
    All values are strings because HTTP headers must be strings.
    """
    exposed = (
        "X-Request-ID, X-Provider, X-Latency-Ms, "
        "X-Retry-Count, X-Circuit-State, X-Tokens-Used, X-Fallback-Used"
    )
    return {
        "X-Request-ID": request_id,
        "X-Provider": provider,
        "X-Latency-Ms": str(latency_ms),
        "X-Retry-Count": str(retry_count),
        "X-Circuit-State": circuit_state,
        "X-Tokens-Used": str(tokens_used),
        "X-Fallback-Used": "true" if fallback_used else "false",
        "Access-Control-Expose-Headers": exposed,
    }
