"""Model health: one Redis round trip per read or write, a breaker per provider model
that half-opens, and a probe that only the turn trying the model claims."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import pytest

from app.core.config import Settings
from app.services import model_health
from app.services.model_health import HealthSample

_SETTINGS = Settings(model_health_cooldown_seconds=30)


def _redis() -> Any:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class _CountingRedis:
    """A fake Redis that counts round trips (a pipeline is one)."""

    def __init__(self) -> None:
        self.inner = _redis()
        self.round_trips = 0

    def pipeline(self, transaction: bool = True) -> Any:
        pipe = self.inner.pipeline(transaction=transaction)
        execute = pipe.execute

        async def counted() -> Any:
            self.round_trips += 1
            return await execute()

        pipe.execute = counted
        return pipe


def _probe_key(alias: str) -> str:
    return f"recall:model_health:probe:{model_health._model_of(alias)}"


async def _store(redis: Any, alias: str, *samples: tuple[bool, int, float]) -> None:
    """Samples with their own timestamps: (ok, latency ms, recorded at)."""
    key = f"recall:model_health:samples:{model_health._model_of(alias)}"
    for ok, ms, at in samples:
        await redis.zadd(key, {f"{int(ok)}|{ms}|{int(at * 1e9)}": at})


async def _health(redis: Any, alias: str) -> model_health.ModelHealthSnapshot:
    return (await model_health.enrich_models_health(redis, _SETTINGS, [alias]))[alias]


@pytest.mark.asyncio
async def test_no_samples_is_healthy() -> None:
    snap = await _health(_redis(), "free-chat")
    assert snap.healthy is True
    assert snap.latency_p50_ms is None
    assert snap.sample_count == 0


@pytest.mark.asyncio
async def test_record_and_p50() -> None:
    redis = _redis()
    await model_health.record_samples(
        redis, [HealthSample("free-chat", latency_ms=ms, success=True) for ms in (100, 200, 300)]
    )
    snap = await _health(redis, "free-chat")
    assert snap.sample_count == 3
    assert snap.healthy is True
    assert snap.latency_p50_ms == 200


@pytest.mark.asyncio
async def test_a_failing_model_opens() -> None:
    redis = _redis()
    now = time.time()
    await _store(
        redis, "smart-chat", (True, 50, now - 4), *[(False, 50, now - i) for i in (3, 2, 1)]
    )
    snap = await _health(redis, "smart-chat")
    assert snap.sample_count == 4
    assert snap.error_rate == 0.75
    assert snap.healthy is False


@pytest.mark.asyncio
async def test_a_model_that_just_answered_is_closed() -> None:
    redis = _redis()
    now = time.time()
    await _store(
        redis, "smart-chat", *[(False, 50, now - i) for i in (4, 3, 2)], (True, 50, now - 1)
    )
    assert (await _health(redis, "smart-chat")).healthy is True


async def _mostly_answering(redis: Any, alias: str, last: HealthSample) -> None:
    """Nine answers, then ``last``: far below the bad rate on its own."""
    await model_health.record_samples(
        redis, [HealthSample(alias, latency_ms=900, success=True) for _ in range(9)]
    )
    await model_health.record_samples(redis, [last])


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["rate_limit", "cap"])
async def test_one_overloaded_failure_opens_a_model_that_mostly_answers(cause: str) -> None:
    redis = _redis()
    await _mostly_answering(
        redis, "qwen-3.7-flash", HealthSample("qwen-3.7-flash", 400, success=False, cause=cause)
    )
    assert (await _health(redis, "qwen-3.7-flash")).healthy is False
    found = await model_health.read_breakers(redis, _SETTINGS, ["qwen-3.7-flash"])
    assert found == model_health.Breakers(cooling=frozenset({"qwen-3.7-flash"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", [None, "server", "timeout", "connection", "empty"])
async def test_one_other_failure_leaves_a_model_that_mostly_answers_closed(
    cause: str | None,
) -> None:
    redis = _redis()
    await _mostly_answering(
        redis, "qwen-3.7-flash", HealthSample("qwen-3.7-flash", 400, success=False, cause=cause)
    )
    assert (await _health(redis, "qwen-3.7-flash")).healthy is True


@pytest.mark.asyncio
async def test_an_answer_after_an_overloaded_failure_closes_the_breaker() -> None:
    redis = _redis()
    await _mostly_answering(
        redis, "qwen-3.7-flash", HealthSample("qwen-3.7-flash", 400, False, cause="rate_limit")
    )
    await model_health.record_samples(redis, [HealthSample("qwen-3.7-flash", 800, success=True)])
    assert (await _health(redis, "qwen-3.7-flash")).healthy is True


@pytest.mark.asyncio
async def test_a_provider_that_is_slow_to_start_counts_as_failing() -> None:
    redis = _redis()
    now = time.time()
    await _store(
        redis, "glm-5.2", (True, 800, now - 3), (True, 31_000, now - 2), (True, 32_000, now)
    )
    assert (await _health(redis, "glm-5.2")).healthy is False


@pytest.mark.asyncio
async def test_every_model_is_read_in_one_round_trip() -> None:
    redis = _CountingRedis()
    aliases = [
        "free-chat",
        "smart-chat",
        "glm-5.3-flash",
        "glm-5.2",
        "gpt-6-luna",
        "qwen-3.7-flash",
        "vision-chat",
        "fallback-vision-model",
    ]
    found = await model_health.read_breakers(redis, _SETTINGS, aliases)  # type: ignore[arg-type]
    assert found == model_health.Breakers()
    assert redis.round_trips == 1


@pytest.mark.asyncio
async def test_aliases_on_one_provider_model_share_its_breaker() -> None:
    redis = _redis()
    # The photo lane runs the everyday lane's model: its failures are the lane's.
    await model_health.record_samples(
        redis, [HealthSample("vision-chat", latency_ms=900, success=False) for _ in range(3)]
    )
    found = await model_health.read_breakers(
        redis, _SETTINGS, ["qwen-3.7-flash", "vision-chat", "glm-5.2"]
    )
    assert found.cooling == {"qwen-3.7-flash", "vision-chat"}
    assert (await _health(redis, "qwen-3.7-flash")).sample_count == 3


@pytest.mark.asyncio
async def test_a_turns_samples_are_written_in_one_round_trip() -> None:
    redis = _CountingRedis()
    await model_health.record_samples(
        redis,  # type: ignore[arg-type]
        [
            HealthSample("smart-chat", latency_ms=4000, success=False),
            HealthSample("glm-5.2", latency_ms=700, success=True),
        ],
    )
    assert redis.round_trips == 1
    assert (await _health(redis.inner, "smart-chat")).error_rate == 1.0
    assert (await _health(redis.inner, "glm-5.2")).healthy is True


@pytest.mark.asyncio
async def test_record_samples_swallows_redis_errors() -> None:
    redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock(side_effect=RuntimeError("down"))
    redis.pipeline.return_value = pipe
    await model_health.record_samples(redis, [HealthSample("free-chat", 10, success=True)])


@pytest.mark.asyncio
async def test_unreadable_health_is_all_healthy() -> None:
    redis = MagicMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock(side_effect=RuntimeError("down"))
    redis.pipeline.return_value = pipe
    found = await model_health.read_breakers(redis, _SETTINGS, ["smart-chat"])
    assert found == model_health.Breakers()


@pytest.mark.asyncio
async def test_an_open_model_cools_down_before_it_is_half_open() -> None:
    redis = _redis()
    await _store(redis, "smart-chat", (False, 50, time.time() - 5))
    found = await model_health.read_breakers(redis, _SETTINGS, ["smart-chat", "glm-5.2"])
    assert found == model_health.Breakers(cooling=frozenset({"smart-chat"}))


@pytest.mark.asyncio
async def test_after_its_cool_down_an_open_model_is_half_open_and_reading_claims_nothing() -> None:
    redis = _redis()
    await _store(redis, "smart-chat", (False, 50, time.time() - 31))
    aliases = ["smart-chat", "glm-5.2"]
    half_open = model_health.Breakers(half_open=frozenset({"smart-chat"}))
    # Every turn reads it half-open; none has used up its probe by reading.
    assert await model_health.read_breakers(redis, _SETTINGS, aliases) == half_open
    assert await model_health.read_breakers(redis, _SETTINGS, aliases) == half_open
    assert await redis.exists(_probe_key("smart-chat")) == 0


@pytest.mark.asyncio
async def test_one_turn_at_a_time_claims_the_probe() -> None:
    redis = _redis()
    assert await model_health.claim_probe(redis, _SETTINGS, "smart-chat") is True
    assert await model_health.claim_probe(redis, _SETTINGS, "smart-chat") is False
    # Another model's probe is its own.
    assert await model_health.claim_probe(redis, _SETTINGS, "glm-5.2") is True


@pytest.mark.asyncio
async def test_the_probe_outlasts_a_try_that_waits_out_its_provider() -> None:
    redis = _redis()
    settings = Settings(
        model_health_cooldown_seconds=30,
        chat_stream_connect_timeout_seconds=15,
        chat_stream_timeout_seconds=45,
    )
    assert model_health.probe_ttl_seconds(settings) == 60
    assert await model_health.claim_probe(redis, settings, "smart-chat")
    assert 55 < await redis.ttl(_probe_key("smart-chat")) <= 60
    # A cool-down longer than one try still bounds it.
    assert model_health.probe_ttl_seconds(Settings(model_health_cooldown_seconds=120)) == 120


@pytest.mark.asyncio
async def test_a_claim_that_cannot_be_made_counts_as_lost() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=RuntimeError("down"))
    assert await model_health.claim_probe(redis, _SETTINGS, "smart-chat") is False


@pytest.mark.asyncio
async def test_the_probes_sample_decides_the_breaker() -> None:
    redis = _redis()
    await _store(redis, "smart-chat", (False, 50, time.time() - 31))
    assert await model_health.claim_probe(redis, _SETTINGS, "smart-chat")
    # The probe failed: open again for a fresh cool-down, and the probe is free
    # for the turn after it.
    await model_health.record_samples(redis, [HealthSample("smart-chat", 3000, success=False)])
    found = await model_health.read_breakers(redis, _SETTINGS, ["smart-chat"])
    assert found == model_health.Breakers(cooling=frozenset({"smart-chat"}))
    assert await redis.exists(_probe_key("smart-chat")) == 0
    # A later probe answered: closed for every turn.
    await model_health.record_samples(redis, [HealthSample("smart-chat", 600, success=True)])
    assert await model_health.read_breakers(redis, _SETTINGS, ["smart-chat"]) == (
        model_health.Breakers()
    )


@pytest.mark.asyncio
async def test_enrich_models_health() -> None:
    redis = _redis()
    await model_health.record_samples(redis, [HealthSample("a", 40, success=True)])
    out = await model_health.enrich_models_health(redis, _SETTINGS, ["a", "b"])
    assert out["a"].sample_count == 1
    assert out["b"].sample_count == 0


@pytest.mark.asyncio
async def test_a_long_healthy_reply_is_not_slow() -> None:
    """Whole-reply time read as latency: a 60 s answer marked its model slow for a day."""
    redis = _redis()
    await model_health.record_samples(
        redis, [HealthSample("smart-chat", latency_ms=ms, success=True) for ms in (900, 1_100)]
    )
    assert (await _health(redis, "smart-chat")).healthy is True


@pytest.mark.asyncio
async def test_samples_written_in_one_second_keep_their_order() -> None:
    """Redis orders equal scores by member, failures first: the newest is the last written."""
    redis = _redis()
    key = f"recall:model_health:samples:{model_health._model_of('smart-chat')}"
    now = time.time()
    for written_ns, ok in enumerate((True, False, False, False), start=1):
        await redis.zadd(key, {f"{int(ok)}|50|{written_ns}": now})
    assert (await _health(redis, "smart-chat")).healthy is False
