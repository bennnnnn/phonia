"""Tests for the durable Redis-stream job queue."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.background import handlers as job_handlers
from app.core import jobs
from app.core.config import Settings
from app.core.jobs import admin, dedupe, delayed, queue, worker
from app.tests.fakes import FakeSessionCM, redis_mock
from app.tests.waiting import wait_until


def _patch_session():
    return patch("app.background.handlers.SessionLocal", lambda: FakeSessionCM())


@pytest.fixture(autouse=True)
def _restore_handlers():
    # Handlers registered here must not leak into later tests' registry.
    with patch.dict(queue._HANDLERS):
        yield


def test_consumer_name_includes_hostname_and_pid():
    import os

    name = worker._consumer_name()
    assert name.startswith("worker-")
    assert str(os.getpid()) in name
    # Hostname segment keeps multi-container PID-1 workers distinct.
    assert name.count("-") >= 2


# ── enqueue ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_adds_to_stream(fake_redis):
    await jobs.enqueue(fake_redis, "memory", {"a": 1})
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 1


@pytest.mark.asyncio
async def test_enqueue_swallows_errors():
    redis = redis_mock()
    redis.xadd = AsyncMock(side_effect=RuntimeError("redis down"))
    await jobs.enqueue(redis, "memory", {"a": 1})  # must not raise


@pytest.mark.asyncio
async def test_enqueue_failure_reports_to_sentry():
    """A failed enqueue must be reported to Sentry (when available) so silent
    job loss is observable — not just logged."""
    redis = redis_mock()
    redis.xadd = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("sentry_sdk.capture_exception") as capture:
        await jobs.enqueue(redis, "memory", {"a": 1})
    capture.assert_called_once()


@pytest.mark.asyncio
async def test_enqueue_failure_still_swallows_when_sentry_unavailable():
    """If sentry-sdk isn't importable, enqueue still swallows the redis error
    (the helper's internal import is guarded)."""
    redis = redis_mock()
    redis.xadd = AsyncMock(side_effect=RuntimeError("redis down"))
    import sys

    original = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = None  # make `import sentry_sdk` raise ImportError
    try:
        await jobs.enqueue(redis, "memory", {"a": 1})
    finally:
        if original is not None:
            sys.modules["sentry_sdk"] = original
        else:
            sys.modules.pop("sentry_sdk", None)


# ── is_worker_alive ───────────────────────────────────────────────────────────


def test_is_worker_alive_false_when_no_task():
    worker._worker_task = None
    assert jobs.is_worker_alive() is False


def test_is_worker_alive_true_when_task_running_and_heartbeat_fresh():
    done_mock = MagicMock()
    done_mock.done.return_value = False
    worker._worker_task = done_mock
    worker._last_heartbeat = time.monotonic()
    try:
        assert jobs.is_worker_alive() is True
    finally:
        worker._worker_task = None
        worker._last_heartbeat = 0.0


def test_is_worker_alive_true_when_task_running_and_heartbeat_never_set():
    """Before the loop's first iteration has had a chance to run, heartbeat is
    still 0.0 — that pre-first-iteration window is already covered by the
    task.done() check, so we must not flag staleness during it."""
    done_mock = MagicMock()
    done_mock.done.return_value = False
    worker._worker_task = done_mock
    worker._last_heartbeat = 0.0
    try:
        assert jobs.is_worker_alive() is True
    finally:
        worker._worker_task = None


def test_is_worker_alive_false_when_task_done():
    done_mock = MagicMock()
    done_mock.done.return_value = True
    worker._worker_task = done_mock
    worker._last_heartbeat = time.monotonic()
    try:
        assert jobs.is_worker_alive() is False
    finally:
        worker._worker_task = None
        worker._last_heartbeat = 0.0


def test_is_worker_alive_false_when_heartbeat_stale_even_if_task_running():
    """A task that's genuinely hung (e.g. a handler awaiting something that
    never resolves) never becomes done() — the heartbeat is what catches it."""
    done_mock = MagicMock()
    done_mock.done.return_value = False
    worker._worker_task = done_mock
    worker._last_heartbeat = time.monotonic() - worker._HEARTBEAT_STALE_THRESHOLD_S - 1
    try:
        assert jobs.is_worker_alive() is False
    finally:
        worker._worker_task = None
        worker._last_heartbeat = 0.0


def test_is_worker_alive_true_when_heartbeat_just_under_threshold():
    done_mock = MagicMock()
    done_mock.done.return_value = False
    worker._worker_task = done_mock
    worker._last_heartbeat = time.monotonic() - (worker._HEARTBEAT_STALE_THRESHOLD_S - 1)
    try:
        assert jobs.is_worker_alive() is True
    finally:
        worker._worker_task = None
        worker._last_heartbeat = 0.0


# ── dispatch ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_routes_to_handler():
    seen = {}

    async def handler(settings, payload):
        seen["payload"] = payload

    jobs.register("unit-test-job", handler)
    await queue._dispatch(Settings(), {"type": "unit-test-job", "payload": json.dumps({"x": 1})})
    assert seen["payload"] == {"x": 1}


@pytest.mark.asyncio
async def test_dispatch_unknown_type_raises_unknown():
    with pytest.raises(queue.UnknownJobTypeError, match="unknown job type"):
        await queue._dispatch(Settings(), {"type": "does-not-exist", "payload": "{}"})


@pytest.mark.asyncio
async def test_dispatch_bad_payload_raises_discard():
    calls = {"n": 0}

    async def handler(settings, payload):
        calls["n"] += 1

    jobs.register("bad-payload-job", handler)
    with pytest.raises(jobs.JobDiscardError, match="bad payload"):
        await queue._dispatch(Settings(), {"type": "bad-payload-job", "payload": "{not-json"})
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_an_entry_of_an_unknown_type_waits_for_a_worker_that_knows_it(fake_redis):
    """An old worker in a blue-green deploy (or after a rollback) dead-lettered new types."""
    seen = []

    async def handler(_settings, payload):
        seen.append(payload)

    await worker._ensure_group(fake_redis)
    fields = {"type": "added-next-release", "payload": json.dumps({"n": 1})}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "old", {jobs.JOBS_STREAM: ">"}, count=1)
    with patch.dict(queue._HANDLERS):
        await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
        assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 0
        assert await delayed.delayed_depth(fake_redis) == 1

        # The new release is up: the entry comes back and runs.
        jobs.register("added-next-release", handler)
        await delayed.move_due(fake_redis, now=time.time() + 3_600)
        resp = await fake_redis.xreadgroup(jobs.JOBS_GROUP, "new", {jobs.JOBS_STREAM: ">"}, count=1)
        entries = [entry for _stream, batch in resp for entry in batch]
        await worker._process_entries(fake_redis, Settings(), entries)
    assert seen == [{"n": 1}]


