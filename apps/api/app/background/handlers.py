"""Job-type → handler registration for the durable job queue.

`app/core/jobs/` owns the queue mechanics (stream, retries, DLQ, metrics)
and exposes `register`; the domain bodies live here, next to the background
modules they call. Keeping this out of `core/` means the lowest layer no
longer imports `app.background` / `app.services`, so importing the queue
does not drag every background module (and its transitive service imports)
into the graph — and adding or deleting a job touches one file that no other
job's feature branch is also editing.

Import this module once at startup, before the worker starts consuming
(`app/main.py` and `app/worker_main.py` do). Registration is an explicit
list, not import-time discovery, so the set of live job types stays greppable.
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.background import message_indexing
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.jobs import (
    JobDiscardError,
    JobSkipped,
    enqueue_later,
    register,
    retry_delay_s,
    unique_dedupe_key,
)
from app.core.redis import get_redis_client
from app.exceptions import RedisUnavailableError
from app.modules.account import lifecycle as account_lifecycle
from app.modules.attachments import jobs as attachment_indexing
from app.modules.chat import compaction, lesson_progress
from app.modules.chat import titles as chat_titles
from app.modules.memory import consolidation_workflow as memory_consolidation
from app.modules.memory import extraction_workflow as memory_extraction
from app.modules.memory import history_scan as memory_history_scan
from app.modules.memory import learning_progress as memory_learning
from app.modules.notifications import transactional_email as transactional_email_service
from app.repositories import users as users_repo
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

# Most memory history scans one worker runs at once (of JOBS_WORKER_CONCURRENCY slots).
HISTORY_SCANS_AT_ONCE = 3


_MEMORY_LOCK_MAX_RETRIES = 3
# A finished welcome or receipt email, storage sweep or chat title must not run again
# for a late duplicate; every other job's done marker lives the default hour.
_ONCE_A_DAY = 86_400


def _memory_lock_retries(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("lock_retries") or 0)
    except (TypeError, ValueError):
        return 0


async def _reenqueue_after_memory_lock(
    *,
    job_type: str,
    retry_payload: dict[str, Any],
    dedupe_stem: str,
    warning: str,
) -> None:
    """Re-enqueue a lock-busy memory job for later, or discard to the DLQ after the cap.

    The retry waits in the delayed queue (the job retry pauses: 15 s, then 1 min,
    4 min), not asleep in this worker slot. Each attempt has its own ``dedupe_key``,
    unique per request, so a reclaim of this entry plus the retry cannot double-run
    the same pass, and a later request is never skipped as already done. Exhausted
    retries raise ``JobDiscardError`` so the worker records the drop in the DLQ
    instead of acking a silent success.
    """
    retries = _memory_lock_retries(retry_payload)
    if retries >= _MEMORY_LOCK_MAX_RETRIES:
        logger.warning("%s", warning)
        raise JobDiscardError(warning)

    next_retries = retries + 1
    await enqueue_later(
        get_redis_client(),
        job_type,
        {**retry_payload, "lock_retries": next_retries},
        delay_s=retry_delay_s(next_retries + 1),
        dedupe_key=unique_dedupe_key(f"{dedupe_stem}:lock{next_retries}"),
    )


async def _spend_capped(settings: Settings) -> bool:
    """Fail-closed: skip extra LLM/embed work when the global $ cap is hit, or Redis is down.

    M12: background LLM jobs (memory/topic/compress) intentionally
    bypass per-user token quota — they are operator cost, not user cost.
    The global $ cap is the guardrail that prevents runaway spend across
    all users. Per-user quota debiting would punish users for the app's
    own background work (title generation, memory extraction).
    """
    if settings.daily_global_spend_usd <= 0:
        return False
    try:
        capped = await quota_service.global_spend_exceeded(get_redis_client(), settings)
    except RedisUnavailableError:
        logger.warning("skipping background LLM job: global spend unreadable (Redis down)")
        return True
    if capped:
        logger.warning("skipping background LLM job: global spend cap")
    return capped


_Handler = Callable[[Settings, dict[str, Any]], Awaitable[None]]


def _unless_spend_capped(handler: _Handler) -> _Handler:
    """Run ``handler`` only while the global $ cap is not reached (see ``_spend_capped``).

    Every job that makes a model or embedding call carries this; a job that
    must run regardless (email, storage sweep, lesson progress) does not.
    """

    @functools.wraps(handler)
    async def run(settings: Settings, payload: dict[str, Any]) -> None:
        if await _spend_capped(settings):
            # Not done: a later request for the same work must still run.
            raise JobSkipped("global spend cap")
        await handler(settings, payload)

    return run


@_unless_spend_capped
async def _handle_topic(settings: Settings, payload: dict[str, Any]) -> None:
    applied = await chat_titles.generate_chat_title(
        settings,
        UUID(payload["chat_id"]),
        payload.get("user_message", ""),
        payload.get("assistant_message", ""),
        user_id=UUID(payload["user_id"]),
    )
    if not applied:
        # No title this time (nothing usable, or the chat already has one): a later
        # request (the message-list backfill) may still try.
        raise JobSkipped("no title applied")


@_unless_spend_capped
async def _handle_memory(settings: Settings, payload: dict[str, Any]) -> None:
    outcome = await memory_extraction.extract_and_store_memories(
        settings,
        user_id=UUID(payload["user_id"]),
        chat_id=UUID(payload["chat_id"]),
        transcript=payload["transcript"],
    )
    if outcome == "model_failed":
        # The lines wait for the chat's next turn, which may never come: "remember I'm
        # allergic to peanuts" as a chat's last line. The job's own retries read them
        # again; after FAILED_PASS_LIMIT failures the pass moves on and returns.
        raise RuntimeError("memory model gave no usable answer; retrying the pass later")
    if outcome != "skipped_lock":
        return
    # Write lock busy (consolidation or sibling extraction). Re-enqueue a
    # bounded number of times so the turn's memory isn't silently dropped.
    await _reenqueue_after_memory_lock(
        job_type="memory",
        retry_payload={
            "user_id": payload["user_id"],
            "chat_id": payload["chat_id"],
            "transcript": payload["transcript"],
            "assistant_message_id": payload.get("assistant_message_id") or "",
            "lock_retries": payload.get("lock_retries") or 0,
        },
        dedupe_stem=f"memory:{payload.get('assistant_message_id') or payload['chat_id']}",
        warning=(
            "Memory extraction dropped after lock retries "
            f"user_id={payload.get('user_id')} chat_id={payload.get('chat_id')}"
        ),
    )


async def _handle_lesson_progress(settings: Settings, payload: dict[str, Any]) -> None:
    """Keep the chat's "Learning X: reached Lesson N" memory line current. No LLM."""
    user_id, chat_id = UUID(payload["user_id"]), UUID(payload["chat_id"])
    async with SessionLocal() as session:
        progress = await lesson_progress.load_lesson_progress(
            session, user_id=user_id, chat_id=chat_id
        )
    if progress is None:
        return
    outcome = await memory_learning.record_learning_progress(
        settings,
        user_id=user_id,
        chat_id=chat_id,
        text=progress.text,
        started_at=progress.started_at,
    )
    if outcome != "skipped_lock":
        return
    await _reenqueue_after_memory_lock(
        job_type="lesson_progress",
        retry_payload={
            "user_id": payload["user_id"],
            "chat_id": payload["chat_id"],
            "assistant_message_id": payload.get("assistant_message_id") or "",
            "lock_retries": payload.get("lock_retries") or 0,
        },
        dedupe_stem=f"lesson_progress:{payload.get('assistant_message_id') or payload['chat_id']}",
        warning=f"Lesson progress dropped after lock retries chat_id={payload.get('chat_id')}",
    )


