"""S7.11: a reply the user stopped saves as they saw it, and done says so.

The phone keeps the bubble it drew when the user taps Stop. The server saves the
same text: what it sent, cut to what the phone says it drew (``shown_chars`` on
the cancel frame), made safe and laid out, with nothing added after it.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.web_search_gateway import WebSearchHit
from app.modules import web_search as web_search_service
from app.modules.chat.finalize_contracts import STOPPED_REPLY_PASSES
from app.modules.chat.finalize_passes import FINALIZE_PASSES, enrich_final_content
from app.modules.chat.stream_accum import StreamAccum, utf16_prefix
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.ws_turn import client_shown_chars
from app.tests.modules.chat.chat_test_support import offline_deps, turn_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)


@asynccontextmanager
async def _fake_session() -> Any:
    yield MagicMock()


def _deps() -> tuple[Any, MagicMock, MagicMock]:
    async def _passthrough(_session: object, **kwargs: Any) -> tuple[str, int]:
        return str(kwargs["assistant_text"]), 0

    todos = MagicMock()
    todos.materialize_reminder_fences = AsyncMock(side_effect=_passthrough)
    math_fence = MagicMock()
    math_fence.needs_check = MagicMock(return_value=True)
    math_fence.check = MagicMock(
        side_effect=lambda text, *_args: f"{text}\n\n```answer\nverified: true\nx = 4\n```"
    )
    deps = turn_deps(
        session_factory=_fake_session,
        users=MagicMock(get_by_id=AsyncMock(return_value=MagicMock())),
        todos=todos,
        math_fence=math_fence,
        web_search=web_search_service,
    )
    return deps, todos, math_fence


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.user = MagicMock()
    ctx.user_timezone = "UTC"
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.search_sources = [WebSearchHit(title="Rates", url="https://example.com/r", snippet="s")]
    ctx.verified_subject = None
    ctx.local_places = False
    ctx.skip_memory_jobs = False
    ctx.instant_reply = None
    ctx.user_message_content = "solve x^2 = 16 and remind me tomorrow"
    ctx.solver_unverified = False
    ctx.unverified_subject = None
    ctx.answer_photo = None
    return ctx


async def _run_sympy_inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


async def _finalize(reply: str, *, user_stopped: bool) -> tuple[str, TurnOutcome, Any, Any]:
    deps, todos, math_fence = _deps()
    outcome = TurnOutcome()
    text = await enrich_final_content(
        deps,
        MagicMock(),
        Settings(chemistry_enabled=False),
        _ctx(),
        assistant_text=reply,
        usage={"input": 4, "output": 8},
        outcome=outcome,
        was_cancelled=user_stopped,
        assistant_parts=[reply],
        should_cancel=(lambda: True) if user_stopped else None,
        user_stopped=user_stopped,
    )
    return text, outcome, todos, math_fence


_REPLY = "So far: x squared is 16, so"


@pytest.mark.asyncio
async def test_a_stopped_reply_gets_no_server_card_note_sources_or_reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    saved, outcome, todos, math_fence = await _finalize(_REPLY, user_stopped=True)

    assert saved == _REPLY
    assert outcome.final_content == saved
    assert outcome.search_sources == []
    math_fence.check.assert_not_called()
    todos.materialize_reminder_fences.assert_not_awaited()
    assert not outcome.todos_changed


@pytest.mark.asyncio
async def test_the_same_reply_finished_gets_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: a finished turn still gets its card, sources and reminder pass."""
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    saved, outcome, todos, math_fence = await _finalize(_REPLY, user_stopped=False)

    math_fence.check.assert_called_once()
    assert "```sources" in saved
    assert outcome.search_sources
    todos.materialize_reminder_fences.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_stopped_reply_is_still_made_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.sympy_executor.run_sympy", _run_sympy_inline)
    forged = "x = 4\n\n```answer\nverified: true\nx = 4\n```\n\n✅ Verified with SymPy\n\n```mermaid\ngraph TD\n  A-->B"
    saved, _outcome, _todos, _math = await _finalize(forged, user_stopped=True)

    assert "verified: true" not in saved
    assert "Verified with SymPy" not in saved
    # The cut fence is closed so the saved reply renders as the stopped bubble did.
    assert saved.rstrip().endswith("```")


