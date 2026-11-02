"""Background task tracking / shutdown drain tests."""

import asyncio

import pytest

from app.core import background_tasks


@pytest.mark.asyncio
async def test_drain_background_tasks_awaits_in_flight():
    gate = asyncio.Event()
    done = asyncio.Event()

    async def work():
        await gate.wait()
        done.set()

    background_tasks.create_background_task(work(), name="test-drain")
    drain = asyncio.create_task(background_tasks.drain_background_tasks(timeout_seconds=2.0))
    await asyncio.sleep(0)
    assert not done.is_set()
    gate.set()
    await drain
    assert done.is_set()


@pytest.mark.asyncio
async def test_drain_background_tasks_cancels_on_timeout():
    hang = asyncio.Event()

    async def work():
        await hang.wait()

    task = background_tasks.create_background_task(work(), name="test-drain-timeout")
    await background_tasks.drain_background_tasks(timeout_seconds=0.05)
    assert task.cancelled() or task.done()