@pytest.mark.asyncio
async def test_an_unknown_type_is_dead_lettered_after_a_day(fake_redis):
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "never-registered",
        "payload": "{}",
        "unknown_since": str(time.time() - 2 * 86_400),
    }
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 1
    assert await delayed.delayed_depth(fake_redis) == 0


# ── handlers ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_compress_delegates():
    cid, uid = uuid4(), uuid4()
    with patch("app.background.handlers.compaction.compress_chat_history", AsyncMock()) as job:
        await job_handlers._handle_compress(Settings(), {"chat_id": str(cid), "user_id": str(uid)})
    job.assert_awaited_once()
    assert job.call_args.args[1] == cid
    assert job.call_args.kwargs["user_id"] == uid


_TOPIC_PAYLOAD = {"user_message": "hi", "assistant_message": "yo"}


@pytest.mark.asyncio
async def test_handle_topic_delegates():
    with (
        _patch_session(),
        patch(
            "app.background.handlers.chat_titles.generate_chat_title",
            AsyncMock(return_value=True),
        ) as job,
    ):
        await job_handlers._handle_topic(
            Settings(), {"chat_id": str(uuid4()), "user_id": str(uuid4()), **_TOPIC_PAYLOAD}
        )
    job.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_title_not_applied_leaves_the_topic_job_not_done():
    """The worker used to mark it done over the handler's own release of the key."""
    with (
        _patch_session(),
        patch(
            "app.background.handlers.chat_titles.generate_chat_title",
            AsyncMock(return_value=False),
        ),
        pytest.raises(jobs.JobSkipped),
    ):
        await job_handlers._handle_topic(
            Settings(), {"chat_id": str(uuid4()), "user_id": str(uuid4()), **_TOPIC_PAYLOAD}
        )


@pytest.mark.asyncio
async def test_a_skipped_job_releases_its_key_so_a_later_request_runs(fake_redis):
    async def skipped(_settings, _payload):
        raise jobs.JobSkipped("nothing to do yet")

    jobs.register("skipping-job", skipped)
    await worker._ensure_group(fake_redis)
    fields = {"type": "skipping-job", "payload": "{}", "dedupe_key": "topic:skip"}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert await fake_redis.get(jobs.job_done_key("topic:skip")) is None
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == 0


