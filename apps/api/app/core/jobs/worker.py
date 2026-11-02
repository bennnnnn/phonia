"""The consumer: dispatch with retries and a deadline, ack or dead-letter, reclaim, liveness."""

import asyncio
import logging
import os
import socket
import time
from functools import partial
from typing import Any, Literal, cast

from redis.asyncio import Redis

from app.core import sentry
from app.core.config import Settings
from app.core.jobs.admin import (
    _METRICS_INTERVAL_S,
    _move_to_dlq,
    replay_safe_dlq_entries,
    report_queue_metrics,
)
from app.core.jobs.dedupe import (
    _claim_dedupe,
    _dedupe_is_complete,
    _extend_dedupe,
    _give_back_delivery,
    _refresh_running_claim_loop,
    _release_dedupe,
)
from app.core.jobs.delayed import move_due
from app.core.jobs.inflight import InFlight
from app.core.jobs.outcomes import hold_unknown_type, retry_later
from app.core.jobs.pending import _ack_trimmed_entries, _drop_poison_entries, _forget_consumer
from app.core.jobs.queue import (
    JOBS_GROUP,
    JOBS_STREAM,
    JobDiscardError,
    JobSkipped,
    UnknownJobTypeError,
    _dispatch,
    done_ttl_seconds,
    trim_jobs_stream,
)
from app.core.log_context import bound_log_ids
from app.core.redis import get_jobs_redis_client

logger = logging.getLogger("app.core.jobs")

_BLOCK_MS = 5_000
_BATCH = 10
_CLAIM_IDLE_MS = 60_000
_RECLAIM_INTERVAL_S = 30.0
# Redis unreachable at boot: retry creating the group with this backoff, forever.
_GROUP_RETRY_FIRST_S = 1.0
_GROUP_RETRY_MAX_S = 30.0
# A failed stream read waits this long before the next one.
_READ_ERROR_BACKOFF_S = 2.0
# How stale the worker-loop heartbeat can get before is_worker_alive() reports
# the worker as dead even though its task hasn't crashed. The live loop never
# waits on a job (jobs run as tasks, see ``inflight``) and touches the
# heartbeat at least every _BLOCK_MS, so it goes stale only when the event
# loop itself is blocked or the loop is wedged. ``_process_entries`` (a
# reclaim without a pool, one-off drains) keeps it fresh with a ticker every
# _JOB_HEARTBEAT_TICK_S; every attempt has a deadline (``job_timeout_seconds``).
_HEARTBEAT_STALE_THRESHOLD_S = 120.0
_JOB_HEARTBEAT_TICK_S = 15.0


async def _process_one_entry(
    redis: Redis,
    settings: Settings,
    entry_id: str,
    fields: dict[str, Any],
) -> None:
    """Claim, dispatch, then ack or dead-letter a single stream entry (safe to run concurrently)."""
    with bound_log_ids(job=entry_id, job_type=fields.get("type")):
        await _process_one_entry_logged(redis, settings, entry_id, fields)


async def _process_one_entry_logged(
    redis: Redis,
    settings: Settings,
    entry_id: str,
    fields: dict[str, Any],
) -> None:
    # Per-entry (and per-attempt) so a long LLM timeout / index batch cannot
    # trip the 120s stale health check while this worker is still healthy.
    _touch_heartbeat()
    dedupe_key = fields.get("dedupe_key") or None
    if isinstance(dedupe_key, str):
        dedupe_key = dedupe_key.strip() or None
    else:
        dedupe_key = None
    should_ack = True
    owns_claim = False
    keepalive: asyncio.Task[None] | None = None
    try:
        claim = await _claim_entry(redis, entry_id, dedupe_key)
        if claim != "run":
            should_ack = claim == "done"
            if claim == "in_flight":
                await _give_back_delivery(redis, entry_id)
            return
        owns_claim = True
        if dedupe_key:
            keepalive = asyncio.create_task(_refresh_running_claim_loop(redis, dedupe_key))
        await _dispatch_with_retries(redis, settings, entry_id, fields, dedupe_key)
    except asyncio.CancelledError:
        # The worker is stopping (deploy, SIGTERM) mid-job. Leave the entry
        # pending so a live worker's reclaim runs it again; acking here
        # dropped every in-flight job on each deploy. Release only a claim
        # this run took: the key a lost SET NX found is another run's claim
        # or done marker, and deleting it let a reclaim run the job twice.
        should_ack = False
        if owns_claim:
            await _release_dedupe(redis, dedupe_key)
        raise
    finally:
        if keepalive is not None:
            keepalive.cancel()
            try:
                await keepalive
            except asyncio.CancelledError:
                pass
        if should_ack:
            # Best-effort jobs: ack after we owned the run so a poison entry
            # can't loop forever. Do not ack an in-flight duplicate — the
            # PEL entry must survive until the running TTL expires.
            await _ack_entry(redis, entry_id)


