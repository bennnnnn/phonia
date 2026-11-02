"""Memory, recent-window, and history-gap reads for one chat prompt."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.orm import Chat, User
from app.modules import memory as memory_service
from app.modules import todos as todos_service
from app.modules.attachments import rag as attachment_rag_service
from app.modules.chat.context_window import (
    UNSUMMARIZED_GAP_MAX_MESSAGES,
    messages_within_token_budget,
    unsummarized_gap_bounds,
)
from app.modules.conversation import history as conversation_history
from app.modules.conversation import history_rag as chat_history_rag_service
from app.modules.turn_reading.routing import is_broad_self_question

if TYPE_CHECKING:
    from app.modules.memory import MemoryScope

_SLIM_MEMORY_MAX_CHARS = 1000
_BROAD_SELF_HISTORY_QUERY = (
    "Personal details the user stated about their background, work, employer, interests, "
    "preferences, communication style, goals, and active projects"
)


def _cap_slim_memory_block(block: str) -> str:
    if len(block) <= _SLIM_MEMORY_MAX_CHARS:
        return block

    lines = block.splitlines()
    if not lines:
        return ""

    # Memory blocks are rendered as a title followed by section headings and
    # bullet facts. Keep complete facts and skip any one fact that does not fit;
    # slicing the string can turn a remembered detail into a different claim.
    packed = [lines[0]]
    current_heading: str | None = None
    emitted_heading: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            current_heading = stripped
            continue
        if not stripped.startswith("- "):
            continue

        addition: list[str] = []
        if current_heading and current_heading != emitted_heading:
            addition.extend(["", current_heading])
        addition.append(stripped)
        trial = "\n".join([*packed, *addition])
        if len(trial) > _SLIM_MEMORY_MAX_CHARS:
            continue
        packed.extend(addition)
        emitted_heading = current_heading

    return "\n".join(packed) if len(packed) > 1 else ""


@dataclass
class _PromptContextBlocks:
    memory_block: str
    todos_section: str | None
    recent_all: list[Any]
    attachment_rag_block: str
    chat: Chat | None
    history_rag_query_vec: list[float] | None = None
    # "ok", or "partial" / "unavailable" when memory did not fully load.
    memory_status: str = "ok"
    # The memory sections the prompt drew on, for the turn's ``done``.
    recalled: int = 0
    memory_hints: list[str] = field(default_factory=list)


@dataclass
class _ContextReads:
    """The reads one prompt may gather; each opens its own short-lived session.

    A single AsyncSession cannot run concurrent operations, and an embed (RAG,
    memory) can take seconds: a shared session would pin the caller's connection
    across the whole gather.
    """

    user: User
    chat_id: UUID
    settings: Settings
    query_text: str | None
    recent_limit: int
    recent_messages: list[Any] | None
    client_timezone: str | None
    memory_scope: MemoryScope
    history_rag: bool
    # The turn is a yes to an offered reminder (``turn_prep.mode``).
    accepted_offer: bool = False

    @cached_property
    def db_slots(self) -> asyncio.Semaphore:
        """Caps this turn's concurrent DB checkouts so one turn cannot saturate the pool."""
        return asyncio.Semaphore(max(1, self.settings.context_db_concurrency))

    @cached_property
    def memory_report(self) -> memory_service.MemoryLoadReport:
        """Whether memory fully loaded, filled in by ``memory_block``."""
        return memory_service.MemoryLoadReport()

    async def history_rag_embed(self) -> list[float] | None:
        """The chat-history query embed; it overlaps the gather, and the recent
        window's ids are excluded later, when hits are filtered."""
        query_text = self.query_text
        if not self.history_rag or not query_text or not query_text.strip():
            return None
        history_query = (
            _BROAD_SELF_HISTORY_QUERY if is_broad_self_question(query_text) else query_text
        )
        return await chat_history_rag_service.embed_query_for_prompt(
            self.settings, user_id=self.user.id, query=history_query
        )

    async def recent(self, *, pooled: bool) -> list[Any]:
        """The recent window, unless the caller already read it. ``pooled`` takes a
        DB slot (the full gather); a slim turn reads it alone."""
        if self.recent_messages is not None:
            return self.recent_messages
        if not pooled:
            async with SessionLocal() as s:
                return await conversation_history.recent_messages(
                    s, self.chat_id, limit=self.recent_limit
                )
        async with self.db_slots, SessionLocal() as s:
            return await conversation_history.recent_messages(
                s, self.chat_id, limit=self.recent_limit
            )

    async def memory_block(self) -> str:
        async with self.db_slots, SessionLocal() as s:
            return await memory_service.get_memory_block(
                s,
                self.user,
                self.settings,
                query_text=self.query_text,
                exclude_sensitive=memory_service.exclude_sensitive_for_query(self.query_text),
                scope=self.memory_scope,
                report=self.memory_report,
            )

    async def todos_section(self) -> str | None:
        async with self.db_slots, SessionLocal() as s:
            return await todos_service.build_todos_system_section(
                s,
                self.user,
                self.settings,
                client_timezone=self.client_timezone,
                query_text=self.query_text,
                accepted_offer=self.accepted_offer,
            )

    async def attachment_rag_block(self) -> str:
        # HTTP/embed-bound — do not hold a DB pool slot.
        if not self.settings.attachment_rag_enabled or not self.query_text:
            return ""
        return await attachment_rag_service.retrieve_for_prompt(
            self.settings,
            user_id=self.user.id,
            chat_id=self.chat_id,
            query=self.query_text,
        )


