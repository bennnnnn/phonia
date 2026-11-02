"""Queue health, the dead-letter queue, and the per-user purge."""

import json
import logging
import time
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

from redis.asyncio import Redis

from app.core import sentry
from app.core.jobs.queue import (
    JOBS_DLQ_STREAM,
    JOBS_GROUP,
    JOBS_STREAM,
    append_entry,
    hard_maxlen,
)

logger = logging.getLogger("app.core.jobs")

_DLQ_MAXLEN = 5_000
# A dead letter older than this is trimmed: by then it was replayed or is not coming back.
_DLQ_MAX_AGE_S = 7 * 86_400
# Observe queue health: report backlog, pending entries and the DLQ to Sentry every
# _METRICS_INTERVAL_S, and capture a warning when a count crosses its threshold so a
# backed-up queue or growing DLQ doesn't go unnoticed (the admin DLQ endpoint is
# dev-only, so prod had no signal before).
_METRICS_INTERVAL_S = 300
# Dead letters added since the last report that warrant a warning. The depth itself
# alerted every 5 minutes, from every worker, forever after one provider blip.
_DLQ_GROWTH_ALERT = 20
_DLQ_DEPTH_KEY = "recall:jobs:dlq:reported_depth"
_PENDING_ALERT_THRESHOLD = 50
# Jobs not yet delivered to any worker, and how long the oldest has waited.
_BACKLOG_ALERT_THRESHOLD = 1_000
_BACKLOG_AGE_ALERT_S = 600
# One worker reports per interval; the rest skip.
_METRICS_LOCK_KEY = "recall:jobs:metrics:lock"
# Types safe to run again by themselves once their dependency is back: replaying one
# twice does no harm. At most this many per pass, each at most _MAX_AUTO_REPLAYS times.
_AUTO_REPLAY_TYPES = frozenset(
    {"storage_sweep", "account_sweep_backstop", "attachment_index", "transactional_email"}
)
_AUTO_REPLAY_BATCH = 50
_MAX_AUTO_REPLAYS = 3
_AUTO_REPLAY_MIN_AGE_S = 3_600
_AUTO_REPLAY_LOCK_KEY = "recall:jobs:dlq:replay_lock"
_AUTO_REPLAY_INTERVAL_S = 3_600


async def _move_to_dlq(
    redis: Redis,
    entry_id: str,
    fields: dict[str, Any],
    error: str,
) -> None:
    """Persist failed jobs for inspection/replay without blocking the worker."""
    try:
        dlq_fields: dict[str, str] = {
            "original_id": entry_id,
            "type": str(fields.get("type", "")),
            "payload": str(fields.get("payload", "{}")),
            "error": error[:2000],
            "failed_at": datetime.now(UTC).isoformat(),
        }
        dedupe_key = fields.get("dedupe_key")
        if dedupe_key:
            dlq_fields["dedupe_key"] = str(dedupe_key)
        if fields.get("replays"):
            dlq_fields["replays"] = str(fields["replays"])
        await redis.xadd(
            JOBS_DLQ_STREAM,
            cast(Any, dlq_fields),
            maxlen=_DLQ_MAXLEN,
            approximate=True,
        )
    except Exception:
        logger.debug("Failed to write job to DLQ id=%s", entry_id, exc_info=True)
        sentry.report_exception("dlq_write_failed")


# ── DLQ inspection / replay ──────────────────────────────────────────────────


class QueueMetrics(TypedDict):
    """A count Redis could not read is None, and ``metrics_error`` names why."""

    dlq_depth: int | None
    pending_entries: int | None
    backlog: int | None
    oldest_undelivered_age_s: float | None
    delayed: int | None
    stream_length: int | None
    metrics_error: str | None


def _entry_age_s(entry_id: str, now: float) -> float:
    ms = int(str(entry_id).partition("-")[0] or 0)
    return max(0.0, now - ms / 1000)


