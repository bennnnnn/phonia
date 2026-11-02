"""Every turn is saved and followed up as a typed one (code-health audit ARCH-08).

A picture, a photo lookup and a voice turn saved their own rows: the chat stayed where
it was in the drawer, a chat that began with a picture got no title, and voice kept its
own job list, without compression, lesson progress or the spend cap, and indexing a
turn for search with memory off.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import Chat
from app.modules.chat import post_turn
from app.modules.chat.turn_prep import StreamContext
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import history, messages_repository, turn_record
from app.modules.speech.live_talk import persist_live_talk_turn
from app.repositories import users as users_repo
from app.services import quota as quota_service
from app.tests.fakes import fake_session, make_user, redis_mock

_USER = UUID(int=1)
_CHAT = UUID(int=2)
_ASSISTANT = UUID(int=3)
_SAID = "I just moved to Lisbon, remind me to call mom tomorrow"
# A lesson step too: every job has a reason to run.
_REPLY = "Welcome to Lisbon!\n\n### Lesson 2: Fractions\n\n```quiz\n{}\n```"
_SETTINGS = Settings(history_compression_enabled=True, chat_history_rag_enabled=True)


async def _queued(run: Any) -> list[tuple[str, dict[str, str]]]:
    calls: list[tuple[str, dict[str, str]]] = []

    async def enqueue(_redis: object, name: str, payload: dict[str, str], dedupe_key=None):
        calls.append((name, payload))

    with (
        patch("app.core.jobs.enqueue", enqueue),
        patch.object(quota_service, "global_spend_exceeded", AsyncMock(return_value=False)),
    ):
        await run()
    return calls


async def _typed() -> None:
    ctx = StreamContext(
        user_id=_USER,
        chat_id=_CHAT,
        model="free-chat",
        prompt_messages=[],
        run_title=True,
        user_message_content=_SAID,
        reserved_tokens=10,
        max_output_tokens=100,
        user=make_user(id=_USER, memory_enabled=True),
        assistant_message_id=_ASSISTANT,
    )
    await post_turn.enqueue_post_turn_jobs(AsyncMock(), _SETTINGS, ctx, _REPLY)


async def _voice() -> None:
    user = MagicMock(id=_USER, memory_enabled=True, timezone="UTC")
    rows = [MagicMock(id=uuid4(), content=_SAID), MagicMock(id=_ASSISTANT, content=_REPLY)]
    session = fake_session()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("app.modules.speech.live_talk.SessionLocal", return_value=session),
        patch.object(chats_repo, "get_by_id", AsyncMock(return_value=MagicMock())),
        patch.object(messages_repository, "create", AsyncMock(side_effect=rows)),
        patch.object(messages_repository, "count_for_chat", AsyncMock(return_value=0)),
        patch(
            "app.modules.speech.live_talk.todos_service.materialize_reminder_fences",
            AsyncMock(return_value=(_REPLY, 0)),
        ),
    ):
        await persist_live_talk_turn(
            user=user,
            chat_id=_CHAT,
            user_text=_SAID,
            assistant_text=_REPLY,
            untitled=True,
            settings=_SETTINGS,
            redis=redis_mock(),
        )


async def _picture() -> None:
    # As images.generation and images.search finish a turn that saved the user's message.
    await post_turn.finish_turn(
        AsyncMock(),
        _SETTINGS,
        user=make_user(id=_USER, memory_enabled=True),
        chat_id=_CHAT,
        user_message=_SAID,
        assistant=MagicMock(id=_ASSISTANT, content=_REPLY),
        prior_count=0,
    )


@pytest.mark.asyncio
async def test_a_voice_turn_and_a_picture_queue_a_typed_turns_jobs() -> None:
    typed = await _queued(_typed)
    assert [name for name, _ in typed] == [
        "memory",
        "lesson_progress",
        "topic",
        "compress",
        "message_index",
    ]
    # Same names and payloads; the compress key is unique per enqueue, not compared.
    assert await _queued(_voice) == typed
    assert await _queued(_picture) == typed


@pytest.mark.asyncio
async def test_a_message_saved_for_a_turn_moves_the_chat_up(db_session) -> None:
    user = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Picture User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    long_ago = datetime.now(UTC) - timedelta(days=3)
    chat.updated_at = long_ago
    await db_session.flush()

    await turn_record.add_turn_message(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        role="assistant",
        content="[Image: /attachments/x/file]",
        model="image-gen-model",
    )
    await db_session.flush()

    moved = await db_session.scalar(
        select(Chat.updated_at).where(Chat.id == chat.id).execution_options(populate_existing=True)
    )
    assert moved is not None and moved > long_ago + timedelta(days=2)
    assert await history.message_count(db_session, chat.id) == 1
