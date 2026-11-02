"""``gather_or_cancel``: a failed branch cancels its siblings and raises its own error."""

from __future__ import annotations

import asyncio

import pytest

from app.core.aio import gather_or_cancel


async def test_a_failed_branch_cancels_the_others() -> None:
    started = asyncio.Event()
    cancelled = False

    async def paid_call() -> str:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return "late"

    async def fails() -> str:
        await started.wait()
        raise ValueError("the other branch failed")

    with pytest.raises(ValueError, match="other branch"):
        await gather_or_cancel(paid_call(), fails())
    assert cancelled


async def test_results_come_back_in_order() -> None:
    async def value(item: int, delay: float) -> int:
        await asyncio.sleep(delay)
        return item

    first, second, third = await gather_or_cancel(value(1, 0.02), value(2, 0.0), value(3, 0.01))
    assert (first, second, third) == (1, 2, 3)
    assert await gather_or_cancel(*(value(n, 0) for n in range(5))) == [0, 1, 2, 3, 4]
