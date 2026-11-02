"""The memory surface: the prompt's memory block, selection order, delete."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings

# ── memory service ─────────────────────────────────────────────────────────────
from app.modules.memory.selection import format_memory_block, select_memories_for_prompt


def _mem(type_: str, text: str, confidence: float | None = 0.9):
    m = MagicMock()
    m.type = type_
    m.text = text
    m.confidence = confidence
    m.status = "active"
    m.sensitivity = "normal"
    m.importance = 0.5
    m.last_confirmed_at = None
    m.updated_at = 0
    return m


def test_format_memory_block_empty():
    assert format_memory_block([]) == ""


def test_format_memory_block_nonempty():
    out = format_memory_block([_mem("preference", "Likes coffee")])
    assert "Preferences" in out
    assert "Likes coffee" in out


def test_select_memories_priority_order():
    settings = Settings(memory_min_confidence=0.0, memory_inject_limit=10)
    mems = [
        _mem("fact", "works at ACME"),
        _mem("profile", "Name is Sam"),
        _mem("preference", "Night owl"),
    ]
    result = select_memories_for_prompt(mems, settings)
    assert [m.type for m in result] == ["profile", "preference", "fact"]


@pytest.mark.asyncio
async def test_load_relevant_memories_disabled():
    from app.modules.memory.retrieval import load_relevant_memories

    user = MagicMock(memory_enabled=False)
    result = await load_relevant_memories(AsyncMock(), user, Settings())
    assert result == []


@pytest.mark.asyncio
async def test_delete_memory_delegates():
    from app.modules.memory import crud, locks
    from app.modules.memory import repository as memories_repo

    delete_by_id = AsyncMock(return_value=True)
    with (
        patch.object(memories_repo, "delete_by_id", delete_by_id),
        patch.object(locks, "take_memory_write_lock", AsyncMock(return_value=True)),
        patch.object(locks, "release_memory_write_lock", AsyncMock()),
    ):
        result = await crud.delete_memory(AsyncMock(), uuid4(), uuid4())
    assert result is True
    delete_by_id.assert_awaited_once()
