"""The consumer keeps working while a job runs, and a dead dependency never parks it.

* Redis unreachable at boot made the consumer log "staying idle" and return for
  good while the worker process stayed up (Fly restarts only on process exit).
* ``_process_entries`` awaited the whole batch, so one slow job (a memory
  history scan: twenty LLM calls) stopped every other job until it finished.
* A peer reclaims entries idle over 60s. A job running longer than that was
  run a second time (no dedupe key) and dead-lettered as poison while running.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core import jobs
from app.core.config import Settings
from app.core.jobs import inflight, queue, worker
from app.tests.fakes import redis_mock
from app.tests.waiting import wait_until


@pytest.fixture(autouse=True)
def _restore_registry():
    with patch.dict(queue._HANDLERS), patch.dict(queue._RUNNING_LIMITS):
        yield


@pytest.fixture
def polling_redis(fake_redis: Any) -> Any:
    """fakeredis does not block on XREADGROUP BLOCK; poll without starving the loop."""
    real_read = fake_redis.xreadgroup

    async def polling_read(*args: Any, block: int | None = None, **kwargs: Any) -> Any:
        await asyncio.sleep(0.01)
        return await real_read(*args, **kwargs)

    fake_redis.xreadgroup = polling_read
    return fake_redis


@pytest.fixture
def stream_clock() -> Iterator[list[int]]:
    """fakeredis's clock for stream idle times, in ms: the test moves it, nothing waits."""
    now = [1_000_000]
    with patch("fakeredis.model._stream.current_time", lambda: now[0]):
        yield now


async def _enqueue(redis: Any, job_type: str, n: int = 1) -> None:
    await redis.xadd(jobs.JOBS_STREAM, {"type": job_type, "payload": json.dumps({"n": n})})


async def _pending(redis: Any) -> int:
    return int((await redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP))["pending"])


async def _nothing_pending(redis: Any) -> bool:
    return await _pending(redis) == 0


async def test_consumer_waits_for_redis_at_boot_instead_of_idling() -> None:
    redis = redis_mock()
    redis.xgroup_create = AsyncMock(
        side_effect=[ConnectionError("down"), ConnectionError("down"), None]
    )
    redis.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    handled = asyncio.Event()
    reads: list[int] = []

    async def read(*_args: Any, **_kwargs: Any) -> Any:
        reads.append(1)
        if len(reads) == 1:
            return [(jobs.JOBS_STREAM, [("1-0", {"type": "boot", "payload": "{}"})])]
        await handled.wait()
        raise asyncio.CancelledError

    redis.xreadgroup = AsyncMock(side_effect=read)

    async def handler(_settings: Settings, _payload: dict[str, Any]) -> None:
        handled.set()

    jobs.register("boot", handler)
    with (
        patch("app.core.jobs.worker.get_jobs_redis_client", return_value=redis),
        patch.object(worker, "_GROUP_RETRY_FIRST_S", 0.0),
    ):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(worker._worker_loop(Settings()), timeout=5)

    assert redis.xgroup_create.await_count == 3
    assert handled.is_set()


async def test_consumer_recreates_a_lost_group() -> None:
    """A Redis restart without persistence drops the group: every read failed
    with NOGROUP while the worker looked idle."""
    redis = redis_mock()
    redis.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    redis.xreadgroup = AsyncMock(
        side_effect=[Exception("NOGROUP No such key 'recall:jobs'"), asyncio.CancelledError()]
    )
    with (
        patch("app.core.jobs.worker.get_jobs_redis_client", return_value=redis),
        patch.object(worker, "_READ_ERROR_BACKOFF_S", 0.0),
    ):
        with pytest.raises(asyncio.CancelledError):
            await worker._worker_loop(Settings())

    # Once at boot, once after the NOGROUP read.
    assert redis.xgroup_create.await_count == 2


