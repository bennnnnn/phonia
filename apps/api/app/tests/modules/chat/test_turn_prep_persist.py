"""The user's row, its links and the indexable read commit together or roll back together."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.turn_prep.mode import _TurnMode
from app.modules.chat.turn_prep.persist import UserTurn, persist_user_turn
from app.modules.chat.turn_timing import TurnTimingTracker

_MODULE = "app.modules.chat.turn_prep.persist"


def _turn(attachment_ids: list[UUID] | None = None, **known: Any) -> UserTurn:
    return UserTurn(
        user_id=uuid4(),
        chat_id=uuid4(),
        message_id=uuid4(),
        content="summarize this",
        stored_content="summarize this\n\n[File: notes.txt]",
        attachment_ids=attachment_ids or [uuid4()],
        has_image_attachment=False,
        model_alias=None,
        recent_messages=None,
        lesson_active=False,
        **known,
    )


def _session_local(session: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context)


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["create", "link", "indexable", "commit"])
async def test_persist_user_turn_rolls_back_its_own_transaction_on_a_failed_write(failing):
    session = AsyncMock()
    error = RuntimeError("database went away")
    create = AsyncMock(side_effect=error if failing == "create" else None)
    create.return_value = SimpleNamespace(id=uuid4())
    link = AsyncMock(side_effect=error if failing == "link" else None, return_value=1)
    rows = AsyncMock(side_effect=error if failing == "indexable" else None, return_value=[])
    if failing == "commit":
        session.commit.side_effect = error
    timing = TurnTimingTracker()
    user = SimpleNamespace(id=uuid4())
    enqueue = AsyncMock()
    with (
        patch(f"{_MODULE}.SessionLocal", _session_local(session)),
        patch("app.modules.conversation.messages_repository.create", create),
        patch("app.modules.attachments.repository.link_to_message", link),
        patch("app.modules.attachments.repository.get_by_ids", rows),
        patch(f"{_MODULE}.attachments_service.enqueue_index_jobs", enqueue),
    ):
        with pytest.raises(RuntimeError, match="database went away"):
            await persist_user_turn(
                _turn(
                    user=user,
                    chat=MagicMock(),
                    model="free-chat",
                    prior_count=2,
                    turn_mode=MagicMock(),
                ),
                Settings(attachments_enabled=True, attachment_rag_enabled=True),
                timing,
            )
    session.rollback.assert_awaited_once()
    assert create.await_args.kwargs["commit"] is False
    if failing != "commit":
        session.commit.assert_not_awaited()
    assert "persist_start" in timing._phases_ms
    assert "persist_done" not in timing._phases_ms
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_user_turn_reads_what_the_caller_left_out_and_queues_its_documents():
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    chat = SimpleNamespace(id=uuid4())
    document = SimpleNamespace(id=uuid4(), content_type="text/plain")
    mode = _TurnMode(
        lightweight=False,
        rich_context=True,
        minimal_personal=False,
        day_planning=False,
        day_reflection=False,
    )
    turn = _turn(attachment_ids=[document.id])

    async def _after_commit(*_args, **_kwargs):
        session.commit.assert_awaited_once()

    enqueue = AsyncMock(side_effect=_after_commit)
    with (
        patch(f"{_MODULE}.SessionLocal", _session_local(session)),
        patch(f"{_MODULE}.users_repo.get_by_id", AsyncMock(return_value=user)),
        patch("app.modules.conversation.chats_repository.get_by_id", AsyncMock(return_value=chat)),
        patch(
            "app.modules.conversation.messages_repository.count_for_chat", AsyncMock(return_value=4)
        ),
        patch(
            "app.modules.conversation.messages_repository.list_recent", AsyncMock(return_value=[])
        ),
        patch(f"{_MODULE}.classify_turn_mode", return_value=mode),
        patch(f"{_MODULE}.model_choice.resolve_user_model_override", return_value="smart-chat"),
        patch(
            "app.modules.conversation.messages_repository.create",
            AsyncMock(return_value=SimpleNamespace(id=turn.message_id)),
        ) as create,
        patch("app.modules.attachments.repository.link_to_message", AsyncMock(return_value=1)),
        patch("app.modules.attachments.repository.get_by_ids", AsyncMock(return_value=[document])),
        patch(f"{_MODULE}.attachments_service.enqueue_index_jobs", enqueue),
    ):
        await persist_user_turn(
            turn,
            Settings(attachments_enabled=True, attachment_rag_enabled=True),
            None,
        )
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs == {
        "user_id": turn.user_id,
        "chat_id": turn.chat_id,
        "attachment_ids": [str(document.id)],
    }
    assert (turn.user, turn.chat, turn.model, turn.prior_count, turn.turn_mode) == (
        user,
        chat,
        "smart-chat",
        4,
        mode,
    )
    assert create.await_args.kwargs["content"] == turn.stored_content
    assert create.await_args.kwargs["message_id"] == turn.message_id
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
