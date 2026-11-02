"""The SymPy executor the tests run: threads in this process, no worker processes.

Production's ``ProcessPoolSympyExecutor`` starts real worker processes (and on macOS leaks
named semaphores). Tests verify the timeout fallback, not the kill, so a dedicated thread
pool is enough. It lived in ``core/``; nothing in production uses it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from app.core.sympy_executor import (
    DEFAULT_SYMPY_QUEUE_WAIT_SECONDS,
    BoundedSympyExecutor,
    WorkerBusyError,
    _clamp_workers,
)
from app.core.sympy_worker_process import wait_until_started

_T = TypeVar("_T")


class ThreadSympyExecutor(BoundedSympyExecutor):
    """In-process thread-based executor — for tests (monkeypatch-friendly).

    Uses a dedicated thread pool (NOT the shared default) so SymPy work is
    still isolated from other ``to_thread`` callers. No hard kill on
    timeout — the thread keeps running — but tests verify the
    timeout-fallback behavior, not the kill itself.
    """

    def __init__(
        self,
        max_workers: int = 1,
        *,
        queue_wait_seconds: float = DEFAULT_SYMPY_QUEUE_WAIT_SECONDS,
    ) -> None:
        self._max_workers = _clamp_workers(max_workers)
        self._queue_wait_seconds = queue_wait_seconds
        self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

    @property
    def max_workers(self) -> int:
        return self._max_workers

    async def run(
        self,
        fn: Callable[..., _T],
        *args: Any,
        timeout: float,  # noqa: ASYNC109 - we IMPLEMENT the timeout, not consume it
    ) -> _T:
        future = self._pool.submit(fn, *args)
        if not await wait_until_started(future, self._queue_wait_seconds):
            future.cancel()
            raise WorkerBusyError("SymPy worker slot wait timed out")
        afut = asyncio.wrap_future(future)
        try:
            async with asyncio.timeout(timeout):
                return await afut
        except TimeoutError:
            raise

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
