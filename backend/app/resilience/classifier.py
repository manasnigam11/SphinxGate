"""
Failure Classifier — Phase 2.

Inspects exceptions / HTTP status codes and classifies them into a
FailureKind that tells the resilience engine what to do next.

Decision logic:
  - TIMEOUT             → retryable (transient)
  - CONNECTION_ERROR    → retryable (transient)
  - HTTP 429            → NOT retried by the gateway (provider is asking us to back off;
                          gateway rate-limiting and fallback handle this)
  - HTTP 500            → retryable (transient server error)
  - HTTP 502            → retryable (bad gateway, transient)
  - HTTP 503            → retryable (service unavailable, transient)
  - HTTP 504            → retryable (gateway timeout, transient)
  - HTTP 4xx (other)    → NOT retryable (client/auth/config error)
  - HTTP 5xx (other)    → retryable
  - QUOTA_EXHAUSTED     → NOT retryable (would just fail again immediately)
  - PROVIDER_ERROR      → NOT retryable (unknown provider-level error)
  - UNKNOWN             → NOT retryable (safe default)
"""

from enum import Enum
from typing import Optional

import httpx


class FailureKind(str, Enum):
    """Classification of a provider failure."""
    TIMEOUT          = "timeout"
    CONNECTION_ERROR = "connection_error"
    RATE_LIMITED     = "rate_limited"       # Upstream 429
    SERVER_ERROR_500 = "server_error_500"
    BAD_GATEWAY_502  = "bad_gateway_502"
    SERVICE_UNAVAILABLE_503 = "service_unavailable_503"
    GATEWAY_TIMEOUT_504     = "gateway_timeout_504"
    OTHER_5XX        = "other_5xx"
    CLIENT_ERROR_4XX = "client_error_4xx"   # 400, 401, 403, 404, …
    QUOTA_EXHAUSTED  = "quota_exhausted"    # insufficient_quota, credit_balance_exhausted
    PROVIDER_ERROR   = "provider_error"     # Generic provider-side API error
    UNKNOWN          = "unknown"


# Which failure kinds are safe to retry.
_RETRYABLE: frozenset[FailureKind] = frozenset({
    FailureKind.TIMEOUT,
    FailureKind.CONNECTION_ERROR,
    FailureKind.SERVER_ERROR_500,
    FailureKind.BAD_GATEWAY_502,
    FailureKind.SERVICE_UNAVAILABLE_503,
    FailureKind.GATEWAY_TIMEOUT_504,
    FailureKind.OTHER_5XX,
})

# Which failure kinds should count towards circuit-breaker failure threshold.
# We count transient upstream failures, not auth errors or quota exhaustion.
_COUNTS_TOWARD_CIRCUIT: frozenset[FailureKind] = frozenset({
    FailureKind.TIMEOUT,
    FailureKind.CONNECTION_ERROR,
    FailureKind.SERVER_ERROR_500,
    FailureKind.BAD_GATEWAY_502,
    FailureKind.SERVICE_UNAVAILABLE_503,
    FailureKind.GATEWAY_TIMEOUT_504,
    FailureKind.OTHER_5XX,
    FailureKind.RATE_LIMITED,
})


def is_retryable(kind: FailureKind) -> bool:
    """Return True if this failure kind is safe to retry."""
    return kind in _RETRYABLE


def counts_toward_circuit(kind: FailureKind) -> bool:
    """Return True if this failure should increment the circuit-breaker counter."""
    return kind in _COUNTS_TOWARD_CIRCUIT


def _is_quota_error(error_body: Optional[dict]) -> bool:
    """
    Check whether an error body from a provider indicates quota exhaustion.
    Handles OpenAI's error format; extend for other providers in future phases.
    """
    if not error_body:
        return False
    error = error_body.get("error", {})
    if not isinstance(error, dict):
        return False
    error_type = error.get("type", "")
    error_code = error.get("code", "")
    known_quota_types = {
        "insufficient_quota",
        "credit_balance_exhausted",
        "billing_not_active",
    }
    known_quota_codes = {
        "insufficient_quota",
        "credit_balance_exhausted",
    }
    return error_type in known_quota_types or error_code in known_quota_codes


def classify_exception(exc: Exception, error_body: Optional[dict] = None) -> FailureKind:
    """
    Classify a Python exception raised during a provider call.

    Parameters
    ----------
    exc:
        The exception that was raised.
    error_body:
        The parsed JSON error body from the provider response, if available.
        Used to detect quota-exhaustion errors buried in 429/400 responses.
    """
    if isinstance(exc, httpx.TimeoutException):
        return FailureKind.TIMEOUT

    if isinstance(exc, httpx.ConnectError):
        return FailureKind.CONNECTION_ERROR

    if isinstance(exc, httpx.NetworkError):
        return FailureKind.CONNECTION_ERROR

    if isinstance(exc, httpx.HTTPStatusError):
        return classify_status_code(exc.response.status_code, error_body)

    # Anything else is unknown — do not retry.
    return FailureKind.UNKNOWN


def classify_status_code(
    status_code: int,
    error_body: Optional[dict] = None,
) -> FailureKind:
    """
    Classify a provider HTTP response by status code.

    Parameters
    ----------
    status_code:
        HTTP status code from the provider.
    error_body:
        Parsed provider error JSON, used to detect quota exhaustion.
    """
    if status_code == 429:
        # Check whether this is a quota error masquerading as rate-limiting.
        if _is_quota_error(error_body):
            return FailureKind.QUOTA_EXHAUSTED
        return FailureKind.RATE_LIMITED

    if status_code == 500:
        return FailureKind.SERVER_ERROR_500

    if status_code == 502:
        return FailureKind.BAD_GATEWAY_502

    if status_code == 503:
        return FailureKind.SERVICE_UNAVAILABLE_503

    if status_code == 504:
        return FailureKind.GATEWAY_TIMEOUT_504

    if 500 <= status_code < 600:
        return FailureKind.OTHER_5XX

    if 400 <= status_code < 500:
        # Check for quota-related 4xx errors (some providers use 400 for billing)
        if _is_quota_error(error_body):
            return FailureKind.QUOTA_EXHAUSTED
        return FailureKind.CLIENT_ERROR_4XX

    # 3xx or unexpected codes — treat as unknown.
    return FailureKind.UNKNOWN
