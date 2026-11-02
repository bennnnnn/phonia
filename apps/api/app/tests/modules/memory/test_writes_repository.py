"""Execute conditional memory statements locally; PostgreSQL coverage lives in *_db.py."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.orm import Memory
from app.tests.modules.memory.sections_support import upsert_sections


@pytest.fixture
def memory_sql():
    engine = create_engine("sqlite://")
    Memory.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as sync_session:
        session = AsyncMock(spec=AsyncSession)
        session.execute.side_effect = sync_session.execute
        session.commit.side_effect = sync_session.commit
        session.flush.side_effect = sync_session.flush
        session.add.side_effect = sync_session.add
        session.delete.side_effect = sync_session.delete
        yield sync_session, session
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["same", "new_text", "wrong_owner", "wrong_id", "stale_text"])
async def test_conditional_section_update_requires_owned_current_snapshot(memory_sql, change):
    sync_session, session = memory_sql
    owner_id = uuid4()
    row = Memory(
        user_id=owner_id,
        type="fact",
        text="Old fact",
        embedding=[0.1] * 1536,
        embedding_json="[0.1]",
        embedding_text_hash="old-hash",
    )
    sync_session.add(row)
    sync_session.commit()
    requested_text = "Old fact" if change == "same" else "New fact"
    await upsert_sections(
        session,
        user_id=uuid4() if change == "wrong_owner" else owner_id,
        items=[("fact", requested_text, 0.9, None)],
        expected_sections={
            "fact": (
                uuid4() if change == "wrong_id" else row.id,
                "Stale fact" if change == "stale_text" else "Old fact",
            )
        },
    )
    sync_session.refresh(
        row, attribute_names=["text", "embedding", "embedding_json", "embedding_text_hash"]
    )
    assert row.text == ("New fact" if change == "new_text" else "Old fact")
    assert (row.embedding is None) == (change == "new_text")
    assert row.embedding_json == (None if change == "new_text" else "[0.1]")
    assert row.embedding_text_hash == (None if change == "new_text" else "old-hash")


@pytest.mark.asyncio
async def test_new_section_conflict_preserves_existing_memory(memory_sql):
    sync_session, session = memory_sql
    owner_id = uuid4()
    await upsert_sections(
        session,
        user_id=owner_id,
        items=[("fact", "First fact", 0.9, None)],
        expected_sections={},
    )
    await upsert_sections(
        session,
        user_id=owner_id,
        items=[("fact", "Stale generated fact", 0.9, None)],
        expected_sections={},
    )
    rows = sync_session.query(Memory).filter_by(user_id=owner_id).all()
    assert {row.text for row in rows} == {"First fact", "Stale generated fact"}