@pytest.mark.asyncio
async def test_handle_memory_delegates():
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_extraction.extract_and_store_memories", AsyncMock()
        ) as job,
    ):
        await job_handlers._handle_memory(
            Settings(),
            {"user_id": str(uuid4()), "chat_id": str(uuid4()), "transcript": "t"},
        )
    job.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_memory_retries_a_failed_model_pass_later():
    """A chat's last line ("remember I'm allergic to peanuts") has no next turn to retry it."""
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_extraction.extract_and_store_memories",
            AsyncMock(return_value="model_failed"),
        ),
        pytest.raises(RuntimeError, match="retrying"),
    ):
        await job_handlers._handle_memory(
            Settings(),
            {"user_id": str(uuid4()), "chat_id": str(uuid4()), "transcript": "t"},
        )


@pytest.mark.asyncio
async def test_handle_memory_retries_skipped_lock_with_backoff():
    payload = {
        "user_id": str(uuid4()),
        "chat_id": str(uuid4()),
        "transcript": "t",
        "assistant_message_id": str(uuid4()),
    }
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_extraction.extract_and_store_memories",
            AsyncMock(return_value="skipped_lock"),
        ),
        patch("app.background.handlers.enqueue_later", AsyncMock()) as enqueue_mock,
        patch("app.background.handlers.get_redis_client", MagicMock()),
    ):
        await job_handlers._handle_memory(Settings(), payload)

    # The retry waits in the delayed queue, not asleep in this worker slot.
    enqueue_mock.assert_awaited_once()
    assert enqueue_mock.await_args.args[2]["lock_retries"] == 1
    assert enqueue_mock.await_args.kwargs["delay_s"] >= 10
    assert enqueue_mock.await_args.kwargs["dedupe_key"].startswith(
        f"memory:{payload['assistant_message_id']}:lock1:"
    )


@pytest.mark.asyncio
async def test_handle_memory_discards_after_lock_retries():
    payload = {
        "user_id": str(uuid4()),
        "chat_id": str(uuid4()),
        "transcript": "t",
        "lock_retries": 3,
    }
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_extraction.extract_and_store_memories",
            AsyncMock(return_value="skipped_lock"),
        ),
        patch("app.background.handlers.enqueue_later", AsyncMock()) as enqueue_mock,
        pytest.raises(jobs.JobDiscardError, match="lock retries"),
    ):
        await job_handlers._handle_memory(Settings(), payload)

    enqueue_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_memory_consolidate_delegates():
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_consolidation.consolidate_user_memory_sections",
            AsyncMock(return_value=True),
        ) as job,
    ):
        await job_handlers._handle_memory_consolidate(Settings(), {"user_id": str(uuid4())})
    job.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_memory_consolidate_retries_skipped_lock_with_backoff():
    payload = {"user_id": str(uuid4())}
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_consolidation.consolidate_user_memory_sections",
            AsyncMock(return_value="skipped_lock"),
        ),
        patch("app.background.handlers.enqueue_later", AsyncMock()) as enqueue_mock,
        patch("app.background.handlers.get_redis_client", MagicMock()),
    ):
        await job_handlers._handle_memory_consolidate(Settings(), payload)

    enqueue_mock.assert_awaited_once()
    assert enqueue_mock.await_args.args[1] == "memory_consolidate"
    assert enqueue_mock.await_args.args[2]["lock_retries"] == 1
    # Unique per request: a later consolidation for this user is never skipped as done.
    assert enqueue_mock.await_args.kwargs["dedupe_key"].startswith(
        f"memory_consolidate:{payload['user_id']}:lock1:"
    )


@pytest.mark.asyncio
async def test_handle_memory_consolidate_discards_after_lock_retries():
    payload = {"user_id": str(uuid4()), "lock_retries": 3}
    with (
        _patch_session(),
        patch(
            "app.background.handlers.memory_consolidation.consolidate_user_memory_sections",
            AsyncMock(return_value="skipped_lock"),
        ),
        patch("app.background.handlers.enqueue_later", AsyncMock()) as enqueue_mock,
        pytest.raises(jobs.JobDiscardError, match="lock retries"),
    ):
        await job_handlers._handle_memory_consolidate(Settings(), payload)

    enqueue_mock.assert_not_awaited()


