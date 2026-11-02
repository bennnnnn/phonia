"""The finalize passes run on every reply, on the event loop: together they stay linear.

A reply is model text, and a model writes what it is asked to: a long run of spaces,
blank lines or backslashes, one long line with an emoji in every sentence. The
couldn't-verify sentence's pattern retried every split of a run of spaces from every start
in it (800 spaces took 2 s, 1,600 took 19 s); the worked-heading patterns ran ``\\s*`` over
every blank line below each line start; the display-maths scan counted back over a run of
backslashes from each of them; the emoji pass searched the whole line again for the word
before each emoji. The budget is loose on purpose: every pass together finishes these
replies in tens of milliseconds, and the super-linear ones took seconds to hours.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.finalize_passes import FinalizeState, run_finalize_passes
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.tests.modules.chat.chat_test_support import turn_deps

_SIZE = 24_000
_BUDGET_SECONDS = 1.0


def _repeat(unit: str, size: int) -> str:
    return (unit * (size // len(unit) + 1))[:size]


_REPLIES = {
    "a run of spaces": "The answer is" + " " * _SIZE + "42.",
    "a run of tabs": "a" + "\t" * _SIZE + "b",
    "wide padded lines": _repeat("x" + " " * 200 + "\n", _SIZE),
    "blank lines": "Intro" + "\n" * (2 * _SIZE) + "End.",
    "backslashes": "\\" * _SIZE,
    "an emoji in every sentence": _repeat("✅ Verified the totals. ", 2 * _SIZE),
    "a long word before an emoji": "a" * _SIZE + "!✅ Next",
    "blanks after an emoji": "🚀 Launch" + " " * _SIZE + "now",
}


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


def _state(text: str) -> FinalizeState:
    user = User(id=uuid4(), name="Bini", plan="pro", emoji_use="some", locale="en")
    ctx = StreamContext(
        user_id=user.id,
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "Explain this"}],
        run_title=False,
        user_message_content="Explain this",
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


@pytest.mark.wall_clock
@pytest.mark.parametrize("name", _REPLIES)
async def test_every_finalize_pass_together_stays_fast_on_a_hostile_reply(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _inline)
    state = _state(_REPLIES[name])
    start = time.perf_counter()
    assert await run_finalize_passes(state) is True
    elapsed = time.perf_counter() - start
    assert elapsed < _BUDGET_SECONDS, f"{name}: {elapsed:.2f}s"
