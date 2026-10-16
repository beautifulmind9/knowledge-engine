"""Best-effort structured timing events. Never include content or raise to callers."""
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

# Uvicorn's default config routes this logger through its configured stdout
# handler. The root logger has no handler in the hosted startup configuration.
logger = logging.getLogger("uvicorn.error")
_operation_context = ContextVar("ke_performance_operation", default={})


def start():
    try:
        return time.perf_counter()
    except Exception:
        return None


@contextmanager
def operation_context(**fields):
    """Attach allowlisted operation identity to nested timing events."""
    token = _operation_context.set({**_operation_context.get(), **fields})
    try:
        yield
    finally:
        _operation_context.reset(token)


def snapshot_utf8_size(state):
    """Approximate psycopg Jsonb's UTF-8 JSON payload size, without returning content."""
    try:
        return len(json.dumps(state).encode("utf-8"))
    except Exception:
        return None


def utf8_size(value):
    try:
        return len(value.encode("utf-8"))
    except Exception:
        return None


def emit(event, started_at=None, *, duration_ms=None, result="success", **fields):
    try:
        if duration_ms is None and started_at is not None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        record = {"event": event, "result": result}
        if duration_ms is not None:
            record["duration_ms"] = duration_ms
        record.update(_operation_context.get())
        record.update(fields)
        logger.info("PERF %s", json.dumps(record, sort_keys=True, separators=(",", ":")))
    except Exception:
        # Measurement/logging must never change application behavior.
        return
