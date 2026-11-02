"""Jobs that wait, markers that expire by type, and dead letters that come back."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from app.core import jobs
from app.core.config import Settings
from app.core.jobs import admin, delayed, queue, worker
from app.core.redis_counters import hincr_with_ttl, incr_with_ttl


@pytest.fixture(autouse=True)
def _restore_handlers():
    with patch.dict(queue._HANDLERS), patch.dict(queue._DONE_TTLS):
        yield


def test_retries_back_off_to_about_fifty_minutes_in_all():
    exact = [delayed.retry_delay_s(attempt, lambda: 0.5) for attempt in range(2, 7)]
    assert exact == [15.0, 60.0, 240.0, 960.0, 1_800.0]
    assert 2_900 < sum(exact) < 3_200
    assert delayed.retry_delay_s(2, lambda: 0.0) == pytest.approx(12.0)
    assert delayed.retry_delay_s(2, lambda: 1.0) == pytest.approx(18.0)


@pytest.mark.wall_clock
async def test_two_workers_moving_at_once_re_add_an_entry_once(fake_redis: Any) -> None:
    await delayed.schedule(fake_redis, {"type": "t", "payload": "{}"}, delay_s=0)
    moved = await asyncio.gather(
        delayed.move_due(fake_redis, now=time.time() + 1),
        delayed.move_due(fake_redis, now=time.time() + 1),
    )
    assert sum(moved) == 1
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 1


@pytest.mark.wall_clock
async def test_an_entry_waits_until_it_is_due(fake_redis: Any) -> None:
    now = time.time()
    await delayed.schedule(fake_redis, {"type": "t", "payload": "{}"}, delay_s=60, now=now)
    assert await delayed.move_due(fake_redis, now=now + 30) == 0
    assert await delayed.move_due(fake_redis, now=now + 61) == 1


async def test_enqueue_later_runs_the_job_after_its_wait(fake_redis: Any) -> None:
    await jobs.enqueue_later(fake_redis, "t", {"a": 1}, delay_s=5, dedupe_key="k:1")
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 0
    await delayed.move_due(fake_redis, now=time.time() + 10)
    _id, fields = (await fake_redis.xrange(jobs.JOBS_STREAM))[0]
    assert json.loads(fields["payload"]) == {"a": 1}
    assert fields["dedupe_key"] == "k:1"


@pytest.mark.parametrize(
    "job_type, done_ttl, expected_max",
    [
        ("message_index", None, queue.DEFAULT_DONE_TTL_SECONDS),
        ("transactional_email", 86_400, 86_400),
    ],
)
async def test_a_done_marker_lives_as_long_as_its_type_needs(
    fake_redis: Any, job_type: str, done_ttl: int | None, expected_max: int
) -> None:
    """Every marker lived a day: millions of keys at scale, walked by every account delete."""

    async def handler(_settings: Settings, _payload: dict[str, Any]) -> None:
        return None

    jobs.register(job_type, handler, done_ttl_seconds=done_ttl)
    await worker._ensure_group(fake_redis)
    fields = {"type": job_type, "payload": "{}", "dedupe_key": f"{job_type}:1"}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    ttl = await fake_redis.ttl(jobs.job_done_key(f"{job_type}:1"))
    assert expected_max - 5 <= ttl <= expected_max


async def _dead_letter(redis: Any, job_type: str, *, age_s: float, replays: int = 0) -> None:
    fields = {"type": job_type, "payload": json.dumps({"user_id": "u"}), "error": "down"}
    if replays:
        fields["replays"] = str(replays)
    ms = int((time.time() - age_s) * 1000)
    await redis.xadd(jobs.JOBS_DLQ_STREAM, fields, id=f"{ms}-0")


async def test_safe_dead_letters_come_back_by_themselves(fake_redis: Any) -> None:
    """Uploads, emails and sweeps from an outage stayed lost unless someone replayed by hand."""
    await _dead_letter(fake_redis, "memory", age_s=7_400)  # not safe to run twice
    await _dead_letter(fake_redis, "transactional_email", age_s=7_300, replays=3)  # spent
    await _dead_letter(fake_redis, "attachment_index", age_s=7_200)
    await _dead_letter(fake_redis, "storage_sweep", age_s=60)  # too fresh
    assert await admin.replay_safe_dlq_entries(fake_redis) == 1
    _id, fields = (await fake_redis.xrange(jobs.JOBS_STREAM))[0]
    assert fields["type"] == "attachment_index"
    assert fields["replays"] == "1"
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 3


async def test_auto_replay_runs_from_one_worker_an_hour_and_in_batches(fake_redis: Any) -> None:
    await _dead_letter(fake_redis, "storage_sweep", age_s=7_300)
    await _dead_letter(fake_redis, "storage_sweep", age_s=7_200)
    with patch.object(admin, "_AUTO_REPLAY_BATCH", 1):
        assert await admin.replay_safe_dlq_entries(fake_redis) == 1
        assert await admin.replay_safe_dlq_entries(fake_redis) == 0  # the hour's lock
        await fake_redis.delete(admin._AUTO_REPLAY_LOCK_KEY)
        assert await admin.replay_safe_dlq_entries(fake_redis) == 1


async def test_old_dead_letters_age_out(fake_redis: Any) -> None:
    await _dead_letter(fake_redis, "memory", age_s=8 * 86_400)
    await _dead_letter(fake_redis, "memory", age_s=86_400)
    with patch("sentry_sdk.add_breadcrumb"), patch("sentry_sdk.capture_message"):
        await worker._ensure_group(fake_redis)
        await jobs.report_queue_metrics(fake_redis)
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 1


async def test_a_counter_gets_its_expiry_in_the_same_transaction(fake_redis: Any) -> None:
    """A crash between INCRBY and EXPIRE left a dated key with no TTL, forever."""
    assert await incr_with_ttl(fake_redis, "c", 5, 100) == 5
    await fake_redis.expire("c", 50)
    assert await incr_with_ttl(fake_redis, "c", 1, 100) == 6
    # NX: a later increment never pushes the day's expiry out.
    assert 0 < await fake_redis.ttl("c") <= 50
    assert await hincr_with_ttl(fake_redis, "h", "f", 2, 100) == 2
    assert 0 < await fake_redis.ttl("h") <= 100
