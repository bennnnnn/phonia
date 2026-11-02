"""Real-Postgres tests for chat's messages repository.

`test_messages.py` mocks `AsyncSession` and returns a canned result no
matter what statement is executed, so it can't catch wrong ordering or a
`chat_id` scoping filter that's missing/inverted. These tests build real
`Message` rows (with explicit `created_at`/`id` values, since Postgres
`now()` is pinned to transaction start and every fixture row in a test
shares one transaction) and exercise the real compiled SQL via the
`db_session` fixture.
"""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.orm import Message
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.repositories import users as users_repo


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


def _build_message(chat_id, user_id, *, created_at, message_id=None, role="user", content="msg"):
    """Construct a Message with an explicit created_at/id (bypassing the
    repository's `create()`, which has no way to control either) so ordering
    and cutoff tests are deterministic instead of racing the DB clock."""
    kwargs = {"id": message_id} if message_id is not None else {}
    return Message(
        chat_id=chat_id,
        user_id=user_id,
        role=role,
        content=content,
        created_at=created_at,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_list_recent_returns_correct_order_and_respects_limit(db_session):
    user = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    messages = [
        _build_message(chat.id, user.id, created_at=base + timedelta(minutes=i), content=f"m{i}")
        for i in range(5)
    ]
    db_session.add_all(messages)
    await db_session.flush()

    result = await messages_repo.list_recent(db_session, chat.id, limit=3)

    # list_recent takes the 3 newest (desc + limit) then reverses back to
    # chronological order — a wrong ORDER BY or a missing .reverse() would
    # both show up here.
    assert [m.content for m in result] == ["m2", "m3", "m4"]


@pytest.mark.asyncio
async def test_get_by_id_scoped_by_chat_does_not_leak_across_chats(db_session):
    user = await _make_user(db_session)
    chat_a = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    chat_b = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    message = await messages_repo.create(
        db_session, chat_id=chat_a.id, user_id=user.id, role="user", content="hi"
    )

    assert await messages_repo.get_by_id(db_session, message.id, chat_b.id) is None

    found = await messages_repo.get_by_id(db_session, message.id, chat_a.id)
    assert found is not None
    assert found.id == message.id


@pytest.mark.asyncio
async def test_list_range_is_stable_across_created_at_ties(db_session):
    """BUG FIX (was silent): list_range previously ordered by created_at alone.
    Postgres doesn't guarantee any particular sub-order among equal
    created_at values, so background/compaction.py's offset/limit pagination
    across successive calls could skip or double-count a row at a page
    boundary whenever two messages landed in the same millisecond. Insert
    rows with identical created_at in an order that does NOT match their id
    order (id order != insertion order) — if the (created_at, id) tiebreak
    in the query is ever dropped, this is very likely to come back in
    insertion order instead of id order and fail this assertion.
    """
    user = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    insertion_order_ids = [3, 1, 4, 0, 2]
    messages = [
        _build_message(
            chat.id,
            user.id,
            created_at=same_time,
            message_id=uuid.UUID(int=i),
            content=f"m{i}",
        )
        for i in insertion_order_ids
    ]
    db_session.add_all(messages)
    await db_session.flush()

    page1 = await messages_repo.list_range(db_session, chat.id, offset=0, limit=2)
    page2 = await messages_repo.list_range(db_session, chat.id, offset=2, limit=2)
    page3 = await messages_repo.list_range(db_session, chat.id, offset=4, limit=2)

    # Every row appears exactly once across consecutive pages, in the query's
    # (created_at, id) order — ascending id here since created_at ties.
    all_content = [m.content for m in page1 + page2 + page3]
    assert all_content == ["m0", "m1", "m2", "m3", "m4"]


async def test_get_last_user_uses_id_tiebreaker_when_created_at_ties(db_session):
    """get_last_user must order by
    (created_at, id) so a shared millisecond doesn't make "last"
    non-deterministic — regenerate relies on a single canonical last row."""
    user = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    # Insert in an order that does NOT match id order, so insertion-order
    # fallback would pick the wrong row if the id tiebreaker were dropped.
    rows = [
        _build_message(
            chat.id,
            user.id,
            created_at=same_time,
            message_id=uuid.UUID(int=1),
            role="user",
            content="u1",
        ),
        _build_message(
            chat.id,
            user.id,
            created_at=same_time,
            message_id=uuid.UUID(int=3),
            role="assistant",
            content="a3",
        ),
        _build_message(
            chat.id,
            user.id,
            created_at=same_time,
            message_id=uuid.UUID(int=2),
            role="user",
            content="u2",
        ),
        _build_message(
            chat.id,
            user.id,
            created_at=same_time,
            message_id=uuid.UUID(int=4),
            role="assistant",
            content="a4",
        ),
    ]
    db_session.add_all(rows)
    await db_session.flush()

    last_user = await messages_repo.get_last_user(db_session, chat.id)

    # Highest id wins the tie — deterministic regardless of insertion order.
    assert last_user is not None and last_user.content == "u2"
