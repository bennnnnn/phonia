"""One SymPy slot per user per machine, and a cancelled solve finishes before its slot frees.

Three chats sending pathological expressions held all three slots, so every other
maths, physics and chemistry turn on the machine waited two seconds and went out
unverified. These run on the executor's in-process path (no worker processes), which
schedules exactly as the process pool does.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from unittest.mock import AsyncMock, patch

import pytest

from app.core.log_context import bound_log_ids
from app.core.sympy_executor import ProcessPoolSympyExecutor


def _add(a: int, b: int) -> int:
    return a + b


def _executor(queue_wait_seconds: float = 0.3) -> ProcessPoolSympyExecutor:
    executor = ProcessPoolSympyExecutor(max_workers=3, queue_wait_seconds=queue_wait_seconds)
    executor._arm_in_process_fallback()
    return executor


async def test_a_user_holds_one_slot_at_a_time_and_others_still_run() -> None:
    executor = _executor()
    started, release = threading.Event(), threading.Event()

    def hold() -> str:
        started.set()
        release.wait(5)
        return "held"

    try:
        with bound_log_ids(user_id="alice"):
            first = asyncio.create_task(executor.run(hold, timeout=10))
            await asyncio.to_thread(started.wait, 5)
            # Alice's second solve waits for her first and gives up at the queue wait.
            with pytest.raises(TimeoutError):
                await executor.run(_add, 1, 2, timeout=5)
        with bound_log_ids(user_id="bob"):
            assert await executor.run(_add, 1, 2, timeout=5) == 3
        release.set()
        assert await first == "held"
        with bound_log_ids(user_id="alice"):
            assert await executor.run(_add, 2, 2, timeout=5) == 4
    finally:
        release.set()
        executor.shutdown()


async def test_a_users_next_solve_runs_once_the_first_ends_within_the_wait() -> None:
    executor = _executor(queue_wait_seconds=2.0)
    started, release = threading.Event(), threading.Event()

    def hold() -> str:
        started.set()
        release.wait(5)
        return "first"

    try:
        with bound_log_ids(user_id="alice"):
            first = asyncio.create_task(executor.run(hold, timeout=10))
            await asyncio.to_thread(started.wait, 5)
            second = asyncio.create_task(executor.run(_add, 1, 1, timeout=5))
            await asyncio.sleep(0.05)
            assert not second.done()
            release.set()
            assert (await first, await second) == ("first", 2)
    finally:
        release.set()
        executor.shutdown()


async def test_calls_with_no_user_are_not_serialized() -> None:
    executor = _executor()
    try:
        results = await asyncio.gather(*(executor.run(_add, i, 1, timeout=5) for i in range(3)))
        assert results == [1, 2, 3]
    finally:
        executor.shutdown()


async def test_a_cancelled_callers_job_frees_its_slot_and_user_when_it_ends() -> None:
    executor = ProcessPoolSympyExecutor(max_workers=1, queue_wait_seconds=0.1)
    free = executor._free_queue()
    slot = free.get_nowait()
    job: Future[int] = Future()
    job.set_running_or_notify_cancel()
    loop = asyncio.get_running_loop()
    await executor._claim_owner("alice", 0.1)

    executor._finish_later(slot, "alice", job, deadline=loop.time() + 5)
    await asyncio.sleep(0.05)
    assert free.empty() and "alice" in executor._owner_jobs

    job.set_result(7)
    await asyncio.sleep(0.05)
    assert free.get_nowait() == slot
    assert "alice" not in executor._owner_jobs


async def test_a_cancelled_callers_job_past_its_deadline_is_killed() -> None:
    executor = ProcessPoolSympyExecutor(max_workers=1, queue_wait_seconds=0.1)
    free = executor._free_queue()
    slot = free.get_nowait()
    job: Future[int] = Future()
    job.set_running_or_notify_cancel()
    loop = asyncio.get_running_loop()

    async def kill(_slot: int) -> None:
        job.set_exception(RuntimeError("worker killed"))

    with patch.object(executor, "_kill_slot_async", AsyncMock(side_effect=kill)) as killed:
        executor._finish_later(slot, None, job, deadline=loop.time() + 0.1)
        await asyncio.sleep(0.3)

    killed.assert_awaited_once_with(slot)
    assert free.get_nowait() == slot
