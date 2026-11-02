"""Load the memory block a prompt carries, and say whether it loaded in full.

A read that fails, or a turn whose query embed is unavailable, is reported on the
``MemoryLoadReport`` the caller passes, so the reply can say "I couldn't load your
saved memory just now" instead of "I don't have that saved".

Selection, the cache and the background spawner are called through their modules, so
a test patches the module that defines a name (``selection.format_memory_block``) and
reaches this code too.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import background_tasks
from app.core.config import Settings
from app.core.redis import get_redis_client
from app.models.orm import Memory, User
from app.modules.memory import cache, selection
from app.modules.memory.profile_name import without_conflicting_names
from app.modules.memory.switch import memory_switch_on
from app.modules.memory.text import (
    is_diet_health_memory_text,
    is_food_or_diet_query,
    is_sensitive_memory_text,
)

logger = logging.getLogger(__name__)

MemoryLoadStatus = Literal["ok", "partial", "unavailable"]
# "query": facts near this question (the default). "profile": those plus the profile
# document, for "what's my job?" and career asks. "self": everything, for "what do
# you know about me". "work": the stack and what the user builds.
MemoryScope = Literal["query", "profile", "self", "work"]
_STATUS_RANK: dict[MemoryLoadStatus, int] = {"ok": 0, "partial": 1, "unavailable": 2}


@dataclass
class MemoryLoadReport:
    """How one turn's memory read went. ``partial``: matched by words only, since
    the query embed was unavailable. ``unavailable``: the read failed."""

    status: MemoryLoadStatus = "ok"

    def degrade(self, status: MemoryLoadStatus) -> None:
        if _STATUS_RANK[status] > _STATUS_RANK[self.status]:
            self.status = status


def _log_inject(user_id: UUID, block: str) -> str:
    logger.info(
        "memory_inject user_id=%s facts=%s packed_chars=%s",
        user_id,
        block.count("\n- "),
        len(block),
    )
    return block


async def semantic_memories_from_vec(
    session: AsyncSession,
    user: User,
    settings: Settings,
    query_vec: list[float],
    *,
    query_text: str | None = None,
    with_profile: bool = False,
) -> list[Memory]:
    from app.modules.memory import repository as memories_repo

    scored = await memories_repo.list_scored_for_user(session, user.id, query_vec)
    # Nothing near the question means nothing to add: never the whole store.
    return selection.select_memories_semantic(
        scored,
        settings,
        query_text=query_text,
        with_profile=with_profile,
        profile_name=user.name,
    )


async def load_relevant_memories(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    query_text: str | None = None,
    query_vec: list[float] | None = None,
    lexical: bool = False,
    with_profile: bool = False,
    report: MemoryLoadReport | None = None,
) -> list[Memory]:
    """Facts for the prompt: by vector, by shared words (``lexical``), or by priority."""
    if not memory_switch_on(user):
        return []
    from app.modules.memory import repository as memories_repo

    try:
        if query_vec is not None:
            return await semantic_memories_from_vec(
                session,
                user,
                settings,
                query_vec,
                query_text=query_text,
                with_profile=with_profile,
            )
        all_memories = await memories_repo.list_for_user(session, user.id)
        if lexical:
            return selection.select_memories_lexical(
                all_memories,
                settings,
                query_text=query_text,
                with_profile=with_profile,
                profile_name=user.name,
            )
        return selection.select_memories_for_prompt(all_memories, settings, profile_name=user.name)
    except Exception:
        logger.warning("Memory retrieval failed for user_id=%s", user.id, exc_info=True)
        if report is not None:
            report.degrade("unavailable")
        return []


def filter_surface_memories(
    memories: list[Memory],
    *,
    exclude_sensitive: bool,
    query_text: str | None = None,
) -> list[Memory]:
    if not exclude_sensitive:
        return memories
    keep_diet = bool(query_text) and is_food_or_diet_query(query_text or "")
    kept: list[Memory] = []
    for memory in memories:
        tagged = (memory.sensitivity or "normal") != "normal"
        sensitive = tagged or is_sensitive_memory_text(memory.text)
        if not sensitive:
            kept.append(memory)
            continue
        if keep_diet and is_diet_health_memory_text(memory.text):
            kept.append(memory)
    return kept


async def semantic_block_from_vec(
    session: AsyncSession,
    user: User,
    settings: Settings,
    query_vec: list[float],
    *,
    exclude_sensitive: bool,
    query_text: str | None = None,
    with_profile: bool = False,
    report: MemoryLoadReport | None = None,
) -> str:
    memories = await load_relevant_memories(
        session,
        user,
        settings,
        query_vec=query_vec,
        query_text=query_text,
        with_profile=with_profile,
        report=report,
    )
    memories = filter_surface_memories(
        memories, exclude_sensitive=exclude_sensitive, query_text=query_text
    )
    return selection.format_memory_block(memories, max_chars=settings.memory_inject_max_chars)


async def warm_semantic_memory_cache(
    settings: Settings,
    user_id: UUID,
    query_text: str,
    *,
    exclude_sensitive: bool = False,
    with_profile: bool = False,
) -> None:
    """After an embed miss, store the semantic block for the scope the turn read."""
    from app.core.db import SessionLocal
    from app.gateways import embedding_gateway
    from app.repositories import users as users_repo

    cleaned = query_text.strip()
    if not cleaned:
        return
    try:
        query_vec = await embedding_gateway.get_or_embed_query(settings, user_id, cleaned)
        if not query_vec:
            return
        redis = get_redis_client()
        gen_before = await redis.get(cache.memory_generation_key(user_id))
        async with SessionLocal() as session:
            user = await users_repo.get_by_id(session, user_id)
            if user is None or not memory_switch_on(user):
                return
            report = MemoryLoadReport()
            block = await semantic_block_from_vec(
                session,
                user,
                settings,
                query_vec,
                exclude_sensitive=exclude_sensitive,
                query_text=cleaned,
                with_profile=with_profile,
                report=report,
            )
            gen_after = await redis.get(cache.memory_generation_key(user_id))
            if gen_before != gen_after or report.status != "ok":
                return
            query_key = cache.memory_query_scoped_key(
                user_id,
                gen_before,
                cleaned,
                exclude_sensitive=exclude_sensitive,
                with_profile=with_profile,
            )
            await cache.write_query_block_cache(query_key, block, settings)
    except Exception:
        logger.debug("Background semantic memory warm failed", exc_info=True)


async def get_memory_block(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    query_text: str | None = None,
    exclude_sensitive: bool = False,
    scope: MemoryScope = "query",
    report: MemoryLoadReport | None = None,
) -> str:
    """The memory block for one prompt; ``report`` says if it loaded in full.

    A saved fact that names the user differently from their profile is left out
    (``profile_name``): the prompt calls them by one name.
    """
    if not memory_switch_on(user):
        return ""
    block = await _scoped_block(
        session,
        user,
        settings,
        query_text=query_text,
        exclude_sensitive=exclude_sensitive,
        scope=scope,
        report=report if report is not None else MemoryLoadReport(),
    )
    return without_conflicting_names(block, user.name)


async def _scoped_block(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    query_text: str | None,
    exclude_sensitive: bool,
    scope: MemoryScope,
    report: MemoryLoadReport,
) -> str:
    if scope == "work":
        return await _cached_block(
            session,
            user,
            settings,
            suffix="w",
            exclude_sensitive=exclude_sensitive,
            report=report,
            select=lambda rows: selection.select_work_memories(
                rows, settings, profile_name=user.name
            ),
        )
    if scope == "self" or not (query_text and settings.semantic_memory_enabled):
        return await _cached_block(
            session,
            user,
            settings,
            suffix="",
            exclude_sensitive=exclude_sensitive,
            report=report,
            select=None,
        )
    return await _query_block(
        session,
        user,
        settings,
        query_text=query_text.strip(),
        exclude_sensitive=exclude_sensitive,
        with_profile=scope == "profile",
        report=report,
    )


async def _query_block(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    query_text: str,
    exclude_sensitive: bool,
    with_profile: bool,
    report: MemoryLoadReport,
) -> str:
    redis = get_redis_client()
    try:
        generation = await redis.get(cache.memory_generation_key(user.id))
    except Exception:
        logger.debug("Memory generation read failed", exc_info=True)
        generation = None
    query_key = cache.memory_query_scoped_key(
        user.id,
        generation,
        query_text,
        exclude_sensitive=exclude_sensitive,
        with_profile=with_profile,
    )
    try:
        cached = await redis.get(query_key)
        if cached is not None:
            return cast(str, cached)
    except Exception:
        logger.debug("Memory query cache read failed", exc_info=True)

    from app.gateways import embedding_gateway

    query_vec = await embedding_gateway.get_or_embed_query(
        settings,
        user.id,
        query_text,
        embed_timeout=settings.memory_query_embed_timeout_seconds,
    )
    if query_vec is not None:
        block = await semantic_block_from_vec(
            session,
            user,
            settings,
            query_vec,
            exclude_sensitive=exclude_sensitive,
            query_text=query_text,
            with_profile=with_profile,
            report=report,
        )
        # A failed read is never cached: the next turn tries again.
        if report.status == "ok":
            await cache.write_query_block_cache(query_key, block, settings)
        return _log_inject(user.id, block)

    logger.warning(
        "Memory query embed unavailable; matching facts by words user_id=%s",
        user.id,
    )
    report.degrade("partial")
    memories = await load_relevant_memories(
        session,
        user,
        settings,
        query_text=query_text,
        lexical=True,
        with_profile=with_profile,
        report=report,
    )
    memories = filter_surface_memories(
        memories, exclude_sensitive=exclude_sensitive, query_text=query_text
    )
    # Not cached: the warm below stores the real block for this same key.
    block = selection.format_memory_block(memories, max_chars=settings.memory_inject_max_chars)
    warm_task = background_tasks.create_background_task(
        warm_semantic_memory_cache(
            settings,
            user.id,
            query_text,
            exclude_sensitive=exclude_sensitive,
            with_profile=with_profile,
        ),
        name="warm_semantic_memory_cache",
    )
    warm_task.add_done_callback(
        lambda task: (
            logger.debug("Semantic memory warm failed", exc_info=task.exception())
            if not task.cancelled() and task.exception()
            else None
        )
    )
    return _log_inject(user.id, block)


async def _cached_block(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    suffix: str,
    exclude_sensitive: bool,
    report: MemoryLoadReport,
    select: Callable[[list[Memory]], list[Memory]] | None,
) -> str:
    """A block that does not depend on the question: everything, or the work scope."""
    redis = get_redis_client()
    key = cache.memory_block_key(user.id)
    cache_key = f"{key}:{suffix}" if suffix else key
    if exclude_sensitive:
        cache_key = f"{cache_key}{'x' if suffix else ':x'}"
    try:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cast(str, cached)
    except Exception:
        logger.debug("Memory block cache read failed", exc_info=True)

    if select is None:
        memories = await load_relevant_memories(session, user, settings, report=report)
    else:
        from app.modules.memory import repository as memories_repo

        try:
            memories = select(await memories_repo.list_for_user(session, user.id))
        except Exception:
            logger.warning("Memory retrieval failed for user_id=%s", user.id, exc_info=True)
            report.degrade("unavailable")
            memories = []
    memories = filter_surface_memories(memories, exclude_sensitive=exclude_sensitive)
    block = selection.format_memory_block(memories, max_chars=settings.memory_inject_max_chars)
    if report.status == "ok":
        try:
            await redis.set(cache_key, block, ex=settings.memory_cache_ttl)
        except Exception:
            logger.debug("Memory block cache write failed", exc_info=True)
    return _log_inject(user.id, block)
