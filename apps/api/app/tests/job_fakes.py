"""Capture the jobs code queues, whether it calls ``jobs.enqueue`` or ``jobs.enqueue_many``.

A finished turn queues its jobs in one pipeline (``enqueue_many``); a test that
records ``enqueue`` calls sees each of them as one call, as before.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

from app.core.jobs import JobRequest


@contextmanager
def patch_job_enqueue(enqueue: Any = None) -> Iterator[Any]:
    """Route ``enqueue`` and every request of ``enqueue_many`` to ``enqueue`` (a mock)."""
    enqueue = AsyncMock() if enqueue is None else enqueue

    async def enqueue_many(redis: Any, requests: Sequence[JobRequest]) -> list[bool]:
        queued: list[bool] = []
        for request in requests:
            try:
                await enqueue(
                    redis, request.job_type, request.payload, dedupe_key=request.dedupe_key
                )
            except Exception:
                queued.append(False)
            else:
                queued.append(True)
        return queued

    with (
        patch("app.core.jobs.enqueue", enqueue),
        patch("app.core.jobs.enqueue_many", enqueue_many),
    ):
        yield enqueue