async def _backlog(redis: Redis, now: float) -> tuple[int, float | None]:
    """Entries no worker has been given yet, and the age of the oldest.

    Undelivered entries follow the group's last-delivered id. The pending count could
    not see a backlog: a worker holds at most its running and waiting entries.
    """
    groups = cast(list[dict[str, Any]], await redis.xinfo_groups(JOBS_STREAM))
    group = next((g for g in groups if g.get("name") == JOBS_GROUP), None)
    last = str(group.get("last-delivered-id") or "0-0") if group else "0-0"
    first = cast(
        list[tuple[str, dict[str, Any]]],
        await redis.xrange(JOBS_STREAM, min=f"({last}" if last != "0-0" else "-", max="+", count=1),
    )
    if not first:
        return 0, None
    lag = group.get("lag") if group else None
    if not isinstance(lag, int):
        # Redis below 7 has no lag field: count from the first undelivered id.
        lag = len(cast(list[Any], await redis.xrange(JOBS_STREAM, min=first[0][0], max="+")))
    return lag, _entry_age_s(first[0][0], now)


async def collect_queue_metrics(redis: Redis) -> QueueMetrics:
    """Return the DLQ depth, pending entries, backlog and waiting retries.

    Never raises into the worker loop, but an unreadable count is None, not 0:
    a failing Redis must not read as an empty, healthy queue.
    """
    from app.core.jobs.delayed import delayed_depth

    metrics = QueueMetrics(
        dlq_depth=None,
        pending_entries=None,
        backlog=None,
        oldest_undelivered_age_s=None,
        delayed=None,
        stream_length=None,
        metrics_error=None,
    )
    try:
        metrics["dlq_depth"] = int(await redis.xlen(JOBS_DLQ_STREAM))
        # redis-py parses the XPENDING summary into {"pending": n, "min", "max", "consumers"}.
        summary = cast(dict[str, Any], await redis.xpending(JOBS_STREAM, JOBS_GROUP))
        metrics["pending_entries"] = int(summary["pending"])
        metrics["stream_length"] = int(await redis.xlen(JOBS_STREAM))
        metrics["backlog"], metrics["oldest_undelivered_age_s"] = await _backlog(redis, time.time())
        metrics["delayed"] = await delayed_depth(redis)
    except Exception as exc:
        metrics["metrics_error"] = type(exc).__name__
        logger.warning("jobs queue metrics unreadable: %s", metrics["metrics_error"])
    return metrics


async def _dlq_growth(redis: Redis, depth: int) -> int:
    """Dead letters added since the last report (0 on the first one)."""
    previous = await redis.getset(_DLQ_DEPTH_KEY, str(depth))
    await redis.expire(_DLQ_DEPTH_KEY, _METRICS_INTERVAL_S * 4)
    try:
        return max(0, depth - int(previous)) if previous is not None else 0
    except (TypeError, ValueError):
        return 0


def _alerts(metrics: QueueMetrics, dlq_growth: int) -> list[str]:
    error = metrics["metrics_error"]
    alerts = [f"Jobs queue metrics unreadable ({error})"] if error else []
    if dlq_growth >= _DLQ_GROWTH_ALERT:
        alerts.append(f"Jobs DLQ grew by {dlq_growth} in {_METRICS_INTERVAL_S}s")
    pending, backlog = metrics["pending_entries"], metrics["backlog"]
    if pending is not None and pending >= _PENDING_ALERT_THRESHOLD:
        alerts.append(f"Jobs pending entries {pending} >= {_PENDING_ALERT_THRESHOLD}")
    if backlog is not None and backlog >= _BACKLOG_ALERT_THRESHOLD:
        alerts.append(f"Jobs backlog {backlog} >= {_BACKLOG_ALERT_THRESHOLD}")
    age = metrics["oldest_undelivered_age_s"]
    if age is not None and age >= _BACKLOG_AGE_ALERT_S:
        alerts.append(f"Oldest undelivered job waited {int(age)}s >= {_BACKLOG_AGE_ALERT_S}s")
    cap, length = hard_maxlen(), metrics["stream_length"]
    if cap is not None and length is not None and length >= cap * 0.9:
        alerts.append(f"Jobs stream at {length} of its {cap} cap: the oldest jobs are dropped next")
    return alerts