# ── worker ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_entries_dispatches_and_acks():
    redis = redis_mock()
    seen = []

    async def handler(settings, payload):
        seen.append(payload)

    jobs.register("proc-job", handler)
    entries = [("1-0", {"type": "proc-job", "payload": json.dumps({"k": 1})})]
    worker._last_heartbeat = 0.0
    await worker._process_entries(redis, Settings(), entries)
    assert seen == [{"k": 1}]
    assert worker._last_heartbeat > 0.0
    redis.xack.assert_awaited_once()
    redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_process_entries_failed_job_waits_for_a_later_attempt(fake_redis):
    """One failure frees the slot and schedules the next attempt; nothing is dead-lettered."""
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1
        raise RuntimeError("boom")

    jobs.register("fail-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {"type": "fail-job", "payload": "{}"}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert calls["n"] == 1
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 0
    assert await delayed.delayed_depth(fake_redis) == 1
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == 0


@pytest.mark.asyncio
async def test_a_job_failing_through_an_outage_runs_once_it_is_over(fake_redis):
    """A 30 s provider outage dead-lettered every job that started in it."""
    outage = {"over": False}
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1
        if not outage["over"]:
            raise RuntimeError("provider down")

    jobs.register("retry-then-ok", handler)
    await worker._ensure_group(fake_redis)
    await jobs.enqueue(fake_redis, "retry-then-ok", {}, dedupe_key="retry:1")
    clock = time.time()
    for _ in range(3):
        resp = await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=10)
        entries = [entry for _stream, batch in resp or [] for entry in batch]
        await worker._process_entries(fake_redis, Settings(), entries)
        clock += 3_600
        await delayed.move_due(fake_redis, now=clock)
        outage["over"] = calls["n"] >= 2
    assert calls["n"] == 3
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 0
    assert await fake_redis.get(jobs.job_done_key("retry:1")) == dedupe._DEDUPE_DONE


