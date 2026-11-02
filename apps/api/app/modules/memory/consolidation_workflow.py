"""Consolidate near-duplicate atomic memory facts."""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.orm import Memory
from app.modules.memory import llm as memory_llm
from app.modules.memory import repository as memories_repo
from app.modules.memory.apply import apply_memory_facts
from app.modules.memory.consolidation import (
    accept_memory_section_rewrite,
    fact_text_jaccard,
    facts_need_consolidation,
)
from app.modules.memory.fact_quality import FactView, texts_to_drop
from app.modules.memory.facts import is_active_memory
from app.modules.memory.locks import acquire_memory_write_lock, release_memory_write_lock
from app.modules.memory.ops import normalize_memory_text
from app.modules.memory.switch import memory_switch_on
from app.modules.memory.writes_repository import MemoryFactWrite
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Pair:
    keep_text: str
    drop_text: str
    memory_type: str


_NEAR_DUP_JACCARD = 0.8


def _duplicate_pairs(facts: list[Memory]) -> list[_Pair]:
    active = [fact for fact in facts if is_active_memory(fact) and normalize_memory_text(fact.text)]
    by_key: dict[tuple[str, str], list[Memory]] = {}
    for fact in active:
        key = (fact.type, normalize_memory_text(fact.text).lower())
        by_key.setdefault(key, []).append(fact)
    pairs: list[_Pair] = []
    used: set[UUID] = set()
    for (_type, _text), group in by_key.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda fact: fact.last_confirmed_at or fact.updated_at, reverse=True)
        keeper = group[0]
        used.add(keeper.id)
        for extra in group[1:]:
            used.add(extra.id)
            pairs.append(
                _Pair(
                    keep_text=keeper.text,
                    drop_text=extra.text,
                    memory_type=keeper.type,
                )
            )
    remaining = [fact for fact in active if fact.id not in used]
    remaining.sort(key=lambda fact: fact.last_confirmed_at or fact.updated_at, reverse=True)
    claimed: set[UUID] = set()
    for index, left in enumerate(remaining):
        if left.id in claimed:
            continue
        for right in remaining[index + 1 :]:
            if right.id in claimed or right.type != left.type:
                continue
            if fact_text_jaccard(left.text, right.text) < _NEAR_DUP_JACCARD:
                continue
            claimed.add(right.id)
            pairs.append(
                _Pair(
                    keep_text=left.text,
                    drop_text=right.text,
                    memory_type=left.type,
                )
            )
    return pairs


async def _load_pairs(
    session: AsyncSession, user_id: UUID
) -> tuple[dict[UUID, str], list[_Pair], list[str]] | None:
    user = await users_repo.get_by_id(session, user_id)
    if user is None or not memory_switch_on(user):
        return None
    existing = await memories_repo.list_for_user(
        session, user_id, include_muted=False, include_superseded=False
    )
    if not existing or not facts_need_consolidation(existing):
        return None
    drops = texts_to_drop(
        [
            FactView(text=fact.text, confirmed_at=fact.last_confirmed_at)
            for fact in existing
            if is_active_memory(fact)
        ]
    )
    return {fact.id: fact.text for fact in existing}, _duplicate_pairs(existing), drops


async def consolidate_user_memory_sections(
    settings: Settings,
    *,
    user_id: UUID,
) -> bool | str:
    """Return ``skipped_lock`` when a caller should retry after backoff."""
    try:
        lock_token = await acquire_memory_write_lock(user_id)
        if not lock_token:
            logger.info(
                "Memory consolidation skipped: write lock held for user_id=%s",
                user_id,
            )
            return "skipped_lock"
        try:
            async with SessionLocal() as session:
                loaded = await _load_pairs(session, user_id)
            if loaded is None:
                return False
            expected, pairs, drops = loaded
            summaries = [await _merged_summary(settings, pair) for pair in pairs]
            writes = _consolidation_writes(pairs, summaries, drops)
            if not writes:
                return False
            await apply_memory_facts(
                settings,
                user_id=user_id,
                writes=writes,
                session_factory=SessionLocal,
                memories=memories_repo,
                expected_facts=expected,
            )
            return True
        finally:
            await release_memory_write_lock(user_id, lock_token)
    except Exception:
        logger.exception("Memory consolidation failed for user_id=%s", user_id)
        raise


async def _merged_summary(settings: Settings, pair: _Pair) -> str:
    """The kept fact's text once the dropped one is merged in; the kept text if none is fit."""
    if (
        normalize_memory_text(pair.keep_text).lower()
        == normalize_memory_text(pair.drop_text).lower()
    ):
        return pair.keep_text
    # Newer first: the merge prompt keeps the first fact on a conflict.
    merged = await memory_llm.merge_memory_section(
        settings,
        section_type=pair.memory_type,
        prior_text=f"{pair.keep_text} {pair.drop_text}",
    )
    if merged is None:
        return pair.keep_text
    accepted = accept_memory_section_rewrite(
        section_type=pair.memory_type,
        prior=pair.keep_text,
        summary=merged.summary,
        confidence=merged.confidence,
        min_confidence=settings.memory_min_confidence,
        enforce_length_floor=False,
    )
    return accepted or pair.keep_text


def _consolidation_writes(
    pairs: list[_Pair], summaries: list[str], drops: list[str]
) -> list[MemoryFactWrite]:
    """Rewrite each kept fact to its summary, then delete the duplicates and stale facts."""
    writes: list[MemoryFactWrite] = []
    dropped: set[str] = set()
    for pair, summary in zip(pairs, summaries, strict=True):
        if normalize_memory_text(summary) != normalize_memory_text(pair.keep_text):
            writes.append(
                MemoryFactWrite(
                    op="update",
                    type=pair.memory_type,
                    text=summary,
                    confidence=0.9,
                    match_text=pair.keep_text,
                )
            )
        writes.append(_delete(pair.drop_text, pair.memory_type))
        dropped.add(pair.drop_text)
    for text in drops:
        if text not in dropped:
            dropped.add(text)
            writes.append(_delete(text, "fact"))
    return writes


def _delete(text: str, memory_type: str) -> MemoryFactWrite:
    return MemoryFactWrite(op="delete", type=memory_type, text="", confidence=1.0, match_text=text)
