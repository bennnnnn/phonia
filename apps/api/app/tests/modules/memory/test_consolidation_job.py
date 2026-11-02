from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory.consolidation_workflow import consolidate_user_memory_sections
from app.modules.memory.schemas import MemorySectionItem
from app.modules.memory.text import embedding_text_hash
from app.modules.memory.writes_repository import MemoryFactWrite
from app.tests.fakes import FakeSessionCM
from app.tests.modules.memory.embedding_support import EMBED_MANY, embed_each


def _consolidation_sessions(*, count: int = 1) -> tuple[AsyncMock, list[FakeSessionCM]]:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session, [FakeSessionCM(session) for _ in range(count)]


def _fact(
    *,
    memory_id=None,
    memory_type: str = "profile",
    text: str,
    status: str = "active",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=memory_id or uuid4(),
        type=memory_type,
        text=text,
        status=status,
        last_confirmed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        embedding=None,
        embedding_json=None,
        embedding_text_hash=None,
    )


@pytest.fixture(autouse=True)
def _memory_persistence_gate_enabled():
    with patch("app.modules.memory.repository.lock_memory_enabled", AsyncMock(return_value=True)):
        yield


@pytest.fixture
def embedding_write():
    with patch("app.modules.memory.repository.update_embedding_if_current", AsyncMock()) as write:
        yield write


@pytest.fixture(autouse=True)
def _memory_write_lock_always_free():
    with (
        patch(
            "app.modules.memory.consolidation_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.consolidation_workflow.release_memory_write_lock", AsyncMock()),
        patch(
            "app.modules.memory.consolidation_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True)),
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_consolidate_skips_clean_sections():
    user_id = uuid4()
    memory = _fact(text="Bini is a software engineer at Hooh.")
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[memory]),
        ),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is False


@pytest.mark.asyncio
async def test_consolidate_skips_when_memory_disabled():
    user_id = uuid4()
    list_for_user = AsyncMock()
    merge = AsyncMock()
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=False)),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user", list_for_user
        ),
        patch("app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section", merge),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is False
    list_for_user.assert_not_awaited()
    merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_skips_when_write_lock_held():
    user_id = uuid4()
    list_for_user = AsyncMock()
    merge = AsyncMock()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user", list_for_user
        ),
        patch("app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section", merge),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed == "skipped_lock"
    list_for_user.assert_not_awaited()
    merge.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_deletes_exact_duplicate_without_llm():
    user_id = uuid4()
    text = "Prefers concise answers."
    keep = _fact(memory_type="preference", text=text)
    extra = _fact(memory_type="preference", text=text)
    apply = AsyncMock()
    merge = AsyncMock()
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch("app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section", merge),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", apply),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    merge.assert_not_awaited()
    apply.assert_awaited_once()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert len(writes) == 1
    assert writes[0].op == "delete"
    assert writes[0].match_text == text


@pytest.mark.asyncio
async def test_consolidate_merges_near_duplicate_pair():
    user_id = uuid4()
    keep = _fact(text="Bini is a developer at Hooh.")
    extra = _fact(text="Bini is a developer at Hooh now.")
    extra.last_confirmed_at = datetime(2026, 1, 1, tzinfo=UTC)
    keep.last_confirmed_at = datetime(2026, 6, 1, tzinfo=UTC)
    merged = MemorySectionItem(
        type="profile",
        summary="Bini is a developer at Hooh today.",
        confidence=0.9,
    )
    apply = AsyncMock()
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section",
            AsyncMock(return_value=merged),
        ),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", apply),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    ops = {write.op for write in writes}
    assert "delete" in ops
    assert any(write.op == "update" and "today" in write.text for write in writes)


@pytest.mark.asyncio
async def test_consolidate_keeps_keeper_when_merge_drops_anchors():
    user_id = uuid4()
    keep = _fact(text="Bini works at Hooh and lives in Oakland.")
    extra = _fact(text="Bini works at Hooh and lives in Oakland now.")
    merged = MemorySectionItem(type="profile", summary="Bini.", confidence=0.9)
    apply = AsyncMock()
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section",
            AsyncMock(return_value=merged),
        ),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", apply),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert all(write.op == "delete" for write in writes)