@pytest.mark.asyncio
async def test_the_last_attempt_goes_to_the_dlq(fake_redis):
    async def handler(_settings, _payload):
        raise RuntimeError("still down")

    jobs.register("spent-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {"type": "spent-job", "payload": "{}", "attempt": str(delayed.MAX_ATTEMPTS)}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=1)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 1
    assert await delayed.delayed_depth(fake_redis) == 0


@pytest.mark.asyncio
async def test_process_entries_runs_batch_concurrently():
    """A batch of slow jobs must overlap — not drain strictly sequentially."""
    redis = redis_mock()
    started: list[int] = []
    release = asyncio.Event()

    async def handler(_settings, payload):
        started.append(int(payload["i"]))
        await release.wait()

    jobs.register("parallel-job", handler)
    entries = [
        (f"{i}-0", {"type": "parallel-job", "payload": json.dumps({"i": i})}) for i in range(5)
    ]
    task = asyncio.create_task(
        worker._process_entries(redis, Settings(jobs_worker_concurrency=8), entries)
    )
    for _ in range(100):
        if len(started) == 5:
            break
        await asyncio.sleep(0.01)
    assert sorted(started) == [0, 1, 2, 3, 4]
    release.set()
    await task
    assert redis.xack.await_count == 5


# ── DLQ inspection / replay ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_and_replay_dlq_roundtrip(fake_redis):
    # Seed a failed job into the DLQ directly.
    await fake_redis.xadd(
        jobs.JOBS_DLQ_STREAM,
        {
            "original_id": "9-0",
            "type": "memory",
            "payload": json.dumps({"user_id": "u", "chat_id": "c", "transcript": "t"}),
            "error": "RuntimeError: boom",
            "failed_at": "2026-07-02T00:00:00+00:00",
        },
    )

    listed = await jobs.list_dlq(fake_redis, count=10)
    assert len(listed) == 1
    assert listed[0]["type"] == "memory"
    assert "boom" in listed[0]["error"]

    # Replay moves it back onto the jobs stream and removes it from the DLQ.
    replayed = await jobs.replay_dlq(fake_redis, count=10, delete=True)
    assert replayed == 1
    assert await fake_redis.xlen(jobs.JOBS_STREAM) == 1
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 0

    # The replayed entry preserves type + payload.
    main_entries = await fake_redis.xrange(jobs.JOBS_STREAM)
    assert main_entries[0][1]["type"] == "memory"
    assert json.loads(main_entries[0][1]["payload"])["transcript"] == "t"


@pytest.mark.asyncio
async def test_worker_loop_processes_then_cancels():
    redis = redis_mock()
    redis.xgroup_create = AsyncMock()
    redis.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    batch = [(jobs.JOBS_STREAM, [("1-0", {"type": "wl-job", "payload": "{}"})])]
    handled = asyncio.Event()
    reads = []

    async def read_then_stop(*_args, **_kwargs):
        # The loop reads again while the job runs; stop once it has run.
        reads.append(1)
        if len(reads) == 1:
            return batch
        await handled.wait()
        raise asyncio.CancelledError

    redis.xreadgroup = AsyncMock(side_effect=read_then_stop)
    redis.xack = AsyncMock()

    seen = []

    async def handler(settings, payload):
        seen.append(payload)
        handled.set()

    jobs.register("wl-job", handler)

    with patch("app.core.jobs.worker.get_jobs_redis_client", return_value=redis):
        with pytest.raises(asyncio.CancelledError):
            await worker._worker_loop(Settings())

    assert seen == [{}]


@pytest.mark.asyncio
async def test_start_and_stop_worker():
    with patch("app.core.jobs.worker._worker_loop", AsyncMock()):
        await jobs.start_worker(Settings())
        await jobs.stop_worker()
    assert worker._worker_task is None


async def _group_pending_is(redis, count: int) -> bool:
    return int((await redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP))["pending"]) == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owns_pending_entry, consumers_left",
    [
        (False, 0),  # clean stop: nothing of ours is pending
        (True, 1),  # deleting it would drop the entry XAUTOCLAIM still needs
    ],
)
async def test_stopped_worker_removes_its_consumer_from_the_group(
    fake_redis, monkeypatch, owns_pending_entry, consumers_left
):
    """Consumers are named per process (host + pid), so every restart, deploy
    and `--reload` added one to the group and nothing ever removed it."""
    processed = asyncio.Event()

    async def handler(settings, payload):
        processed.set()

    monkeypatch.setitem(queue._HANDLERS, "consumer-cleanup", handler)
    await fake_redis.xgroup_create(jobs.JOBS_STREAM, jobs.JOBS_GROUP, id="0", mkstream=True)
    if owns_pending_entry:
        # Delivered to this process earlier and never acked (crash mid-job).
        await fake_redis.xadd(jobs.JOBS_STREAM, {"type": "consumer-cleanup", "payload": "{}"})
        await fake_redis.xreadgroup(
            jobs.JOBS_GROUP, worker._consumer_name(), {jobs.JOBS_STREAM: ">"}, count=1
        )
    await fake_redis.xadd(jobs.JOBS_STREAM, {"type": "consumer-cleanup", "payload": "{}"})

    # fakeredis does not block on XREADGROUP BLOCK; poll without starving the loop.
    real_read = fake_redis.xreadgroup

    async def polling_read(*args, block=None, **kwargs):
        await asyncio.sleep(0.01)
        return await real_read(*args, **kwargs)

    fake_redis.xreadgroup = polling_read

    with patch("app.core.jobs.worker.get_jobs_redis_client", return_value=fake_redis):
        await jobs.start_worker(Settings(jobs_worker_concurrency=1))
        await asyncio.wait_for(processed.wait(), timeout=5)
        # The new entry is acked; one delivered earlier and never acked stays ours.
        await wait_until(lambda: _group_pending_is(fake_redis, int(owns_pending_entry)))
        await jobs.stop_worker()

    consumers = await fake_redis.xinfo_consumers(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert len(consumers) == consumers_left
    if owns_pending_entry:
        assert consumers[0]["pending"] == 1


# ── queue metrics / observability ────────────────────────────────────────────


def _metrics(**overrides):
    metrics = {
        "dlq_depth": 0,
        "pending_entries": 0,
        "backlog": 0,
        "oldest_undelivered_age_s": None,
        "delayed": 0,
        "stream_length": 0,
        "metrics_error": None,
    }
    metrics.update(overrides)
    return metrics


@pytest.mark.asyncio
async def test_collect_queue_metrics_empty(fake_redis):
    await worker._ensure_group(fake_redis)
    metrics = await admin.collect_queue_metrics(fake_redis)
    assert metrics == _metrics()


@pytest.mark.asyncio
async def test_collect_queue_metrics_counts_dlq_depth(fake_redis):
    await worker._ensure_group(fake_redis)
    await fake_redis.xadd(jobs.JOBS_DLQ_STREAM, {"type": "memory", "error": "x"})
    await fake_redis.xadd(jobs.JOBS_DLQ_STREAM, {"type": "topic", "error": "y"})
    await fake_redis.xadd(jobs.JOBS_DLQ_STREAM, {"type": "todos", "error": "z"})
    metrics = await admin.collect_queue_metrics(fake_redis)
    assert metrics["dlq_depth"] == 3


@pytest.mark.asyncio
async def test_collect_queue_metrics_sees_a_backlog_no_worker_has_read(fake_redis):
    """The pending count could not see a backlog: a worker holds only what it runs."""
    await worker._ensure_group(fake_redis)
    for i in range(30):
        await jobs.enqueue(fake_redis, "topic", {"chat_id": str(i)})
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w", {jobs.JOBS_STREAM: ">"}, count=5)
    metrics = await admin.collect_queue_metrics(fake_redis)
    assert metrics["backlog"] == 25
    assert metrics["pending_entries"] == 5
    assert metrics["oldest_undelivered_age_s"] is not None


@pytest.mark.asyncio
async def test_collect_queue_metrics_redis_error_is_unknown_not_zero():
    """Never raises into the worker loop, but a count it could not read is None."""
    redis = redis_mock()
    redis.xlen = AsyncMock(side_effect=RuntimeError("redis down"))
    redis.xpending = AsyncMock(side_effect=RuntimeError("redis down"))
    metrics = await admin.collect_queue_metrics(redis)
    assert metrics == _metrics(
        dlq_depth=None,
        pending_entries=None,
        backlog=None,
        delayed=None,
        stream_length=None,
        metrics_error="RuntimeError",
    )


@pytest.mark.asyncio
async def test_report_queue_metrics_warns_when_the_dlq_grows(fake_redis):
    """Growth, not depth: the depth alerted every 5 minutes forever after one blip."""
    await worker._ensure_group(fake_redis)
    with patch("sentry_sdk.add_breadcrumb"), patch("sentry_sdk.capture_message") as capture:
        await jobs.report_queue_metrics(fake_redis)
        for _ in range(admin._DLQ_GROWTH_ALERT):
            await fake_redis.xadd(jobs.JOBS_DLQ_STREAM, {"type": "memory", "error": "x"})
        await fake_redis.delete(admin._METRICS_LOCK_KEY)
        await jobs.report_queue_metrics(fake_redis)
        assert capture.call_count == 1
        assert "DLQ grew" in capture.call_args.args[0]
        assert capture.call_args.kwargs.get("level") == "warning"

        # The same depth next time is quiet.
        await fake_redis.delete(admin._METRICS_LOCK_KEY)
        await jobs.report_queue_metrics(fake_redis)
        assert capture.call_count == 1


@pytest.mark.asyncio
async def test_only_one_worker_reports_per_interval(fake_redis):
    await worker._ensure_group(fake_redis)
    with (
        patch("sentry_sdk.add_breadcrumb") as breadcrumb,
        patch("sentry_sdk.capture_message"),
    ):
        await jobs.report_queue_metrics(fake_redis)
        await jobs.report_queue_metrics(fake_redis)
    breadcrumb.assert_called_once()


@pytest.mark.asyncio
async def test_report_queue_metrics_warns_when_pending_exceeds_threshold():
    redis = redis_mock()
    with (
        patch.object(
            admin,
            "collect_queue_metrics",
            AsyncMock(return_value=_metrics(pending_entries=admin._PENDING_ALERT_THRESHOLD)),
        ),
        patch("sentry_sdk.add_breadcrumb"),
        patch("sentry_sdk.capture_message") as capture,
    ):
        await jobs.report_queue_metrics(redis)

    capture.assert_called_once()
    assert "pending entries" in capture.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides, words",
    [
        ({"backlog": 1_000}, "backlog"),
        ({"oldest_undelivered_age_s": 900.0}, "Oldest undelivered"),
        ({"stream_length": 49_000}, "cap"),
    ],
)
async def test_report_queue_metrics_warns_on_a_backlog(overrides, words):
    with (
        patch.object(admin, "collect_queue_metrics", AsyncMock(return_value=_metrics(**overrides))),
        patch.object(admin, "hard_maxlen", return_value=50_000),
        patch("sentry_sdk.add_breadcrumb"),
        patch("sentry_sdk.capture_message") as capture,
    ):
        await jobs.report_queue_metrics(AsyncMock())
    capture.assert_called_once()
    assert words in capture.call_args.args[0]