async def _claim_entry(
    redis: Redis, entry_id: str, dedupe_key: str | None
) -> Literal["run", "done", "in_flight"]:
    """Own the run, or say why not: a duplicate already done, or one still in flight."""
    if await _claim_dedupe(redis, dedupe_key):
        return "run"
    if await _dedupe_is_complete(redis, dedupe_key):
        logger.info("Skipping already-processed job id=%s dedupe_key=%s", entry_id, dedupe_key)
        return "done"
    logger.info("Skipping in-flight job id=%s dedupe_key=%s", entry_id, dedupe_key)
    return "in_flight"


async def _dispatch_with_retries(
    redis: Redis,
    settings: Settings,
    entry_id: str,
    fields: dict[str, Any],
    dedupe_key: str | None,
) -> None:
    """Run one attempt; a transient failure comes back later (``delayed``), not in this slot.

    The claim was just taken with its full TTL, and the keepalive refreshes it while the
    handler runs: refreshing it here too was two Redis round trips per job for nothing.
    """
    job_timeout = _job_timeout(settings)
    _touch_heartbeat()
    deadline = asyncio.timeout(job_timeout)
    try:
        async with deadline:
            await _dispatch(settings, fields)
        # Success — overwrite the short running claim so a later duplicate
        # enqueue skips and acks. Crash before this line leaves the running
        # TTL; reclaim must not xack until it expires (or the keepalive dies
        # with the worker).
        await _extend_dedupe(redis, dedupe_key, done_ttl_seconds(fields.get("type")))
    except JobSkipped:
        # Nothing done this time: a later request for the same job must still run.
        await _release_dedupe(redis, dedupe_key)
    except JobDiscardError as exc:
        logger.warning("Discarding job id=%s: %s", entry_id, exc)
        await _dead_letter(redis, entry_id, fields, dedupe_key, str(exc))
    except UnknownJobTypeError as exc:
        await hold_unknown_type(redis, entry_id, fields, dedupe_key, str(exc))
    except Exception as exc:
        if isinstance(exc, TimeoutError) and deadline.expired():
            # Not retried: a handler that ran out its whole deadline would
            # likely do it again, holding its slot each time.
            logger.error(
                "Job id=%s type=%s exceeded %ss; moving to DLQ",
                entry_id,
                fields.get("type"),
                job_timeout,
            )
            sentry.report_exception(f"job_timeout:{fields.get('type')}")
            error = f"timed out after {job_timeout}s"
            await _dead_letter(redis, entry_id, fields, dedupe_key, error)
            return
        await retry_later(redis, entry_id, fields, dedupe_key)


async def _dead_letter(
    redis: Redis, entry_id: str, fields: dict[str, Any], dedupe_key: str | None, error: str
) -> None:
    # Release so a future re-enqueue / DLQ replay can retry.
    await _release_dedupe(redis, dedupe_key)
    await _move_to_dlq(redis, entry_id, fields, error)


async def _ack_entry(redis: Redis, entry_id: str) -> None:
    try:
        await redis.xack(JOBS_STREAM, JOBS_GROUP, entry_id)
    except Exception:
        logger.debug("xack failed id=%s", entry_id, exc_info=True)


