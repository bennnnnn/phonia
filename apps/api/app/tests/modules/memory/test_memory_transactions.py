from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory.apply import apply_memory_facts
from app.modules.memory.writes_repository import MemoryFactWrite
from app.tests.modules.memory.sections_support import apply_memory_section_rows


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_apply_memory_rows_commits_once_after_repository_writes():
    session = AsyncMock()
    memories = AsyncMock()
    memories.list_for_user.return_value = []

    def session_factory() -> _SessionContext:
        return _SessionContext(session)

    user_id = uuid4()

    with (
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
    ):
        await apply_memory_section_rows(
            Settings(),
            user_id=user_id,
            rows=[("fact", "Owns a bicycle.", 0.9, None)],
            session_factory=session_factory,
            memories=memories,
        )

    memories.apply_writes.assert_awaited_once()
    assert memories.apply_writes.await_args.kwargs["commit"] is False
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_memory_rows_rolls_back_when_post_write_read_fails():
    session = AsyncMock()
    memories = AsyncMock()
    memories.list_embed_state.side_effect = RuntimeError("reload failed")

    def session_factory() -> _SessionContext:
        return _SessionContext(session)

    invalidate_memory = AsyncMock()

    with (
        patch("app.modules.memory.cache.invalidate_memory_block", invalidate_memory),
    ):
        with pytest.raises(RuntimeError, match="reload failed"):
            await apply_memory_section_rows(
                Settings(),
                user_id=uuid4(),
                rows=[("fact", "Owns a bicycle.", 0.9, None)],
                session_factory=session_factory,
                memories=memories,
            )

    assert memories.apply_writes.await_args.kwargs["commit"] is False
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    invalidate_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_memory_facts_bounds_embed_concurrency_and_backfill():
    import asyncio

    session = AsyncMock()
    # (id, text, has_vector, embedding_text_hash) of twelve facts with no vector yet.
    stale = [(uuid4(), f"Fact {index}", False, None) for index in range(12)]
    memories = AsyncMock()
    memories.apply_writes = AsyncMock(return_value=[stale[0][0]])
    memories.list_embed_state = AsyncMock(return_value=stale)
    memories.update_embedding_if_current = AsyncMock()

    current = 0
    peak = 0

    async def embed(_settings: Settings, _text: str) -> list[float]:
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.02)
        current -= 1
        return [0.1, 0.2]

    def session_factory() -> _SessionContext:
        return _SessionContext(session)

    with (
        patch("app.gateways.embedding_gateway.embed_text", embed),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
    ):
        await apply_memory_facts(
            Settings(embedding_concurrency=3, memory_embed_backfill_per_pass=4),
            user_id=uuid4(),
            writes=[MemoryFactWrite(op="add", type="fact", text="Fact 0", confidence=0.9)],
            session_factory=session_factory,
            memories=memories,
        )

    assert peak <= 3
    assert memories.update_embedding_if_current.await_count == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("op", "manual_edit", "stamped"),
    [
        ("delete", True, True),
        ("update", True, True),
        ("add", True, False),
        ("delete", False, False),
    ],
)
async def test_apply_memory_facts_stamps_a_hand_edit_in_the_same_commit(op, manual_edit, stamped):
    session = AsyncMock()
    memories = AsyncMock()
    memories.apply_writes = AsyncMock(return_value=[])
    memories.list_for_user = AsyncMock(return_value=[])
    user_id = uuid4()

    def session_factory() -> _SessionContext:
        return _SessionContext(session)

    with (
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()),
    ):
        await apply_memory_facts(
            Settings(),
            user_id=user_id,
            writes=[
                MemoryFactWrite(
                    op=op, type="fact", text="User likes chess", confidence=0.9, match_text="chess"
                )
            ],
            session_factory=session_factory,
            memories=memories,
            manual_edit=manual_edit,
        )

    if stamped:
        memories.note_manual_edit.assert_awaited_once_with(session, user_id)
    else:
        memories.note_manual_edit.assert_not_awaited()
    session.commit.assert_awaited_once()