@pytest.mark.asyncio
async def test_report_queue_metrics_quiet_below_thresholds():
    redis = redis_mock()
    with (
        patch.object(
            admin,
            "collect_queue_metrics",
            AsyncMock(return_value=_metrics(pending_entries=admin._PENDING_ALERT_THRESHOLD - 1)),
        ),
        patch("sentry_sdk.add_breadcrumb") as breadcrumb,
        patch("sentry_sdk.capture_message") as capture,
    ):
        await jobs.report_queue_metrics(redis)

    # Breadcrumb still records the periodic status, but no warning is captured.
    breadcrumb.assert_called_once()
    capture.assert_not_called()


@pytest.mark.asyncio
async def test_report_queue_metrics_noop_without_sentry():
    """If sentry-sdk isn't importable, report_queue_metrics still returns the
    metrics and never raises into the worker loop."""
    redis = redis_mock()
    import sys

    original = sys.modules.get("sentry_sdk")
    sys.modules["sentry_sdk"] = None
    try:
        with patch.object(
            admin, "collect_queue_metrics", AsyncMock(return_value=_metrics(dlq_depth=40))
        ):
            metrics = await jobs.report_queue_metrics(redis)
    finally:
        if original is not None:
            sys.modules["sentry_sdk"] = original
        else:
            sys.modules.pop("sentry_sdk", None)
    assert metrics["dlq_depth"] == 40


