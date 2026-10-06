"""
SQLite-backed telemetry store — Phase 3.

Design decisions:
  - Uses aiosqlite for non-blocking async I/O (SQLite is the correct scale for a
    prototype; it can be swapped for Postgres/ClickHouse later by replacing this
    module without touching the facade or gateway).
  - Bounded storage: records older than MAX_AGE_DAYS are pruned automatically.
  - Write failures never break the user request (the facade catches all store errors).
  - No API keys, no secrets, no full request/response bodies are stored.
  - Store is a singleton shared across the process lifetime.

Limitations (documented honestly):
  - In-process SQLite is not distributed — a multi-instance deployment would need
    shared external storage.
  - Pruning is triggered on write, not on a separate cron, to keep the design simple.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import aiosqlite

from app.telemetry.models import TelemetryRecord, TelemetrySummary

logger = logging.getLogger("sphinxgate.telemetry")

# ── Constants ──────────────────────────────────────────────────────────────────
_DB_PATH_ENV = "TELEMETRY_DB_PATH"
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "telemetry.db")
MAX_RECORDS = 10_000          # Hard cap (prune oldest when exceeded)
MAX_AGE_DAYS = 7              # Auto-prune records older than this
PRUNE_EVERY_N = 100           # Prune check every N writes

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS requests (
    request_id          TEXT     PRIMARY KEY,
    timestamp           REAL     NOT NULL,
    provider_slug       TEXT     NOT NULL,
    provider_display_name TEXT   NOT NULL,
    provider_category   TEXT     NOT NULL,
    endpoint            TEXT     NOT NULL,
    success             INTEGER  NOT NULL,
    status_code         INTEGER  NOT NULL,
    latency_ms          INTEGER  NOT NULL,
    retry_count         INTEGER  NOT NULL DEFAULT 0,
    fallback_used       INTEGER  NOT NULL DEFAULT 0,
    circuit_state       TEXT     NOT NULL DEFAULT 'closed',
    error_type          TEXT,
    error_message       TEXT,
    tokens_used         INTEGER  NOT NULL DEFAULT 0,
    cache_hit           INTEGER  NOT NULL DEFAULT 0,
    cache_key           TEXT,
    events_json         TEXT     NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON requests(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_provider  ON requests(provider_slug);
CREATE INDEX IF NOT EXISTS idx_success   ON requests(success);
"""


