"""A chat turn waits for the account's consent to outside AI services.

Before the user agrees (or after they withdraw) nothing about the turn runs: no
message is saved, no quota is reserved, the prepare lock is released, and both
transports send ``code: "consent_required"`` with ``user_message_saved: false``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.exceptions import ConsentRequiredError
from app.modules.chat import stream_api, stream_entry, ws_turn
from app.modules.chat.stream_events import turn_error_payload
from app.tests.fakes import redis_mock
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps

pytestmark = pytest.mark.usefixtures("consent_enforced")


def _user(*, agreed: bool) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"
    user.default_model = "free-chat"
    user.ai_data_consent_at = datetime(2026, 10, 19, tzinfo=UTC) if agreed else None
    return user


def _fakes(stored: MagicMock) -> dict[str, Any]:
    """The turn's outside calls, recorded: the lock, quota, and the saved user row."""
    return {
        "acquire": AsyncMock(return_value="tok"),
        "release": AsyncMock(),
        "reserve": AsyncMock(return_value=100),
        "refund": AsyncMock(),
        "prepare": AsyncMock(),
        "get_user": AsyncMock(return_value=stored),
    }


def _deps(fakes: dict[str, Any]) -> Any:
    return turn_deps(
        session_factory=FakeSessionCM,
        locks={"acquire_lock": fakes["acquire"], "release_lock": fakes["release"]},
        quota={"refund_usage": fakes["refund"], "daily_limit_for_user": MagicMock(return_value=1)},
        users={"get_by_id": fakes["get_user"]},
        chats={"get_by_id": AsyncMock(return_value=MagicMock(summary=None))},
        messages={
            "list_recent": AsyncMock(return_value=[]),
            "count_for_chat": AsyncMock(return_value=0),
            "get_last_user": AsyncMock(return_value=MagicMock(content="hi")),
        },
    )


def _turn(kind: str, deps: Any, *, user: MagicMock | None, outcome: Any = None) -> Any:
    if kind == "regenerate":
        return stream_entry.stream_regenerate_response(
            deps, redis_mock(), Settings(), user_id=user.id if user else uuid4(), chat_id=uuid4()
        )
    return stream_entry.stream_chat_response(
        deps,
        redis_mock(),
        Settings(),
        user_id=user.id if user else uuid4(),
        chat_id=uuid4(),
        content="hello",
        user=user,
        outcome=outcome,
        skip_usage_seed=True,
    )


def _patches(fakes: dict[str, Any]) -> Any:
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()))
    stack.enter_context(patch("app.modules.chat.stream_entry.prepare_chat_turn", fakes["prepare"]))
    stack.enter_context(
        patch("app.modules.chat.turn_resources.reserve_turn_quota", fakes["reserve"])
    )
    return stack


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "handed_in"),
    [("new", True), ("new", False), ("regenerate", False)],
    ids=["new turn, SSE user", "new turn, WebSocket", "regenerate"],
)
async def test_a_turn_without_consent_runs_nothing_and_releases_the_lock(
    kind: str, handed_in: bool
) -> None:
    stored = _user(agreed=False)
    fakes = _fakes(stored)
    with _patches(fakes), pytest.raises(ConsentRequiredError):
        async for _ in _turn(kind, _deps(fakes), user=stored if handed_in else None):
            pass

    fakes["prepare"].assert_not_awaited()
    fakes["reserve"].assert_not_awaited()
    fakes["refund"].assert_not_awaited()
    fakes["release"].assert_awaited_once()


@pytest.mark.asyncio
async def test_a_cached_user_that_agreed_on_another_machine_is_read_again() -> None:
    """The request cache can trail an agreement by a minute; the row decides."""
    cached = _user(agreed=False)
    stored = _user(agreed=True)
    stored.id = cached.id
    fakes = _fakes(stored)

    async def fake_stream(*_args: Any, **_kwargs: Any) -> Any:
        yield "ok"

    with (
        _patches(fakes),
        patch("app.modules.chat.stream_entry.stream_and_finalize", fake_stream),
        patch(
            "app.modules.chat.turn_intercepts.try_image_gen_for_turn",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.chat.stream_entry.top_up_reserve_for_prompt", AsyncMock()),
        patch("app.modules.chat.stream_entry.await_user_message_persist", AsyncMock()),
    ):
        tokens = [token async for token in _turn("new", _deps(fakes), user=cached)]

    assert tokens == ["ok"]
    fakes["get_user"].assert_awaited_once()


def test_the_error_frame_names_the_code_and_says_nothing_was_saved() -> None:
    payload = turn_error_payload(ConsentRequiredError(), user_message_saved=False)
    assert payload["type"] == "error"
    assert payload["code"] == "consent_required"
    assert payload["user_message_saved"] is False
    assert payload["message"]


@pytest.mark.asyncio
async def test_the_websocket_sends_consent_required() -> None:
    stored = _user(agreed=False)
    fakes = _fakes(stored)
    websocket = AsyncMock()
    with _patches(fakes):
        await ws_turn.run_chat_stream(
            websocket,
            cancel_event=asyncio.Event(),
            stream_factory=lambda outcome: _turn("new", _deps(fakes), user=None, outcome=outcome),
        )

    frames = [call.args[0] for call in websocket.send_json.await_args_list]
    assert frames[0] == {"type": "start"}
    assert frames[-1]["code"] == "consent_required"
    assert frames[-1]["user_message_saved"] is False
    assert not any(frame.get("type") == "done" for frame in frames)


@pytest.mark.asyncio
async def test_server_sent_events_send_consent_required() -> None:
    stored = _user(agreed=False)
    fakes = _fakes(stored)
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    with _patches(fakes):
        frames = [
            json.loads(chunk.removeprefix("data: "))
            async for chunk in stream_api._stream_tokens_sse(
                chat_id=uuid4(),
                request=request,
                stream_factory=lambda outcome, *_callbacks: _turn(
                    "new", _deps(fakes), user=stored, outcome=outcome
                ),
            )
        ]

    assert frames[0] == {"type": "start"}
    assert frames[-1]["code"] == "consent_required"
    assert frames[-1]["user_message_saved"] is False
