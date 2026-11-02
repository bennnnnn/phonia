"""A WebSocket turn reads the user row once per change to it, not once per turn.

The socket's turns passed no user, so every turn read the row from Postgres in a
session of its own (BEGIN, SELECT, ROLLBACK). The process's user cache now serves
it while the user's generation, read in the same MGET as the frame's token check,
is unchanged: a plan, consent, memory or preferences change made on any machine
moves the generation, and the next turn reads the row again.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import make_transient_to_detached

from app.core import user_cache
from app.core.access_tokens import AccessCheck
from app.core.config import Settings
from app.models.orm import User
from app.modules.chat import stream_entry, turn_load, ws_api
from app.modules.chat.turn_timing import TurnTimingTracker
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps


def _row(plan: str = "free") -> User:
    row = User(id=uuid4(), email="someone@example.com", plan=plan)
    make_transient_to_detached(row)
    return row


@pytest.fixture(autouse=True)
def _empty_cache():
    user_cache.clear()
    yield
    user_cache.clear()


async def _ws_turn(monkeypatch: pytest.MonkeyPatch, user: User, generation: str) -> dict[str, Any]:
    """Send one message frame's turn and return what the stream was started with."""
    captured: dict[str, Any] = {}

    async def fake_stream(*_args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return
        yield  # pragma: no cover - an async generator

    monkeypatch.setattr(stream_entry, "stream_chat_response", fake_stream)
    await ws_api._handle_message(
        AsyncMock(),
        redis=redis_mock(),
        settings=Settings(),
        user_id=user.id,
        chat_id=uuid4(),
        payload={"type": "message", "content": "hi"},
        client_timezone=None,
        cancel_event=asyncio.Event(),
        emit_status=AsyncMock(),
        emit_reasoning=AsyncMock(),
        access=AccessCheck(user_id=user.id, user_generation=generation),
    )
    return captured


async def test_a_ws_turn_gets_the_cached_user_while_its_generation_holds(monkeypatch) -> None:
    user = _row()
    user_cache.remember_user(user, "g1")

    started = await _ws_turn(monkeypatch, user, "g1")

    assert started["user"] is not None
    assert started["user"].id == user.id
    assert started["user_generation"] == "g1"


async def test_a_ws_turn_after_a_change_elsewhere_reads_the_row_again(monkeypatch) -> None:
    user = _row()
    user_cache.remember_user(user, "g1")

    # A settings change on another machine published generation g2.
    started = await _ws_turn(monkeypatch, user, "g2")

    assert started["user"] is None
    assert started["user_generation"] == "g2"


async def test_a_turn_that_reads_the_user_keeps_it_for_the_next_turn() -> None:
    row = _row(plan="pro")
    load = AsyncMock(return_value=row)
    deps = turn_deps(session_factory=FakeSessionCM, users={"get_by_id": load})

    first = await turn_load._load_user(deps, TurnTimingTracker(), row.id, None, "g1")
    cached = user_cache.cached_user(row.id, "g1")
    second = await turn_load._load_user(deps, TurnTimingTracker(), row.id, cached, "g1")

    assert first.plan == second.plan == "pro"
    assert load.await_count == 1
