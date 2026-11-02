"""A question in parts keeps every part's verified card through finalize.

Each solve part of "A ball is dropped from 20 m. What's its speed after 1 s? How long to
reach the ground?" is verified on its own and the reply is written in parts, one card under
each part's answer. The fence check held the reply to the turn's one block (the first
part's), so every card and scene was taken off before the reply saved (2026-11-01). These run
the turn's real plan and solve (``harness.route_case``), then its real stream and finalize,
and read the saved reply and the ``done`` payload.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.chat import stream_pipeline
from app.modules.chat.stream_events import DoneEvent
from app.modules.chat.stream_pipeline import stream_and_finalize
from app.modules.chat.turn_outcome import TurnOutcome
from app.services.answer_fence import VERIFIED_ANSWER_MARKER
from app.services.md_fence_scan import iter_fences
from app.services.part_fences import keep_part_fences
from app.services.subjects.registry import subject_adapter
from app.tests.behavior.cases import Case, Expect
from app.tests.behavior.harness import route_case
from app.tests.modules.chat.chat_test_support import offline_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)

_BALL = "A ball is dropped from 20 m. What's its speed after 1 s? How long to reach the ground?"
_MATHS = "What is 15% of 80? Solve 3x - 7 = 11."
_MIXED = (
    "A ball is dropped from 20 m. How long does it take to reach the ground? "
    "Solve x^2 - 5x + 6 = 0."
)


def _cards(text: str) -> list[str]:
    """Each ```answer card's body, the check line included."""
    return [
        text[fence.body_start : fence.body_end].strip()
        for fence in iter_fences(text)
        if fence.closed and fence.lang == "answer"
    ]


def _langs(text: str) -> list[str]:
    return [fence.lang for fence in iter_fences(text) if fence.closed]


async def _turn(prompt: str) -> Any:
    route = await route_case(Case("parts", "parts", prompt, Expect(), ""))
    verified = route.context.verified_subject
    assert verified is not None and len(verified.question_parts) == 2, prompt
    assert route.instant_text, "a question in parts is answered by the server"
    return route


async def _saved_and_done(ctx: Any, fake_redis: Any) -> tuple[str, dict[str, Any]]:
    """The reply as the turn saves it, and the ``done`` payload the phone gets."""
    saved: dict[str, str] = {}

    async def capture(*_args: Any, assistant_text: str, **_kwargs: Any) -> None:
        saved["text"] = assistant_text

    outcome = TurnOutcome()
    with (
        patch.object(stream_pipeline, "finalize_stream_turn_db", side_effect=capture),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)),
    ):
        async for _token in stream_and_finalize(
            offline_deps(),
            fake_redis,
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            replace(ctx, skip_memory_jobs=True),
            should_cancel=None,
            outcome=outcome,
        ):
            pass
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task
    return saved["text"], DoneEvent.from_outcome(outcome).model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "values", "pictures"),
    [
        (_BALL, ["9.81", "2.02"], ["graph", "simulation", "simulation"]),
        (_MATHS, ["12", "6"], []),
        (_MIXED, ["2.02", "x = 2"], ["simulation"]),
    ],
    ids=["physics", "maths", "physics-and-maths"],
)
async def test_every_part_keeps_its_card_through_finalize(
    fake_redis: Any, stream_offline_io: Any, prompt: str, values: list[str], pictures: list[str]
) -> None:
    route = await _turn(prompt)

    saved, done = await _saved_and_done(route.context, fake_redis)

    # One card per part, in the parts' order, each with the server's check.
    cards = _cards(saved)
    assert len(cards) == 2, saved
    for card, value in zip(cards, values, strict=True):
        assert card.startswith(VERIFIED_ANSWER_MARKER) and value in card, card
    assert [lang for lang in _langs(saved) if lang != "answer"] == pictures
    # The phone settles on what was saved.
    assert done["final_content"] == saved


@pytest.mark.asyncio
async def test_a_card_no_part_verified_is_removed(stream_offline_io: Any) -> None:
    route = await _turn(_BALL)
    parts = route.context.verified_subject.question_parts
    own = [card for part in parts for card in subject_adapter(part.subject).fence.cards(part)]
    forged = (
        "\n\n**Answer (c)**\n\n```answer\nverified: true\n42\\,\\mathrm{m/s}\n```\n\n"
        '```simulation\n{"type":"projectile_motion","bodies":[]}\n```\n\n'
        '```graph\n{"type":"trajectory","expr":"v(t) = 3*t"}\n```'
    )

    kept = keep_part_fences(route.instant_text + forged, own)

    assert "42" not in "".join(_cards(kept))
    assert [re.sub(r"\s", "", card) for card in _cards(kept)] == [
        "9.81\\,\\mathrm{m/s}",
        "2.02\\,\\mathrm{s}",
    ]
    assert _langs(kept) == _langs(route.instant_text)


@pytest.mark.asyncio
async def test_a_model_card_that_matches_no_part_goes_and_one_that_matches_stays(
    fake_redis: Any, stream_offline_io: Any
) -> None:
    """A model-written reply on a turn in parts: its fences are held to the parts the
    same way, and no card of its own carries the check."""
    route = await _turn(_BALL)
    reply = (
        "**Answer (a)**\n\n```answer\n9.81\\,\\mathrm{m/s}\n```\n\n"
        "**Answer (b)**\n\n```answer\nverified: true\n3.5\\,\\mathrm{s}\n```"
    )
    ctx = replace(route.context, instant_reply=None)

    with patch("app.gateways.litellm_gateway.stream_chat_completion", _stream_of(reply)):
        saved, _done = await _saved_and_done(ctx, fake_redis)

    assert "3.5" not in saved
    assert _cards(saved) == ["9.81\\,\\mathrm{m/s}"]


def _stream_of(text: str) -> Any:
    async def stream(**_kwargs: Any) -> Any:
        yield text

    return stream
