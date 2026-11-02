"""Entries the consumer group still holds: trimmed ones, poison ones, a stopped consumer."""

import logging
from typing import Any

from redis.asyncio import Redis

from app.core import sentry
from app.core.jobs.admin import _move_to_dlq
from app.core.jobs.queue import JOBS_GROUP, JOBS_STREAM

logger = logging.getLogger("app.core.jobs")

# An entry delivered this many times without being acked keeps killing the
# process that runs it (OOM, segfault) or never finishes. Reclaim moves it to
# the DLQ instead of starting the crash loop again.
MAX_JOB_DELIVERIES = 5


async def _ack_trimmed_entries(
    redis: Redis, entries: list[tuple[str, dict[str, Any] | None]]
) -> list[tuple[str, dict[str, Any]]]:
    """Drop entries the stream cap trimmed before they ran; ack them.

    XAUTOCLAIM on Redis 6.2 returns a deleted entry as ``(id, None)`` and
    leaves it pending. Acking removes it so it cannot fail every reclaim.
    """
    live: list[tuple[str, dict[str, Any]]] = []
    for entry_id, fields in entries:
        if fields is not None:
            live.append((entry_id, fields))
            continue
        if not entry_id:
            continue
        logger.warning("Job id=%s was trimmed from the stream before it ran", entry_id)
        try:
            await redis.xack(JOBS_STREAM, JOBS_GROUP, entry_id)
        except Exception:
            logger.debug("xack of trimmed entry failed id=%s", entry_id, exc_info=True)
    return live


async def _times_delivered(redis: Redis, entry_id: str) -> int:
    try:
        rows = await redis.xpending_range(
            JOBS_STREAM, JOBS_GROUP, min=entry_id, max=entry_id, count=1
        )
    except Exception:
        logger.debug("xpending_range failed id=%s", entry_id, exc_info=True)
        return 0
    if not rows:
        return 0
    try:
        return int(rows[0].get("times_delivered") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


async def _drop_poison_entries(
    redis: Redis, entries: list[tuple[str, dict[str, Any] | None]]
) -> list[tuple[str, dict[str, Any] | None]]:
    """Move reclaimed entries past MAX_JOB_DELIVERIES to the DLQ and ack them.

    A handler exception is retried and dead-lettered in-process, and a running
    job's lease (``inflight``) keeps peers from reclaiming it, so only an entry
    that never gets acked (the process died or was killed while running it)
    reaches this count.
    """
    keep: list[tuple[str, dict[str, Any] | None]] = []
    for entry_id, fields in entries:
        if fields is None:
            keep.append((entry_id, fields))
            continue
        delivered = await _times_delivered(redis, entry_id)
        if delivered <= MAX_JOB_DELIVERIES:
            keep.append((entry_id, fields))
            continue
        logger.error(
            "Job id=%s type=%s delivered %s times without finishing; moving to DLQ",
            entry_id,
            fields.get("type"),
            delivered,
        )
        sentry.report_exception(f"job_poison:{fields.get('type')}")
        await _move_to_dlq(
            redis, entry_id, fields, f"delivered {delivered} times without finishing"
        )
        try:
            await redis.xack(JOBS_STREAM, JOBS_GROUP, entry_id)
        except Exception:
            logger.debug("xack of poison entry failed id=%s", entry_id, exc_info=True)
    return keep


async def _forget_consumer(redis: Redis, consumer: str) -> None:
    """Remove this process's consumer from the group when its loop stops.

    Consumers are named per process (host + pid), so every restart, deploy and
    ``--reload`` added one to the group and nothing ever removed it. One that
    still owns pending entries stays: XGROUP DELCONSUMER would drop them from
    the pending list, and XAUTOCLAIM hands them to a live worker first.
    """
    try:
        owned = await redis.xpending_range(
            JOBS_STREAM, JOBS_GROUP, min="-", max="+", count=1, consumername=consumer
        )
        if not owned:
            await redis.xgroup_delconsumer(JOBS_STREAM, JOBS_GROUP, consumer)
    except Exception:
        logger.debug("jobs consumer cleanup skipped consumer=%s", consumer, exc_info=True)
