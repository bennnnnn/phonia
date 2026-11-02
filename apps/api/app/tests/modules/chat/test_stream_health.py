"""A turn's model health samples: one per model it tried, each blamed on its own model."""

from __future__ import annotations

import time
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import fakeredis
import pytest

from app.core.config import Settings
from app.gateways.litellm_gateway import ModelUnavailableError
from app.gateways.stream_signals import StreamAttempt
from app.models import model_catalog
from app.modules.chat.stream_health import StreamEnd, health_samples
from app.modules.chat.turn_outcome import TurnOutcome
from app.services import model_health
from app.services.model_health import Breakers
from app.tests.modules.chat.chat_test_support import offline_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)


def _end(**fields: Any) -> StreamEnd:
    base: dict[str, Any] = {
        "model": "free-chat",
        "answered": True,
        "failed": False,
        "stopped": False,
        "elapsed_ms": 900.0,
        "first_token_ms": 400.0,
    }
    return StreamEnd(**{**base, **fields})


def _read(samples: list[Any]) -> list[tuple[str, bool, float]]:
    return [(sample.alias, sample.success, sample.latency_ms) for sample in samples]


def test_a_failed_model_is_blamed_and_the_model_that_answered_is_not() -> None:
    attempts = [
        StreamAttempt("smart-chat", failed=True, elapsed_ms=8000),
        StreamAttempt("glm-5.2", first_delta_ms=650),
    ]
    samples = health_samples(attempts, _end(model="glm-5.2"))
    # Latency is how fast the provider started, not how long the reply ran.
    assert _read(samples) == [("smart-chat", False, 8000), ("glm-5.2", True, 650)]


def test_a_model_that_fails_partway_is_a_failure() -> None:
    attempts = [StreamAttempt("free-chat", failed=True, first_delta_ms=300, elapsed_ms=5000)]
    assert _read(health_samples(attempts, _end(failed=True))) == [("free-chat", False, 5000)]


def test_a_request_the_provider_refused_leaves_no_sample() -> None:
    attempts = [
        StreamAttempt("smart-chat", failed=True, cause="request", elapsed_ms=300),
        StreamAttempt("glm-5.2", failed=True, cause="cap", elapsed_ms=8000),
        StreamAttempt("free-chat", first_delta_ms=500),
    ]
    samples = health_samples(attempts, _end())
    assert _read(samples) == [("glm-5.2", False, 8000), ("free-chat", True, 500)]


def test_a_failed_tries_cause_goes_into_its_sample() -> None:
    attempts = [
        StreamAttempt("qwen-3.7-flash", failed=True, cause="rate_limit", elapsed_ms=400),
        StreamAttempt("free-chat", first_delta_ms=700),
    ]
    samples = health_samples(attempts, _end())
    assert [sample.cause for sample in samples] == ["rate_limit", None]


def test_a_stop_leaves_no_sample_for_the_model_it_cut_short() -> None:
    attempts = [
        StreamAttempt("qwen-3.7-flash", failed=True, elapsed_ms=3000),
        StreamAttempt("free-chat"),
    ]
    samples = health_samples(attempts, _end(stopped=True, answered=False))
    assert _read(samples) == [("qwen-3.7-flash", False, 3000)]


@pytest.mark.parametrize(
    "answered, failed, stopped, expected",
    [
        (True, False, False, [("free-chat", True, 400.0)]),
        (True, True, False, [("free-chat", False, 900.0)]),
        (False, False, False, [("free-chat", False, 900.0)]),
        (False, False, True, []),
        (True, False, True, []),
    ],
)
def test_a_model_call_that_reports_no_tries_counts_as_one(
    answered: bool, failed: bool, stopped: bool, expected: list[tuple[str, bool, float]]
) -> None:
    end = _end(answered=answered, failed=failed, stopped=stopped)
    assert _read(health_samples([], end)) == expected


def _ctx() -> Any:
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="smart-chat",
        prompt_messages=[{"role": "user", "content": "hi"}],
        run_title=False,
        user_message_content="hi",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
    )


async def _run(fake_stream: Any, outcome: TurnOutcome | None = None) -> AsyncMock:
    from app.modules.chat.stream_pipeline import stream_and_finalize

    record = AsyncMock()
    outcome = outcome or TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(patch("app.services.model_health.record_samples", record))
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock())
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for _ in stream_and_finalize(
            offline_deps(),
            AsyncMock(),
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            _ctx(),
            should_cancel=None,
            outcome=outcome,
        ):
            pass
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task
    return record


@pytest.mark.asyncio
async def test_the_turn_records_every_model_it_tried(stream_offline_io: None) -> None:
    async def fake_stream(**kwargs: Any) -> Any:
        kwargs["attempts"].extend(
            [
                StreamAttempt("smart-chat", failed=True, elapsed_ms=8000),
                StreamAttempt("glm-5.2", first_delta_ms=700),
            ]
        )
        kwargs["stream_meta"]["model_alias"] = "glm-5.2"
        yield "answer"

    record = await _run(fake_stream)
    record.assert_awaited_once()
    assert record.await_args is not None
    samples = record.await_args.args[1]
    assert [(s.alias, s.success) for s in samples] == [("smart-chat", False), ("glm-5.2", True)]


