"""A turn that ends before its reply streams still logs its trace line, once."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import ConsentRequiredError
from app.modules.chat import stream_entry, turn_trace
from app.modules.chat.turn_outcome import TurnOutcome
from app.tests.fakes import make_user, redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps


@pytest.fixture(autouse=True)
def _no_trace_between_tests() -> Iterator[None]:
    token = turn_trace._TRACE.set(None)
    yield
    turn_trace._TRACE.reset(token)


def _deps(user: MagicMock, *, recent: AsyncMock) -> Any:
    return turn_deps(
        session_factory=FakeSessionCM,
        locks={"acquire_lock": AsyncMock(return_value="tok"), "release_lock": AsyncMock()},
        quota={"refund_usage": AsyncMock(), "daily_limit_for_user": MagicMock(return_value=1)},
        users={"get_by_id": AsyncMock(return_value=user)},
        chats={"get_by_id": AsyncMock(return_value=MagicMock(summary=None))},
        messages={"list_recent": recent, "count_for_chat": AsyncMock(return_value=0)},
    )


async def _run(user: MagicMock, *, recent: AsyncMock) -> None:
    # No earlier turn of the chat is still saving (``finalize_registry``).
    async for _ in stream_entry.stream_chat_response(
        _deps(user, recent=recent),
        redis_mock(exists=0),
        Settings(),
        user_id=user.id,
        chat_id=uuid4(),
        content="hello",
        user=user,
        outcome=TurnOutcome(),
        skip_usage_seed=True,
    ):
        pass


def _traces(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [
        record.turn_trace  # type: ignore[attr-defined]
        for record in caplog.records
        if record.getMessage().startswith("turn_trace")
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("consent_enforced")
async def test_a_refused_turn_logs_its_line_with_the_refusal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    with pytest.raises(ConsentRequiredError):
        await _run(make_user(ai_data_consent_at=None), recent=AsyncMock(return_value=[]))
    [trace] = _traces(caplog)
    assert (trace["kind"], trace["path"]) == ("new", "prep")
    assert (trace["outcome"], trace["error"]) == ("error", "ConsentRequiredError")


@pytest.mark.asyncio
async def test_a_stop_while_the_turn_loads_logs_it_as_cancelled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)
    user = make_user(ai_data_consent_at=datetime(2026, 10, 19, tzinfo=UTC))
    with pytest.raises(asyncio.CancelledError):
        await _run(user, recent=AsyncMock(side_effect=asyncio.CancelledError()))
    [trace] = _traces(caplog)
    assert (trace["path"], trace["outcome"], trace["error"]) == (
        "prep",
        "cancelled",
        "CancelledError",
    )


@pytest.mark.asyncio
async def test_the_line_comes_once_whatever_logs_it_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=turn_trace.__name__)

    @turn_trace.traced_turn("new")
    async def stream(**_kwargs: Any) -> Any:
        turn_trace.emit_turn_trace(None, outcome=None)  # as the stream's own end does
        yield "ok"

    assert [token async for token in stream(outcome=None)] == ["ok"]
    [trace] = _traces(caplog)
    assert trace["path"] == "stream"


@pytest.mark.asyncio
async def test_a_turn_closed_early_closes_its_stream_at_once() -> None:
    """The trace's wrapper hands a close straight on: the turn's locks end with it."""
    closed: list[str] = []

    @turn_trace.traced_turn("new")
    async def stream(**_kwargs: Any) -> Any:
        try:
            yield "a"
            yield "b"
        finally:
            closed.append("inner")

    tokens = stream(outcome=None)
    assert await anext(tokens) == "a"
    await tokens.aclose()  # type: ignore[attr-defined]
    assert closed == ["inner"]
