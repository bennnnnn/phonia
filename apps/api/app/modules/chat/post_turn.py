"""What a saved turn sets off: the durable post-turn jobs (``core/jobs``).

Title, memory, lesson progress, compression and indexing are best-effort background
work: enqueued after the reply commits, never on the stream's path. A typed turn
commits in ``turn_settle``; a picture, a photo lookup or a voice turn commits through
``turn_record`` and sets off the same jobs (code-health audit ARCH-08).
``POST_TURN_JOBS`` is the list, in order: each entry reads the ``FinishedTurn`` and
returns the jobs it wants (none or one). A turn's documents are not here: they are
queued for indexing as soon as the user's message commits (``turn_prep/persist.py``).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core import jobs
from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.models.orm import Message, User
from app.modules.chat.context_window import compute_history_split, should_run_compression
from app.modules.chat.titles import title_job_key
from app.modules.chat.turn_prep import StreamContext
from app.modules.memory import (
    memory_extract_user_text,
    memory_extraction_due,
)
from app.modules.memory.switch import memory_switch_on
from app.modules.turn_reading.lesson_flow import lesson_step
from app.services import quota as quota_service
from app.services.text_normalize import cap_text_head_tail

logger = logging.getLogger(__name__)

# Memory extraction only needs recent head+tail; keep the job payload bounded.
_MEMORY_TRANSCRIPT_MAX_CHARS = 4000


@dataclass(frozen=True)
class PostTurnJob:
    """One durable job a finished turn enqueues (``core/jobs``)."""

    name: str
    payload: dict[str, str]
    # Delivery is at least once: the key keeps a redelivered job from applying
    # its side effects twice (duplicate todos, etc.).
    dedupe_key: str | None


@dataclass(frozen=True)
class SavedTurn:
    """A committed turn as its jobs read it, whichever path saved it."""

    user_id: UUID
    chat_id: UUID
    # The account as the turn read it; None when the turn did not load it.
    user: User | None
    user_message: str
    assistant_text: str
    assistant_message_id: UUID | None
    # Messages in the chat before this turn.
    prior_count: int
    # The chat needs a title: a typed turn's first, or an untitled voice chat.
    run_title: bool
    # A quiz answer reads nothing new about the user.
    skip_memory_jobs: bool = False
    # The chat's last messages as the turn read them, its user's message last
    # (``StreamContext.recent_messages``). None when the turn did not read them, or
    # replaced a reply (a regenerate): the rows saved then are not these plus the reply.
    window: Sequence[Any] | None = None

    @classmethod
    def from_context(cls, ctx: StreamContext, assistant_text: str) -> "SavedTurn":
        return cls(
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            user=ctx.user,
            user_message=ctx.user_message_content,
            assistant_text=assistant_text,
            assistant_message_id=ctx.assistant_message_id,
            prior_count=ctx.prior_count,
            run_title=ctx.run_title,
            skip_memory_jobs=ctx.skip_memory_jobs,
            window=None if ctx.regenerate_backup is not None else ctx.recent_messages,
        )


@dataclass(frozen=True)
class FinishedTurn:
    """What the post-turn jobs read about the turn they follow."""

    settings: Settings
    saved: SavedTurn
    # The user line only (stripped): assistant restatements and attachment OCR
    # must not become durable memories.
    memory_user_text: str
    # The assistant message id, or the turn's place in the chat before one exists.
    turn_key: str
    # Jobs that call a model wait while the global spend cap is reached.
    spend_capped: bool


async def _memory_job(turn: FinishedTurn) -> list[PostTurnJob]:
    saved, settings = turn.saved, turn.settings
    memory_transcript = f"User: {turn.memory_user_text}" if turn.memory_user_text else ""
    should_extract_memory = memory_extraction_due(
        turn.memory_user_text,
        turn_number=(saved.prior_count + 2) // 2,
        every_n_turns=settings.memory_extract_every_n_turns,
    )
    if (
        turn.spend_capped
        or saved.skip_memory_jobs
        or not should_extract_memory
        or saved.user is None
        or not memory_switch_on(saved.user)
        or not memory_transcript
    ):
        return []
    # Dedupe per assistant message. Lock-busy retries use `{stem}:lock{n}`.
    return [
        PostTurnJob(
            "memory",
            {
                "user_id": str(saved.user_id),
                "chat_id": str(saved.chat_id),
                "transcript": cap_text_head_tail(memory_transcript, _MEMORY_TRANSCRIPT_MAX_CHARS),
                "assistant_message_id": turn.turn_key,
            },
            f"memory:{turn.turn_key}",
        )
    ]


async def _lesson_progress_job(turn: FinishedTurn) -> list[PostTurnJob]:
    """A lesson reply updates the chat's one "Learning X" memory line (no LLM)."""
    saved = turn.saved
    if (
        saved.skip_memory_jobs
        or saved.user is None
        or not memory_switch_on(saved.user)
        or lesson_step(saved.assistant_text) is None
    ):
        return []
    return [
        PostTurnJob(
            "lesson_progress",
            {
                "user_id": str(saved.user_id),
                "chat_id": str(saved.chat_id),
                "assistant_message_id": turn.turn_key,
            },
            f"lesson_progress:{turn.turn_key}",
        )
    ]