async def _process_entries(
    redis: Redis,
    settings: Settings,
    entries: list[tuple[str, dict[str, Any] | None]] | list[tuple[str, dict[str, Any]]],
    consumer: str | None = None,
) -> None:
    """Run a batch to the end, at most ``settings.jobs_worker_concurrency`` at once.

    The live loop does not wait like this: it submits to its own ``InFlight``
    and keeps reading. A reclaim without a pool (and the tests) use this.
    """
    if not entries:
        return
    live = await _ack_trimmed_entries(redis, cast(list[tuple[str, dict[str, Any] | None]], entries))
    if not live:
        return
    ticker = _HeartbeatTicker()
    ticker.start()
    pool = InFlight(redis, consumer or _consumer_name(), _concurrency(settings))
    try:
        _submit_all(pool, redis, settings, live)
        await pool.join()
    finally:
        await pool.close()
        ticker.stop()
        _touch_heartbeat()


def _concurrency(settings: Settings) -> int:
    return max(1, int(settings.jobs_worker_concurrency))


def _submit_all(
    pool: InFlight, redis: Redis, settings: Settings, live: list[tuple[str, dict[str, Any]]]
) -> None:
    for entry_id, fields in live:
        run = partial(_process_one_entry, redis, settings, entry_id, fields)
        pool.submit(entry_id, fields.get("type"), run)


