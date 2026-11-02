"""The job contract: a handler per type, entries enqueued and dispatched, a bounded stream."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from redis.asyncio import Redis

from app.core import sentry
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.core.jobs")

JOBS_STREAM = "recall:jobs"
JOBS_DLQ_STREAM = "recall:jobs:dlq"
JOBS_GROUP = "workers"
# The floor under the stream's hard ceiling (``jobs_stream_max_len``).
_MAXLEN = 10_000
# How long a finished job's dedupe marker skips a duplicate, unless its type asks for
# longer: an acked entry needs cover only for a crash between success and ack.
DEFAULT_DONE_TTL_SECONDS = 3_600


class JobDiscardError(Exception):
    """Non-retryable job — move to DLQ and ack (bad payload, a permanent refusal)."""


class UnknownJobTypeError(Exception):
    """No handler here for this type: an older worker during a deploy, or after a rollback.

    The worker keeps such an entry waiting (``delayed``) instead of dead-lettering it,
    so the release that knows the type runs it.
    """


class JobSkipped(Exception):
    """The handler did nothing this time (a spend cap, a title already set): not done.

    The worker releases the dedupe claim and acks, so a later request for the same
    job still runs. Marking it done hid that work for the marker's lifetime.
    """


JobHandler = Callable[[Settings, dict[str, Any]], Awaitable[None]]
_HANDLERS: dict[str, JobHandler] = {}
# Job type -> most jobs of that type one worker runs at once (see ``register``).
_RUNNING_LIMITS: dict[str, int] = {}
# Job type -> how long its done marker lives (see ``register``).
_DONE_TTLS: dict[str, int] = {}


def register(
    job_type: str,
    handler: JobHandler,
    *,
    max_running: int | None = None,
    done_ttl_seconds: int | None = None,
) -> None:
    """Route ``job_type`` to ``handler``.

    ``max_running`` caps how many jobs of this type one worker runs at once, so
    a burst of a slow type cannot take every slot from the quick ones.
    ``done_ttl_seconds`` keeps its done marker longer than an hour, for a job whose
    duplicate must not run again even much later (an email, a once-per-chat title).
    """
    _HANDLERS[job_type] = handler
    if max_running is None:
        _RUNNING_LIMITS.pop(job_type, None)
    else:
        _RUNNING_LIMITS[job_type] = max(1, max_running)
    if done_ttl_seconds is None:
        _DONE_TTLS.pop(job_type, None)
    else:
        _DONE_TTLS[job_type] = max(1, done_ttl_seconds)


def done_ttl_seconds(job_type: str | None) -> int:
    """How long a finished job of this type keeps duplicates out."""
    return _DONE_TTLS.get(job_type or "", DEFAULT_DONE_TTL_SECONDS)


def running_limit(job_type: str | None) -> int | None:
    """The ``max_running`` cap registered for this type (None = only the worker's limit)."""
    return _RUNNING_LIMITS.get(job_type or "")


async def enqueue(
    redis: Redis,
    job_type: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> None:
    """Persist a job. Best-effort — a failure here never breaks the chat path.

    A failed enqueue is logged AND reported to Sentry (when initialized) so
    silent job loss is observable — otherwise titles/memory/compression can
    quietly stop running with no signal.

    ``dedupe_key``, when set, is stored on the stream entry so the worker can
    skip redelivery / duplicate enqueue after a successful (or in-flight)
    run of the same logical job.
    """
    try:
        await append_entry(redis, job_fields(job_type, payload, dedupe_key=dedupe_key))
    except Exception:
        logger.exception("Failed to enqueue job type=%s", job_type)
        # Never raises: a silent job loss is still visible in Sentry.
        sentry.report_exception(f"enqueue_failed:{job_type}")


def job_fields(
    job_type: str, payload: dict[str, Any], *, dedupe_key: str | None = None
) -> dict[str, str]:
    """A stream entry for one job."""
    fields: dict[str, str] = {"type": job_type, "payload": json.dumps(payload)}
    if dedupe_key:
        fields["dedupe_key"] = dedupe_key
    return fields


async def append_entry(redis: Redis, fields: dict[str, str]) -> None:
    """XADD one job entry under the stream's hard ceiling (enqueue, retries, DLQ replay).

    The ceiling rides on XADD itself (no extra round trip) so the stream stays
    bounded even while no worker trims it. Reaching it drops the oldest entries,
    run or not; the queue metrics alert before that.
    """
    # redis-py stubs type xadd fields as an invariant EncodedT dict; cast.
    hard_cap = hard_maxlen()
    if hard_cap is None:
        await redis.xadd(JOBS_STREAM, cast(Any, fields))
    else:
        await redis.xadd(JOBS_STREAM, cast(Any, fields), maxlen=hard_cap, approximate=True)


def hard_maxlen() -> int | None:
    """Ceiling on the jobs stream (None = off), never below ``_MAXLEN``.

    Dropping the oldest entries past it is the price of keeping Redis (shared with
    quota, auth revocation and rate limits) alive when no worker is reading.
    """
    configured = get_settings().jobs_stream_max_len
    if configured <= 0:
        return None
    return max(configured, _MAXLEN)


def _id_key(entry_id: str) -> tuple[int, int]:
    ms, _, seq = entry_id.partition("-")
    return int(ms), int(seq or 0)


def _after(entry_id: str) -> str:
    ms, seq = _id_key(entry_id)
    return f"{ms}-{seq + 1}"


async def trim_floor(redis: Redis) -> str | None:
    """The lowest id still needed: the oldest pending entry, or the first undelivered one.

    Entries below it were delivered and acked. None (nothing may go) when the group
    does not exist yet or has delivered nothing.
    """
    groups = cast(list[dict[str, Any]], await redis.xinfo_groups(JOBS_STREAM))
    group = next((g for g in groups if g.get("name") == JOBS_GROUP), None)
    if group is None:
        return None
    last_delivered = str(group.get("last-delivered-id") or "0-0")
    if last_delivered == "0-0":
        return None
    floor = _after(last_delivered)
    summary = await redis.xpending(JOBS_STREAM, JOBS_GROUP)
    oldest_pending = summary.get("min") if isinstance(summary, dict) else None
    if oldest_pending and _id_key(str(oldest_pending)) < _id_key(floor):
        floor = str(oldest_pending)
    return floor


async def trim_jobs_stream(redis: Redis) -> None:
    """Drop entries that were delivered and acked; never pending or undelivered ones.

    The worker runs this on its reclaim cadence. Enqueue used to trim with MAXLEN
    whenever nothing was pending, and undelivered entries sit at the newest end, so
    with no worker reading (scaled to zero, a crash-looping release) every enqueue
    cut the backlog of jobs nobody had run to about 10,000.
    """
    try:
        floor = await trim_floor(redis)
        if floor:
            await redis.xtrim(JOBS_STREAM, minid=floor, approximate=True)
    except Exception:
        logger.debug("jobs stream trim skipped", exc_info=True)


async def _dispatch(settings: Settings, fields: dict[str, Any]) -> None:
    job_type = fields.get("type")
    handler = _HANDLERS.get(job_type or "")
    if handler is None:
        raise UnknownJobTypeError(f"unknown job type={job_type!r}")
    try:
        payload = json.loads(fields.get("payload") or "{}")
    except json.JSONDecodeError as exc:
        raise JobDiscardError(f"bad payload type={job_type!r}") from exc
    await handler(settings, payload)
