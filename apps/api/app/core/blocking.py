"""Bounded thread pools for blocking calls, one per kind of call; never the default executor.

``asyncio.to_thread`` runs on the loop's default executor: ``min(32, cpus + 4)`` threads,
five on a one-CPU machine, shared by every caller. R2 calls with their retries,
thumbnail resizes, Google sign-in and a stalled DuckDuckGo search queued behind one
another, and a wait that timed out left its thread running (code-health audit LEAK-02).
Each kind gets its own small pool, so one kind filling up delays only itself.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

Kind = Literal["storage", "images", "sign_in", "web_search", "processes"]

# Threads per kind. R2 calls are the most frequent and mostly wait on the network;
# ``processes`` reaps a killed pool worker (a join of up to a second).
_SIZES: dict[Kind, int] = {
    "storage": 8,
    "images": 2,
    "sign_in": 2,
    "web_search": 2,
    "processes": 2,
}

_pools: dict[Kind, ThreadPoolExecutor] = {}
_running: dict[Kind, int] = dict.fromkeys(_SIZES, 0)
_lock = threading.Lock()


def _pool(kind: Kind) -> ThreadPoolExecutor:
    with _lock:
        pool = _pools.get(kind)
        if pool is None:
            pool = ThreadPoolExecutor(max_workers=_SIZES[kind], thread_name_prefix=kind)
            _pools[kind] = pool
        return pool


def _counted[T](kind: Kind, call: Callable[[], T]) -> T:
    with _lock:
        _running[kind] += 1
    try:
        return call()
    finally:
        with _lock:
            _running[kind] -= 1


async def run_blocking[T](kind: Kind, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """``fn(*args, **kwargs)`` on ``kind``'s pool, with this task's context (log ids)."""
    context = contextvars.copy_context()
    call = functools.partial(context.run, fn, *args, **kwargs)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool(kind), _counted, kind, call)


def has_room(kind: Kind) -> bool:
    """A thread of ``kind``'s pool is free now: a caller that would rather skip than queue."""
    with _lock:
        return _running[kind] < _SIZES[kind]


def running() -> dict[Kind, int]:
    """Calls running per kind, for the saturation report."""
    with _lock:
        return dict(_running)


def shutdown() -> None:
    """Stop the pools at process exit; a running call finishes on its own thread."""
    with _lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.shutdown(wait=False, cancel_futures=True)