@pytest.mark.asyncio
async def test_a_run_ends_the_reply_whole_and_closes_the_provider(
    stream_offline_io: None,
) -> None:
    """2026-11-01: the guard read a runaway run to the provider's length limit, so the user
    waited on it and the clean reply was marked cut short."""
    closed: list[bool] = []
    read: list[int] = []

    async def fake_stream(**kwargs: Any) -> Any:
        try:
            yield "The time is 2e-8 s."
            for count in range(500):
                read.append(count)
                yield "<|im_end|>"
            kwargs["stream_meta"]["finish_reason"] = "length"
        finally:
            closed.append(True)

    outcome = TurnOutcome()
    record = await _run(fake_stream, outcome)
    assert outcome.completion != "interrupted"
    assert outcome.final_content == "The time is 2e-8 s."
    assert closed == [True]
    assert len(read) < 10
    # The model wrote a reply: a run is its health, not a failure.
    assert record.await_args is not None
    assert [s.success for s in record.await_args.args[1]] == [True]


@pytest.mark.asyncio
async def test_a_reply_that_fails_partway_is_its_models_failure(stream_offline_io: None) -> None:
    """Regression: a stream that died after its first token was sampled as a success."""

    async def fake_stream(**_kwargs: Any) -> Any:
        yield "partial "
        raise ModelUnavailableError("provider died", failed_alias="smart-chat")

    record = await _run(fake_stream)
    assert record.await_args is not None
    samples = record.await_args.args[1]
    assert [(s.alias, s.success) for s in samples] == [("smart-chat", False)]


# ── a recovering model's probe, through the real gateway ──────────────────────


class _Provider:
    """One provider stream that sends ``text`` and ends."""

    def __init__(self, text: str) -> None:
        self._chunks = [text]

    def __aiter__(self) -> _Provider:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            raise StopAsyncIteration
        delta = SimpleNamespace(content=self._chunks.pop(0), reasoning_content=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None
        )


_LIVE = Settings(
    max_output_tokens=100,
    mcp_tool_loop_enabled=False,
    mock_llm_enabled=False,
    openrouter_api_key="sk-or-test",
)


async def _open_since_cool_down(redis: Any, alias: str) -> None:
    key = f"recall:model_health:samples:{model_health._model_of(alias)}"
    stale = time.time() - _LIVE.model_health_cooldown_seconds - 1
    await redis.zadd(key, {f"0|900|{int(stale * 1e9)}": stale})


async def _live_turn(redis: Any, model: str, fallbacks: list[str], probe: set[str]) -> list[str]:
    """Stream one turn on the real gateway; the provider models it was asked to run."""
    from app.modules.chat.stream_pipeline import stream_and_finalize

    asked: list[str] = []

    async def acompletion(**kwargs: Any) -> _Provider:
        asked.append(kwargs["model"])
        return _Provider("Hello there, friend.")

    ctx = _ctx()
    ctx.model = model
    ctx.fallback_models = fallbacks
    ctx.probe_models = frozenset(probe)
    outcome = TurnOutcome()
    with ExitStack() as stack:
        stack.enter_context(patch("app.gateways.litellm_gateway.acompletion", acompletion))
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock())
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for _ in stream_and_finalize(
            offline_deps(), redis, _LIVE, ctx, should_cancel=None, outcome=outcome
        ):
            pass
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task
    return asked


def _model(alias: str) -> str:
    return model_catalog.get(alias).model


@pytest.mark.asyncio
async def test_a_turn_routed_elsewhere_leaves_the_probe(stream_offline_io: None) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _open_since_cool_down(redis, "smart-chat")
    asked = await _live_turn(redis, "free-chat", ["glm-5.2"], {"smart-chat"})
    assert asked == [_model("free-chat")]
    # The recovering model's one try is still there for a turn that tries it.
    assert await model_health.claim_probe(redis, _LIVE, "smart-chat") is True


@pytest.mark.asyncio
async def test_the_turn_that_tries_a_recovering_model_claims_its_probe(
    stream_offline_io: None,
) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _open_since_cool_down(redis, "smart-chat")
    claim = AsyncMock(wraps=model_health.claim_probe)
    with patch.object(model_health, "claim_probe", claim):
        asked = await _live_turn(redis, "smart-chat", ["glm-5.2"], {"smart-chat"})
    assert asked == [_model("smart-chat")]
    claim.assert_awaited_once()
    # It answered: closed for every turn, and its probe let go.
    assert await model_health.read_breakers(redis, _LIVE, ["smart-chat"]) == Breakers()


@pytest.mark.asyncio
async def test_a_turn_passes_by_a_model_another_turn_is_trying(stream_offline_io: None) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await _open_since_cool_down(redis, "smart-chat")
    assert await model_health.claim_probe(redis, _LIVE, "smart-chat")
    asked = await _live_turn(redis, "smart-chat", ["glm-5.2"], {"smart-chat"})
    assert asked == [_model("glm-5.2")]
    # Untried, so no sample: it stays half-open for the probe in flight.
    found = await model_health.read_breakers(redis, _LIVE, ["smart-chat", "glm-5.2"])
    assert found == Breakers(half_open=frozenset({"smart-chat"}))


def test_a_model_the_user_named_runs_without_a_probe() -> None:
    from app.modules.chat.turn_prep import stream_context_from_bundle
    from app.tests.modules.chat.chat_test_support import prompt_bundle

    bundle = prompt_bundle(half_open_models=frozenset({"smart-chat", "glm-5.2"}))
    common: dict[str, Any] = {
        "user_id": uuid4(),
        "chat_id": uuid4(),
        "model": "smart-chat",
        "user_message_content": "hi",
        "reserved_tokens": 10,
        "user": SimpleNamespace(),
        "prior_count": 0,
    }
    routed = stream_context_from_bundle(bundle, **common)
    named = stream_context_from_bundle(bundle, **common, model_named=True)
    assert routed.probe_models == {"smart-chat", "glm-5.2"}
    # A backup is still the turn's choice: it claims its probe when reached.
    assert named.probe_models == {"glm-5.2"}
