"""Track fire-and-forget asyncio tasks so they aren't dropped mid-flight."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[Any]] = set()


def create_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def drain_background_tasks(*, timeout_seconds: float = 10.0) -> None:
    """Await in-flight background tasks on shutdown (best-effort)."""
    pending = [task for task in _background_tasks if not task.done()]
    if not pending:
        return
    logger.info("Draining %d background task(s) (timeout=%.1fs)", len(pending), timeout_seconds)
    done, still = await asyncio.wait(pending, timeout=timeout_seconds)
    for task in still:
        task.cancel()
    if still:
        await asyncio.gather(*still, return_exceptions=True)
    _ = done
