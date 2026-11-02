"""Finalize must not refund after a successful DB commit."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import RegenerateBackup, StreamContext
from app.modules.chat.turn_settle import finalize_stream_turn_db
from app.tests.fakes import FakeSessionCM, fake_session, isolated_settings, redis_mock
from app.tests.modules.chat.chat_test_support import turn_deps


def _ctx(**fields: Any) -> StreamContext:
    base: dict[str, Any] = {
        "user_id": uuid4(),
        "chat_id": uuid4(),
        "model": "free-chat",
        "prompt_messages": [{"role": "user", "content": "hi"}],
        "run_title": False,
        "user_message_content": "hi",
        "reserved_tokens": 200,
        "max_output_tokens": 50,
        "skip_memory_jobs": True,
        "user": MagicMock(plan="free"),
    }
    return StreamContext(**{**base, **fields})


def _deps(session: Any, **fields: dict[str, Any]) -> ChatTurnDeps:
    """Finalize's reads and writes faked; each test swaps the ones it checks."""
    swapped: dict[str, dict[str, Any]] = {
        "messages": {"create": AsyncMock(return_value=MagicMock(id=uuid4()))},
        "chats": {"touch_by_id": AsyncMock()},
        "usage": {"add_tokens": AsyncMock()},
        "quota": {
            "adjust_usage": AsyncMock(return_value=0),
            "refund_usage": AsyncMock(),
            "mark_usage_needs_heal": AsyncMock(),
            "record_global_spend": AsyncMock(),
            "daily_limit_for_user": MagicMock(return_value=100_000),
        },
    }
    for name, values in fields.items():
        swapped[name] = {**swapped.get(name, {}), **values}
    return turn_deps(session_factory=FakeSessionCM(session), **swapped)


@pytest.mark.asyncio
async def test_adjust_usage_failure_after_commit_does_not_refund():
    session = fake_session()
    refund = AsyncMock()
    adjust = AsyncMock(side_effect=RuntimeError("redis blip"))
    mark_heal = AsyncMock()
    deps = _deps(
        session,
        quota={"adjust_usage": adjust, "refund_usage": refund, "mark_usage_needs_heal": mark_heal},
    )

    await finalize_stream_turn_db(
        deps,
        redis_mock(),
        Settings(),
        _ctx(),
        "hello",
        {"input": 10, "output": 5},
        outcome=TurnOutcome(),
    )

    session.commit.assert_awaited()
    # H2: adjust_usage retries 3 times on failure before giving up.
    assert adjust.await_count == 3
    refund.assert_not_awaited()
    mark_heal.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_persists_estimated_cost_usd():
    """Known model + usage → est_cost_usd written on the usage row."""
    add_tokens = AsyncMock()
    deps = _deps(fake_session(), usage={"add_tokens": add_tokens})

    await finalize_stream_turn_db(
        deps,
        redis_mock(),
        Settings(),
        _ctx(),
        "hello",
        {"input": 1_000_000, "output": 1_000_000},
        outcome=TurnOutcome(),
    )

    add_tokens.assert_awaited_once()
    assert add_tokens.await_args.kwargs["est_cost_usd"] == pytest.approx(0.10 + 0.50)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_step", ["create", "usage", "commit"])
async def test_failed_regenerate_preserves_original_attachment_bytes(failure_step):
    session = fake_session()
    old = MagicMock(id=uuid4())
    ctx = _ctx(
        prompt_messages=[],
        user_message_content="question",
        skip_memory_jobs=False,
        user=None,
        regenerate_backup=RegenerateBackup("original", "free-chat", old.id),
    )
    create = AsyncMock(return_value=MagicMock(id=uuid4()))
    add_usage = AsyncMock()
    {"create": create, "usage": add_usage, "commit": session.commit}[
        failure_step
    ].side_effect = RuntimeError("database unavailable")
    delete_bytes = AsyncMock()
    refund = AsyncMock()
    deps = _deps(
        session,
        messages={"get_by_id": AsyncMock(return_value=old), "create": create},
        usage={"add_tokens": add_usage},
        attachments={
            "detach_attachments_for_messages": AsyncMock(return_value=["original.png"]),
            "delete_storage_keys": delete_bytes,
        },
        quota={"refund_usage": refund},
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await finalize_stream_turn_db(
            deps,
            redis_mock(),
            isolated_settings(),
            ctx,
            "replacement",
            {"input": 10, "output": 5},
            outcome=TurnOutcome(),
        )
    delete_bytes.assert_not_awaited()
    refund.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_success_does_not_depend_on_post_commit_refresh():
    session = fake_session()
    session.refresh.side_effect = RuntimeError("connection lost after commit")
    refund = AsyncMock()
    adjust = AsyncMock(return_value=0)
    outcome = TurnOutcome()
    assistant_id = uuid4()
    deps = _deps(
        session,
        messages={"create": AsyncMock(return_value=MagicMock(id=assistant_id))},
        quota={"adjust_usage": adjust, "refund_usage": refund},
    )

    await finalize_stream_turn_db(
        deps,
        redis_mock(),
        isolated_settings(),
        _ctx(prompt_messages=[], user_message_content="question", user=None),
        "reply",
        {"input": 10, "output": 5},
        outcome=outcome,
    )

    session.commit.assert_awaited_once()
    assert outcome.message_id == str(assistant_id)
    adjust.assert_awaited_once()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_links_the_answer_photo_to_the_reply():
    session = fake_session()
    assistant = MagicMock(id=uuid4())
    photo_id = uuid4()
    link = AsyncMock(return_value=1)
    deps = _deps(
        session,
        messages={"create": AsyncMock(return_value=assistant)},
        attachment_links={"link_to_message": link},
    )

    await finalize_stream_turn_db(
        deps,
        redis_mock(),
        Settings(),
        _ctx(
            prompt_messages=[{"role": "user", "content": "where is ethiopia"}],
            user_message_content="where is ethiopia",
            answer_photo_ids=[photo_id],
        ),
        "[Image: x]\n\nEthiopia.",
        {"input": 1, "output": 1},
        outcome=TurnOutcome(),
    )

    link.assert_awaited_once()
    assert link.await_args.kwargs["attachment_ids"] == [photo_id]
    assert link.await_args.kwargs["message_id"] == assistant.id
    assert link.await_args.kwargs["commit"] is False
    session.commit.assert_awaited_once()