async def _topic_job(turn: FinishedTurn) -> list[PostTurnJob]:
    saved = turn.saved
    # A voice turn may have one side only (a transcript came back empty): the title
    # reads the side there is.
    user_message = saved.user_message or saved.assistant_text
    assistant_message = saved.assistant_text or saved.user_message
    if not saved.run_title or not (user_message and assistant_message):
        return []
    return [
        PostTurnJob(
            "topic",
            {
                "chat_id": str(saved.chat_id),
                "user_id": str(saved.user_id),
                "user_message": user_message,
                "assistant_message": assistant_message,
            },
            title_job_key(saved.chat_id),
        )
    ]


async def _compress_job(turn: FinishedTurn) -> list[PostTurnJob]:
    """One key per enqueue: a fixed ``compress:{chat}`` key was marked done for 24 h by
    turn 1's no-op run, so the chat was never compressed again that day and the middle
    of a long chat fell out of the prompt. Runs on one chat still coalesce: the
    ``chatcompress:`` lock serializes them and a run with too little pending returns
    before reading the transcript.
    """
    saved = turn.saved
    if (
        turn.spend_capped
        or not turn.settings.history_compression_enabled
        or _nothing_to_fold(turn.settings, saved)
    ):
        return []
    return [
        PostTurnJob(
            "compress",
            {"chat_id": str(saved.chat_id), "user_id": str(saved.user_id)},
            jobs.unique_dedupe_key(f"compress:{saved.chat_id}"),
        )
    ]


def _nothing_to_fold(settings: Settings, saved: SavedTurn) -> bool:
    """The chat as the turn just saved it has no message out of its window to fold.

    The compress job decides from the chat's message count, its newest window and how
    many it already summarized (``compaction._pending_fold``). The turn holds the first
    two exactly: the window it read, then its reply. It takes none as summarized, which
    can only find more to fold, so a chat this finds nothing in is one where the job
    would read the chat and return. Most chats are shorter than the window: their every
    turn queued a job that read three statements and its own Redis to do nothing.
    """
    if saved.window is None:
        return False
    limit = settings.recent_message_window
    window = [*saved.window, SimpleNamespace(content=saved.assistant_text)][-limit:]
    split = compute_history_split(
        saved.prior_count + 2, window, settings.context_token_budget, limit
    )
    return not should_run_compression(
        split,
        0,
        settings.history_summary_batch,
        urgent_min_pending=settings.history_summary_urgent_pending,
    )


