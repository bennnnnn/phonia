"""Memory as documents for the Memory screen: You, Topics and Areas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Memory, MemoryArea
from app.modules.memory import repository as memories_repo
from app.modules.memory.topics import (
    AREA_PREFIX,
    STANDARD_BY_KEY,
    TopicGroup,
    fact_topic,
    is_area,
)

_GROUP_ORDER: dict[TopicGroup, int] = {"you": 0, "topics": 1, "areas": 2}
_EARLIEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class MemoryDocument:
    key: str
    group: TopicGroup
    # English for standard topics (the app shows its own translation by key);
    # the model's words for an area.
    title: str
    summary: str
    updated_at: datetime | None
    facts: list[Memory]


def area_title_from_key(key: str) -> str:
    slug = key[len(AREA_PREFIX) :]
    return " ".join(part.capitalize() for part in slug.split("-") if part) or slug


def _fact_time(fact: Memory) -> datetime | None:
    return fact.updated_at or fact.created_at


def build_documents(facts: list[Memory], areas: list[MemoryArea]) -> list[MemoryDocument]:
    """One document per topic that has facts, in reading order within each group."""
    by_topic: dict[str, list[Memory]] = {}
    for fact in facts:
        by_topic.setdefault(fact_topic(fact), []).append(fact)
    area_rows = {area.key: area for area in areas}

    documents: list[MemoryDocument] = []
    for key, members in by_topic.items():
        # Oldest first, so a document reads in the order it was learned.
        members.sort(key=lambda fact: fact.created_at or _EARLIEST)
        times = [time for time in (_fact_time(fact) for fact in members) if time is not None]
        updated_at = max(times) if times else None
        group: TopicGroup
        if is_area(key):
            row = area_rows.get(key)
            title = row.title if row else area_title_from_key(key)
            summary = row.summary if row else ""
            group = "areas"
        else:
            spec = STANDARD_BY_KEY.get(key) or STANDARD_BY_KEY["notes"]
            title, summary, group = spec.title, spec.summary, spec.group
        documents.append(
            MemoryDocument(
                key=key,
                group=group,
                title=title,
                summary=summary,
                updated_at=updated_at,
                facts=members,
            )
        )
    documents.sort(key=lambda doc: (_GROUP_ORDER[doc.group], doc.title.casefold()))
    return documents


async def list_documents(session: AsyncSession, user_id: UUID) -> list[MemoryDocument]:
    facts = await memories_repo.list_for_user(session, user_id)
    areas = await memories_repo.list_areas(session, user_id)
    return build_documents(facts, areas)
