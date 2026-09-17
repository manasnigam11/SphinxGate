# Resilience engine package — Phase 2 of SphinxGate.
#
# Modules:
#   policy          — Centralized ResiliencePolicy (configurable timeouts, retries, etc.)
#   classifier      — Failure classification (timeout, 429, 5xx, etc.)
#   circuit_breaker — Per-provider circuit breaker (CLOSED/OPEN/HALF-OPEN)
#   rate_limiter    — Gateway-side in-memory rate limiter
#   retry           — Bounded exponential-backoff retry engine
#   fallback        — Fallback routing when primary provider is unavailable
#   engine          — Top-level ResilienceEngine that composes all of the above
#   events          — Structured resilience event types for Phase 3 observability
