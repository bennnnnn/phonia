"""A window of messages around a search hit, and the pages after it (code-health audit NET-18)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.models.orm import Message
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.repositories import users as users_repo


async def _chat_with(db_session, count: int):
    user = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Window",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        row = await messages_repo.create(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"m{index}",
        )
        rows.append(row)
    for index, row in enumerate(rows):
        await db_session.execute(
            update(Message)
            .where(Message.id == row.id)
            .values(created_at=start + timedelta(minutes=index))
        )
    await db_session.commit()
    return chat, rows


def _contents(messages) -> list[str]:
    return [message.content for message in messages]


@pytest.mark.asyncio
async def test_a_window_puts_the_hit_in_its_middle(db_session):
    chat, rows = await _chat_with(db_session, 100)
    window, older, newer = await messages_repo.list_around(
        db_session, chat.id, limit=10, around_id=rows[50].id
    )
    assert _contents(window) == [f"m{index}" for index in range(46, 56)]
    assert (older, newer) == (True, True)


@pytest.mark.asyncio
async def test_a_window_near_either_end_says_so(db_session):
    chat, rows = await _chat_with(db_session, 20)
    first, older, newer = await messages_repo.list_around(
        db_session, chat.id, limit=10, around_id=rows[1].id
    )
    assert _contents(first)[:2] == ["m0", "m1"]
    assert (older, newer) == (False, True)
    last, older, newer = await messages_repo.list_around(
        db_session, chat.id, limit=10, around_id=rows[19].id
    )
    assert _contents(last)[-1] == "m19"
    assert (older, newer) == (True, False)


@pytest.mark.asyncio
async def test_pages_after_a_message_reach_the_newest(db_session):
    chat, rows = await _chat_with(db_session, 25)
    page, more = await messages_repo.list_after(db_session, chat.id, limit=10, after_id=rows[4].id)
    assert _contents(page) == [f"m{index}" for index in range(5, 15)]
    assert more is True
    page, more = await messages_repo.list_after(db_session, chat.id, limit=10, after_id=rows[14].id)
    assert _contents(page) == [f"m{index}" for index in range(15, 25)]
    assert more is False


@pytest.mark.asyncio
async def test_an_unknown_anchor_is_an_empty_window(db_session):
    chat, _rows = await _chat_with(db_session, 3)
    assert await messages_repo.list_around(db_session, chat.id, limit=10, around_id=uuid4()) == (
        [],
        False,
        False,
    )
    assert await messages_repo.list_after(db_session, chat.id, limit=10, after_id=uuid4()) == (
        [],
        False,
    )