class TelemetryStore:
    """
    Async SQLite-backed telemetry persistence.

    Usage:
        store = TelemetryStore()
        await store.initialize()
        await store.record(telemetry_record)
        records = await store.recent(limit=50)
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or os.environ.get(_DB_PATH_ENV, _DEFAULT_DB_PATH)
        self._write_count = 0
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create tables and indexes if they don't exist."""
        if self._initialized:
            return
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_CREATE_TABLE_SQL)
            await db.commit()
        self._initialized = True
        logger.info("TelemetryStore initialized at %s", self._db_path)

    async def record(self, rec: TelemetryRecord) -> None:
        """Persist a single telemetry record. Errors are logged, not raised."""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO requests (
                            request_id, timestamp, provider_slug, provider_display_name,
                            provider_category, endpoint, success, status_code, latency_ms,
                            retry_count, fallback_used, circuit_state,
                            error_type, error_message, tokens_used,
                            cache_hit, cache_key, events_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            rec.request_id,
                            rec.timestamp,
                            rec.provider_slug,
                            rec.provider_display_name,
                            rec.provider_category,
                            rec.endpoint,
                            1 if rec.success else 0,
                            rec.status_code,
                            rec.latency_ms,
                            rec.retry_count,
                            1 if rec.fallback_used else 0,
                            rec.circuit_state,
                            rec.error_type,
                            rec.error_message,
                            rec.tokens_used,
                            1 if rec.cache_hit else 0,
                            rec.cache_key,
                            rec.events_json,
                        ),
                    )
                    await db.commit()

                self._write_count += 1
                if self._write_count % PRUNE_EVERY_N == 0:
                    await self._prune()
        except Exception:
            logger.exception("TelemetryStore.record failed — request will still complete")

    async def recent(self, limit: int = 100, offset: int = 0) -> list[TelemetryRecord]:
        """Return the most recent telemetry records (newest first)."""
        try:
            await self._ensure_initialized()
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT * FROM requests
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                rows = await cursor.fetchall()
            return [self._row_to_record(r) for r in rows]
        except Exception:
            logger.exception("TelemetryStore.recent failed")
            return []

    async def get(self, request_id: str) -> Optional[TelemetryRecord]:
        """Fetch a single record by request_id."""
        try:
            await self._ensure_initialized()
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM requests WHERE request_id = ?",
                    (request_id,),
                )
                row = await cursor.fetchone()
            return self._row_to_record(row) if row else None
        except Exception:
            logger.exception("TelemetryStore.get failed")
            return None

    async def summary(self, since_seconds: float = 3600.0) -> TelemetrySummary:
        """
        Compute aggregate statistics for requests in the last `since_seconds` window.
        """
        try:
            await self._ensure_initialized()
            since_ts = time.time() - since_seconds
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row

                # Overall stats
                cur = await db.execute(
                    """
                    SELECT
                        COUNT(*)                        AS total,
                        SUM(success)                    AS successful,
                        SUM(1 - success)                AS failed,
                        AVG(latency_ms)                 AS avg_latency,
                        SUM(tokens_used)                AS total_tokens,
                        SUM(retry_count)                AS total_retries,
                        SUM(fallback_used)              AS total_fallbacks,
                        SUM(cache_hit)                  AS cache_hits,
                        SUM(CASE WHEN cache_hit=0 AND provider_category='public_api' THEN 1 ELSE 0 END) AS cache_misses
                    FROM requests
                    WHERE timestamp >= ?
                    """,
                    (since_ts,),
                )
                overall = await cur.fetchone()

                # p95 latency (approximate via percentile trick)
                cur2 = await db.execute(
                    """
                    SELECT latency_ms FROM requests
                    WHERE timestamp >= ?
                    ORDER BY latency_ms
                    """,
                    (since_ts,),
                )
                all_latencies = [r[0] for r in await cur2.fetchall()]

                # Per-provider stats
                cur3 = await db.execute(
                    """
                    SELECT provider_slug,
                           COUNT(*)     AS total,
                           SUM(success) AS successful,
                           AVG(latency_ms) AS avg_latency
                    FROM requests
                    WHERE timestamp >= ?
                    GROUP BY provider_slug
                    """,
                    (since_ts,),
                )
                provider_rows = await cur3.fetchall()

                # Failure type distribution
                cur4 = await db.execute(
                    """
                    SELECT error_type, COUNT(*) AS cnt
                    FROM requests
                    WHERE timestamp >= ? AND success = 0 AND error_type IS NOT NULL
                    GROUP BY error_type
                    """,
                    (since_ts,),
                )
                failure_rows = await cur4.fetchall()

            p95 = 0.0
            if all_latencies:
                idx = int(len(all_latencies) * 0.95)
                p95 = float(all_latencies[min(idx, len(all_latencies) - 1)])

            provider_stats = {
                r["provider_slug"]: {
                    "total": r["total"],
                    "successful": r["successful"] or 0,
                    "avg_latency_ms": round(r["avg_latency"] or 0, 1),
                }
                for r in provider_rows
            }
            failure_types = {r["error_type"]: r["cnt"] for r in failure_rows}

            return TelemetrySummary(
                total_requests=overall["total"] or 0,
                successful_requests=overall["successful"] or 0,
                failed_requests=overall["failed"] or 0,
                avg_latency_ms=round(overall["avg_latency"] or 0, 1),
                p95_latency_ms=p95,
                total_tokens_used=overall["total_tokens"] or 0,
                total_retries=overall["total_retries"] or 0,
                total_fallbacks=overall["total_fallbacks"] or 0,
                cache_hits=overall["cache_hits"] or 0,
                cache_misses=overall["cache_misses"] or 0,
                provider_stats=provider_stats,
                failure_types=failure_types,
            )
        except Exception:
            logger.exception("TelemetryStore.summary failed")
            return TelemetrySummary()

    async def provider_stats(self, provider_slug: str, since_seconds: float = 86400.0) -> dict[str, Any]:
        """Return per-provider statistics."""
        try:
            await self._ensure_initialized()
            since_ts = time.time() - since_seconds
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(
                    """
                    SELECT COUNT(*) AS total, SUM(success) AS successful,
                           AVG(latency_ms) AS avg_latency, SUM(retry_count) AS retries,
                           SUM(fallback_used) AS fallbacks, SUM(tokens_used) AS tokens
                    FROM requests
                    WHERE provider_slug = ? AND timestamp >= ?
                    """,
                    (provider_slug, since_ts),
                )
                row = await cur.fetchone()
            if not row or row["total"] == 0:
                return {"provider": provider_slug, "total_requests": 0}
            return {
                "provider": provider_slug,
                "total_requests": row["total"] or 0,
                "successful_requests": row["successful"] or 0,
                "avg_latency_ms": round(row["avg_latency"] or 0, 1),
                "total_retries": row["retries"] or 0,
                "total_fallbacks": row["fallbacks"] or 0,
                "total_tokens": row["tokens"] or 0,
            }
        except Exception:
            logger.exception("TelemetryStore.provider_stats failed")
            return {}

    # ── Private helpers ──────────────────────────────────────────────────────────

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def _prune(self) -> None:
        """Remove records older than MAX_AGE_DAYS and beyond MAX_RECORDS cap."""
        try:
            cutoff = time.time() - (MAX_AGE_DAYS * 86400)
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("DELETE FROM requests WHERE timestamp < ?", (cutoff,))
                # Hard cap: delete oldest beyond MAX_RECORDS
                await db.execute(
                    """
                    DELETE FROM requests WHERE request_id IN (
                        SELECT request_id FROM requests
                        ORDER BY timestamp DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (MAX_RECORDS,),
                )
                await db.commit()
            logger.debug("TelemetryStore pruned old records")
        except Exception:
            logger.warning("TelemetryStore._prune failed (non-fatal)")

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> TelemetryRecord:
        return TelemetryRecord(
            request_id=row["request_id"],
            timestamp=row["timestamp"],
            provider_slug=row["provider_slug"],
            provider_display_name=row["provider_display_name"],
            provider_category=row["provider_category"],
            endpoint=row["endpoint"],
            success=bool(row["success"]),
            status_code=row["status_code"],
            latency_ms=row["latency_ms"],
            retry_count=row["retry_count"],
            fallback_used=bool(row["fallback_used"]),
            circuit_state=row["circuit_state"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            tokens_used=row["tokens_used"],
            cache_hit=bool(row["cache_hit"]),
            cache_key=row["cache_key"],
            events_json=row["events_json"],
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
_store: Optional[TelemetryStore] = None


def get_telemetry_store() -> TelemetryStore:
    """Return the process-level singleton TelemetryStore."""
    global _store
    if _store is None:
        _store = TelemetryStore()
    return _store