async def test_a_slow_job_does_not_hold_back_the_next_one(polling_redis: Any) -> None:
    release = asyncio.Event()
    slow_started = asyncio.Event()
    done: list[str] = []

    async def slow(_settings: Settings, _payload: dict[str, Any]) -> None:
        slow_started.set()
        await release.wait()
        done.append("slow")

    async def quick(_settings: Settings, _payload: dict[str, Any]) -> None:
        done.append("quick")

    jobs.register("slow", slow)
    jobs.register("quick", quick)
    await worker._ensure_group(polling_redis)
    await _enqueue(polling_redis, "slow")
    with patch("app.core.jobs.worker.get_jobs_redis_client", return_value=polling_redis):
        await jobs.start_worker(Settings(jobs_worker_concurrency=4))
        try:
            await asyncio.wait_for(slow_started.wait(), timeout=5)
            await _enqueue(polling_redis, "quick")
            await wait_until(lambda: "quick" in done)
            assert done == ["quick"], "the quick job waited for the slow one"
            release.set()
            await wait_until(lambda: "slow" in done)
            await wait_until(lambda: _nothing_pending(polling_redis))
        finally:
            await jobs.stop_worker()


async def test_running_jobs_stay_within_the_limit(polling_redis: Any) -> None:
    release = asyncio.Event()
    running: list[int] = []
    peak: list[int] = [0]

    async def held(_settings: Settings, _payload: dict[str, Any]) -> None:
        running.append(1)
        peak[0] = max(peak[0], len(running))
        await release.wait()
        running.pop()

    # The worker waits for a free slot only when every slot is busy: from then on it
    # can take nothing more, so what it holds there is what the limit let it read.
    at_capacity = asyncio.Event()
    wait_for_room = inflight.InFlight.wait_for_room

    async def parked(pool: inflight.InFlight, at_most_s: float) -> None:
        at_capacity.set()
        await wait_for_room(pool, at_most_s)

    jobs.register("held", held)
    await worker._ensure_group(polling_redis)
    for n in range(5):
        await _enqueue(polling_redis, "held", n)
    with (
        patch("app.core.jobs.worker.get_jobs_redis_client", return_value=polling_redis),
        patch.object(inflight.InFlight, "wait_for_room", parked),
    ):
        await jobs.start_worker(Settings(jobs_worker_concurrency=2))
        try:
            await asyncio.wait_for(at_capacity.wait(), timeout=5)
            await wait_until(lambda: len(running) == 2)
            assert peak[0] == 2
            # Only what can run was read; the rest stays in the stream for a peer.
            assert await _pending(polling_redis) == 2
            release.set()
            await wait_until(lambda: not running)
            await wait_until(lambda: _nothing_pending(polling_redis))
            assert peak[0] == 2
        finally:
            await jobs.stop_worker()


async def test_a_burst_of_a_capped_type_leaves_slots_for_the_rest(polling_redis: Any) -> None:
    release = asyncio.Event()
    scans: list[int] = []
    peak_scans: list[int] = [0]
    titles: list[int] = []

    async def scan(_settings: Settings, _payload: dict[str, Any]) -> None:
        scans.append(1)
        peak_scans[0] = max(peak_scans[0], len(scans))
        await release.wait()
        scans.pop()

    async def title(_settings: Settings, _payload: dict[str, Any]) -> None:
        titles.append(1)

    jobs.register("scan", scan, max_running=1)
    jobs.register("title", title)
    await worker._ensure_group(polling_redis)
    for n in range(4):
        await _enqueue(polling_redis, "scan", n)
    await _enqueue(polling_redis, "title")
    with patch("app.core.jobs.worker.get_jobs_redis_client", return_value=polling_redis):
        await jobs.start_worker(Settings(jobs_worker_concurrency=2))
        try:
            await wait_until(lambda: titles == [1])
            assert peak_scans[0] == 1
            release.set()
            await wait_until(lambda: not scans and peak_scans[0] == 1)
            await wait_until(lambda: _nothing_pending(polling_redis))
            assert peak_scans[0] == 1
        finally:
            await jobs.stop_worker()


async def test_a_long_job_keeps_its_lease_so_no_peer_runs_it_again(
    fake_redis: Any, stream_clock: list[int]
) -> None:
    calls: list[int] = []
    release = asyncio.Event()

    async def long_job(_settings: Settings, _payload: dict[str, Any]) -> None:
        calls.append(1)
        if len(calls) == 1:  # a second (wrong) run returns at once
            await release.wait()

    jobs.register("long", long_job)
    await worker._ensure_group(fake_redis)
    await _enqueue(fake_redis, "long")
    entries = await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w1", {jobs.JOBS_STREAM: ">"}, count=1)
    pool = inflight.InFlight(fake_redis, "w1", limit=1)
    worker._submit_all(pool, fake_redis, Settings(), entries[0][1])
    await wait_until(lambda: calls == [1])

    # Long past the idle time a peer reclaims after, the lease was renewed just now.
    stream_clock[0] += 2 * worker._CLAIM_IDLE_MS
    await pool.renew_leases()
    stream_clock[0] += worker._CLAIM_IDLE_MS // 2
    await worker._reclaim_pending_jobs(fake_redis, Settings(), "peer")
    release.set()
    await pool.join()
    await pool.close()

    assert calls == [1], f"the job ran {len(calls)} times"
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 0
    assert await _pending(fake_redis) == 0


