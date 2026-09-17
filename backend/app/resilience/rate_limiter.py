"""
Gateway-side In-Memory Rate Limiter — Phase 2.

Limits the total number of requests SphinxGate accepts within a sliding
time window, regardless of which provider is being called.

This is a GATEWAY rate limit — it is distinct from provider-side 429s.
A gateway 429 means "SphinxGate is protecting itself / its downstream";
a provider 429 means "the upstream provider is asking us to back off".

Implementation:
  - Sliding window counter using a deque of timestamps.
  - asyncio.Lock for async safety.
  - In-memory only — appropriate for a modular-monolith hackathon.
  - No Redis / distributed coordination needed here.
"""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger("sphinxgate.rate_limiter")


class GatewayRateLimiter:
    """
    Token-bucket approximation using a sliding window of request timestamps.

    Parameters
    ----------
    max_requests:
        Maximum number of requests allowed within the window.
    window_seconds:
        Length of the sliding window.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        """
        Return True if this request is within the rate limit.
        Return False if the limit is exceeded (caller should return HTTP 429).

        Internally records the current timestamp if allowed.
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds

            # Evict timestamps outside the window.
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_requests:
                logger.warning(
                    "Gateway rate limit exceeded: %d requests in %.1fs window",
                    len(self._timestamps), self._window_seconds,
                )
                return False

            self._timestamps.append(now)
            return True

    @property
    def current_count(self) -> int:
        """Approximate number of requests in the current window (for observability)."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        return sum(1 for ts in self._timestamps if ts >= cutoff)