def _memory_hints(memory_block: str) -> list[str]:
    """The memory sections in the block, by their ``## Label`` headers."""
    labels = set(memory_service.SECTION_LABELS.values())
    return [
        line[3:].strip()
        for line in memory_block.split("\n")
        if line.startswith("## ") and line[3:].strip() in labels
    ]


async def _slim_blocks(reads: _ContextReads, chat: Chat | None) -> _PromptContextBlocks:
    """A slim turn without memory: the recent window, and the history embed if asked."""
    if reads.history_rag:
        recent_all, history_rag_query_vec = await gather_or_cancel(
            reads.recent(pooled=False),
            reads.history_rag_embed(),
        )
    else:
        recent_all = await reads.recent(pooled=False)
        history_rag_query_vec = None
    return _PromptContextBlocks(
        memory_block="",
        todos_section=None,
        recent_all=recent_all,
        attachment_rag_block="",
        chat=chat,
        history_rag_query_vec=history_rag_query_vec,
    )


async def _slim_memory_blocks(reads: _ContextReads, chat: Chat | None) -> _PromptContextBlocks:
    """A slim turn that recalls: memory too, capped to whole facts."""
    recent_all, memory_block, history_rag_query_vec = await gather_or_cancel(
        reads.recent(pooled=False),
        reads.memory_block(),
        reads.history_rag_embed(),
    )
    return _PromptContextBlocks(
        memory_block=_cap_slim_memory_block(memory_block),
        todos_section=None,
        recent_all=recent_all,
        attachment_rag_block="",
        chat=chat,
        history_rag_query_vec=history_rag_query_vec,
        memory_status=reads.memory_report.status,
    )


async def _full_blocks(reads: _ContextReads, chat: Chat | None) -> _PromptContextBlocks:
    """A rich turn: memory, the schedule, the recent window, file excerpts and the
    history embed, each an independent read, gathered instead of awaited in turn."""
    (
        memory_block,
        todos_section,
        recent_all,
        attachment_rag_block,
        history_rag_query_vec,
    ) = await gather_or_cancel(
        reads.memory_block(),
        reads.todos_section(),
        reads.recent(pooled=True),
        reads.attachment_rag_block(),
        reads.history_rag_embed(),
    )
    hints = _memory_hints(memory_block)
    return _PromptContextBlocks(
        memory_block=memory_block,
        todos_section=todos_section,
        recent_all=recent_all,
        attachment_rag_block=attachment_rag_block,
        chat=chat,
        history_rag_query_vec=history_rag_query_vec,
        memory_status=reads.memory_report.status,
        recalled=len(hints),
        memory_hints=hints[:3],
    )