class _HeartbeatTicker:
    """Keep the liveness heartbeat fresh while deadline-bounded jobs run.

    A loop timer rather than a sleeping task: it stops with one call (no task
    cancellation to get wrong) and only fires while the event loop is free,
    so a blocked loop still goes stale.
    """

    def __init__(self) -> None:
        self._handle: asyncio.TimerHandle | None = None

    def start(self) -> None:
        self._tick()

    def _tick(self) -> None:
        _touch_heartbeat()
        loop = asyncio.get_running_loop()
        self._handle = loop.call_later(_JOB_HEARTBEAT_TICK_S, self._tick)

    def stop(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None


def _job_timeout(settings: Settings) -> float | None:
    """Per-attempt handler deadline in seconds (None = unbounded, tests only)."""
    timeout = float(settings.job_timeout_seconds)
    return timeout if timeout > 0 else None


async def _ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(JOBS_STREAM, JOBS_GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _wait_for_group(redis: Redis) -> None:
    """Create the consumer group, retrying with backoff until Redis answers.

    Redis unreachable at boot used to end the loop for good while the process
    stayed up: Fly restarts a Machine only when its process exits, never for a
    failing health check, so jobs stopped until someone restarted the worker.
    """
    delay = _GROUP_RETRY_FIRST_S
    failures = 0
    while True:
        _touch_heartbeat()
        try:
            await _ensure_group(redis)
        except Exception:
            failures += 1
            logger.warning(
                "Jobs worker cannot reach Redis (attempt %s); retrying in %.0fs",
                failures,
                delay,
                exc_info=failures == 1,
            )
        else:
            if failures:
                logger.info("Jobs worker reached Redis after %s failed attempt(s)", failures)
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, _GROUP_RETRY_MAX_S)


def _touch_heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = time.monotonic()


async def _reclaim_pending_jobs(
    redis: Redis, settings: Settings, consumer: str, pool: InFlight | None = None
) -> None:
    """Reclaim entries left pending by a crashed/slow worker via XAUTOCLAIM.

    Called both on startup and periodically from the live loop. A crashed
    worker leaves its in-flight entries in the consumer group's pending list;
    XAUTOCLAIM transfers them to this consumer once they've been idle for
    ``_CLAIM_IDLE_MS`` (a live worker's leases keep its own entries fresher).
    With ``pool`` the entries join the live loop's jobs, up to its free room;
    without one this runs them to the end.
    """
    count = _BATCH if pool is None else min(_BATCH, pool.room())
    if count <= 0:
        return
    try:
        claimed = await redis.xautoclaim(
            JOBS_STREAM, JOBS_GROUP, consumer, min_idle_time=_CLAIM_IDLE_MS, count=count
        )
        entries = claimed[1] if len(claimed) > 1 else []
        if not entries:
            return
        entries = await _drop_poison_entries(redis, entries)
        if pool is None:
            await _process_entries(redis, settings, entries, consumer)
            return
        _submit_all(pool, redis, settings, await _ack_trimmed_entries(redis, entries))
    except Exception:
        logger.debug("xautoclaim failed", exc_info=True)


def _consumer_name() -> str:
    """Unique per container — Docker replicas all see PID 1 without hostname."""
    host = (socket.gethostname() or "host").replace(" ", "-")[:64]
    return f"worker-{host}-{os.getpid()}"


async def _worker_loop(settings: Settings) -> None:
    # Longer socket_timeout than request-path Redis — XREADGROUP blocks 5s.
    redis = get_jobs_redis_client()
    consumer = _consumer_name()
    _touch_heartbeat()
    await _wait_for_group(redis)
    pool = InFlight(redis, consumer, _concurrency(settings))
    loop = asyncio.get_running_loop()
    last_metrics_at = 0.0
    # Reclaim on startup (entries a crashed worker left pending), then on a
    # cadence, so a peer that dies mid-job has its entries picked up within
    # ~_CLAIM_IDLE_MS + _RECLAIM_INTERVAL_S instead of at the next restart.
    last_reclaim_at: float | None = None
    try:
        while True:
            _touch_heartbeat()
            now = loop.time()
            if now - last_metrics_at >= _METRICS_INTERVAL_S:
                last_metrics_at = now
                await report_queue_metrics(redis)
            if last_reclaim_at is None or now - last_reclaim_at >= _RECLAIM_INTERVAL_S:
                last_reclaim_at = now
                await _reclaim_pending_jobs(redis, settings, consumer, pool)
                await trim_jobs_stream(redis)
                await replay_safe_dlq_entries(redis)
            await _move_due_retries(redis)
            room = pool.room()
            if room <= 0:
                # Every slot is busy: wait for one rather than take entries
                # that would sit here while a peer could run them.
                await pool.wait_for_room(_BLOCK_MS / 1000)
                continue
            try:
                resp = cast(
                    list[tuple[str, list[tuple[str, dict[str, Any] | None]]]],
                    await redis.xreadgroup(
                        JOBS_GROUP,
                        consumer,
                        {JOBS_STREAM: ">"},
                        count=min(_BATCH, room),
                        block=_BLOCK_MS,
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await _back_off_after_read_error(redis, exc)
                continue
            for _stream, entries in resp or []:
                _submit_all(pool, redis, settings, await _ack_trimmed_entries(redis, entries))
    finally:
        await pool.close()
        await _forget_consumer(redis, consumer)


async def _move_due_retries(redis: Redis) -> None:
    try:
        await move_due(redis)
    except Exception:
        logger.debug("delayed jobs move failed", exc_info=True)


async def _back_off_after_read_error(redis: Redis, exc: Exception) -> None:
    """Wait out a failed XREADGROUP; recreate the group when Redis lost it.

    A Redis restart without persistence (or a flush) drops the stream and its
    group, and every later read then failed with NOGROUP while the worker
    looked idle.
    """
    logger.debug("xreadgroup failed; backing off", exc_info=True)
    await asyncio.sleep(_READ_ERROR_BACKOFF_S)
    if "NOGROUP" in str(exc):
        logger.warning("Jobs consumer group is gone; creating it again")
        try:
            await _ensure_group(redis)
        except Exception:
            logger.debug("jobs consumer group re-create failed", exc_info=True)


_worker_task: asyncio.Task[None] | None = None
_last_heartbeat: float = 0.0


def is_worker_alive() -> bool:
    """True when the job-loop background task exists, hasn't finished, and is
    still checking in.

    The worker health endpoint reports this, and ``worker_main`` exits the
    process when it turns false, because Fly restarts a Machine only when its
    process exits. A genuinely hung task never becomes done(), so we also
    track a heartbeat that `_worker_loop` refreshes on every iteration; if it
    goes stale while the task is still "running", the worker is treated as
    dead. `_last_heartbeat` being unset (0.0) means the loop hasn't had a
    chance to run its first iteration yet, which the task.done() check
    already covers correctly, so we don't flag staleness in that window.
    """
    if _worker_task is None or _worker_task.done():
        return False
    if _last_heartbeat == 0.0:
        return True
    return time.monotonic() - _last_heartbeat < _HEARTBEAT_STALE_THRESHOLD_S


async def start_worker(settings: Settings) -> None:
    global _worker_task
    if _worker_task is not None:
        return
    _worker_task = asyncio.create_task(_worker_loop(settings))


async def stop_worker() -> None:
    global _worker_task, _last_heartbeat
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
    _last_heartbeat = 0.0
