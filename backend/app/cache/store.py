"""
In-memory TTL cache — Phase 3.

Design decisions:
  - Simple dict-based in-memory cache suitable for a single-process prototype.
  - Each provider can have its own TTL policy (or caching disabled entirely).
  - Cache keys are deterministic hashes of (provider_slug, canonical_params).
  - Cache metadata (hit/miss, age) is returned alongside data so the frontend
    can display it and responses are never silently stale.
  - No stale-while-revalidate or stale-on-failure by default; stale fallback
    must be explicitly opted into per provider policy and is clearly marked.
  - Cache growth is bounded by max_entries per provider.

Scalability note (documented limitation):
  - In-process cache means different SphinxGate instances have independent
    caches.  A production multi-instance deployment would use Redis or similar.

Providers targeted for caching (sensible defaults):
  - open_meteo:   TTL 10 min  (weather changes slowly; identical lat/lon/params)
  - frankfurter:  TTL 1 hour  (exchange rates update ~daily, hourly is fine)
  - jokeapi:      disabled    (users expect variety; caching defeats the purpose)
  - trivia:       disabled    (same reason as jokes)
  - LLM providers: disabled   (responses are non-deterministic; caching would be incorrect)
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("sphinxgate.cache")


@dataclass
class CachePolicy:
    """Cache policy for a single provider."""
    enabled: bool = False
    ttl_seconds: float = 300.0           # Time-to-live
    max_entries: int = 500               # Bounded growth
    allow_stale_on_failure: bool = False # Serve stale if provider is down?
    stale_max_age_seconds: float = 1800.0  # Only serve stale this fresh


# Default policies — tweaked per Phase 3 spec.
# Phase 5: open_meteo and frankfurter opt in to stale-on-failure (graceful
# degradation).  The gateway only serves a stale entry when the whole resilience
# pipeline failed AND the global degradation policy is enabled, and it always
# labels the response as degraded.
DEFAULT_CACHE_POLICIES: dict[str, CachePolicy] = {
    "open_meteo":   CachePolicy(enabled=True,  ttl_seconds=600,    max_entries=200,
                                allow_stale_on_failure=True, stale_max_age_seconds=3600),
    "frankfurter":  CachePolicy(enabled=True,  ttl_seconds=3600,   max_entries=100,
                                allow_stale_on_failure=True, stale_max_age_seconds=86400),
    "jokeapi":      CachePolicy(enabled=True, ttl_seconds=600, max_entries=200,
                                allow_stale_on_failure=True, stale_max_age_seconds=86400),
    "trivia":       CachePolicy(enabled=True, ttl_seconds=600, max_entries=200,
                                allow_stale_on_failure=True, stale_max_age_seconds=86400),
    "openai":       CachePolicy(enabled=False),
    "gemini":       CachePolicy(enabled=False),
    "groq":         CachePolicy(enabled=False),
}


@dataclass
class CacheEntry:
    """A single cached response."""
    key: str
    provider_slug: str
    data: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def is_expired(self) -> bool:
        return self.age_seconds >= self.ttl_seconds


@dataclass
class CacheResult:
    """What the cache returned for a lookup."""
    hit: bool
    data: Any = None
    age_seconds: float = 0.0
    is_stale: bool = False              # True when served past TTL during failure
    cache_key: Optional[str] = None


class ResponseCache:
    """
    In-memory TTL cache for public API responses.

    Thread-safety: Python's GIL provides adequate safety for dict operations
    in a single-process async context.
    """

    def __init__(self, policies: dict[str, CachePolicy] | None = None) -> None:
        self._policies = policies or dict(DEFAULT_CACHE_POLICIES)
        # _store: provider_slug → {cache_key: CacheEntry}
        self._store: dict[str, dict[str, CacheEntry]] = {}

    def get_policy(self, provider_slug: str) -> CachePolicy:
        return self._policies.get(provider_slug, CachePolicy(enabled=False))

    def make_key(self, provider_slug: str, params: dict[str, Any]) -> str:
        """Generate a stable cache key from provider + canonical params."""
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha256(f"{provider_slug}:{canonical}".encode()).hexdigest()[:16]
        return f"{provider_slug}:{digest}"

    def get(
        self,
        provider_slug: str,
        params: dict[str, Any],
        allow_stale: bool = False,
        max_stale_age: Optional[float] = None,
    ) -> CacheResult:
        """
        Look up a cached response.

        Parameters
        ----------
        provider_slug:
            Provider to look up.
        params:
            The normalized request parameters (used to derive the cache key).
        allow_stale:
            If True and the entry is expired, return it anyway with is_stale=True.
            Used when the provider is failing and the policy permits stale fallback.
        """
        policy = self.get_policy(provider_slug)
        if not policy.enabled:
            return CacheResult(hit=False)

        cache_key = self.make_key(provider_slug, params)
        provider_cache = self._store.get(provider_slug, {})
        entry = provider_cache.get(cache_key)

        if entry is None:
            return CacheResult(hit=False, cache_key=cache_key)

        if not entry.is_expired:
            logger.debug("Cache HIT  provider=%s key=%s age=%.1fs", provider_slug, cache_key, entry.age_seconds)
            return CacheResult(hit=True, data=entry.data, age_seconds=entry.age_seconds, cache_key=cache_key)

        # Entry is expired
        stale_limit = policy.stale_max_age_seconds
        if max_stale_age is not None:
            stale_limit = min(stale_limit, max_stale_age)
        servable_stale = policy.allow_stale_on_failure and entry.age_seconds < stale_limit

        if allow_stale and servable_stale:
            logger.info(
                "Cache STALE provider=%s key=%s age=%.1fs (serving stale during failure)",
                provider_slug, cache_key, entry.age_seconds,
            )
            return CacheResult(hit=True, data=entry.data, age_seconds=entry.age_seconds, is_stale=True, cache_key=cache_key)

        # Keep expired-but-still-stale-servable entries so a later upstream
        # failure can degrade gracefully; evict everything else.
        if not (policy.allow_stale_on_failure and entry.age_seconds < policy.stale_max_age_seconds):
            provider_cache.pop(cache_key, None)
        return CacheResult(hit=False, cache_key=cache_key)

    def set(
        self,
        provider_slug: str,
        params: dict[str, Any],
        data: Any,
    ) -> str:
        """
        Store a response in the cache.

        Returns the cache key used.
        """
        policy = self.get_policy(provider_slug)
        if not policy.enabled:
            return ""

        cache_key = self.make_key(provider_slug, params)

        if provider_slug not in self._store:
            self._store[provider_slug] = {}
        provider_cache = self._store[provider_slug]

        # Evict oldest entry if at capacity
        if len(provider_cache) >= policy.max_entries:
            oldest_key = min(provider_cache, key=lambda k: provider_cache[k].created_at)
            del provider_cache[oldest_key]
            logger.debug("Cache EVICT provider=%s (capacity=%d)", provider_slug, policy.max_entries)

        provider_cache[cache_key] = CacheEntry(
            key=cache_key,
            provider_slug=provider_slug,
            data=data,
            ttl_seconds=policy.ttl_seconds,
        )
        logger.debug("Cache SET   provider=%s key=%s ttl=%.0fs", provider_slug, cache_key, policy.ttl_seconds)
        return cache_key

    def invalidate(self, provider_slug: str) -> int:
        """Invalidate all cached entries for a provider. Returns count removed."""
        removed = len(self._store.get(provider_slug, {}))
        self._store.pop(provider_slug, None)
        return removed

    def stats(self) -> dict[str, Any]:
        """Return cache statistics for the observability API."""
        result = {}
        for slug, entries in self._store.items():
            alive = sum(1 for e in entries.values() if not e.is_expired)
            result[slug] = {
                "total_entries": len(entries),
                "live_entries": alive,
                "expired_entries": len(entries) - alive,
                "policy": {
                    "enabled": self._policies.get(slug, CachePolicy()).enabled,
                    "ttl_seconds": self._policies.get(slug, CachePolicy()).ttl_seconds,
                },
            }
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
_cache: Optional[ResponseCache] = None


def get_cache() -> ResponseCache:
    """Return the process-level singleton ResponseCache."""
    global _cache
    if _cache is None:
        _cache = ResponseCache()
    return _cache
