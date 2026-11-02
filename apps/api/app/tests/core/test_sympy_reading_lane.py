"""Slow solves cannot starve a turn's message reading of a SymPy slot.

Every turn reads its message in the pool; it shared the three slots with real solves,
so three slow solves made every turn on the machine wait the 2 s slot wait and then
route without its subject reading. These run on the executor's in-process path (no
worker processes), which takes slots exactly as the process pool does.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, patch

import pytest

from app.core import readings, sympy_executor
from app.core.log_context import bound_log_ids
from app.core.sympy_executor import ProcessPoolSympyExecutor
from app.core.sympy_slots import SlotPool
from app.tests.sympy_support import ThreadSympyExecutor


def _add(a: int, b: int) -> int:
    return a + b


def _executor(reserved: int, queue_wait_seconds: float = 0.3) -> ProcessPoolSympyExecutor:
    executor = ProcessPoolSympyExecutor(
        max_workers=3, queue_wait_seconds=queue_wait_seconds, reserved_for_readings=reserved
    )
    executor._arm_in_process_fallback()
    return executor


async def _hold_slots(executor: ProcessPoolSympyExecutor, users: list[str], release):
    started = [threading.Event() for _ in users]
    tasks = []
    for user, event in zip(users, started, strict=True):

        def hold(event: threading.Event = event) -> str:
            event.set()
            release.wait(5)
            return "held"

        with bound_log_ids(user_id=user):
            tasks.append(asyncio.create_task(executor.run(hold, timeout=10)))
        await asyncio.to_thread(event.wait, 5)
    return tasks


@pytest.mark.parametrize(
    "reserved, solves_running, reading_runs",
    [
        (1, 2, True),  # solves fill their two slots; the reading takes the third
        (0, 3, False),  # no reserve: three slow solves starve the reading
    ],
)
async def test_slow_solves_leave_a_slot_for_readings(reserved, solves_running, reading_runs):
    executor = _executor(reserved)
    release = threading.Event()
    try:
        held = await _hold_slots(executor, [f"u{n}" for n in range(solves_running)], release)
        if reserved:
            # A further solve may not take the reserved slot.
            with bound_log_ids(user_id="late"), pytest.raises(TimeoutError):
                await executor.run(_add, 1, 1, timeout=5)
        with bound_log_ids(user_id="reader"):
            if reading_runs:
                assert await executor.run_reading(_add, 2, 3, timeout=5) == 5
            else:
                with pytest.raises(TimeoutError):
                    await executor.run_reading(_add, 2, 3, timeout=5)
        release.set()
        assert await asyncio.gather(*held) == ["held"] * solves_running
    finally:
        release.set()
        executor.shutdown()


async def test_a_users_reading_does_not_wait_behind_their_own_solve():
    executor = _executor(reserved=1)
    release = threading.Event()
    try:
        held = await _hold_slots(executor, ["alice"], release)
        with bound_log_ids(user_id="alice"):
            assert await executor.run_reading(_add, 1, 2, timeout=5) == 3
            # Her next solve still waits for her first one.
            with pytest.raises(TimeoutError):
                await executor.run(_add, 1, 2, timeout=5)
        release.set()
        await asyncio.gather(*held)
    finally:
        release.set()
        executor.shutdown()


async def test_readings_use_idle_solve_slots_too():
    executor = _executor(reserved=1)
    try:
        results = await asyncio.gather(
            *(executor.run_reading(_add, n, 0, timeout=5) for n in range(3))
        )
        assert results == [0, 1, 2]
    finally:
        executor.shutdown()


def test_slot_pool_caps_solves_but_not_readings():
    pool = SlotPool(3, reserved_for_readings=1)
    solves = [pool.get_nowait("solve"), pool.get_nowait("solve")]
    with pytest.raises(asyncio.QueueEmpty):
        pool.get_nowait("solve")
    reading = pool.get_nowait("reading")
    assert pool.empty()
    pool.put_nowait(solves[0])
    assert pool.get_nowait("solve") == solves[0]
    assert sorted([*solves, reading]) == [0, 1, 2]


@pytest.mark.parametrize("slots, reserved, solve_cap", [(1, 1, 1), (2, 5, 1), (3, 0, 3)])
def test_slot_pool_always_leaves_solves_a_slot(slots, reserved, solve_cap):
    pool = SlotPool(slots, reserved_for_readings=reserved)
    for _ in range(solve_cap):
        pool.get_nowait("solve")
    with pytest.raises(asyncio.QueueEmpty):
        pool.get_nowait("solve")


async def test_a_freed_slot_goes_to_a_waiting_reading_before_a_waiting_solve():
    pool = SlotPool(1)
    slot = pool.get_nowait("solve")
    solve = asyncio.create_task(pool.get("solve"))
    await asyncio.sleep(0)
    reading = asyncio.create_task(pool.get("reading"))
    await asyncio.sleep(0)

    pool.put_nowait(slot)
    assert await reading == slot
    assert not solve.done()
    pool.put_nowait(slot)
    assert await solve == slot


async def test_a_waiter_that_gives_up_takes_no_slot():
    pool = SlotPool(1)
    slot = pool.get_nowait("solve")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(pool.get("reading"), timeout=0.01)
    pool.put_nowait(slot)
    assert pool.qsize() == 1


async def test_a_slot_handed_to_a_cancelled_waiter_comes_back():
    pool = SlotPool(1)
    slot = pool.get_nowait("solve")
    waiter = asyncio.create_task(pool.get("reading"))
    await asyncio.sleep(0)
    pool.put_nowait(slot)  # handed to the waiter, which is cancelled before it runs
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert pool.qsize() == 1


async def test_run_sympy_reading_lane_falls_back_to_run_on_a_plain_executor():
    executor = ThreadSympyExecutor(max_workers=1)
    sympy_executor.set_sympy_executor(executor)
    try:
        assert await sympy_executor.run_sympy(_add, 4, 5, timeout=5, lane="reading") == 9
    finally:
        sympy_executor.set_sympy_executor(None)


async def test_read_off_loop_reads_on_the_reading_lane():
    readings.begin_turn()
    pool = AsyncMock(return_value=(1, {}))
    with patch("app.core.sympy_executor.run_sympy", pool):
        assert await readings.read_off_loop(_add, 1, 0, timeout=3) == 1
    assert pool.await_args.kwargs["lane"] == "reading"
