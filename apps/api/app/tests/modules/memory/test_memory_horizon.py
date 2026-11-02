"""Planted-fact memory horizon evals. Mocked LLM — zero provider calls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import Memory
from app.modules.memory.extraction_workflow import extract_and_store_memories
from app.modules.memory.facts import is_active_memory
from app.modules.memory.schemas import MemoryFactOp, MemoryFactUpdateResult
from app.modules.memory.selection import format_memory_block
from app.modules.memory.text import is_memory_candidate, memory_extract_user_text
from app.tests.fakes import redis_mock


def _row(text: str, *, memory_type: str = "fact", status: str = "active") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        type=memory_type,
        text=text,
        status=status,
        sensitivity="normal",
        importance=0.5,
        confidence=0.9,
        last_confirmed_at=None,
        updated_at=0,
    )


def _apply(store: list[SimpleNamespace], ops: list[MemoryFactOp]) -> None:
    for op in ops:
        if op.op == "add":
            store.append(_row(op.text, memory_type=op.type))
        elif op.op == "delete":
            needle = (op.match_text or op.text).lower()
            store[:] = [
                row
                for row in store
                if not (is_active_memory(row) and needle and needle in row.text.lower())
            ]
        elif op.op == "supersede":
            needle = (op.match_text or "").lower()
            for row in store:
                if is_active_memory(row) and needle and needle in row.text.lower():
                    row.status = "superseded"
            store.append(_row(op.text, memory_type=op.type))
        elif op.op == "update":
            needle = (op.match_text or op.text).lower()
            for row in store:
                if is_active_memory(row) and needle in row.text.lower():
                    row.text = op.text


def _block(store: list[SimpleNamespace]) -> str:
    # The rows stand in for Memory: the same fields, no database.
    active = cast(list[Memory], [row for row in store if is_active_memory(row)])
    return format_memory_block(active, max_chars=1500)


def test_horizon_max_python_oakland_forget_luna():
    store: list[SimpleNamespace] = []
    _apply(
        store,
        [MemoryFactOp(op="add", type="fact", text="User's dog is named Max.", confidence=0.95)],
    )
    assert "Max" in _block(store)

    _apply(
        store,
        [MemoryFactOp(op="add", type="preference", text="User prefers Python.", confidence=0.9)],
    )
    packed = _block(store)
    assert "Max" in packed
    assert "Python" in packed

    store.append(_row("User lives in San Francisco.", memory_type="profile"))
    _apply(
        store,
        [
            MemoryFactOp(
                op="supersede",
                type="profile",
                text="User lives in Oakland.",
                confidence=0.95,
                match_text="User lives in San Francisco.",
            )
        ],
    )
    packed = _block(store)
    assert "Oakland" in packed
    assert "San Francisco" not in packed

    _apply(
        store,
        [
            MemoryFactOp(
                op="delete",
                type="fact",
                text="",
                confidence=1.0,
                match_text="User's dog is named Max.",
            )
        ],
    )
    packed = _block(store)
    assert "Max" not in packed

    _apply(
        store,
        [MemoryFactOp(op="add", type="fact", text="User's dog is named Luna.", confidence=0.95)],
    )
    packed = _block(store)
    assert "Luna" in packed
    assert "Max" not in packed


def test_horizon_does_not_upgrade_undecided_redis():
    store: list[SimpleNamespace] = [
        _row("User is considering Redis.", memory_type="fact"),
    ]
    packed = _block(store)
    assert "considering Redis" in packed
    assert "uses Redis" not in packed


def test_horizon_false_memory_not_in_user_line():
    user_line = memory_extract_user_text("thanks")
    assert "Rex" not in user_line
    assert is_memory_candidate("Assistant: The user's dog is named Rex.\nUser: thanks") is False


@pytest.mark.asyncio
async def test_extract_remember_max_persists_via_ops():
    apply = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    with (
        patch("app.modules.memory.extraction_workflow.SessionLocal", return_value=_CM()),
        patch(
            "app.modules.memory.extraction_workflow.users_repo.get_by_id",
            AsyncMock(return_value=MagicMock(memory_enabled=True, memory_include_sensitive=False)),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memories_repo.list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extraction_workflow.memory_llm.revise_memory_facts",
            AsyncMock(
                return_value=MemoryFactUpdateResult(
                    ops=[
                        MemoryFactOp(
                            op="add",
                            type="fact",
                            text="User's dog is named Max.",
                            confidence=0.95,
                        )
                    ]
                )
            ),
        ),
        patch("app.modules.memory.extraction_workflow.apply_memory_facts", apply),
        patch(
            "app.modules.memory.extraction_workflow.acquire_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.extraction_workflow.release_memory_write_lock", AsyncMock()),
        patch(
            "app.modules.memory.extract_backlog.chat_history.user_lines_since",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.memory.extract_backlog.get_redis_client",
            MagicMock(return_value=redis_mock(get=None)),
        ),
    ):
        await extract_and_store_memories(
            Settings(memory_min_confidence=0.4),
            user_id=uuid4(),
            chat_id=uuid4(),
            transcript="Remember that my dog is named Max.",
        )

    apply.assert_awaited_once()
    writes = apply.await_args.kwargs["writes"]
    assert writes[0].op == "add"
    assert "Max" in writes[0].text