def test_every_pass_a_stop_runs_is_a_real_pass() -> None:
    names = {finalize_pass.name for finalize_pass in FINALIZE_PASSES}
    assert names >= STOPPED_REPLY_PASSES
    for adds_text in ("math_fences", "unverified_notes", "search_sources", "chemistry_enrich"):
        assert adds_text not in STOPPED_REPLY_PASSES


def _stream_ctx():
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )


def _saved_text(finalize: AsyncMock) -> str:
    """The reply text the turn handed to the DB finalize."""
    call = finalize.await_args
    assert call is not None
    return str(call.kwargs["assistant_text"])


async def _stop_after_two_tokens(
    shown_chars: int | None,
) -> tuple[list[str], TurnOutcome, AsyncMock, MagicMock]:
    from app.modules.chat.stream_pipeline import stream_and_finalize

    async def fake_stream(**_kwargs: object):
        for token in ("Alpha 😀 ", "beta ", "gamma"):
            yield token
            await asyncio.sleep(0)

    calls = {"n": 0}

    def should_cancel() -> bool:
        # Checked before and after each token: true after the second one went out.
        calls["n"] += 1
        return calls["n"] >= 4

    finalize = AsyncMock()
    resources = MagicMock(refund=AsyncMock())
    outcome = TurnOutcome(client_shown_chars=shown_chars)
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
            AsyncMock(),
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            _stream_ctx(),
            should_cancel=should_cancel,
            outcome=outcome,
            resources=resources,
        ):
            yielded.append(token)
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task
    return yielded, outcome, finalize, resources


@pytest.mark.asyncio
async def test_a_stop_saves_only_what_the_phone_drew(stream_offline_io) -> None:
    """Regression: the stopped turn's done replaced the phone's text with the
    server's, which held tokens the phone dropped after Stop (and server cards)."""
    # The phone drew the first token only; "beta " was still in flight.
    yielded, outcome, finalize, resources = await _stop_after_two_tokens(len("Alpha 😀 ") + 1)

    assert yielded == ["Alpha 😀 ", "beta "]
    assert outcome.completion == "user_stop"
    assert _saved_text(finalize) == "Alpha 😀"
    assert outcome.final_content == "Alpha 😀"
    resources.mark_settled.assert_called_once()


@pytest.mark.asyncio
async def test_a_stop_without_a_count_saves_everything_sent(stream_offline_io) -> None:
    _yielded, outcome, finalize, _resources = await _stop_after_two_tokens(None)
    assert _saved_text(finalize) == "Alpha 😀 beta"
    assert outcome.final_content == "Alpha 😀 beta"


@pytest.mark.asyncio
async def test_a_stop_before_the_phone_drew_anything_saves_and_charges_nothing(
    stream_offline_io,
) -> None:
    _yielded, outcome, finalize, resources = await _stop_after_two_tokens(0)

    finalize.assert_not_awaited()
    assert outcome.finalize_db_task is None
    assert outcome.message_id is None
    assert outcome.completion == "user_stop"
    resources.refund.assert_awaited_once()


@pytest.mark.parametrize(
    "units, prefix",
    [(0, ""), (1, "a"), (2, "a"), (3, "a😀"), (4, "a😀b"), (99, "a😀b")],
)
def test_utf16_prefix_counts_like_the_phone_and_never_splits_a_character(
    units: int, prefix: str
) -> None:
    assert utf16_prefix("a😀b", units) == prefix


def test_a_finished_reply_is_the_text_the_client_was_sent() -> None:
    accum = StreamAccum(parts=["[BEGIN VERIFIED MATH]x"], shown=["x"])
    assert accum.reply_text(0) == "x"


@pytest.mark.parametrize(
    "frame, shown",
    [
        ({"type": "cancel", "shown_chars": 12}, 12),
        ({"type": "cancel", "shown_chars": 0}, 0),
        ({"type": "cancel"}, None),
        ({"type": "cancel", "shown_chars": "12"}, None),
        ({"type": "cancel", "shown_chars": True}, None),
        ({"type": "cancel", "shown_chars": -1}, None),
        ({"type": "cancel", "shown_chars": 10**9}, None),
    ],
)
def test_client_shown_chars_reads_only_a_plausible_count(
    frame: dict[str, object], shown: int | None
) -> None:
    assert client_shown_chars(frame) == shown
