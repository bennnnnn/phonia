"""What a machine is running short of: the event loop, the DB pool, threads, SymPy, Redis.

Nothing measured these, so a blocked loop, an exhausted pool or a starved executor
showed only as user-visible timeouts and "Dependency unavailable" lines. A heartbeat
task sleeps 100 ms at a time and records how late it wakes (the loop's lag); every
minute the worst lag and the pools' fill are logged at INFO, and at WARNING (with a
Sentry message) when the loop lagged past 250 ms or the DB pool ran full.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from typing import Any

from app.core import sentry

logger = logging.getLogger(__name__)

_TICK_S = 0.1
_REPORT_EVERY_S = 60.0
LAG_ALERT_MS = 250.0

_task: asyncio.Task[None] | None = None


def _db_pool() -> dict[str, int]:
    from app.core.db import engine

    pool: Any = engine.pool
    checked_out = int(pool.checkedout()) if hasattr(pool, "checkedout") else 0
    capacity = int(pool.size()) + max(0, int(getattr(pool, "_max_overflow", 0)))
    return {"db_checked_out": checked_out, "db_capacity": capacity}


def _default_executor_queue() -> int | None:
    executor = getattr(asyncio.get_running_loop(), "_default_executor", None)
    queue = getattr(executor, "_work_queue", None)
    return queue.qsize() if queue is not None else None


def _sympy_free() -> int | None:
    from app.core.sympy_executor import get_sympy_executor

    return get_sympy_executor().free_slots()


def _documents_free() -> int | None:
    from app.core.document_executor import get_document_executor

    return get_document_executor().free_slots()


def _blocking_running() -> dict[str, int]:
    from app.core import blocking

    return {kind: count for kind, count in blocking.running().items() if count}


def _redis_in_use() -> int | None:
    from app.core.redis import get_redis_client

    pool = get_redis_client().connection_pool
    in_use = getattr(pool, "_in_use_connections", None)
    return len(in_use) if in_use is not None else None


_PROBES: tuple[tuple[str, Callable[[], object]], ...] = (
    ("executor_queue", _default_executor_queue),
    ("blocking_running", _blocking_running),
    ("sympy_free", _sympy_free),
    ("documents_free", _documents_free),
    ("redis_in_use", _redis_in_use),
)
# Gauges a product module owns (open chat sockets), handed in at start-up: core
# does not import modules.
_extra_probes: dict[str, Callable[[], object]] = {}


def snapshot() -> dict[str, object]:
    """The pools' fill right now; a probe that fails is left out, never raised."""
    values: dict[str, object] = {}
    try:
        values.update(_db_pool())
    except Exception:
        logger.debug("db pool probe failed", exc_info=True)
    for name, probe in (*_PROBES, *_extra_probes.items()):
        try:
            value = probe()
        except Exception:
            logger.debug("%s probe failed", name, exc_info=True)
            continue
        if value is not None:
            values[name] = value
    return values


def report(max_lag_ms: float) -> dict[str, object]:
    """Log one report; warn when the loop lagged or the DB pool ran full."""
    values = {"loop_lag_max_ms": round(max_lag_ms, 1), **snapshot()}
    line = " ".join(f"{key}={value}" for key, value in values.items())
    checked_out, capacity = values.get("db_checked_out"), values.get("db_capacity")
    pool_full = (
        isinstance(checked_out, int) and isinstance(capacity, int) and checked_out >= capacity
    )
    if max_lag_ms >= LAG_ALERT_MS or pool_full:
        logger.warning("Saturation: %s", line)
        reason = "event loop lag" if max_lag_ms >= LAG_ALERT_MS else "DB pool full"
        sentry.report_message(f"Saturation: {reason}", level="warning")
    else:
        logger.info("Saturation: %s", line)
    return values


async def _monitor() -> None:
    loop = asyncio.get_running_loop()
    max_lag_ms = 0.0
    next_report = loop.time() + _REPORT_EVERY_S
    while True:
        started = loop.time()
        await asyncio.sleep(_TICK_S)
        max_lag_ms = max(max_lag_ms, (loop.time() - started - _TICK_S) * 1000)
        if loop.time() >= next_report:
            report(max_lag_ms)
            max_lag_ms = 0.0
            next_report = loop.time() + _REPORT_EVERY_S


def start_saturation_monitor(probes: Mapping[str, Callable[[], object]] | None = None) -> None:
    """Start the heartbeat on this process's loop (idempotent); ``probes`` adds gauges."""
    global _task
    _extra_probes.update(probes or {})
    if _task is None or _task.done():
        _task = asyncio.create_task(_monitor(), name="saturation_monitor")


async def stop_saturation_monitor() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None
