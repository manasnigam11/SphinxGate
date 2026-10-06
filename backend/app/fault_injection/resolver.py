"""
Fault-aware provider wrapping — Phase 4 (rewired in Phase 5).

Fault injection works by wrapping the resolved provider in FaultAwareProvider:

  registry.get_provider(slug)
        ↓
  FaultAwareProvider.call()            ← only when fault injection is enabled
        ↓
  Fault check (FaultStore)
        ↓
  Either: raise exception (the ResilienceEngine handles it as a real failure)
  Or:     delegate to the real provider.call()

The ResilienceEngine is completely unmodified — it receives a provider object
that happens to be fault-aware, but from its perspective it's just a
BaseProvider that raises the same exception types a real upstream would.

Phase 5 note:
  Phase 4 installed this by replacing `registry.get_provider` at startup.  That
  silently did nothing for the engine (it had already imported the original
  function object).  `registry.get_provider` now calls
  `wrap_if_fault_injection_enabled` itself, evaluated on every call.
"""

import logging
from typing import Optional

from app.fault_injection.middleware import FaultAwareProvider
from app.fault_injection.store import FaultStore, get_fault_store, is_fault_injection_enabled
from app.providers.base import BaseProvider

logger = logging.getLogger("sphinxgate.fault_injection")


def wrap_if_fault_injection_enabled(
    provider: BaseProvider,
    fault_store: Optional[FaultStore] = None,
) -> BaseProvider:
    """
    Wrap `provider` in FaultAwareProvider when fault injection is enabled.

    Already-wrapped providers are returned unchanged (idempotent).
    """
    if not is_fault_injection_enabled():
        return provider
    if isinstance(provider, FaultAwareProvider):
        return provider
    return FaultAwareProvider(inner=provider, fault_store=fault_store or get_fault_store())


def make_fault_aware_resolver(fault_store: Optional[FaultStore] = None):
    """
    Return a get_provider-style function that wraps providers with fault
    injection.  Kept for backwards compatibility with Phase 4 callers/tests.
    """
    store = fault_store or get_fault_store()

    def fault_aware_get_provider(slug: str) -> BaseProvider:
        # Import here to avoid circular imports at module level.
        from app.providers.registry import REGISTRY
        provider = REGISTRY.get(slug)
        if provider is None:
            raise KeyError(f"Unknown provider: '{slug}'. Available: {list(REGISTRY)}")
        return wrap_if_fault_injection_enabled(provider, store)

    return fault_aware_get_provider
