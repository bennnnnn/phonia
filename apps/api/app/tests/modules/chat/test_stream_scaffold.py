"""S7.6: verified-solve markers and text-written tool calls never reach the live stream."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.stream_scaffold import MAX_HELD_CALL_CHARS, ScaffoldFilter
from app.modules.chat.turn_outcome import TurnOutcome
from app.services.solving import VERIFIED_MATH_BEGIN, VERIFIED_MATH_END, VERIFIED_PHYSICS_END
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import offline_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)

_LEAKS = ("[BEGIN VERIFIED", "[END VERIFIED", "!function_call", '"name": "graph"')


def _filtered(chunks: list[str]) -> tuple[list[str], str]:
    scaffold = ScaffoldFilter()
    out = [scaffold.feed(chunk) for chunk in chunks]
    out.append(scaffold.flush())
    return out, "".join(out)


def _every_split(text: str) -> list[list[str]]:
    """The text as two chunks at every position, and as single characters."""
    return [[text[:i], text[i:]] for i in range(len(text) + 1)] + [list(text)]


@pytest.mark.parametrize(
    "reply, visible",
    [
        (
            f"{VERIFIED_MATH_BEGIN}\nx = 4\n{VERIFIED_MATH_END}\nSo x is 4.",
            "\nx = 4\n\nSo x is 4.",
        ),
        (
            'Let me plot it. !function_call:{"name": "graph", "args": {"expr": "x^2"}} Done.',
            "Let me plot it.  Done.",
        ),
        (
            'Here!function_call: {"s": "a } in a string \\" ok"}!',
            "Here!",
        ),
        (f"Speed: 39.6 m/s{VERIFIED_PHYSICS_END}", "Speed: 39.6 m/s"),
    ],
)
def test_scaffold_filter_strips_markers_split_at_every_chunk_boundary(
    reply: str, visible: str
) -> None:
    for chunks in _every_split(reply):
        pieces, joined = _filtered(chunks)
        assert joined == visible, chunks
        for piece in pieces:
            for leak in _LEAKS:
                assert leak not in piece, (chunks, piece)


@pytest.mark.parametrize(
    "reply",
    [
        "Plain prose with [brackets] and a link [here](https://example.com).",
        "Wow! Really! [B] and [E] and !f",
        "Ends in a partial marker [BEGIN VERI",
        "",
    ],
)
def test_scaffold_filter_keeps_ordinary_text(reply: str) -> None:
    for chunks in _every_split(reply):
        assert _filtered(chunks)[1] == reply


def test_scaffold_filter_holds_only_a_possible_marker_start() -> None:
    scaffold = ScaffoldFilter()
    assert scaffold.feed("Hello [") == "Hello "
    assert scaffold.feed("x] world!") == "[x] world"
    assert scaffold.flush() == "!"


def test_an_unclosed_call_keeps_its_object_like_the_finalize_pass() -> None:
    _pieces, joined = _filtered(["See !function_call:", ' {"name": "graph"'])
    assert joined == 'See {"name": "graph"'


def test_a_call_that_never_closes_is_released_past_the_cap() -> None:
    scaffold = ScaffoldFilter()
    body = "{" + "a" * (MAX_HELD_CALL_CHARS + 10)
    shown = scaffold.feed("!function_call:" + body)
    assert shown == body
    assert scaffold.feed(" more") == " more"


def _ctx():
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "solve x^2 = 16"}],
        run_title=False,
        user_message_content="solve x^2 = 16",
        reserved_tokens=0,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )


@pytest.mark.asyncio
async def test_live_tokens_carry_no_scaffolding_while_finalize_still_reads_it(
    stream_offline_io,
) -> None:
    from app.modules.chat.stream_pipeline import stream_and_finalize

    tokens = [
        "[BEGIN VER",
        "IFIED MATH]\nx = 4",
        "\n[END VERIFIED MA",
        "TH]\nDone !func",
        "tion_call:{",
        '"a": 1}.',
    ]

    async def fake_stream(**_kwargs: object):
        for token in tokens:
            yield token
            await asyncio.sleep(0)

    statuses: list[tuple[str, str | None]] = []

    async def on_status(
        phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        statuses.append((phase, detail))

    finalize = AsyncMock()
    outcome = TurnOutcome()
    yielded: list[str] = []
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", finalize)
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for token in stream_and_finalize(
            offline_deps(),
            redis_mock(),
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            _ctx(),
            should_cancel=None,
            outcome=outcome,
            on_status=on_status,
        ):
            yielded.append(token)
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task

    for token in yielded:
        for leak in _LEAKS:
            assert leak not in token
    assert "".join(yielded) == "\nx = 4\n\nDone ."
    # The model is asked once the tool rounds are over; their labels end there.
    assert statuses == [("composing", None)]
    call = finalize.await_args
    assert call is not None
    saved = call.kwargs["assistant_text"]
    assert "VERIFIED" not in saved
    assert "function_call" not in saved
