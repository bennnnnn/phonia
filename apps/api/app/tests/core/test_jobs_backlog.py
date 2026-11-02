"""The jobs stream never drops a job no worker has run, and stays bounded.

Enqueue used to trim with MAXLEN ~10,000 whenever nothing was pending. Undelivered
entries sit at the newest end of the stream, so with no worker reading (scaled to
zero, a crash-looping release) every enqueue cut the backlog itself. Now the worker
trims only entries that were delivered and acked, and the hard ceiling on XADD
(``jobs_stream_max_len``) is the only bound while no worker reads.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.core import jobs
from app.core.config import Settings
from app.core.jobs import admin, queue, worker


@pytest.fixture(autouse=True)
def _restore_handlers():
    """Handlers registered here must not leak into later tests."""
    with patch.dict(queue._HANDLERS):
        yield


_HARD_CAP = 300
# Approximate trimming may keep up to one macro node past the cap.
_SLACK = 100


def _capped(cap: int = _HARD_CAP) -> Any:
    return patch.object(queue, "get_settings", return_value=Settings(jobs_stream_max_len=cap))


async def test_enqueue_never_drops_a_job_no_worker_has_read(fake_redis: Any) -> None:
    await worker._ensure_group(fake_redis)
    with _capped(), patch.object(queue, "_MAXLEN", 100):
        for i in range(250):
            await jobs.enqueue(fake_redis, "topic", {"chat_id": str(i)})
        await queue.trim_jobs_stream(fake_redis)
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 250
    delivered = await fake_redis.xreadgroup(
        jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1_000
    )
    assert sum(len(batch) for _stream, batch in delivered) == 250


async def test_the_stream_stays_under_its_hard_ceiling(fake_redis: Any) -> None:
    await worker._ensure_group(fake_redis)
    with _capped(), patch.object(queue, "_MAXLEN", 100):
        for i in range(1_000):
            await jobs.enqueue(fake_redis, "topic", {"chat_id": str(i)})
    assert await fake_redis.xlen(jobs.JOBS_STREAM) <= _HARD_CAP + _SLACK


async def _delivered_and_acked(redis: Any, *, enqueued: int, read: int, acked: int) -> list[str]:
    await worker._ensure_group(redis)
    for i in range(enqueued):
        await jobs.enqueue(redis, "topic", {"chat_id": str(i)})
    resp = await redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=read)
    ids = [entry_id for _stream, batch in resp for entry_id, _fields in batch]
    if acked:
        await redis.xack(jobs.JOBS_STREAM, jobs.JOBS_GROUP, *ids[:acked])
    return ids


@pytest.mark.parametrize(
    "read, acked, floor_index",
    [
        (6, 6, 6),  # nothing pending: everything after the last delivered stays
        (6, 2, 2),  # the oldest pending entry is the floor
        (6, 0, 0),  # all six pending
    ],
)
async def test_trim_floor_keeps_pending_and_undelivered_entries(
    fake_redis: Any, read: int, acked: int, floor_index: int
) -> None:
    await _delivered_and_acked(fake_redis, enqueued=10, read=read, acked=acked)
    every = [entry_id for entry_id, _ in await fake_redis.xrange(jobs.JOBS_STREAM)]
    floor = await queue.trim_floor(fake_redis)
    assert floor is not None
    kept = [entry_id for entry_id in every if queue._id_key(entry_id) >= queue._id_key(floor)]
    assert kept == every[floor_index:]


async def test_nothing_is_trimmed_before_any_delivery(fake_redis: Any) -> None:
    await worker._ensure_group(fake_redis)
    await jobs.enqueue(fake_redis, "topic", {"chat_id": "a"})
    assert await queue.trim_floor(fake_redis) is None


async def test_replay_dlq_does_not_trim_the_backlog(fake_redis: Any) -> None:
    await worker._ensure_group(fake_redis)
    with _capped():
        for i in range(200):
            await jobs.enqueue(fake_redis, "topic", {"chat_id": str(i)})
        await fake_redis.xadd(jobs.JOBS_DLQ_STREAM, {"type": "topic", "payload": "{}"})
        await jobs.replay_dlq(fake_redis, count=10)
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 201


async def test_process_entries_acks_an_entry_trimmed_before_reclaim(fake_redis: Any) -> None:
    """XAUTOCLAIM on Redis 6.2 returns a trimmed entry as (id, None)."""
    await worker._ensure_group(fake_redis)
    calls: list[dict[str, Any]] = []

    async def handler(_settings: Settings, payload: dict[str, Any]) -> None:
        calls.append(payload)

    jobs.register("topic", handler)
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, {"type": "topic", "payload": "{}"})
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    entries: list[tuple[str, dict[str, Any] | None]] = [("0-1", None), (entry_id, None)]
    await worker._process_entries(fake_redis, Settings(), entries)
    assert calls == []
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert pending["pending"] == 0


# ── queue metrics: an unreadable queue never reads as a healthy one ─────────


async def test_queue_metrics_count_a_real_pending_backlog(fake_redis: Any) -> None:
    """redis-py parses the XPENDING summary into a dict; reading it as a list
    raised, was swallowed, and reported 0 pending forever."""
    await worker._ensure_group(fake_redis)
    for i in range(admin._PENDING_ALERT_THRESHOLD):
        await jobs.enqueue(fake_redis, "topic", {"chat_id": str(i)})
    await fake_redis.xreadgroup(
        jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=admin._PENDING_ALERT_THRESHOLD
    )
    with patch("sentry_sdk.add_breadcrumb"), patch("sentry_sdk.capture_message") as capture:
        metrics = await jobs.report_queue_metrics(fake_redis)
    assert metrics["pending_entries"] == admin._PENDING_ALERT_THRESHOLD
    assert metrics["backlog"] == 0
    assert metrics["metrics_error"] is None
    capture.assert_called_once()
    assert "pending entries" in capture.call_args.args[0]


@pytest.mark.parametrize("failing", ["xlen", "xpending"])
async def test_queue_metrics_redis_error_alerts_instead_of_reporting_zero(
    fake_redis: Any, failing: str, caplog: pytest.LogCaptureFixture
) -> None:
    await worker._ensure_group(fake_redis)
    with (
        patch.object(fake_redis, failing, side_effect=ConnectionError("redis down")),
        patch("sentry_sdk.add_breadcrumb"),
        patch("sentry_sdk.capture_message") as capture,
        caplog.at_level("WARNING", logger=admin.logger.name),
    ):
        metrics = await jobs.report_queue_metrics(fake_redis)
    assert metrics["pending_entries"] is None
    assert metrics["dlq_depth"] == (0 if failing == "xpending" else None)
    assert metrics["metrics_error"] == "ConnectionError"
    capture.assert_called_once()
    assert "unreadable" in capture.call_args.args[0]
    assert capture.call_args.kwargs.get("level") == "warning"
    assert any(r.levelname == "WARNING" for r in caplog.records)
    # The alert names the failure class, never the Redis message or address.
    assert "redis down" not in capture.call_args.args[0]
