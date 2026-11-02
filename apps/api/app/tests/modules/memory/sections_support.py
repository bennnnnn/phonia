"""Test helpers: write memory facts from (type, text, confidence, source_chat_id) rows.

Production writes ``MemoryFactWrite`` ops through ``repository.apply_writes`` and
``apply.apply_memory_facts``; these adapters turn the older row tuples into those ops.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.modules.memory import apply as memory_apply
from app.modules.memory import repository as memories_repo
from app.modules.memory.apply import MemorySessionFactory
from app.modules.memory.writes_repository import MemoryFactWrite


async def upsert_sections(
    session: AsyncSession,
    *,
    user_id: UUID,
    items: list[tuple[str, str, float, UUID | None]],
    commit: bool = True,
    expected_sections: dict[str, tuple[UUID, str]] | None = None,
) -> None:
    """One repository write per (type, text) tuple."""
    if not items:
        return
    writes: list[MemoryFactWrite] = []
    expected_facts: dict[UUID, str] = {}
    for memory_type, text, confidence, source_chat_id in items:
        if not text.strip():
            continue
        prior = None if expected_sections is None else expected_sections.get(memory_type)
        writes.append(
            MemoryFactWrite(
                op="update" if prior is not None else "add",
                type=memory_type,
                text=text,
                confidence=confidence,
                match_text=prior[1] if prior is not None else text,
                source_chat_id=source_chat_id,
            )
        )
        if prior is not None:
            expected_facts[prior[0]] = prior[1]
    if not writes:
        return
    await memories_repo.apply_writes(
        session,
        user_id=user_id,
        writes=writes,
        expected_facts=None if expected_sections is None else expected_facts,
        active_cap=150,
        commit=commit,
    )


async def apply_memory_section_rows(
    settings: Settings,
    *,
    user_id: UUID,
    rows: list[tuple[str, str, float, UUID | None]],
    session_factory: MemorySessionFactory = SessionLocal,
    memories: Any = memories_repo,
    expected_sections: dict[str, tuple[UUID, str]] | None = None,
) -> None:
    """One add/update per type-keyed section tuple, through ``apply_memory_facts``."""
    writes: list[MemoryFactWrite] = []
    expected_facts: dict[UUID, str] | None = None
    if expected_sections is not None:
        expected_facts = {memory_id: text for memory_id, text in expected_sections.values()}
    for memory_type, text, confidence, source_chat_id in rows:
        if not text.strip():
            continue
        prior = None if expected_sections is None else expected_sections.get(memory_type)
        writes.append(
            MemoryFactWrite(
                op="update" if prior is not None else "add",
                type=memory_type,
                text=text,
                confidence=confidence,
                match_text=prior[1] if prior is not None else None,
                source_chat_id=source_chat_id,
            )
        )
    await memory_apply.apply_memory_facts(
        settings,
        user_id=user_id,
        writes=writes,
        session_factory=session_factory,
        memories=memories,
        expected_facts=expected_facts,
    )
