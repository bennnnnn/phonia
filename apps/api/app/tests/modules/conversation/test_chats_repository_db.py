"""Real-Postgres tests for chat's chats repository.

`test_chats.py` mocks `AsyncSession`, so it can only prove "did the
repository call `.execute()`". It cannot catch a `WHERE user_id ==` filter
that's missing or inverted, a broken `has_messages` EXISTS subquery/join, or
`archived` filtering that silently happens in Python instead of SQL — since
the mock returns the same canned rows regardless of the statement built.
These tests build real `User`/`Chat`/`Message` rows and run the real
compiled queries against Postgres via the `db_session` fixture
(`app/tests/repositories/conftest.py`).
"""

from uuid import uuid4

import pytest
from sqlalchemy import update

from app.models.orm import Chat
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


async def _make_chat_with_message(session, user_id):
    """A chat with >=1 message — list_for_user only surfaces chats that have
    at least one message (has_messages EXISTS subquery)."""
    chat = await chats_repo.create(session, user_id=user_id, model="free-chat")
    await messages_repo.create(
        session,
        chat_id=chat.id,
        user_id=user_id,
        role="user",
        content="hello",
    )
    return chat


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_a_different_users_chat(db_session):
    """Proves the WHERE user_id == filter is real, not just present but
    broken/inverted — a mocked test can't distinguish "filtered correctly"
    from "ignored the filter and returned the canned row anyway"."""
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=owner.id, model="free-chat")

    assert await chats_repo.get_by_id(db_session, chat.id, other_user.id) is None

    found = await chats_repo.get_by_id(db_session, chat.id, owner.id)
    assert found is not None
    assert found.id == chat.id


@pytest.mark.asyncio
async def test_list_for_user_only_returns_calling_users_chats(db_session):
    """Two users each have a chat; list_for_user(user_a) must not leak
    user_b's chat."""
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    chat_a = await _make_chat_with_message(db_session, user_a.id)
    await _make_chat_with_message(db_session, user_b.id)

    result = await chats_repo.list_for_user(db_session, user_a.id)

    assert [c.id for c in result] == [chat_a.id]


@pytest.mark.asyncio
async def test_list_for_user_excludes_chats_with_no_messages(db_session):
    """The has_messages EXISTS subquery must actually filter at the SQL
    level — an abandoned draft chat (zero messages) should never surface."""
    user = await _make_user(db_session)
    with_message = await _make_chat_with_message(db_session, user.id)
    await chats_repo.create(db_session, user_id=user.id, model="free-chat")  # no messages

    result = await chats_repo.list_for_user(db_session, user.id)

    assert [c.id for c in result] == [with_message.id]


@pytest.mark.asyncio
async def test_list_for_user_archived_filtering_happens_in_sql(db_session):
    """include_archived=False (default) must exclude archived chats at the
    SQL level; include_archived=True must include them."""
    user = await _make_user(db_session)
    active = await _make_chat_with_message(db_session, user.id)
    archived = await _make_chat_with_message(db_session, user.id)
    await chats_repo.set_archived(db_session, archived, True)

    default_result = await chats_repo.list_for_user(db_session, user.id)
    assert [c.id for c in default_result] == [active.id]

    with_archived = await chats_repo.list_for_user(db_session, user.id, include_archived=True)
    assert {c.id for c in with_archived} == {active.id, archived.id}


