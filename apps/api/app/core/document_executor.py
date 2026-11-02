"""Bounded, killable processes for parsing documents and rendering PDF pages.

A parse ran on a default-executor thread under a timeout that ended only the await:
pypdf kept parsing (holding the GIL), five such threads filled the executor that R2,
thumbnails and sign-in share, and an index job retried the same file twice more on top
(code-health audit LEAK-02). This is the SymPy executor's class, a separate instance,
so a slow PDF never takes a maths slot and a timeout kills its worker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.sympy_executor import BoundedSympyExecutor, ProcessPoolSympyExecutor

_executor: BoundedSympyExecutor | None = None


def get_document_executor() -> BoundedSympyExecutor:
    global _executor
    if _executor is None:
        from app.core.config import get_settings

        settings = get_settings()
        _executor = ProcessPoolSympyExecutor(
            max_workers=settings.document_pool_workers,
            queue_wait_seconds=settings.document_pool_queue_wait_seconds,
            per_user=False,
        )
    return _executor


def set_document_executor(executor: BoundedSympyExecutor | None) -> None:
    """Swap the executor (tests); the previous one is shut down. None resets."""
    global _executor
    if _executor is not None:
        _executor.shutdown()
    _executor = executor


def shutdown_document_executor() -> None:
    """Stop the document workers when the process exits."""
    set_document_executor(None)


async def run_document[T](
    fn: Callable[..., T],
    *args: Any,
    timeout: float,  # noqa: ASYNC109 - the executor implements it
) -> T:
    """``fn(*args)`` in a document worker; past ``timeout`` the worker is killed.

    Raises ``TimeoutError`` past the deadline, or when no worker came free in the
    queue wait.
    """
    return await get_document_executor().run(fn, *args, timeout=timeout)