# ── periodic reclaim ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reclaim_pending_jobs_processes_claimed_entries():
    """_reclaim_pending_jobs must process entries returned by XAUTOCLAIM,
    so a crashed worker's stuck entries are picked up by a live peer."""
    redis = redis_mock()
    claimed_entries = [("1-0", {"type": "reclaim-job", "payload": "{}"})]
    redis.xautoclaim = AsyncMock(return_value=("0-0", claimed_entries, []))
    redis.xack = AsyncMock()

    seen = []

    async def handler(settings, payload):
        seen.append(payload)

    jobs.register("reclaim-job", handler)

    # _reclaim_pending_jobs takes redis as an argument; it never resolved a
    # client itself, so the old get_redis_client patch here was a no-op.
    await worker._reclaim_pending_jobs(redis, Settings(), "worker-test")

    assert seen == [{}]
    redis.xautoclaim.assert_awaited_once()


@pytest.mark.asyncio
async def test_reclaim_pending_jobs_swallows_xautoclaim_errors():
    """A Redis error during reclaim must not crash the worker loop."""
    redis = redis_mock()
    redis.xautoclaim = AsyncMock(side_effect=Exception("redis down"))

    # Must not raise.
    await worker._reclaim_pending_jobs(redis, Settings(), "worker-test")

    redis.xautoclaim.assert_awaited_once()


# ── job idempotency (dedupe_key) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_stores_dedupe_key(fake_redis):
    await jobs.enqueue(fake_redis, "memory", {"a": 1}, dedupe_key="mem:1")
    _id, fields = (await fake_redis.xrange(jobs.JOBS_STREAM))[0]
    assert fields["dedupe_key"] == "mem:1"


@pytest.mark.asyncio
async def test_process_entries_skips_duplicate_dedupe_key(fake_redis):
    """Redelivery / duplicate enqueue with the same dedupe_key must not re-run."""
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1

    jobs.register("dedupe-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "dedupe-job",
        "payload": "{}",
        "dedupe_key": "todosync:chat:msg1",
    }
    entry_a = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    entry_b = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await worker._process_entries(
        fake_redis,
        Settings(),
        [(entry_a, fields), (entry_b, dict(fields))],
    )
    assert calls["n"] == 1
    assert await fake_redis.get(jobs.job_done_key("todosync:chat:msg1")) == dedupe._DEDUPE_DONE


@pytest.mark.asyncio
async def test_process_entries_releases_dedupe_after_permanent_failure(fake_redis):
    """A exhausted retry must clear the claim so DLQ replay can run again."""

    async def handler(_settings, _payload):
        raise RuntimeError("boom")

    jobs.register("dedupe-fail-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "dedupe-fail-job",
        "payload": "{}",
        "dedupe_key": "welcome:user-1",
        "attempt": str(delayed.MAX_ATTEMPTS),
    }
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert await fake_redis.get(jobs.job_done_key("welcome:user-1")) is None
    assert await fake_redis.xlen(jobs.JOBS_DLQ_STREAM) == 1


@pytest.mark.asyncio
async def test_process_entries_claims_with_short_ttl_then_extends_on_success(fake_redis):
    """M2: dedupe claim uses a short TTL so a crash mid-handler lets the
    reclaim re-run; on success the TTL is extended to the full window."""
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1

    jobs.register("dedupe-ttl-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "dedupe-ttl-job",
        "payload": "{}",
        "dedupe_key": "ttl:test",
    }
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert calls["n"] == 1
    ttl = await fake_redis.ttl(jobs.job_done_key("ttl:test"))
    # Success overwrites the running claim with the 24h done marker.
    assert await fake_redis.get(jobs.job_done_key("ttl:test")) == dedupe._DEDUPE_DONE
    assert ttl > dedupe._JOB_DONE_CLAIM_TTL_SECONDS


