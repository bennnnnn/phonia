"""PostgreSQL regressions for memory management versus stale background results."""

from uuid import uuid4

import pytest

from app.models.orm import Memory
from app.modules.memory import repository as memories_repo
from app.repositories import users as users_repo
from app.tests.modules.memory.sections_support import upsert_sections


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["same", "new_text", "manual_edit", "delete", "wrong_owner"])
async def test_background_snapshot_preserves_manual_changes_and_ownership(db_session, change):
    user = await _make_user(db_session)
    row = Memory(
        user_id=user.id,
        type="fact",
        text="Old fact",
        embedding=[0.1] * 1536,
        embedding_json="[0.1]",
        embedding_text_hash="old-hash",
    )
    db_session.add(row)
    await db_session.flush()
    memory_id = row.id
    if change == "manual_edit":
        row.text = "Manual edit"
    elif change == "delete":
        await db_session.delete(row)
    await db_session.flush()

    await upsert_sections(
        db_session,
        user_id=uuid4() if change == "wrong_owner" else user.id,
        items=[("fact", "Old fact" if change == "same" else "Generated fact", 0.9, None)],
        expected_sections={"fact": (memory_id, "Old fact")},
    )

    if change == "delete":
        assert await memories_repo.list_for_user(db_session, user.id) == []
        return
    await db_session.refresh(
        row, attribute_names=["text", "embedding", "embedding_json", "embedding_text_hash"]
    )
    expected = {"manual_edit": "Manual edit", "new_text": "Generated fact"}.get(change, "Old fact")
    assert row.text == expected
    assert (row.embedding is None) == (change == "new_text")
    assert row.embedding_json == (None if change == "new_text" else "[0.1]")
    assert row.embedding_text_hash == (None if change == "new_text" else "old-hash")


@pytest.mark.asyncio
async def test_new_section_conflict_does_not_replace_competing_creation(db_session):
    user = await _make_user(db_session)
    for content in ["First fact", "Stale generated fact"]:
        await upsert_sections(
            db_session,
            user_id=user.id,
            items=[("fact", content, 0.9, None)],
            expected_sections={},
        )
    rows = await memories_repo.list_for_user(db_session, user.id)
    assert {row.text for row in rows} == {"First fact", "Stale generated fact"}


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False, None])
async def test_background_persistence_checks_current_account_preference(db_session, enabled):
    user = await _make_user(db_session)
    user.memory_enabled = bool(enabled)
    await db_session.flush()
    assert await memories_repo.lock_memory_enabled(
        db_session, user.id if enabled is not None else uuid4()
    ) is bool(enabled)


@pytest.mark.asyncio
@pytest.mark.parametrize("match", ["current", "stale_text", "wrong_owner", "deleted"])
async def test_background_embedding_only_updates_owned_current_text(db_session, match):
    user = await _make_user(db_session)
    row = Memory(user_id=user.id, type="fact", text="Current fact")
    db_session.add(row)
    await db_session.flush()
    memory_id = row.id
    if match == "deleted":
        await db_session.delete(row)
        await db_session.flush()
    await memories_repo.update_embedding_if_current(
        db_session,
        uuid4() if match == "wrong_owner" else user.id,
        memory_id,
        "Stale fact" if match == "stale_text" else "Current fact",
        [0.2] * 1536,
        "current-hash",
    )
    if match == "deleted":
        assert await memories_repo.list_for_user(db_session, user.id) == []
        return
    await db_session.refresh(
        row, attribute_names=["text", "embedding", "embedding_json", "embedding_text_hash"]
    )
    assert (row.embedding is not None) == (match == "current")
    # The JSON copy is no longer written.
    assert row.embedding_json is None
    assert row.embedding_text_hash == ("current-hash" if match == "current" else None)
