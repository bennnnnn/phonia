"""Waiting on a condition in the event loop instead of betting on a sleep.

A fixed ``sleep(0.05)`` before an assert fails on a busy runner, and before a negative
check it passes wrongly (code-health audit TEST-04). ``wait_until`` polls until the
condition holds and fails only after a bound far past any healthy run, so the bound is
never what a test measures.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable


async def wait_until(
    predicate: Callable[[], object | Awaitable[object]], *, within: float = 5.0
) -> None:
    """Return once ``predicate()`` is true; an awaitable answer is awaited first."""
    try:
        async with asyncio.timeout(within):
            while True:
                answer = predicate()
                if inspect.isawaitable(answer):
                    answer = await answer
                if answer:
                    return
                await asyncio.sleep(0.01)
    except TimeoutError:
        raise AssertionError(f"still false after {within:g}s") from None