async def _load_context_blocks(
    user: User,
    chat_id: UUID,
    settings: Settings,
    *,
    chat: Chat | None,
    query_text: str | None,
    recent_limit: int,
    slim_context: bool,
    client_timezone: str | None,
    load_memory: bool = False,
    memory_scope: MemoryScope = "query",
    history_rag: bool = False,
    recent_messages: list[Any] | None = None,
    accepted_offer: bool = False,
) -> _PromptContextBlocks:
    """Load memory/todos/RAG + recent messages for the system prompt.

    A slim turn reads the recent window (and memory, when it recalls); a rich
    turn gathers every block (``_ContextReads``).
    """
    reads = _ContextReads(
        user=user,
        chat_id=chat_id,
        settings=settings,
        query_text=query_text,
        recent_limit=recent_limit,
        recent_messages=recent_messages,
        client_timezone=client_timezone,
        memory_scope=memory_scope,
        history_rag=history_rag,
        accepted_offer=accepted_offer,
    )
    if slim_context and not load_memory:
        return await _slim_blocks(reads, chat)
    if slim_context:
        return await _slim_memory_blocks(reads, chat)
    if chat is None:
        async with SessionLocal() as s:
            chat = await conversation_history.get_chat(s, chat_id, user.id)
    return await _full_blocks(reads, chat)


def _persisted_messages(window: list[Any], current_user_message_id: UUID | None) -> list[Any]:
    """Drop the synthetic current turn. It is not a stored row yet."""
    if current_user_message_id is None:
        return window
    return [
        message for message in window if getattr(message, "id", None) != current_user_message_id
    ]


async def _load_unsummarized_gap(
    chat_id: UUID,
    chat: Chat | None,
    window: list[Any],
    tail: list[Any],
    *,
    recent_limit: int,
    token_budget: int,
    current_user_message_id: UUID | None,
    prior_count: int | None = None,
) -> list[Any]:
    """Messages after the summary and before the messages the prompt kept.

    ``tail`` is that kept list. A synthetic current user row can push one
    stored message out of a full window; that row is included here, then the
    whole gap is cut to the tokens the recent window did not already use.
    ``prior_count`` is the chat's count read with the window; without it the chat is
    counted here (a count that could race the current line's insert).
    """
    tail_ids = {message.id for message in tail}
    persisted = _persisted_messages(window, current_user_message_id)
    summarized = (chat.summary_message_count or 0) if chat is not None else 0
    # A loaded row the budget left out may already be in the summary: long replies
    # kept the tail short when the summary was written, and it folded them in.
    first = prior_count - len(persisted) if prior_count is not None else None
    dropped = [
        message
        for index, message in enumerate(persisted)
        if message.id not in tail_ids and (first is None or first + index >= summarized)
    ]
    older: list[Any] = []
    if chat is not None and len(persisted) >= recent_limit and persisted:
        oldest = persisted[0]
        created_at = getattr(oldest, "created_at", None)
        oldest_id = getattr(oldest, "id", None)
        if created_at is not None and oldest_id is not None:
            async with SessionLocal() as session:
                total = prior_count
                if total is None:
                    total = await conversation_history.message_count(session, chat_id)
                bounds = unsummarized_gap_bounds(
                    total=total,
                    summarized=summarized,
                    loaded=len(persisted),
                )
                if bounds is not None:
                    _offset, count = bounds
                    older = await conversation_history.messages_before(
                        session, chat_id, oldest, limit=count
                    )
    return messages_within_token_budget(
        [*older, *dropped],
        token_budget,
        max_messages=UNSUMMARIZED_GAP_MAX_MESSAGES,
    )
