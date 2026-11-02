"""Readings: read once off the event loop, kept for the turn, declined after a timeout.

A turn asks the same reading of its message from routing, the prompt builder, the
subject fetch, the tool loop and the finalize passes; the readers parse with SymPy
and are unbounded on a hostile message (code-health audit SCALE-01).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from app.core import readings
from app.core.readings import begin_turn, first_read, read_off_loop, reading

CALLS: list[str] = []


@reading(declined=None)
def shout(text: str, *, loud: bool = True) -> dict[str, str]:
    CALLS.append(text)
    return {"said": text.upper() if loud else text}


@reading(declined=lambda text: f"declined {text}")
def spelled(text: str) -> str:
    CALLS.append(text)
    return text


def read_both(first: str, second: str) -> str:
    """What a turn's pool read does: ask several readings, return something."""
    shout(first)
    spelled(second)
    return "done"


def _slow_read(_text: str) -> str:
    raise TimeoutError("the reader ran past its budget")


@pytest.fixture(autouse=True)
def _no_calls_yet() -> None:
    CALLS.clear()


async def test_a_reading_is_computed_once_a_turn_and_each_caller_gets_its_own_copy() -> None:
    begin_turn()
    first = shout("hi")
    first["said"] = "changed"
    again = shout("hi", loud=True)

    assert again == {"said": "HI"}
    assert CALLS == ["hi"]


async def test_the_next_turn_reads_again() -> None:
    begin_turn()
    shout("hi")
    begin_turn()
    shout("hi")
    assert CALLS == ["hi", "hi"]


async def test_a_pool_read_keeps_every_reading_it_made_for_the_sync_callers() -> None:
    begin_turn()
    assert await read_off_loop(read_both, "a", "b", timeout=5) == "done"
    CALLS.clear()

    assert shout("a") == {"said": "A"}
    assert spelled("b") == "b"
    assert CALLS == []


async def test_a_read_reading_answers_without_the_pool() -> None:
    begin_turn()
    shout("hi")
    with patch("app.core.sympy_executor.run_sympy") as pool:
        assert await read_off_loop(shout, "hi", timeout=5) == {"said": "HI"}
    pool.assert_not_called()


async def test_a_timed_out_read_declines_every_later_reading_of_the_turn() -> None:
    begin_turn()
    assert await read_off_loop(_slow_read, "x", timeout=5) is None

    assert shout("never read") is None
    assert spelled("y") == "declined y"
    assert CALLS == []
    with patch("app.core.sympy_executor.run_sympy") as pool:
        assert await read_off_loop(read_both, "a", "b", timeout=5) is None
    pool.assert_not_called()


async def test_a_read_outside_a_turn_starts_the_readings_it_keeps() -> None:
    async def request() -> None:
        await read_off_loop(read_both, "a", "b", timeout=5)
        CALLS.clear()
        shout("a")
        assert CALLS == []

    await asyncio.create_task(request())


def test_readings_outside_a_turn_compute_every_time() -> None:
    shout("hi")
    shout("hi")
    assert CALLS == ["hi", "hi"]


async def test_first_read_is_true_once_a_turn() -> None:
    begin_turn()
    assert first_read(("turn_message", "hi")) is True
    assert first_read(("turn_message", "hi")) is False
    begin_turn()
    assert first_read(("turn_message", "hi")) is True


def test_an_lru_cache_under_a_reading_keeps_its_controls() -> None:
    from app.modules.physics.extract import needs_physics

    needs_physics.cache_clear()
    assert needs_physics.cache_info().currsize == 0


async def test_a_missed_reading_inside_a_read_turn_is_reported_with_its_caller() -> None:
    """Production code (here, a coroutine whose module is not a test's) reading on the loop."""
    seen: list[tuple[str, str]] = []
    namespace: dict[str, Any] = {"__name__": "app.modules.fake_turn", "shout": shout}
    exec(  # noqa: S102 - defines a coroutine whose frames carry a production module name
        "async def prepare():\n    return shout('missed')\n",
        namespace,
    )
    begin_turn()
    with patch.object(
        readings, "on_loop_hooks", [lambda name, caller: seen.append((name, caller))]
    ):
        await namespace["prepare"]()

    assert seen == [(f"{__name__}.shout", "app.modules.fake_turn.prepare")]
