"""
SphinxGate secret redaction — Phase 5.

A single, dependency-free module that scrubs credentials from any text or
structure before it is logged, persisted (telemetry / incidents), or returned
through an API.

Two complementary strategies:

1. Pattern-based  — Authorization/Bearer headers, PEM private keys, vendor key
   formats (sk-…, AIza…, gsk_…, AKIA…, ghp_…, xox…, JWT), `key=value` secrets
   and credentials embedded in URLs.
2. Exact-value    — the actual values of configured provider keys and of any
   environment variable whose name looks secret (KEY / SECRET / TOKEN /
   PASSWORD / CREDENTIAL).  This catches secrets that have no recognisable
   format.

The module never raises: redaction is a safety net and must not break a
request path.
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterable

REDACTED = "[REDACTED]"

# Keys whose *values* must never be emitted, whatever they contain.
_SENSITIVE_KEY_RE = re.compile(
    r"(authorization|api[-_]?key|apikey|x-goog-api-key|secret|password|passwd|"
    r"credential|private[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"bearer|^token$|cookie|set-cookie)",
    re.IGNORECASE,
)

# Names that look like secrets but are NOT (token *counts*, etc.).
_BENIGN_KEY_RE = re.compile(
    r"(tokens?_(used|count|limit)|max_tokens|total_tokens|prompt_tokens|"
    r"completion_tokens|tokens_used|token_count|input_tokens|output_tokens)",
    re.IGNORECASE,
)

_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
    re.DOTALL,
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\b(\s*[:=]\s*)(?:bearer\s+|basic\s+|token\s+)?[^\s,;\"'}]+"
    r"(?:\s+[A-Za-z0-9._~+/=-]{8,})?"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_KV_SECRET_RE = re.compile(
    r"(?i)(?P<k>[\"']?(?:x-goog-api-key|x-api-key|api[-_]?key|apikey|access[-_]?token|"
    r"refresh[-_]?token|client[-_]?secret|secret(?:[-_]?key)?|password|passwd|"
    r"private[-_]?key|token)[\"']?)(?P<sep>\s*[:=]\s*)"
    r"(?P<q>[\"']?)(?P<v>[^\s\"',;&}]{3,})(?P=q)"
)
_URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")
_URL_QUERY_RE = re.compile(
    r"(?i)([?&](?:key|api[-_]?key|apikey|access[-_]?token|token|secret|password|auth)=)([^&\s\"']+)"
)
_VENDOR_RES = [
    re.compile(r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"),  # OpenAI / Anthropic style
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),                              # Google API key
    re.compile(r"\bgsk_[A-Za-z0-9]{16,}"),                                # Groq
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                         # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                          # GitHub
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),                        # Slack
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
]

_SECRET_ENV_NAME_RE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
_MIN_SECRET_LEN = 8

# Secrets registered explicitly at runtime (tests, dynamic config).
_registered: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register an exact secret value so it is always masked."""
    if value and len(value) >= _MIN_SECRET_LEN:
        _registered.add(value)


def clear_registered_secrets() -> None:
    """Forget explicitly registered secrets — used by tests."""
    _registered.clear()


def _exact_secret_values() -> list[str]:
    values: set[str] = set(_registered)
    try:
        for name, val in os.environ.items():
            if val and len(val) >= _MIN_SECRET_LEN and _SECRET_ENV_NAME_RE.search(name):
                if not _BENIGN_KEY_RE.search(name):
                    values.add(val)
    except Exception:
        pass
    try:
        from app.config import get_settings, _dotenv_values  # type: ignore

        settings = get_settings()
        for field in ("openai_api_key", "gemini_api_key", "groq_api_key"):
            v = getattr(settings, field, None)
            if v and len(v) >= _MIN_SECRET_LEN:
                values.add(v)
        for name, val in _dotenv_values().items():
            if val and len(val) >= _MIN_SECRET_LEN and _SECRET_ENV_NAME_RE.search(name):
                values.add(val)
    except Exception:
        pass
    # Longest first so a secret that contains another is masked fully.
    return sorted(values, key=len, reverse=True)


def redact_text(text: Any) -> str:
    """Return `text` (coerced to str) with credentials masked. Never raises."""
    try:
        if text is None:
            return ""
        s = text if isinstance(text, str) else str(text)
        if not s:
            return s
        for secret in _exact_secret_values():
            if secret in s:
                s = s.replace(secret, REDACTED)
        s = _PEM_RE.sub(REDACTED, s)
        s = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", s)
        s = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", s)
        s = _URL_CRED_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:{REDACTED}@", s)
        s = _URL_QUERY_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", s)
        for rx in _VENDOR_RES:
            s = rx.sub(REDACTED, s)

        def _kv(m: re.Match) -> str:
            key = m.group("k")
            if _BENIGN_KEY_RE.search(key):
                return m.group(0)
            if m.group("v") == REDACTED or m.group("v").startswith("[REDACTED"):
                return m.group(0)
            q = m.group("q")
            return f"{key}{m.group('sep')}{q}{REDACTED}{q}"

        s = _KV_SECRET_RE.sub(_kv, s)
        return s
    except Exception:
        return REDACTED


def truncate(text: str, limit: int = 500) -> str:
    """Truncate with an ellipsis marker."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_sensitive_key(key: Any) -> bool:
    k = str(key)
    if _BENIGN_KEY_RE.search(k):
        return False
    return bool(_SENSITIVE_KEY_RE.search(k))


def redact_value(value: Any, _depth: int = 0) -> Any:
    """Deep-redact a JSON-like structure. Sensitive dict keys are fully masked."""
    if _depth > 12:
        return REDACTED
    try:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            for k, v in value.items():
                out[k] = REDACTED if is_sensitive_key(k) and v not in (None, "") else redact_value(v, _depth + 1)
            return out
        if isinstance(value, (list, tuple, set)):
            return [redact_value(v, _depth + 1) for v in value]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return redact_text(str(value))
    except Exception:
        return REDACTED


def sanitize_exception(exc: BaseException, limit: int = 300) -> str:
    """A safe, bounded, human-readable description of an exception."""
    try:
        msg = redact_text(str(exc)).strip()
    except Exception:
        msg = ""
    name = type(exc).__name__
    text = f"{name}: {msg}" if msg else name
    return truncate(text, limit)


def redact_headers(headers: Iterable[tuple[str, str]] | dict[str, str]) -> dict[str, str]:
    """Return headers with credential-bearing values masked."""
    items = headers.items() if isinstance(headers, dict) else headers
    return {k: (REDACTED if is_sensitive_key(k) else redact_text(v)) for k, v in items}
