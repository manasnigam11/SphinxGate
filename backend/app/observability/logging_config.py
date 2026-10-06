"""
SphinxGate structured logging — Phase 5.

Guarantees:
  * Every log record is redacted at creation time (LogRecord factory), so the
    message AND any pre-rendered exception text are secret-free for every
    handler (console, ring buffer, pytest caplog, third-party handlers).
  * Console output is structured JSON (LOG_FORMAT=json, default) or plain text.
  * A bounded in-memory ring buffer retains recent `sphinxgate*` records so the
    UI can show real logs (`GET /api/v1/logs`).  Nothing is persisted.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import get_env
from app.security.redaction import redact_text, redact_value

_STD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime", "taskName"}
_REQ_ID_RE = re.compile(r"\[(req_[A-Za-z0-9_-]+)\]")

_factory_installed = False
_original_factory = logging.getLogRecordFactory()


def _install_record_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = _original_factory(*args, **kwargs)
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact_text(msg)
        record.args = None
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = redact_text(
                    "".join(traceback.format_exception(*record.exc_info))
                ).rstrip()
            except Exception:
                record.exc_text = "[exception text unavailable]"
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        # Redact structured extras too.
        for k in list(record.__dict__.keys()):
            if k not in _STD_ATTRS and not k.startswith("_"):
                record.__dict__[k] = redact_value(record.__dict__[k])
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def _record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
    message = record.getMessage()
    data: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "logger": record.name,
        "message": message,
    }
    m = _REQ_ID_RE.search(message)
    if m:
        data["request_id"] = m.group(1)
    for k, v in record.__dict__.items():
        if k not in _STD_ATTRS and not k.startswith("_"):
            data[k] = v
    if record.exc_text:
        data["exception"] = record.exc_text
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_record_to_dict(record), default=str, ensure_ascii=False)


class RingBufferHandler(logging.Handler):
    """Bounded, thread-safe in-memory buffer of recent structured records."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__(level=logging.INFO)
        self._buf: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock2 = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = _record_to_dict(record)
            with self._lock2:
                self._seq += 1
                entry["seq"] = self._seq
                self._buf.append(entry)
        except Exception:
            pass

    def query(
        self,
        *,
        level: Optional[str] = None,
        limit: int = 200,
        search: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        min_level = order.get((level or "").upper(), 0)
        with self._lock2:
            items = list(self._buf)
        out = []
        needle = search.lower() if search else None
        for e in reversed(items):
            if order.get(e["level"], 0) < min_level:
                continue
            if request_id and e.get("request_id") != request_id:
                continue
            if needle and needle not in json.dumps(e, default=str).lower():
                continue
            out.append(e)
            if len(out) >= max(1, min(limit, 1000)):
                break
        return out

    def clear(self) -> None:
        with self._lock2:
            self._buf.clear()


_ring = RingBufferHandler()


def get_log_buffer() -> RingBufferHandler:
    return _ring


def configure_logging() -> None:
    """Idempotently configure console + ring-buffer logging."""
    _install_record_factory()
    fmt = (get_env("LOG_FORMAT", "json") or "json").lower()
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = None
    for h in root.handlers:
        if getattr(h, "_sphinxgate_console", False):
            console = h
            break
    if console is None:
        console = logging.StreamHandler()
        console._sphinxgate_console = True  # type: ignore[attr-defined]
        root.addHandler(console)
    if fmt == "text":
        console.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s", "%H:%M:%S")
        )
    else:
        console.setFormatter(JsonFormatter())

    sg = logging.getLogger("sphinxgate")
    if _ring not in sg.handlers:
        sg.addHandler(_ring)
    # Keep third-party HTTP client chatter out of the structured stream
    # (httpx logs full request URLs, which can carry query-string keys).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
