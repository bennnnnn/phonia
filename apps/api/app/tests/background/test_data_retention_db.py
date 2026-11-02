"""Hourly data retention: drafts never sent to and old daily usage rows go, in batches."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.background import data_retention_scheduler
from app.core.config import Settings
from app.models.orm import Chat, Message, UsageDaily
from app.modules.conversation import chats_repository as chats_repo
from app.repositories import usage as usage_repo
from app.repositories import users as users_repo

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


async def _user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def _chat(session, user_id, *, age: timedelta, with_message: bool) -> Chat:
    chat = await chats_repo.create(session, user_id=user_id, model="free-chat")
    chat.created_at = NOW - age
    if with_message:
        session.add(Message(chat_id=chat.id, user_id=user_id, role="user", content="hi"))
    await session.flush()
    return chat


async def test_only_old_chats_with_no_message_are_deleted(db_session) -> None:
    user = await _user(db_session)
    old_draft = await _chat(db_session, user.id, age=timedelta(days=8), with_message=False)
    new_draft = await _chat(db_session, user.id, age=timedelta(hours=1), with_message=False)
    old_chat = await _chat(db_session, user.id, age=timedelta(days=30), with_message=True)

    removed = await chats_repo.delete_abandoned_drafts(
        db_session, NOW - timedelta(days=7), limit=100
    )

    left = set((await db_session.execute(select(Chat.id).where(Chat.user_id == user.id))).scalars())
    assert removed == 1
    assert left == {new_draft.id, old_chat.id}
    assert old_draft.id not in left


async def test_daily_usage_rows_older_than_the_cutoff_are_deleted(db_session) -> None:
    user = await _user(db_session)
    for day in (date(2025, 1, 1), date(2025, 9, 1), date(2026, 10, 22)):
        db_session.add(UsageDaily(user_id=user.id, date=day, input_tokens=1, output_tokens=1))
    await db_session.flush()

    removed = await usage_repo.delete_before(db_session, date(2025, 9, 1), limit=100)

    days = (
        await db_session.execute(select(UsageDaily.date).where(UsageDaily.user_id == user.id))
    ).scalars()
    assert removed == 1
    assert sorted(days) == [date(2025, 9, 1), date(2026, 10, 22)]


@pytest.mark.asyncio
async def test_a_cycle_deletes_in_batches_until_a_short_one_or_the_budget() -> None:
    settings = Settings(data_retention_delete_batch=10, data_retention_max_deletes_per_cycle=25)
    drafts = AsyncMock(side_effect=[10, 10, 10, 10])
    usage = AsyncMock(side_effect=[3])
    with (
        patch.object(
            data_retention_scheduler.conversation_service, "delete_abandoned_drafts", drafts
        ),
        patch.object(data_retention_scheduler.usage_repo, "delete_before", usage),
    ):
        deleted = await data_retention_scheduler.run_retention(
            settings, AsyncMock(return_value=True)
        )

    # Drafts stop at the 25-row budget (three batches); usage stops on its short batch.
    assert drafts.await_count == 3
    assert usage.await_count == 1
    assert deleted == 33


@pytest.mark.asyncio
async def test_a_lost_lock_stops_the_cycle() -> None:
    drafts = AsyncMock(return_value=10)
    with patch.object(
        data_retention_scheduler.conversation_service, "delete_abandoned_drafts", drafts
    ):
        deleted = await data_retention_scheduler.run_retention(
            Settings(), AsyncMock(return_value=False)
        )
    assert deleted == 0
    drafts.assert_not_awaited()
