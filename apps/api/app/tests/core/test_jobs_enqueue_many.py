"""A finished turn's jobs go to the stream in one round trip, each keeping its dedupe key."""

from __future__ import annotations

import json
from unittest.mock import patch

from redis.asyncio.client import Pipeline
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import jobs
from app.core.jobs import JOBS_STREAM, JobRequest


async def test_enqueue_many_writes_every_job_in_one_pipeline(fake_redis):
    sent: list[int] = []
    run = Pipeline.execute

    async def counted(self, *args, **kwargs):
        sent.append(len(self.command_stack))
        return await run(self, *args, **kwargs)

    requests = [
        JobRequest("memory", {"chat_id": "c"}, "memory:m1"),
        JobRequest("topic", {"chat_id": "c"}, "topic:c"),
        JobRequest("compress", {"chat_id": "c"}),
    ]
    with patch.object(Pipeline, "execute", counted):
        assert await jobs.enqueue_many(fake_redis, requests) == [True, True, True]

    assert sent == [3]
    entries = await fake_redis.xrange(JOBS_STREAM)
    fields = [entry for _id, entry in entries]
    assert [f["type"] for f in fields] == ["memory", "topic", "compress"]
    assert [f.get("dedupe_key") for f in fields] == ["memory:m1", "topic:c", None]
    assert json.loads(fields[0]["payload"]) == {"chat_id": "c"}


async def test_enqueue_many_with_nothing_sends_nothing(fake_redis):
    assert await jobs.enqueue_many(fake_redis, []) == []
    assert await fake_redis.exists(JOBS_STREAM) == 0


async def test_enqueue_many_reports_a_rejected_job_and_keeps_the_others(fake_redis):
    # The pipeline answers per command (raise_on_error=False): the second XADD failed.
    requests = [JobRequest("memory", {"n": "1"}), JobRequest("topic", {"n": "2"})]
    run = Pipeline.execute

    async def one_rejected(self, *args, **kwargs):
        results = await run(self, *args, **kwargs)
        return [results[0], RuntimeError("rejected")]

    with (
        patch.object(Pipeline, "execute", one_rejected),
        patch("app.core.jobs.queue.sentry.report_exception") as reported,
    ):
        assert await jobs.enqueue_many(fake_redis, requests) == [True, False]
    reported.assert_called_once_with("enqueue_failed:topic")


async def test_enqueue_many_never_raises_when_redis_is_down(fake_redis):
    async def down(self, *args, **kwargs):
        raise RedisConnectionError("down")

    with (
        patch.object(Pipeline, "execute", down),
        patch("app.core.jobs.queue.sentry.report_exception") as reported,
    ):
        queued = await jobs.enqueue_many(
            fake_redis, [JobRequest("memory", {}), JobRequest("topic", {})]
        )
    assert queued == [False, False]
    assert reported.call_count == 2
