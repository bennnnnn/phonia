"""Account delete removes the user's finished and failed jobs from the jobs streams.

Job payloads carry chat text (memory transcripts, todo transcripts, titles'
user and assistant lines). The jobs stream keeps acked entries until its cap
trims them and the DLQ keeps failed ones, so they would outlive the account.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from app.core import jobs
from app.core.jobs import admin


async def _enqueue_turn_jobs(redis: Any, user_id: str, secret: str) -> None:
    chat_id = str(uuid4())
    await jobs.enqueue(
        redis,
        "memory",
        {"user_id": user_id, "chat_id": chat_id, "transcript": f"User: my {secret}"},
        dedupe_key=f"memory:{uuid4()}",
    )
    await jobs.enqueue(
        redis,
        "topic",
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "user_message": f"plan {secret}",
            "assistant_message": f"about {secret}",
        },
    )
    await jobs.enqueue(
        redis,
        "todos",
        {"user_id": user_id, "chat_id": chat_id, "transcript": f"remind me {secret}"},
    )


async def _fail_into_dlq(redis: Any, user_id: str, secret: str) -> None:
    fields = {
        "type": "memory",
        "payload": json.dumps({"user_id": user_id, "chat_id": "c", "transcript": secret}),
        "dedupe_key": f"memory:{uuid4()}",
    }
    await admin._move_to_dlq(redis, f"{uuid4().int % 10**6}-0", fields, "boom")


async def _entries(redis: Any, stream: str) -> list[tuple[str, dict[str, str]]]:
    return [(entry_id, dict(fields)) for entry_id, fields in await redis.xrange(stream)]


@pytest.mark.asyncio
async def test_purge_user_jobs_removes_only_that_users_entries(fake_redis: Any) -> None:
    gone, kept = str(uuid4()), str(uuid4())
    for round_ in range(3):
        await _enqueue_turn_jobs(fake_redis, gone, f"gone-secret-{round_}")
        await _enqueue_turn_jobs(fake_redis, kept, f"kept-secret-{round_}")
        await _fail_into_dlq(fake_redis, gone, f"gone-dlq-{round_}")
        await _fail_into_dlq(fake_redis, kept, f"kept-dlq-{round_}")
    # A job with no user id (shape changes, admin replays) is someone else's.
    await jobs.enqueue(fake_redis, "storage_sweep_probe", {"note": "no user"})
    # The delete's own sweep is still running: it stays (its payload is the id only).
    await jobs.enqueue(fake_redis, "storage_sweep", {"user_id": gone})
    kept_before = {
        stream: [
            entry
            for entry in await _entries(fake_redis, stream)
            if gone not in entry[1].get("payload", "")
        ]
        for stream in (jobs.JOBS_STREAM, jobs.JOBS_DLQ_STREAM)
    }

    # A small batch walks both streams in several XRANGE pages.
    removed = await jobs.purge_user_jobs(
        fake_redis, gone, keep_types=frozenset({"storage_sweep"}), batch=4
    )

    assert removed == 3 * 3 + 3
    stream_left = await _entries(fake_redis, jobs.JOBS_STREAM)
    dlq_left = await _entries(fake_redis, jobs.JOBS_DLQ_STREAM)
    assert "gone-" not in json.dumps(stream_left + dlq_left)
    assert [fields["type"] for _id, fields in stream_left if gone in fields["payload"]] == [
        "storage_sweep"
    ]
    # Other users' entries are untouched: same ids, same fields, same order.
    assert [entry for entry in stream_left if entry[1]["type"] != "storage_sweep"] == [
        entry for entry in kept_before[jobs.JOBS_STREAM] if entry[1]["type"] != "storage_sweep"
    ]
    assert dlq_left == kept_before[jobs.JOBS_DLQ_STREAM]


@pytest.mark.asyncio
async def test_purge_user_jobs_handles_empty_and_missing_streams(fake_redis: Any) -> None:
    assert await jobs.purge_user_jobs(fake_redis, str(uuid4())) == 0


@pytest.mark.asyncio
async def test_storage_sweep_purges_the_users_jobs(fake_redis: Any, monkeypatch) -> None:
    from app.background import handlers
    from app.core.config import Settings
    from app.modules.attachments import lifecycle as attachment_lifecycle

    gone, kept = str(uuid4()), str(uuid4())
    await _enqueue_turn_jobs(fake_redis, gone, "gone-secret")
    await _enqueue_turn_jobs(fake_redis, kept, "kept-secret")
    await _fail_into_dlq(fake_redis, gone, "gone-dlq")

    async def _no_storage(_settings: Any, _user_id: Any) -> int:
        return 0

    monkeypatch.setattr(handlers, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(attachment_lifecycle, "sweep_user_storage", _no_storage)
    await handlers._handle_storage_sweep(Settings(), {"user_id": gone})

    text = json.dumps(
        await _entries(fake_redis, jobs.JOBS_STREAM)
        + await _entries(fake_redis, jobs.JOBS_DLQ_STREAM)
    )
    assert "gone-" not in text and gone not in text
    assert "kept-secret" in text