@pytest.mark.asyncio
async def test_generated_title_preserves_rename_and_owner_scope(db_session):
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=owner.id, model="free-chat")
    assert not await chats_repo.set_title_if_empty(
        db_session, chat.id, "Wrong owner", user_id=other_user.id
    )
    await db_session.execute(
        update(Chat)
        .where(Chat.id == chat.id)
        .values(title="Manual title")
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert chat.title is None

    assert not await chats_repo.set_title_if_empty(
        db_session, chat.id, "Generated title", user_id=owner.id
    )
    await db_session.refresh(chat)
    assert chat.title == "Manual title"


@pytest.mark.asyncio
async def test_pin_archive_races_preserve_archived_unpinned_state(db_session):
    owner = await _make_user(db_session)
    chat = await chats_repo.create(db_session, user_id=owner.id, model="free-chat")
    await db_session.execute(
        update(Chat)
        .where(Chat.id == chat.id)
        .values(pinned=True)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert chat.pinned is False

    await chats_repo.set_archived(db_session, chat, True)
    assert chat.archived is True
    assert chat.pinned is False
    await chats_repo.set_pinned(db_session, chat, True)
    assert chat.archived is True
    assert chat.pinned is False


@pytest.mark.asyncio
async def test_the_drawer_pages_every_dated_chat_by_cursor(db_session):
    """CLAR-12: past the first page the drawer reads on; pinned and archived chats stay out."""
    from datetime import UTC, datetime, timedelta

    owner = await _make_user(db_session)
    dated = [await _make_chat_with_message(db_session, owner.id) for _ in range(5)]
    pinned = await _make_chat_with_message(db_session, owner.id)
    archived = await _make_chat_with_message(db_session, owner.id)
    base = datetime(2026, 10, 1, tzinfo=UTC)
    # Two chats share a time, so the id breaks the tie.
    times = {chat.id: base + timedelta(minutes=min(index, 3)) for index, chat in enumerate(dated)}
    for chat_id, at in times.items():
        await db_session.execute(update(Chat).where(Chat.id == chat_id).values(updated_at=at))
    await db_session.execute(update(Chat).where(Chat.id == pinned.id).values(pinned=True))
    await db_session.execute(update(Chat).where(Chat.id == archived.id).values(archived=True))
    await db_session.commit()

    read: list = []
    cursor = None
    for _ in range(3):
        page, cursor = await chats_repo.list_recent_page(
            db_session, owner.id, limit=2, cursor=cursor
        )
        read += [chat.id for chat in page]
        if cursor is None:
            break

    assert read == sorted(times, key=lambda chat_id: (times[chat_id], chat_id), reverse=True)
    assert cursor is None
    assert [chat.id for chat in await chats_repo.list_pinned(db_session, owner.id)] == [pinned.id]


@pytest.mark.asyncio
async def test_only_activity_moves_a_chat_up_the_drawer(db_session):
    """Pin, unpin, rename, archive, unarchive and a generated title used to bump
    updated_at (onupdate=now()), so tidying a chat moved it to Today."""
    from datetime import UTC, datetime

    user = await _make_user(db_session)
    chat = await _make_chat_with_message(db_session, user.id)
    long_ago = datetime(2025, 1, 1, tzinfo=UTC)

    async def updated_at() -> datetime:
        await db_session.execute(update(Chat).where(Chat.id == chat.id).values(updated_at=long_ago))
        await db_session.commit()
        return long_ago

    steps = [
        lambda: chats_repo.set_pinned(db_session, chat, True),
        lambda: chats_repo.set_pinned(db_session, chat, False),
        lambda: chats_repo.set_title(db_session, chat, "Renamed"),
        lambda: chats_repo.set_archived(db_session, chat, True),
        lambda: chats_repo.set_archived(db_session, chat, False),
        lambda: chats_repo.archive_all_for_user(db_session, user.id),
    ]
    for step in steps:
        before = await updated_at()
        await step()
        await db_session.refresh(chat)
        assert chat.updated_at == before

    await updated_at()
    await chats_repo.set_title(db_session, chat, "")
    await chats_repo.set_title_if_empty(db_session, chat.id, "Generated", user_id=user.id)
    await db_session.refresh(chat)
    assert chat.updated_at == long_ago

    await chats_repo.touch_by_id(db_session, chat.id)
    await db_session.refresh(chat)
    assert chat.updated_at > long_ago


@pytest.mark.asyncio
async def test_every_archived_chat_is_reachable_by_cursor(db_session):
    """Only the newest 50 archived chats were ever listed; "Archive all" put the rest
    out of reach."""
    from datetime import UTC, datetime, timedelta

    user = await _make_user(db_session)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    made = []
    for step in range(7):
        chat = await _make_chat_with_message(db_session, user.id)
        await db_session.execute(
            update(Chat)
            .where(Chat.id == chat.id)
            .values(archived=True, updated_at=start + timedelta(hours=step))
        )
        made.append(chat.id)
    await db_session.commit()

    seen = []
    cursor = None
    while True:
        page, cursor = await chats_repo.list_archived_page(
            db_session, user.id, limit=3, cursor=cursor
        )
        seen.extend(chat.id for chat in page)
        if cursor is None:
            break
    assert seen == list(reversed(made))


@pytest.mark.asyncio
async def test_bulk_archive_and_delete_change_only_the_users_own_chats(db_session):
    """The drawer's selection in one request: another user's id in the list is skipped."""
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    mine = [await _make_chat_with_message(db_session, owner.id) for _ in range(3)]
    theirs = await _make_chat_with_message(db_session, other.id)
    await chats_repo.set_pinned(db_session, mine[0], True)
    ids = [chat.id for chat in mine] + [theirs.id]

    archived = await chats_repo.set_archived_many(db_session, owner.id, ids, archived=True)
    await db_session.commit()
    assert set(archived) == {chat.id for chat in mine}
    for chat in mine:
        await db_session.refresh(chat)
        assert chat.archived and not chat.pinned
    await db_session.refresh(theirs)
    assert not theirs.archived

    restored = await chats_repo.set_archived_many(db_session, owner.id, ids[:1], archived=False)
    await db_session.commit()
    assert restored == [mine[0].id]

    deleted = await chats_repo.delete_many(db_session, owner.id, ids)
    await db_session.commit()
    assert set(deleted) == {chat.id for chat in mine}
    assert await chats_repo.get_by_id(db_session, theirs.id, other.id) is not None
    assert await chats_repo.get_by_id(db_session, mine[1].id, owner.id) is None
