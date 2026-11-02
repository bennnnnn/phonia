"""Real-Postgres tests for app.modules.memory.repository.

`test_memories.py` mocks `AsyncSession`, so a `WHERE user_id ==` filter that
was dropped would be invisible to it — the mock hands back the same canned result regardless
of the statement executed. These tests build real `Memory` rows for
multiple users/types and run the real compiled SQL via the `db_session`
fixture.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.orm import Chat, Memory
from app.modules.memory import enqueue_policy
from app.modules.memory import repository as memories_repo
from app.modules.memory.schemas import MemoryOut
from app.repositories import users as users_repo


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


def _build_memory(user_id, *, memory_type, text):
    return Memory(user_id=user_id, type=memory_type, text=text)


@pytest.mark.asyncio
async def test_list_for_user_only_returns_that_users_memories(db_session):
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    db_session.add_all(
        [
            _build_memory(user_a.id, memory_type="profile", text="A profile"),
            _build_memory(user_a.id, memory_type="preference", text="A preference"),
            _build_memory(user_b.id, memory_type="profile", text="B profile"),
        ]
    )
    await db_session.flush()

    result = await memories_repo.list_for_user(db_session, user_a.id)

    assert {m.text for m in result} == {"A profile", "A preference"}
    assert all(m.user_id == user_a.id for m in result)


@pytest.mark.asyncio
async def test_list_for_user_breaks_confirmed_at_ties_by_id(db_session):
    """Facts confirmed in one write share ``last_confirmed_at``: the id fixes their order."""
    user = await _make_user(db_session)
    same_time = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [_build_memory(user.id, memory_type="fact", text=f"Fact {n}") for n in range(5)]
    for row in rows:
        row.last_confirmed_at = same_time
    db_session.add_all(rows)
    await db_session.flush()

    result = await memories_repo.list_for_user(db_session, user.id)

    assert [m.id for m in result] == sorted((r.id for r in rows), reverse=True)


@pytest.mark.asyncio
async def test_source_chat_titles_names_only_the_users_chats(db_session):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    own_chat = Chat(user_id=owner.id, title="Trip planning")
    foreign_chat = Chat(user_id=other.id, title="Someone else's secret")
    db_session.add_all([own_chat, foreign_chat])
    await db_session.flush()
    facts = [
        _build_memory(owner.id, memory_type="fact", text="Own"),
        _build_memory(owner.id, memory_type="fact", text="Foreign"),
    ]
    facts[0].source_chat_id = own_chat.id
    facts[1].source_chat_id = foreign_chat.id

    titles = await enqueue_policy.source_chat_titles(db_session, owner.id, facts)

    assert titles == {own_chat.id: "Trip planning"}


@pytest.mark.asyncio
async def test_update_text_flush_serializes_memory_out(db_session):
    """commit=False flush expires updated_at; PATCH then MemoryOut.model_validate 500'd."""
    user = await _make_user(db_session)
    row = _build_memory(user.id, memory_type="fact", text="Old fact")
    db_session.add(row)
    await db_session.commit()

    updated = await memories_repo.update_text(
        db_session, user.id, row.id, "New fact about hiking", commit=False
    )
    await db_session.commit()

    assert updated is not None
    out = MemoryOut.model_validate(updated)
    assert out.text == "New fact about hiking"
    assert out.id == row.id
    assert out.updated_at is not None
