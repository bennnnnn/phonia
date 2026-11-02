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


async def test_finish_despite_cancel_finishes_the_save_then_passes_the_cancel_on() -> None:
    from app.core.aio import finish_despite_cancel

    started, release = asyncio.Event(), asyncio.Event()
    marked: list[str] = []

    async def save() -> str:
        started.set()
        await release.wait()
        return "saved"

    caller = asyncio.create_task(finish_despite_cancel(save(), then=lambda: marked.append("kept")))
    await started.wait()
    caller.cancel()
    await asyncio.sleep(0)
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await caller
    assert marked == ["kept"]


@pytest.mark.parametrize("error", [ValueError("db down"), asyncio.CancelledError()])
async def test_finish_despite_cancel_raises_the_saves_own_failure_unmarked(
    error: BaseException,
) -> None:
    from app.core.aio import finish_despite_cancel

    marked: list[str] = []

    async def save() -> str:
        raise error

    with pytest.raises(type(error)):
        await finish_despite_cancel(save(), then=lambda: marked.append("kept"))
    assert marked == []


async def test_finish_despite_cancel_returns_the_result_when_nothing_cancels() -> None:
    from app.core.aio import finish_despite_cancel

    async def save() -> int:
        return 7

    assert await finish_despite_cancel(save()) == 7
