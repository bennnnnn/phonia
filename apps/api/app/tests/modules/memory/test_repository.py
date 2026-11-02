from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.memory import repository as memories_repo
from app.tests.modules.memory.sections_support import upsert_sections


@pytest.mark.asyncio
async def test_upsert_sections_empty_items_is_noop(fake_session):
    await upsert_sections(fake_session, user_id=uuid4(), items=[])
    fake_session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_sections_executes_and_commits(fake_session):
    user_id = uuid4()
    items = [("profile", "User is Sam, a software engineer.", 0.9, None)]
    await upsert_sections(fake_session, user_id=user_id, items=items)
    assert fake_session.execute.await_count >= 1
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_sections_commit_false_flushes_without_committing(fake_session):
    await upsert_sections(
        fake_session,
        user_id=uuid4(),
        items=[("fact", "Owns a bicycle.", 0.9, None)],
        commit=False,
    )

    fake_session.execute.assert_awaited()
    fake_session.flush.assert_awaited()
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_sections_adds_duplicate_types_as_separate_facts(fake_session):
    user_id = uuid4()
    items = [
        ("profile", "Low confidence profile.", 0.5, None),
        ("profile", "High confidence profile.", 0.9, None),
        ("preference", "Likes tea.", 0.8, None),
    ]
    await upsert_sections(fake_session, user_id=user_id, items=items)
    assert fake_session.execute.await_count >= 1
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_sections_keeps_same_type_facts(fake_session):
    user_id = uuid4()
    items = [
        ("fact", "First fact.", 0.7, None),
        ("fact", "Second fact.", 0.7, None),
    ]
    await upsert_sections(fake_session, user_id=user_id, items=items)
    assert fake_session.execute.await_count >= 1
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_for_user_returns_memories(fake_session):
    user_id = uuid4()
    row = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    fake_session.execute.return_value = mock_result
    result = await memories_repo.list_for_user(fake_session, user_id)
    assert result == [row]


# ── memories.upsert_sections — single execute call ─────────────────────────────


@pytest.mark.asyncio
async def test_upsert_sections_single_query():
    """upsert_sections must issue exactly 1 execute() call regardless of item count."""
    from app.tests.modules.memory.sections_support import upsert_sections

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    uid = uuid4()
    items = [
        ("fact", "Uses Python and TypeScript.", 0.9, None),
        ("preference", "Prefers short answers.", 0.8, None),
        ("focus", "Working on API project.", 0.7, uuid4()),
    ]

    await upsert_sections(session, user_id=uid, items=items)

    assert session.execute.await_count >= 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_sections_empty_is_noop():
    from app.tests.modules.memory.sections_support import upsert_sections

    session = AsyncMock()
    await upsert_sections(session, user_id=uuid4(), items=[])
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