async def report_queue_metrics(redis: Redis) -> QueueMetrics:
    """Report queue metrics to Sentry when it is installed: a breadcrumb every call, and a
    warning when a count crosses its threshold or could not be read at all.

    One worker reports per interval (a lock), and the DLQ alerts on growth, not depth.
    Old dead letters are trimmed by age here.
    """
    try:
        if not await redis.set(_METRICS_LOCK_KEY, "1", ex=_METRICS_INTERVAL_S - 5, nx=True):
            return await collect_queue_metrics(redis)
    except Exception:
        logger.debug("jobs metrics lock unavailable; reporting anyway", exc_info=True)
    metrics = await collect_queue_metrics(redis)
    growth = 0
    if metrics["dlq_depth"] is not None:
        try:
            growth = await _dlq_growth(redis, metrics["dlq_depth"])
            await _trim_old_dead_letters(redis)
        except Exception:
            logger.debug("DLQ growth read failed", exc_info=True)
    sentry.report_breadcrumb(
        "jobs.queue",
        f"queue metrics: dlq={metrics['dlq_depth']} pending={metrics['pending_entries']} "
        f"backlog={metrics['backlog']}",
        level="info",
        data=metrics,
    )
    for alert in _alerts(metrics, growth):
        sentry.report_message(alert, level="warning")
    return metrics


async def _trim_old_dead_letters(redis: Redis) -> None:
    oldest_kept_ms = int((time.time() - _DLQ_MAX_AGE_S) * 1000)
    # Exact: the DLQ is small, and an approximate trim may keep a whole old node.
    await redis.xtrim(JOBS_DLQ_STREAM, minid=f"{oldest_kept_ms}-0", approximate=False)


async def list_dlq(redis: Redis, *, count: int = 50) -> list[dict[str, Any]]:
    """Return up to `count` recent DLQ entries for inspection."""
    resp = await redis.xrevrange(JOBS_DLQ_STREAM, count=count)
    out: list[dict[str, Any]] = []
    if not resp:
        return out
    for entry in resp:
        entry_id, fields = entry
        f = cast(dict[str, Any], fields)
        out.append(
            {
                "id": entry_id,
                "original_id": f.get("original_id", ""),
                "type": f.get("type", ""),
                "payload": f.get("payload", "{}"),
                "error": f.get("error", ""),
                "failed_at": f.get("failed_at", ""),
                "dedupe_key": f.get("dedupe_key", ""),
                "replays": f.get("replays", ""),
            }
        )
    return out


# ── account delete ───────────────────────────────────────────────────────────

_PURGE_SCAN_BATCH = 500