@_unless_spend_capped
async def _handle_memory_history_scan(settings: Settings, payload: dict[str, Any]) -> None:
    await memory_history_scan.scan_recent_chats(settings, user_id=UUID(payload["user_id"]))


@_unless_spend_capped
async def _handle_memory_consolidate(settings: Settings, payload: dict[str, Any]) -> None:
    outcome = await memory_consolidation.consolidate_user_memory_sections(
        settings,
        user_id=UUID(payload["user_id"]),
    )
    if outcome != "skipped_lock":
        return
    await _reenqueue_after_memory_lock(
        job_type="memory_consolidate",
        retry_payload={
            "user_id": payload["user_id"],
            "lock_retries": payload.get("lock_retries") or 0,
        },
        dedupe_stem=f"memory_consolidate:{payload['user_id']}",
        warning=(
            f"Memory consolidation dropped after lock retries user_id={payload.get('user_id')}"
        ),
    )


@_unless_spend_capped
async def _handle_compress(settings: Settings, payload: dict[str, Any]) -> None:
    await compaction.compress_chat_history(
        settings, UUID(payload["chat_id"]), user_id=UUID(payload["user_id"])
    )


async def _handle_transactional_email(settings: Settings, payload: dict[str, Any]) -> None:
    """Best-effort outbound email (welcome / receipts). Re-raises transient
    failures so the worker retry loop can retry; user-not-found is a permanent
    discard (JobDiscardError → DLQ, no retry)."""
    async with SessionLocal() as session:
        user = await users_repo.get_by_id(session, UUID(payload["user_id"]))
    if user is None:
        logger.warning("transactional_email: user not found id=%s", payload.get("user_id"))
        raise JobDiscardError(f"transactional_email: user not found id={payload.get('user_id')}")
    kind = payload.get("kind")
    if kind == "welcome":
        await transactional_email_service.send_welcome(settings, user)
    elif kind == "receipt":
        await transactional_email_service.send_purchase_receipt(
            settings,
            user,
            event_type=str(payload.get("event_type") or ""),
            store=payload.get("store"),
            product_id=payload.get("product_id"),
            expiration=payload.get("expiration"),
        )
    else:
        logger.warning("transactional_email: unknown kind=%s", kind)
        raise JobDiscardError(f"transactional_email: unknown kind={kind!r}")


