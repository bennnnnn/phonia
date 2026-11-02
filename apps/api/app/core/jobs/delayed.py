"""Jobs that wait: a retry, or an entry for a type this worker does not know yet.

A failed job used to retry in-process twice within about six seconds and then
go to the dead-letter queue, so a 30-second embedding or email outage lost
every job that started in it. Now each failure puts the entry back with
``attempt`` + 1 into a sorted set scored by when it may run, and the worker
loop moves due entries onto the stream. Six attempts span about 50 minutes,
long enough to outlast a provider blip, before the job is dead-lettered. The
slot is free while the job waits.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis

from app.core import sentry
from app.core.jobs.queue import append_entry, job_fields

logger = logging.getLogger("app.core.jobs")

DELAYED_ZSET = "recall:jobs:delayed"
ATTEMPT_FIELD = "attempt"
# Attempts in all, the first included: 15 s, 1 min, 4 min, 16 min and 30 min apart.
MAX_ATTEMPTS = 6
_FIRST_RETRY_S = 15.0
_RETRY_FACTOR = 4.0
_MAX_RETRY_S = 1_800.0
_JITTER = 0.2
_MOVE_BATCH = 100
# A due entry that could not go back on the stream waits this long before the next try.
_MOVE_FAILED_RETRY_S = 60.0
# Waiting out a lock another job holds for a model round trip, inside one job.
LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_BACKOFF_S = 2.0


def attempt_of(fields: dict[str, str]) -> int:
    """Which attempt this entry is (1 for a fresh enqueue)."""
    try:
        return max(1, int(fields.get(ATTEMPT_FIELD) or 1))
    except (TypeError, ValueError):
        return 1


def retry_delay_s(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """The wait before ``attempt`` (2 is the first retry), ±20% so retries do not move in step."""
    base = min(_MAX_RETRY_S, _FIRST_RETRY_S * _RETRY_FACTOR ** max(0, attempt - 2))
    return base * (1 - _JITTER + 2 * _JITTER * rand())


async def schedule(
    redis: Redis, fields: dict[str, str], *, delay_s: float, now: float | None = None
) -> None:
    """Hold ``fields`` (a stream entry) until ``delay_s`` from now, then the worker re-adds it."""
    member = json.dumps({"fields": fields, "nonce": uuid4().hex}, sort_keys=True)
    await redis.zadd(DELAYED_ZSET, {member: (now if now is not None else time.time()) + delay_s})


async def schedule_retry(
    redis: Redis, fields: dict[str, str], *, now: float | None = None
) -> int | None:
    """Put a failed entry back for its next attempt; None when its attempts are spent."""
    attempt = attempt_of(fields) + 1
    if attempt > MAX_ATTEMPTS:
        return None
    await schedule(
        redis, {**fields, ATTEMPT_FIELD: str(attempt)}, delay_s=retry_delay_s(attempt), now=now
    )
    return attempt


async def move_due(redis: Redis, *, now: float | None = None, limit: int = _MOVE_BATCH) -> int:
    """Move entries whose wait is over onto the jobs stream; returns how many moved.

    ZREM claims each member before its XADD, so of two workers moving at once only one
    re-adds it. A failed XADD puts the member back for a later pass; a crash between
    the two commands loses that one entry, the price of not needing a Lua script.
    """
    due = cast(
        list[str],
        await redis.zrangebyscore(
            DELAYED_ZSET, "-inf", now if now is not None else time.time(), start=0, num=limit
        ),
    )
    moved = 0
    for member in due:
        if not await redis.zrem(DELAYED_ZSET, member):
            continue
        try:
            fields = json.loads(member)["fields"]
            await append_entry(redis, {str(key): str(value) for key, value in fields.items()})
            moved += 1
        except Exception:
            logger.warning("Delayed job could not go back on the stream; retrying", exc_info=True)
            await redis.zadd(DELAYED_ZSET, {member: time.time() + _MOVE_FAILED_RETRY_S})
    return moved


async def delayed_depth(redis: Redis) -> int:
    """Entries waiting for their next attempt."""
    return int(await redis.zcard(DELAYED_ZSET))


async def schedule_job(
    redis: Redis,
    job_type: str,
    payload: dict[str, object],
    *,
    delay_s: float,
    dedupe_key: str | None = None,
) -> None:
    """``enqueue_later`` that raises when Redis does: for a caller that must not go on
    without the job (account delete's backstop sweep)."""
    await schedule(redis, job_fields(job_type, payload, dedupe_key=dedupe_key), delay_s=delay_s)


async def enqueue_later(
    redis: Redis,
    job_type: str,
    payload: dict[str, object],
    *,
    delay_s: float,
    dedupe_key: str | None = None,
) -> None:
    """Enqueue a job to run no sooner than ``delay_s`` from now; best-effort like ``enqueue``."""
    try:
        await schedule_job(redis, job_type, payload, delay_s=delay_s, dedupe_key=dedupe_key)
    except Exception:
        logger.exception("Failed to schedule job type=%s", job_type)
        sentry.report_exception(f"enqueue_failed:{job_type}")