def _pending_count(summary: object) -> int:
    if isinstance(summary, dict):
        return int(summary.get("pending") or summary.get("count") or 0)
    if isinstance(summary, list | tuple) and summary:
        return int(summary[0] or 0)
    return 0


@pytest.mark.asyncio
async def test_process_entries_inflight_claim_does_not_ack(fake_redis):
    """A reclaim that loses NX while the running TTL is still held must leave
    the PEL entry so a later reclaim can run after the crashed worker's key
    expires — not skip+xack (which dropped the job forever)."""
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1

    jobs.register("inflight-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "inflight-job",
        "payload": "{}",
        "dedupe_key": "attach:index:1",
    }
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "tester", {jobs.JOBS_STREAM: ">"}, count=1)
    await fake_redis.set(
        jobs.job_done_key("attach:index:1"),
        dedupe._DEDUPE_RUNNING,
        ex=dedupe._JOB_DONE_CLAIM_TTL_SECONDS,
    )
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert calls["n"] == 0
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == 1


@pytest.mark.asyncio
async def test_process_entries_done_claim_skips_and_acks(fake_redis):
    """A duplicate enqueue after success must skip the handler and ack."""
    calls = {"n": 0}

    async def handler(_settings, _payload):
        calls["n"] += 1

    jobs.register("done-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {
        "type": "done-job",
        "payload": "{}",
        "dedupe_key": "attach:index:2",
    }
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "tester", {jobs.JOBS_STREAM: ">"}, count=1)
    await fake_redis.set(
        jobs.job_done_key("attach:index:2"),
        dedupe._DEDUPE_DONE,
        ex=queue.DEFAULT_DONE_TTL_SECONDS,
    )
    await worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    assert calls["n"] == 0
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == 0


@pytest.mark.asyncio
async def test_process_entries_cancelled_job_stays_pending(fake_redis):
    """A worker stopped mid-job (deploy, SIGTERM) must not ack the entry:
    it stays pending, and its running claim is released, so a live worker's
    reclaim runs it again instead of the job being dropped."""
    started = asyncio.Event()

    async def handler(_settings, _payload):
        started.set()
        await asyncio.sleep(3600)

    jobs.register("shutdown-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {"type": "shutdown-job", "payload": "{}", "dedupe_key": "memory:1"}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "tester", {jobs.JOBS_STREAM: ">"}, count=1)

    task = asyncio.create_task(
        worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == 1
    assert await fake_redis.get(jobs.job_done_key("memory:1")) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "held, ttl, pending_after_reclaim",
    [
        # Another worker is running the job: the entry waits for that run.
        (dedupe._DEDUPE_RUNNING, dedupe._JOB_DONE_CLAIM_TTL_SECONDS, 1),
        # Another worker finished it: the duplicate is acked.
        (dedupe._DEDUPE_DONE, queue.DEFAULT_DONE_TTL_SECONDS, 0),
    ],
)
async def test_cancel_after_losing_the_claim_keeps_the_other_runs_key(
    fake_redis, held, ttl, pending_after_reclaim
):
    """A worker stopped while it reads why it lost the claim must not release
    the claim: it never owned it. Deleting another run's key (or the done
    marker) let the next reclaim win SET NX and run the job a second time."""
    calls = []

    async def handler(_settings, _payload):
        calls.append(1)

    jobs.register("lost-claim-job", handler)
    await worker._ensure_group(fake_redis)
    fields = {"type": "lost-claim-job", "payload": "{}", "dedupe_key": "memory:2"}
    entry_id = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w2", {jobs.JOBS_STREAM: ">"}, count=1)
    key = jobs.job_done_key("memory:2")
    await fake_redis.set(key, held, ex=ttl)

    reading = asyncio.Event()

    async def stalled_get(_name):
        # The state read after a lost SET NX is in flight when the deploy cancels.
        reading.set()
        await asyncio.Event().wait()

    with patch.object(fake_redis, "get", stalled_get):
        task = asyncio.create_task(
            worker._process_entries(fake_redis, Settings(), [(entry_id, fields)])
        )
        await reading.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    after_cancel = await fake_redis.get(key)
    with patch.object(worker, "_CLAIM_IDLE_MS", 0):
        await worker._reclaim_pending_jobs(fake_redis, Settings(), "w3")
    assert after_cancel == held, f"claim key after the cancel: {after_cancel!r}"
    assert calls == [], f"the reclaim ran the job {len(calls)} more time(s)"
    pending = await fake_redis.xpending(jobs.JOBS_STREAM, jobs.JOBS_GROUP)
    assert _pending_count(pending) == pending_after_reclaim
