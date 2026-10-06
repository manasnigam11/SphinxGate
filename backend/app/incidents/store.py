"""
Incident Store — Phase 4.

In-memory store for incidents.  Incidents are development/operational
artifacts that do not need multi-process persistence in Phase 4
(a future phase can add SQLite/Postgres backing if needed).

Design decisions:
  - Bounded memory: maximum MAX_INCIDENTS active + resolved incidents.
  - Thread/coroutine safe via asyncio.Lock.
  - Deduplication is enforced here via dedup_key lookup.
  - Incidents are never automatically deleted — resolved incidents stay
    for audit purposes until the store is cleared.
"""

import asyncio
import logging
from typing import Optional

from app.incidents.models import Incident, IncidentStatus

logger = logging.getLogger("sphinxgate.incidents")

MAX_INCIDENTS = 500   # Hard cap to bound memory growth


class IncidentStore:
    """
    In-memory registry of all incidents.
    """

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}  # incident_id → Incident
        self._lock = asyncio.Lock()

    async def create(self, incident: Incident) -> None:
        """Persist a new incident."""
        async with self._lock:
            if len(self._incidents) >= MAX_INCIDENTS:
                # Prune oldest resolved incidents to make room.
                self._prune_resolved()
            self._incidents[incident.incident_id] = incident
            logger.warning(
                "Incident created: %s  provider=%s  severity=%s  title=%s",
                incident.incident_id,
                incident.provider_slug,
                incident.severity.value,
                incident.title,
            )

    async def update(self, incident: Incident) -> None:
        """Persist an updated incident (in-place mutation is sufficient)."""
        # The incident object is already mutated in place by update_from_new_failure.
        # This method exists as a semantic checkpoint for future DB persistence.
        logger.debug("Incident updated: %s  errors=%d", incident.incident_id, incident.error_count)

    async def get(self, incident_id: str) -> Optional[Incident]:
        """Return an incident by ID, or None."""
        return self._incidents.get(incident_id)

    async def get_active_by_dedup_key(self, dedup_key: str) -> Optional[Incident]:
        """
        Return the first open/acknowledged/investigating incident matching
        the deduplication key, or None.

        Used to prevent duplicate incidents for the same ongoing failure.
        """
        for inc in self._incidents.values():
            if (
                inc.dedup_key == dedup_key
                and inc.status != IncidentStatus.RESOLVED
            ):
                return inc
        return None

    async def list_all(
        self,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Incident]:
        """
        Return incidents, most-recent first, optionally filtered.
        """
        results = sorted(
            self._incidents.values(),
            key=lambda i: i.started_at,
            reverse=True,
        )
        if status:
            results = [i for i in results if i.status.value == status]
        if provider:
            results = [i for i in results if i.provider_slug == provider]
        return results[offset: offset + limit]

    async def count(self, status: Optional[str] = None) -> int:
        if status:
            return sum(1 for i in self._incidents.values() if i.status.value == status)
        return len(self._incidents)

    def _prune_resolved(self) -> None:
        """Remove the oldest resolved incidents to cap memory usage."""
        resolved = sorted(
            [i for i in self._incidents.values() if i.status == IncidentStatus.RESOLVED],
            key=lambda i: i.resolved_at or 0,
        )
        to_remove = resolved[: len(resolved) // 2]  # Remove oldest half
        for inc in to_remove:
            del self._incidents[inc.incident_id]
        logger.debug("Pruned %d resolved incidents", len(to_remove))


# ── Singleton ──────────────────────────────────────────────────────────────────

_incident_store: Optional["IncidentStore"] = None


def get_incident_store() -> IncidentStore:
    """Return the process-lifetime singleton IncidentStore."""
    global _incident_store
    if _incident_store is None:
        _incident_store = IncidentStore()
    return _incident_store


def _reset_incident_store() -> None:
    """Test helper — resets the singleton."""
    global _incident_store
    _incident_store = None