async def _message_index_job(turn: FinishedTurn) -> list[PostTurnJob]:
    """Memory off means no personal recall: past turns are not indexed for it either."""
    saved = turn.saved
    if (
        turn.spend_capped
        or not turn.settings.chat_history_rag_enabled
        or saved.assistant_message_id is None
        or saved.skip_memory_jobs
        or not (saved.user is None or memory_switch_on(saved.user))
    ):
        return []
    return [
        PostTurnJob(
            "message_index",
            {
                "user_id": str(saved.user_id),
                "chat_id": str(saved.chat_id),
                "assistant_message_id": str(saved.assistant_message_id),
            },
            f"message_index:{saved.assistant_message_id}",
        )
    ]


# The jobs a finished turn enqueues, in this order. A new post-turn job is one
# entry here (and its handler in ``background/handlers.py``).
POST_TURN_JOBS: tuple[Callable[[FinishedTurn], Awaitable[list[PostTurnJob]]], ...] = (
    _memory_job,
    _lesson_progress_job,
    _topic_job,
    _compress_job,
    _message_index_job,
)


async def enqueue_post_turn_jobs(
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    assistant_text: str,
) -> None:
    """The jobs for a streamed turn the stream just saved."""
    await enqueue_saved_turn_jobs(redis, settings, SavedTurn.from_context(ctx, assistant_text))


async def _spend_capped(redis: Redis, settings: Settings, saved: SavedTurn) -> bool:
    """The day's cap reached, or the spend unreadable (Redis down): the jobs that spend skip."""
    try:
        capped = await quota_service.global_spend_exceeded(redis, settings)
        reason = "global spend cap"
    except RedisUnavailableError:
        capped, reason = True, "global spend unreadable (Redis down)"
    if capped:
        logger.warning(
            "skipping background LLM jobs: %s user_id=%s chat_id=%s",
            reason,
            saved.user_id,
            saved.chat_id,
        )
    return capped


async def enqueue_saved_turn_jobs(redis: Redis, settings: Settings, saved: SavedTurn) -> None:
    """The jobs for any committed turn, in ``POST_TURN_JOBS`` order."""
    spend_capped = await _spend_capped(redis, settings, saved)
    turn = FinishedTurn(
        settings=settings,
        saved=saved,
        memory_user_text=memory_extract_user_text(saved.user_message),
        turn_key=(
            str(saved.assistant_message_id)
            if saved.assistant_message_id is not None
            else f"prior{saved.prior_count}"
        ),
        spend_capped=spend_capped,
    )
    queued = [job for build in POST_TURN_JOBS for job in await build(turn)]
    # Each job is queued whatever happens to the others: one failed enqueue loses only itself.
    results = await asyncio.gather(
        *(jobs.enqueue(redis, job.name, job.payload, dedupe_key=job.dedupe_key) for job in queued),
        return_exceptions=True,
    )
    for job, result in zip(queued, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                "Post-turn job %s not queued chat_id=%s", job.name, saved.chat_id, exc_info=result
            )


async def finish_turn(
    redis: Redis,
    settings: Settings,
    *,
    user: User,
    chat_id: UUID,
    user_message: str,
    assistant: Message | None,
    prior_count: int,
    run_title: bool | None = None,
) -> None:
    """After a turn chat did not stream committed (conversation's ``turn_record`` saved it):
    its title, memory, indexing and compression jobs.

    ``run_title`` defaults to a typed turn's rule, the chat's first turn. Never raises:
    the turn is saved.
    """
    saved = SavedTurn(
        user_id=user.id,
        chat_id=chat_id,
        user=user,
        user_message=user_message,
        assistant_text=assistant.content if assistant is not None else "",
        assistant_message_id=assistant.id if assistant is not None else None,
        prior_count=prior_count,
        run_title=prior_count == 0 if run_title is None else run_title,
    )
    try:
        await enqueue_saved_turn_jobs(redis, settings, saved)
    except Exception:
        logger.exception("Post-turn jobs not queued chat_id=%s", chat_id)
