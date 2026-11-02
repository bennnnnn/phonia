"""``until_client_leaves``: the work runs while the client stays, and stops when it goes."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from starlette.requests import Request

from app.core.client_disconnect import ClientLeft, until_client_leaves


class _Connection:
    """A request whose client hangs up after ``stays`` checks."""

    def __init__(self, stays: int) -> None:
        self.stays = stays
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return self.checks > self.stays


def _request(stays: int) -> Request:
    return cast(Request, _Connection(stays))


async def test_the_work_finishes_while_the_client_stays() -> None:
    async def work() -> str:
        await asyncio.sleep(0.03)
        return "picture"

    assert await until_client_leaves(_request(10**6), work(), poll_seconds=0.01) == "picture"


async def test_a_client_that_leaves_cancels_the_work_after_its_cleanup() -> None:
    cleaned: list[str] = []

    async def work() -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cleaned.append("slot given back")
            raise
        return "late"

    with pytest.raises(ClientLeft):
        await until_client_leaves(_request(2), work(), poll_seconds=0.01)
    assert cleaned == ["slot given back"]


async def test_a_failure_of_the_work_is_raised_as_it_is() -> None:
    async def work() -> Any:
        raise ValueError("provider down")

    with pytest.raises(ValueError, match="provider down"):
        await until_client_leaves(_request(10**6), work(), poll_seconds=0.01)


async def test_a_cancelled_handler_stops_the_work_with_it() -> None:
    stopped = asyncio.Event()

    async def work() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stopped.set()
            raise

    handler = asyncio.create_task(until_client_leaves(_request(10**6), work(), poll_seconds=0.01))
    await asyncio.sleep(0.02)
    handler.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handler
    await asyncio.wait_for(stopped.wait(), timeout=1)
