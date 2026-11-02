"""A new turn reads model health beside its account and routes around failing providers.

Reading claims nothing: a half-open model's probe is claimed only by the turn that
tries it (``stream_paths``), never by a turn that loads and routes elsewhere.
"""

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis
import pytest

from app.core.config import Settings
from app.modules.chat.turn_load import load_new_turn
from app.modules.chat.turn_timing import TurnTimingTracker
from app.services import model_health
from app.services.model_health import Breakers, HealthSample
from app.tests.modules.chat.chat_test_support import FakeSessionCM, turn_deps


@pytest.mark.asyncio
async def test_read_breakers_reads_failing_providers_and_never_raises() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    failures = [HealthSample("smart-chat", latency_ms=900, success=False) for _ in range(4)]
    await model_health.record_samples(redis, failures)
    await model_health.record_samples(
        redis, [HealthSample("glm-5.2", latency_ms=900, success=True)]
    )
    settings = Settings()
    found = await model_health.read_breakers(redis, settings, ["smart-chat", "glm-5.2"])
    assert found == Breakers(cooling=frozenset({"smart-chat"}))
    broken = MagicMock()
    with patch.object(model_health, "enrich_models_health", AsyncMock(side_effect=OSError)):
        assert await model_health.read_breakers(broken, settings, ["smart-chat"]) == Breakers()


def _deps(resolve: MagicMock) -> tuple[Any, Any, Any]:
    user = SimpleNamespace(id=uuid4(), plan="pro", enabled_models=None)
    chat = SimpleNamespace(id=uuid4())
    deps = turn_deps(
        session_factory=FakeSessionCM,
        quota={
            "has_daily_usage_key": AsyncMock(return_value=True),
            "daily_limit_for_user": lambda _user, _settings: 100_000,
        },
        users={"get_by_id": AsyncMock(return_value=user)},
        chats={"get_by_id": AsyncMock(return_value=chat), "peek_recent_chat": lambda *_a: chat},
        messages={"list_recent": AsyncMock(return_value=[]), "count_for_chat": AsyncMock()},
        model_choice={"resolve_user_model_override": resolve},
    )
    return deps, user, chat


async def _load(deps: Any, user: Any, chat: Any, redis: Any, content: str) -> Any:
    with (
        patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock()),
    ):
        return await load_new_turn(
            deps,
            redis,
            Settings(),
            TurnTimingTracker(),
            user_id=user.id,
            chat_id=chat.id,
            content=content,
            model_alias=None,
            user=None,
            chat=None,
            skip_usage_seed=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["hi", "plan a zero-downtime migration of a postgres schema"])
async def test_load_new_turn_hands_model_health_to_routing(content: str) -> None:
    resolve = MagicMock(return_value="glm-5.2")
    deps, user, chat = _deps(resolve)
    health = Breakers(cooling=frozenset({"smart-chat"}), half_open=frozenset({"glm-5.2"}))
    with patch.object(model_health, "read_breakers", AsyncMock(return_value=health)) as read:
        turn = await _load(deps, user, chat, AsyncMock(), content)
    read.assert_awaited_once()
    assert read.await_args is not None
    # The photo lanes are read with the chat models, in the same round trip.
    assert {"vision-chat", "fallback-vision-model"} <= set(read.await_args.args[2])
    # Routing skips a cooling model; a half-open one stays routable.
    assert resolve.call_args.kwargs["unhealthy"] == health.cooling
    assert (turn.unhealthy, turn.half_open) == (health.cooling, health.half_open)
    assert turn.model == "glm-5.2"


@pytest.mark.asyncio
async def test_loading_a_turn_claims_no_probe() -> None:
    """Regression: every new turn claimed the probe of each cooled-down model, so a
    free "hi" used up smart-chat's one retry."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    key = f"recall:model_health:samples:{model_health._model_of('smart-chat')}"
    stale = time.time() - 31
    await redis.zadd(key, {f"0|900|{int(stale * 1e9)}": stale})
    deps, user, chat = _deps(MagicMock(return_value="qwen-3.7-flash"))
    turn = await _load(deps, user, chat, redis, "hi")
    assert turn.half_open == {"smart-chat"}
    assert await model_health.claim_probe(redis, Settings(), "smart-chat") is True


@pytest.mark.asyncio
async def test_a_regenerate_reads_health_for_its_backups_and_claims_nothing() -> None:
    from app.modules.chat.turn_prep.context import _fallback_models

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    now = time.time()
    for alias, at in (("smart-chat", now - 31), ("glm-5.2", now - 5)):
        key = f"recall:model_health:samples:{model_health._model_of(alias)}"
        await redis.zadd(key, {f"0|900|{int(at * 1e9)}": at})
    user: Any = SimpleNamespace(plan="pro", enabled_models=None)
    fallbacks, half_open = await _fallback_models(user, Settings(), redis, "gpt-6-luna")
    # The cooling model is no backup; the half-open one is, behind its probe.
    assert "glm-5.2" not in fallbacks
    assert half_open == {"smart-chat"}
    assert await model_health.claim_probe(redis, Settings(), "smart-chat") is True