@pytest.mark.asyncio
async def test_consolidate_applies_only_duplicate_types():
    user_id = uuid4()
    profile_a = _fact(text="Bini is a developer at Hooh.")
    profile_b = _fact(text="Bini is a developer at Hooh.")
    preference = _fact(memory_type="preference", text="Prefers concise answers.")
    apply = AsyncMock()
    merge = AsyncMock()
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[profile_a, profile_b, preference]),
        ),
        patch("app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section", merge),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", apply),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    merge.assert_not_awaited()
    writes: list[MemoryFactWrite] = apply.await_args.kwargs["writes"]
    assert all(write.type == "profile" for write in writes)


@pytest.mark.asyncio
async def test_consolidate_stores_embedding_when_vector_present(embedding_write):
    user_id = uuid4()
    text = "Prefers concise answers."
    keep = _fact(memory_type="preference", text=text)
    extra = _fact(memory_type="preference", text=text)
    listed = SimpleNamespace(id=keep.id, text=text)
    vector = [0.1, 0.2, 0.3]
    session, session_locals = _consolidation_sessions(count=3)
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_embed_state",
            AsyncMock(return_value=[(listed.id, listed.text, False, None)]),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.apply_writes",
            AsyncMock(return_value=[keep.id]),
        ),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
        patch(EMBED_MANY, embed_each(AsyncMock(return_value=vector))),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    embedding_write.assert_awaited_once_with(
        session,
        user_id,
        keep.id,
        listed.text,
        vector,
        embedding_text_hash(listed.text),
        commit=False,
    )


@pytest.mark.asyncio
async def test_consolidate_releases_db_before_llm():
    user_id = uuid4()
    keep = _fact(text="Bini is a developer at Hooh.")
    extra = _fact(text="Bini is a developer at Hooh now.")
    session = AsyncMock()
    session.commit = AsyncMock()
    db_open_during_merge: list[bool] = []

    class _TrackingSessionCM(FakeSessionCM):
        def __init__(self) -> None:
            super().__init__(session)
            self.open = False

        async def __aenter__(self) -> AsyncMock:
            self.open = True
            return await super().__aenter__()

        async def __aexit__(self, *args: object) -> bool:
            self.open = False
            return await super().__aexit__(*args)

    load_cm = _TrackingSessionCM()
    apply_cm = _TrackingSessionCM()

    async def fake_merge(*_args: object, **_kwargs: object) -> None:
        db_open_during_merge.append(load_cm.open or apply_cm.open)
        return None

    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=[load_cm, apply_cm],
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[keep, extra]),
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memory_llm.merge_memory_section",
            AsyncMock(side_effect=fake_merge),
        ),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", AsyncMock()),
    ):
        changed = await consolidate_user_memory_sections(Settings(), user_id=user_id)

    assert changed is True
    assert db_open_during_merge == [False]
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_merge_is_told_which_fact_is_newer(monkeypatch):
    """M9: the newer fact goes first in the draft, and the prompt keeps the first."""
    from app.modules.memory import llm as memory_llm

    older = _fact(text="Bini works at Uber in Nairobi as an engineer.")
    newer = _fact(text="Bini works at Uber in Nairobi as an engineer now.")
    older.last_confirmed_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer.last_confirmed_at = datetime(2026, 6, 1, tzinfo=UTC)
    captured: dict[str, object] = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(memory_llm.litellm_gateway, "complete_structured", fake_complete)
    _, session_locals = _consolidation_sessions()
    with (
        patch(
            "app.modules.memory.consolidation_workflow.SessionLocal",
            side_effect=session_locals,
        ),
        patch(
            "app.modules.memory.consolidation_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[older, newer]),
        ),
        patch("app.modules.memory.consolidation_workflow.apply_memory_facts", AsyncMock()),
    ):
        await consolidate_user_memory_sections(Settings(mock_llm_enabled=False), user_id=uuid4())

    system, user = captured["messages"]
    assert "The first fact in the draft is the newer one" in system["content"]
    assert user["content"].index("engineer now") < user["content"].index("engineer.")