@_unless_spend_capped
async def _handle_attachment_index(settings: Settings, payload: dict[str, Any]) -> None:
    await attachment_indexing.index_attachment_job(settings, payload)


@_unless_spend_capped
async def _handle_message_index(settings: Settings, payload: dict[str, Any]) -> None:
    await message_indexing.index_message_job(settings, payload)


async def _handle_storage_sweep(settings: Settings, payload: dict[str, Any]) -> None:
    """GDPR residual after account wipe: sessions, leftover R2 objects, Redis keys and jobs
    (``account.lifecycle.sweep_deleted_account``; skipped while the account exists).

    Must not be spend-capped — leftover blobs and cached text are a privacy
    residual, not optional enrichment. The user's finished and failed jobs
    (their payloads carry chat text) leave the jobs stream and the DLQ; this
    sweep's own entry stays, since it holds only ids and must survive a
    worker crash to run again.
    """
    raw = payload.get("user_id")
    try:
        user_id = UUID(str(raw))
    except (TypeError, ValueError):
        logger.warning("storage_sweep invalid user_id=%r", raw)
        return
    reply_ids = payload.get("reply_ids")
    replies = [str(item) for item in reply_ids] if isinstance(reply_ids, list) else []
    await account_lifecycle.sweep_deleted_account(settings, get_redis_client(), user_id, replies)


def register_all() -> None:
    """Register every live job type. Idempotent — `register` overwrites by key."""
    register("topic", _handle_topic, done_ttl_seconds=_ONCE_A_DAY)
    register("memory", _handle_memory)
    register("memory_consolidate", _handle_memory_consolidate)
    register("lesson_progress", _handle_lesson_progress)
    # About twenty LLM extractions each, queued the first time someone opens
    # Memory: a launch-day burst must leave slots for titles, memory and email.
    register(
        memory_history_scan.HISTORY_SCAN_JOB,
        _handle_memory_history_scan,
        max_running=HISTORY_SCANS_AT_ONCE,
    )
    register("compress", _handle_compress)
    register("transactional_email", _handle_transactional_email, done_ttl_seconds=_ONCE_A_DAY)
    # No more at once than the worker has document processes: a parse that waits for one
    # past the queue wait is retried, but need not wait at all.
    register(
        "attachment_index",
        _handle_attachment_index,
        max_running=get_settings().document_pool_workers,
    )
    register("message_index", _handle_message_index)
    register(account_lifecycle.SWEEP_JOB, _handle_storage_sweep, done_ttl_seconds=_ONCE_A_DAY)
    # The same sweep, scheduled before an account delete commits (account.lifecycle).
    register(
        account_lifecycle.SWEEP_BACKSTOP_JOB, _handle_storage_sweep, done_ttl_seconds=_ONCE_A_DAY
    )
