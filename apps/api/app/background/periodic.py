"""Shared periodic scheduler loop, Redis lock, and cancellation handling.

Each scheduler keeps its own interval and cycle body so a slow cycle cannot
delay the others. Lock TTL helpers mark the two intended conventions:
hold-across-ticks (bounded work) vs yield-next-tick (unbounded work + refresh).

Every worker runs every loop, out of phase with the others. The lock only
keeps two cycles from overlapping; a finished cycle also leaves a ``:ran``
marker that expires just before the next interval, so a peer whose tick comes
later in the same interval skips it. A cycle runs about once per interval
however many workers there are, not once per worker. The marker is written
only when the cycle ends, so a holder that crashes mid-cycle leaves none and
the next tick after its lock expires runs as before.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.redis import get_redis_client
from app.core.redis_lock import acquire_lock, refresh_lock, release_lock

logger = logging.getLogger(__name__)

# Same idea as core.jobs.worker._HEARTBEAT_STALE_THRESHOLD_S: a started loop
# that is still "running" but no longer checking in is treated as dead. Sleep
# between ticks is chunked so a long interval does not look stale.
_HEARTBEAT_STALE_THRESHOLD_S = 120.0
_HEARTBEAT_SLEEP_CHUNK_S = 30

_tasks: dict[str, asyncio.Task[None]] = {}
_heartbeats: dict[str, float] = {}
# Name of the periodic loop running in this task (set by _loop). Lets a cycle's
# progress keep its own loop's heartbeat fresh without threading the name in.
_current_loop: ContextVar[str | None] = ContextVar("periodic_loop", default=None)


@dataclass(frozen=True, slots=True)
class CycleLock:
    """Lock held for one cycle; refresh during unbounded work."""

    redis: Redis
    key: str
    token: str
    ttl_seconds: int

    async def refresh(self) -> bool:
        """Extend the lock; a successful refresh also counts as loop progress.

        The heartbeat used to move only between cycles, so a cycle longer than
        _HEARTBEAT_STALE_THRESHOLD_S (billing reconcile: one RevenueCat call per
        Pro user) failed the worker's readiness. A cycle that stops refreshing
        still goes stale.
        """
        refreshed = await refresh_lock(self.redis, self.key, self.token, self.ttl_seconds)
        name = _current_loop.get()
        if refreshed and name is not None:
            _touch_heartbeat(name)
        return refreshed


CycleFn = Callable[[Settings, CycleLock], Awaitable[None]]


def lock_ttl_hold_across_ticks(interval_seconds: int) -> int:
    """Bounded cycles: hold longer than one interval so a slow run cannot overlap."""
    return max(interval_seconds * 10, 300)


def lock_ttl_yield_next_tick(interval_seconds: int) -> int:
    """Unbounded cycles: expire before the next tick. Refresh during work.

    Do not raise this past ``interval_seconds`` — a crashed holder would then
    block the following cycle entirely.
    """
    return max(interval_seconds - 30, 60)


def ran_marker_ttl(interval_seconds: int) -> int:
    """How long a finished cycle keeps peers from running it again.

    A tenth of the interval short of it (at least a second), so the worker
    that ran it is never skipped on its own next tick by a few milliseconds of
    clock slop; peers then run the cycle at most about once per interval.
    """
    interval = max(interval_seconds, 1)
    return max(interval - max(interval // 10, 1), 1)


def ran_marker_key(lock_key: str) -> str:
    return f"{lock_key}:ran"


async def _ran_recently(redis: Redis, marker_key: str) -> bool:
    return bool(await redis.get(marker_key))


async def _mark_ran(redis: Redis, marker_key: str, interval_seconds: int) -> None:
    """Best effort: without the marker a peer may run the cycle again this interval."""
    try:
        await redis.set(marker_key, "1", ex=ran_marker_ttl(interval_seconds))
    except (RedisError, OSError) as exc:
        logger.warning("Could not mark %s as run; a peer may repeat it: %r", marker_key, exc)


async def run_locked_cycle(
    *,
    name: str,
    lock_key: str,
    lock_ttl_seconds: int,
    interval_seconds: int,
    enabled: bool,
    fn: CycleFn,
    settings: Settings,
) -> None:
    """Run ``fn`` on one worker at a time, at most about once per ``interval_seconds``.

    The marker is checked before the lock (the common skip costs one GET) and
    again once the lock is held, in case a peer finished in between. A failed
    cycle is marked too: one attempt per interval, as one worker alone makes.
    """
    if not enabled:
        return
    redis = get_redis_client()
    marker_key = ran_marker_key(lock_key)
    if await _ran_recently(redis, marker_key):
        return
    token = await acquire_lock(redis, lock_key, lock_ttl_seconds)
    if not token:
        return
    try:
        if await _ran_recently(redis, marker_key):
            return
        lock = CycleLock(redis=redis, key=lock_key, token=token, ttl_seconds=lock_ttl_seconds)
        try:
            await fn(settings, lock)
        except Exception:
            logger.exception("%s cycle failed", name)
        await _mark_ran(redis, marker_key, interval_seconds)
    finally:
        await release_lock(redis, lock_key, token)


def _touch_heartbeat(name: str) -> None:
    _heartbeats[name] = time.monotonic()


async def _sleep_interval(name: str, interval_seconds: int) -> None:
    remaining = max(interval_seconds, 1)
    while remaining > 0:
        _touch_heartbeat(name)
        chunk = min(_HEARTBEAT_SLEEP_CHUNK_S, remaining)
        await asyncio.sleep(chunk)
        remaining -= chunk


def is_periodic_alive(name: str) -> bool:
    """True when this named loop was started, has not finished, and is checking in."""
    task = _tasks.get(name)
    if task is None or task.done():
        return False
    last = _heartbeats.get(name, 0.0)
    if last == 0.0:
        return True
    return time.monotonic() - last < _HEARTBEAT_STALE_THRESHOLD_S


def started_periodic_unhealthy() -> list[str]:
    """Names of loops that were started but have died or gone stale."""
    return sorted(name for name in _tasks if not is_periodic_alive(name))


def stopped_periodic() -> list[str]:
    """Names of started loops whose task has ended (it crashed or returned).

    Stale is not stopped: a long cycle (a burst of reminder emails) can go
    quiet past the threshold and still finish, so only a dead task means the
    loop will never run again.
    """
    return sorted(name for name, task in _tasks.items() if task.done())


async def start_periodic(
    *,
    name: str,
    interval_seconds: int,
    enabled: bool,
    cycle: Callable[[Settings], Awaitable[None]],
    settings: Settings,
) -> None:
    if not enabled or name in _tasks:
        return

    async def _loop() -> None:
        _current_loop.set(name)
        _touch_heartbeat(name)
        while True:
            _touch_heartbeat(name)
            try:
                await cycle(settings)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s loop error", name)
            await _sleep_interval(name, interval_seconds)

    _heartbeats[name] = 0.0
    _tasks[name] = asyncio.create_task(_loop(), name=f"periodic:{name}")


async def stop_periodic(name: str) -> None:
    task = _tasks.pop(name, None)
    _heartbeats.pop(name, None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
