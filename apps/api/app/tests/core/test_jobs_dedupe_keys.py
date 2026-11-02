"""Jobs that had no dedupe key get one per enqueue.

With two workers, a peer reclaims an entry idle over 60s. An entry with no
dedupe key had no claim, so the peer ran it again while the first run was
still going (two memory history scans, two consolidations, two title calls),
and each reclaim counted a delivery until the entry went to the DLQ as poison.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core import jobs
from app.core.config import Settings
from app.core.jobs import queue, worker
from app.modules.memory import enqueue_policy, history_scan


@pytest.fixture(autouse=True)
def _restore_handlers():
    with patch.dict(queue._HANDLERS):
        yield


def _user() -> Any:
    """Stands in for the ORM row: only the fields the enqueue reads."""
    return SimpleNamespace(id=uuid4(), memory_enabled=True, memory_history_scanned_at=None)


def test_unique_dedupe_key_names_the_job_and_differs_per_enqueue() -> None:
    first, second = jobs.unique_dedupe_key("scan:u1"), jobs.unique_dedupe_key("scan:u1")
    assert first.startswith("scan:u1:") and second.startswith("scan:u1:")
    assert first != second


async def test_history_scan_enqueue_carries_a_dedupe_key(fake_redis: Any) -> None:
    user = _user()
    enqueue = AsyncMock()
    with patch("app.modules.memory.history_scan.jobs.enqueue", enqueue):
        assert await history_scan.request_history_scan(fake_redis, user)
    assert enqueue.await_args is not None
    key = enqueue.await_args.kwargs["dedupe_key"]
    assert key.startswith(f"memory_history_scan:{user.id}:")


async def test_consolidation_enqueue_carries_a_dedupe_key(fake_redis: Any) -> None:
    user = _user()
    enqueue = AsyncMock()
    with (
        patch("app.modules.memory.enqueue_policy.jobs.enqueue", enqueue),
        patch("app.modules.memory.consolidation.facts_need_consolidation", return_value=True),
    ):
        outcome = await enqueue_policy.request_consolidation(
            fake_redis,
            user,
            [SimpleNamespace(type="fact", text="likes tea")],
            skip_if_already_queued=False,
        )
    assert outcome == "queued"
    assert enqueue.await_args is not None
    key = enqueue.await_args.kwargs["dedupe_key"]
    assert key.startswith(f"memory_consolidate:{user.id}:")


async def test_a_redelivery_waits_but_a_new_request_runs(fake_redis: Any) -> None:
    calls: list[int] = []

    async def handler(_settings: Settings, _payload: dict[str, Any]) -> None:
        calls.append(1)

    jobs.register("keyed_scan", handler)
    await worker._ensure_group(fake_redis)
    running_key = jobs.unique_dedupe_key("keyed_scan:u1")
    # A run of this entry holds its claim on another worker.
    await fake_redis.set(jobs.job_done_key(running_key), "1", ex=300)
    redelivered = await fake_redis.xadd(
        jobs.JOBS_STREAM,
        {"type": "keyed_scan", "payload": json.dumps({}), "dedupe_key": running_key},
    )
    later = await fake_redis.xadd(
        jobs.JOBS_STREAM,
        {
            "type": "keyed_scan",
            "payload": json.dumps({}),
            "dedupe_key": jobs.unique_dedupe_key("keyed_scan:u1"),
        },
    )
    batch = (await fake_redis.xreadgroup(jobs.JOBS_GROUP, "w2", {jobs.JOBS_STREAM: ">"}))[0][1]
    await worker._process_entries(fake_redis, Settings(), batch, consumer="w2")

    assert calls == [1], "only the later request ran"
    pending = await fake_redis.xpending_range(jobs.JOBS_STREAM, jobs.JOBS_GROUP, "-", "+", 10)
    assert [row["message_id"] for row in pending] == [redelivered]
    assert later != redelivered


@pytest.mark.asyncio
async def test_a_job_run_claims_marks_done_and_acks_in_three_round_trips(fake_redis: Any) -> None:
    """Each run also re-read and re-set the claim's TTL just after taking it (a GET and an
    EXPIRE), left from when one slot retried: two Redis round trips per job, three or four
    jobs a turn."""
    sent: list[str] = []
    send = fake_redis.execute_command

    async def counted(*args: Any, **kwargs: Any) -> Any:
        sent.append(str(args[0]).upper())
        return await send(*args, **kwargs)

    jobs.register("count-round-trips", AsyncMock())
    await worker._ensure_group(fake_redis)
    fields = {"type": "count-round-trips", "payload": "{}", "dedupe_key": "count:1"}
    entry = await fake_redis.xadd(jobs.JOBS_STREAM, fields)
    with patch.object(fake_redis, "execute_command", counted):
        await worker._process_one_entry(fake_redis, Settings(), entry, fields)
    assert sent == ["SET", "SET", "XACK"]
