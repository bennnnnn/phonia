"""The export's lists, read from Postgres: newest product events, pages by key."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.orm import Chat, Message, ProductEvent
from app.modules.conversation import history as chat_history
from app.repositories import product_events as product_events_repo
from app.repositories import users as users_repo


async def _user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Export",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_capped_product_events_keep_the_newest_oldest_first(db_session):
    """The export kept the oldest events past its cap, leaving out recent activity."""
    user = await _user(db_session)
    start = datetime(2026, 10, 1, tzinfo=UTC)
    db_session.add_all(
        ProductEvent(user_id=user.id, name="paywall_viewed", recorded_at=start + timedelta(hours=n))
        for n in range(5)
    )
    await db_session.commit()

    events = await product_events_repo.list_for_user(db_session, user.id, limit=3)

    assert [event.recorded_at for event in events] == [
        start + timedelta(hours=n) for n in (2, 3, 4)
    ]


@pytest.mark.asyncio
async def test_export_message_pages_skip_nothing_when_an_earlier_message_goes(db_session):
    """An offset skipped a message when one before it was deleted mid-export (a
    regenerate replaces a reply); each page now reads after the last row read."""
    user = await _user(db_session)
    chat = Chat(user_id=user.id, title="t")
    db_session.add(chat)
    await db_session.flush()
    start = datetime(2026, 10, 1, tzinfo=UTC)
    messages = [
        Message(
            chat_id=chat.id,
            user_id=user.id,
            role="user",
            content=f"m{n}",
            created_at=start + timedelta(minutes=n),
        )
        for n in range(5)
    ]
    db_session.add_all(messages)
    await db_session.commit()

    first = await chat_history.messages_for_export(db_session, chat.id, after=None, limit=2)
    await db_session.delete(messages[0])
    await db_session.commit()
    last = first[-1]
    rest = await chat_history.messages_for_export(
        db_session, chat.id, after=(last.created_at, last.id), limit=10
    )

    assert [m.content for m in first + rest] == ["m0", "m1", "m2", "m3", "m4"]