def _payload_user_id(fields: dict[str, Any]) -> str | None:
    try:
        payload = json.loads(fields.get("payload") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get("user_id")
    return str(raw) if raw else None


def _after(entry_id: str) -> str:
    """The smallest stream id after *entry_id* (an exclusive XRANGE start)."""
    ms, _, seq = str(entry_id).partition("-")
    return f"{ms}-{int(seq or 0) + 1}"


async def purge_user_jobs(
    redis: Redis,
    user_id: UUID | str,
    *,
    keep_types: Collection[str] = (),
    batch: int = _PURGE_SCAN_BATCH,
) -> int:
    """XDEL every jobs-stream and DLQ entry whose payload names *user_id*.

    Acked and failed entries stay in both streams until the length cap trims
    them, and their payloads carry chat text. Walks each stream in bounded
    XRANGE pages and deletes only entries whose payload ``user_id`` equals
    this one; *keep_types* entries stay (the caller's own running job).
    Worker-only (account delete's sweep): never call it on a request path.
    """
    needle = str(user_id)
    page = max(1, batch)
    removed = 0
    for stream in (JOBS_STREAM, JOBS_DLQ_STREAM):
        start = "-"
        while True:
            entries = cast(
                list[tuple[str, dict[str, Any]]],
                await redis.xrange(stream, min=start, max="+", count=page),
            )
            if not entries:
                break
            doomed = [
                entry_id
                for entry_id, fields in entries
                if fields.get("type") not in keep_types and _payload_user_id(fields) == needle
            ]
            if doomed:
                removed += int(await redis.xdel(stream, *doomed) or 0)
            if len(entries) < page:
                break
            start = _after(entries[-1][0])
    if removed:
        logger.info("Jobs purge user_id=%s removed=%s", needle, removed)
    return removed


async def replay_dlq(redis: Redis, *, count: int = 50, delete: bool = True) -> int:
    """Re-enqueue up to `count` DLQ entries back onto the jobs stream.

    Returns the number of entries replayed. When ``delete`` is True (default),
    replayed entries are trimmed from the DLQ so they aren't replayed twice.
    """
    entries = await list_dlq(redis, count=count)
    replayed = 0
    for entry in entries:
        job_type = entry.get("type") or ""
        if not job_type:
            continue
        try:
            fields: dict[str, str] = {
                "type": job_type,
                "payload": str(entry.get("payload", "{}")),
            }
            dedupe_key = entry.get("dedupe_key") or ""
            if dedupe_key:
                fields["dedupe_key"] = str(dedupe_key)
            # Same hard ceiling as enqueue: the soft cap here would trim
            # queued and pending work whenever a backlog exists.
            await append_entry(redis, fields)
            if delete:
                await redis.xdel(JOBS_DLQ_STREAM, entry["id"])
            replayed += 1
        except Exception:
            logger.exception("Failed to replay DLQ entry id=%s", entry.get("id"))
    return replayed


async def replay_safe_dlq_entries(redis: Redis, *, now: float | None = None) -> int:
    """Re-enqueue dead letters of types safe to run again, at most hourly and boundedly.

    Documents uploaded, emails sent and storage swept during an outage stayed lost unless
    someone replayed the DLQ by hand. Each entry is replayed at most ``_MAX_AUTO_REPLAYS``
    times and only after it has sat an hour, so a dependency that stays down cannot loop.
    """
    try:
        if not await redis.set(_AUTO_REPLAY_LOCK_KEY, "1", ex=_AUTO_REPLAY_INTERVAL_S, nx=True):
            return 0
    except Exception:
        logger.debug("DLQ auto-replay lock unavailable", exc_info=True)
        return 0
    cutoff_ms = int(((now if now is not None else time.time()) - _AUTO_REPLAY_MIN_AGE_S) * 1000)
    replayed = 0
    for entry in reversed(await list_dlq(redis, count=_DLQ_MAXLEN)):
        if replayed >= _AUTO_REPLAY_BATCH:
            break
        if entry.get("type") not in _AUTO_REPLAY_TYPES:
            continue
        if int(str(entry["id"]).partition("-")[0] or 0) > cutoff_ms:
            continue
        try:
            replays = int(entry.get("replays") or 0)
        except (TypeError, ValueError):
            replays = 0
        if replays >= _MAX_AUTO_REPLAYS:
            continue
        fields: dict[str, str] = {
            "type": str(entry["type"]),
            "payload": str(entry.get("payload", "{}")),
            "replays": str(replays + 1),
        }
        if entry.get("dedupe_key"):
            fields["dedupe_key"] = str(entry["dedupe_key"])
        try:
            await append_entry(redis, fields)
            await redis.xdel(JOBS_DLQ_STREAM, entry["id"])
            replayed += 1
        except Exception:
            logger.warning("DLQ auto-replay failed id=%s", entry.get("id"), exc_info=True)
    if replayed:
        logger.info("DLQ auto-replay re-enqueued count=%s", replayed)
    return replayed
