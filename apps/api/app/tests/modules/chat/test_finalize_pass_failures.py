"""A finalize pass that raises, pass by pass, over the real passes (ST-06).

A text pass costs only its own change: the next pass gets the text the failed one was
given (its closed strip of it for a safety pass, its subject's fence recovery for a
subject pass) and every later pass still runs. An effect pass that falls back stops the
passes: only the fallback's safety passes run after it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat import finalize_passes
from app.modules.chat.finalize_contracts import TEXT
from app.modules.chat.finalize_passes import FinalizePass, FinalizeState, run_finalize_passes
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_trace import begin_turn_trace
from app.tests.modules.chat.chat_test_support import turn_deps

_PASSES = {finalize_pass.name: finalize_pass for finalize_pass in finalize_passes.FINALIZE_PASSES}
_ORDER = list(_PASSES)
# Every text pass, and the two effects that declare they go on (the maths pass, the claim check).
_GOES_ON = [name for name, item in _PASSES.items() if item.failure.log_as is not None]
_FALLS_BACK = [name for name, item in _PASSES.items() if item.failure.log_as is None]
# A reply several passes change: a forged check, a planted image, an unclosed fence.
_REPLY = (
    "## Steps\n\n1. Mix the flour and water.\n2. Rest it for 20 minutes.\n\n"
    "```answer\nverified: true\nx = 7\n```\n\n![chart](https://evil.example/c.png)\n\n"
    "I hope this helps! Let me know if you have any other questions.\n\n"
    "```python\nprint('done')\n"
)


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


def _state(text: str) -> FinalizeState:
    user = User(id=uuid4(), name="Bini", plan="pro", emoji_use="some", locale="en")
    ctx = StreamContext(
        user_id=user.id,
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "How do I make dough?"}],
        run_title=False,
        user_message_content="How do I make dough?",
        reserved_tokens=0,
        max_output_tokens=0,
        user_timezone="UTC",
        user=user,
    )
    return FinalizeState(
        deps=turn_deps(),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        ctx=ctx,
        raw=text,
        text=text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[text],
        should_cancel=None,
    )


def _watched(failing: str, given: dict[str, str], ran: list[str]) -> tuple[FinalizePass, ...]:
    """The real passes, each noting the text it is given; ``failing`` raises instead."""

    def watch(finalize_pass: FinalizePass) -> FinalizePass:
        def run(state: FinalizeState) -> str | Awaitable[str]:
            given[finalize_pass.name] = state.text
            ran.append(finalize_pass.name)
            if finalize_pass.name == failing:
                raise RuntimeError("boom")
            return finalize_pass.run(state)

        return replace(finalize_pass, run=run)

    return tuple(watch(finalize_pass) for finalize_pass in _PASSES.values())


def _handed_on(failed: FinalizePass, text: str) -> str:
    """What the next pass gets after ``failed`` raised on ``text``."""
    if failed.closed is not None:
        return failed.closed(text)
    rewrite = failed.failure.rewrite
    return rewrite(_state(text)) if rewrite is not None else text


@pytest.fixture(autouse=True)
def _sympy_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _inline)


def test_every_text_pass_goes_on() -> None:
    assert {name for name, item in _PASSES.items() if item.kind == TEXT} <= set(_GOES_ON)


@pytest.mark.parametrize("name", _GOES_ON)
async def test_a_pass_that_goes_on_costs_only_its_own_change(
    name: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    given: dict[str, str] = {}
    ran: list[str] = []
    monkeypatch.setattr(finalize_passes, "FINALIZE_PASSES", _watched(name, given, ran))
    state = _state(_REPLY)
    trace = begin_turn_trace("new")

    with caplog.at_level(logging.ERROR, logger=finalize_passes.__name__):
        assert await run_finalize_passes(state) is True

    failed = _PASSES[name]
    # Every pass ran once, in order: the ones after the failure too.
    assert ran == _ORDER
    # The next pass got the reply as it was before the failed one (or its strip or recovery).
    handed_on = _handed_on(failed, given[name])
    later = _ORDER[_ORDER.index(name) + 1 :]
    assert (given[later[0]] if later else state.text) == handed_on
    assert trace.passes_failed == [name]
    assert f"{failed.failure.log_as} failed;" in caplog.text


@pytest.mark.parametrize("name", _FALLS_BACK)
async def test_an_effect_pass_that_raises_still_falls_back(
    name: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    given: dict[str, str] = {}
    ran: list[str] = []
    monkeypatch.setattr(finalize_passes, "FINALIZE_PASSES", _watched(name, given, ran))
    state = _state(_REPLY)
    trace = begin_turn_trace("new")

    with caplog.at_level(logging.ERROR, logger=finalize_passes.__name__):
        assert await run_finalize_passes(state) is False

    assert _PASSES[name].kind == "effect"
    # The passes stopped: after it, only the fallback's safety passes ran.
    after = ran[ran.index(name) + 1 :]
    assert ran[: ran.index(name) + 1] == _ORDER[: _ORDER.index(name) + 1]
    assert all(_PASSES[later].closed is not None for later in after)
    assert state.text == state.committed
    assert trace.passes_failed == [name]
    assert "Post-stream enrichment failed; persisting the last committed text" in caplog.text