async def test_without_a_lease_a_peer_takes_the_idle_entry(
    fake_redis: Any, stream_clock: list[int]
) -> None:
    """The control for the lease test: an entry nobody renews is reclaimed."""
    calls: list[int] = []

    async def job(_settings: Settings, _payload: dict[str, Any]) -> None:
        calls.append(1)

    jobs.register("orphan", job)
    await worker._ensure_group(fake_redis)
    await _enqueue(fake_redis, "orphan")
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "dead", {jobs.JOBS_STREAM: ">"}, count=1)
    stream_clock[0] += worker._CLAIM_IDLE_MS + 1
    await worker._reclaim_pending_jobs(fake_redis, Settings(), "peer")
    assert calls == [1]


async def test_the_lease_loop_renews_held_entries_while_they_run(fake_redis: Any) -> None:
    """The renewal the lease test calls by hand runs on its own while a job is held."""
    release = asyncio.Event()

    async def held() -> None:
        await release.wait()

    renewed: list[list[Any]] = []
    real_claim = fake_redis.xclaim

    async def claim(*args: Any, **kwargs: Any) -> Any:
        renewed.append(list(args[4]))
        return await real_claim(*args, **kwargs)

    fake_redis.xclaim = claim
    pool = inflight.InFlight(fake_redis, "w1", limit=1)
    with patch.object(inflight, "LEASE_INTERVAL_S", 0.001):
        pool.submit("1-0", "x", held)
        await wait_until(lambda: len(renewed) >= 2)
        release.set()
        await pool.join()
        await pool.close()

    assert all(ids == ["1-0"] for ids in renewed)


async def test_stopping_leaves_running_jobs_pending_for_a_live_worker(
    polling_redis: Any,
) -> None:
    started = asyncio.Event()

    async def endless(_settings: Settings, _payload: dict[str, Any]) -> None:
        started.set()
        await asyncio.Event().wait()

    jobs.register("endless", endless)
    await worker._ensure_group(polling_redis)
    await polling_redis.xadd(
        jobs.JOBS_STREAM, {"type": "endless", "payload": "{}", "dedupe_key": "endless:1"}
    )
    with patch("app.core.jobs.worker.get_jobs_redis_client", return_value=polling_redis):
        await jobs.start_worker(Settings())
        await asyncio.wait_for(started.wait(), timeout=5)
        await jobs.stop_worker()

    assert await _pending(polling_redis) == 1
    assert await polling_redis.get(jobs.job_done_key("endless:1")) is None


async def test_room_counts_waiting_entries_apart_from_running_ones() -> None:
    """Entries waiting for their type's cap hold no slot: the consumer still reads."""
    queue.register("capped", AsyncMock(), max_running=1)
    pool = inflight.InFlight(AsyncMock(), "w", limit=2)
    release = asyncio.Event()

    async def held() -> None:
        await release.wait()

    assert pool.room() == 2
    for n in range(3):
        pool.submit(f"{n}-0", "capped", held)
    await asyncio.sleep(0)
    assert pool.room() == 1  # one capped job runs, two wait, one slot is free
    release.set()
    await pool.join()
    await pool.close()
    assert pool.room() == 2


async def test_a_runner_failure_is_logged_and_the_pool_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pool = inflight.InFlight(AsyncMock(), "w", limit=1)

    async def broken() -> None:
        raise RuntimeError("runner bug")

    ran: list[int] = []

    async def fine() -> None:
        ran.append(1)

    assert pool.submit("1-0", "x", broken)
    assert not pool.submit("1-0", "x", broken), "an entry already held is not run twice"
    assert pool.submit("2-0", "x", fine)
    await pool.join()
    await pool.close()
    assert ran == [1]
    assert "runner failed" in caplog.text
