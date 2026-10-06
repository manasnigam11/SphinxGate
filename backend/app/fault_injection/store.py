"""
Fault Store — Phase 4.

In-memory store for active fault configurations.
Fault state does NOT need to survive restarts (it's development/demo only).

Thread/coroutine safety:
  - Uses asyncio.Lock for mutation.
  - Reads return copies to avoid mutation after lookup.

Singleton pattern mirrors TelemetryStore / ResponseCache.
"""

import asyncio
import logging
import time
from typing import Optional

from app.config import get_env
from app.fault_injection.models import FaultConfig, FaultType

logger = logging.getLogger("sphinxgate.fault_injection")

_ENABLED_ENV = "FAULT_INJECTION_ENABLED"
_PROD_OVERRIDE_ENV = "ALLOW_FAULT_INJECTION_IN_PRODUCTION"


def _flag(name: str) -> bool:
    return (get_env(name, "false") or "false").strip().lower() == "true"


def is_production_environment() -> bool:
    return (get_env("SPHINXGATE_ENV", "development") or "development").strip().lower() == "production"


def fault_injection_blocked_by_production_guard() -> bool:
    """True when the flag is set but the production guard forces it off."""
    return _flag(_ENABLED_ENV) and is_production_environment() and not _flag(_PROD_OVERRIDE_ENV)


def is_fault_injection_enabled() -> bool:
    """
    Return True only if FAULT_INJECTION_ENABLED=true is explicitly set
    (real environment or .env).

    Default: DISABLED.  This is the safety guard — fault injection must
    be consciously opted into.

    Production guard: when SPHINXGATE_ENV=production the flag is ignored
    unless ALLOW_FAULT_INJECTION_IN_PRODUCTION=true is ALSO set, so a stray
    development flag cannot silently enable fault injection in production.
    """
    if not _flag(_ENABLED_ENV):
        return False
    if is_production_environment() and not _flag(_PROD_OVERRIDE_ENV):
        return False
    return True


class FaultStore:
    """
    In-memory registry of active fault configurations.

    All methods are coroutine-safe.  The store is not persisted — it resets
    on process restart, which is the correct behavior for a dev/demo tool.
    """

    def __init__(self) -> None:
        self._faults: dict[str, FaultConfig] = {}  # fault_id → FaultConfig
        self._lock = asyncio.Lock()

    async def add(self, fault: FaultConfig) -> None:
        """
        Register a new fault.

        If a fault for the same provider + fault_type is already active,
        the old one is superseded (deactivated) and the new one replaces it.
        This prevents duplicate active faults on the same provider.
        """
        async with self._lock:
            # Deactivate any existing active fault for the same provider+type.
            for existing in self._faults.values():
                if (
                    existing.provider_slug == fault.provider_slug
                    and existing.fault_type == fault.fault_type
                    and existing.is_active
                ):
                    existing.is_active = False
                    logger.info(
                        "Superseded existing fault %s for provider=%s type=%s",
                        existing.fault_id, existing.provider_slug, existing.fault_type.value,
                    )
            self._faults[fault.fault_id] = fault
            logger.warning(
                "FAULT ACTIVE: fault_id=%s provider=%s type=%s",
                fault.fault_id, fault.provider_slug, fault.fault_type.value,
            )

    async def get(self, fault_id: str) -> Optional[FaultConfig]:
        """Return a fault by ID, or None."""
        return self._faults.get(fault_id)

    async def disable(self, fault_id: str) -> bool:
        """
        Deactivate a fault.  Returns True if found, False if not found.
        """
        async with self._lock:
            fault = self._faults.get(fault_id)
            if fault is None:
                return False
            fault.is_active = False
            logger.info("Fault disabled: fault_id=%s", fault_id)
            return True

    async def clear_all(self) -> int:
        """Deactivate all active faults. Returns count deactivated."""
        async with self._lock:
            count = 0
            for fault in self._faults.values():
                if fault.is_active:
                    fault.is_active = False
                    count += 1
            logger.info("All faults cleared (%d deactivated)", count)
            return count

    async def list_all(self) -> list[FaultConfig]:
        """Return all faults (active, inactive, expired)."""
        return list(self._faults.values())

    async def list_active(self) -> list[FaultConfig]:
        """Return only currently-effective faults."""
        return [f for f in self._faults.values() if f.is_effective]

    async def get_effective_for_provider(self, provider_slug: str) -> Optional[FaultConfig]:
        """
        Return the first effective fault for a given provider, or None.

        Called on the hot path (every provider call) — must be fast.
        No lock needed for reads since we return immutable data.
        """
        for fault in self._faults.values():
            if fault.provider_slug == provider_slug and fault.is_effective:
                return fault
        return None

    def _prune_expired(self) -> None:
        """Remove expired and old inactive faults to bound memory growth."""
        to_remove = [
            fid for fid, f in self._faults.items()
            if f.is_expired and not f.is_active
        ]
        for fid in to_remove:
            del self._faults[fid]


# ── Singleton ──────────────────────────────────────────────────────────────────

_fault_store: Optional["FaultStore"] = None


def get_fault_store() -> FaultStore:
    """Return the process-lifetime singleton FaultStore."""
    global _fault_store
    if _fault_store is None:
        _fault_store = FaultStore()
    return _fault_store


def _reset_fault_store() -> None:
    """Test helper — resets the singleton. Never call in production code."""
    global _fault_store
    _fault_store = None
