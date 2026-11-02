import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest

from app.core.config import Settings
from app.gateways.mcp.base import ToolResult
from app.modules.speech.live_talk_tools import _key, execute_tool, search_sources_for_turn
from app.tests.fakes import make_user, redis_mock


@pytest.mark.asyncio
async def test_voice_search_reserves_once_for_duplicate_tool_calls_and_keeps_sources():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user = make_user(memory_enabled=True)
    sources = [{"title": "Official score", "url": "https://example.com/score"}]
    invoke = AsyncMock(
        return_value=ToolResult(name="web_search", content="Score 2-1", data={"hits": sources})
    )
    with patch("app.modules.speech.live_talk_tools.WebSearchAdapter.invoke", invoke):
        args = dict(
            user=user, call_id="call", turn_id="turn", name="web_search", query="latest score"
        )
        await asyncio.gather(
            execute_tool(Settings(), redis, **args), execute_tool(Settings(), redis, **args)
        )
        cached = await execute_tool(Settings(), redis, **args)
    assert invoke.await_count == 1
    assert cached["sources"] == sources
    assert await search_sources_for_turn(redis, user.id, "call", "turn") == sources


@pytest.mark.asyncio
async def test_voice_search_runs_in_its_own_turn_context():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user = make_user(memory_enabled=True, timezone="Africa/Nairobi")
    invoke = AsyncMock(return_value=ToolResult(name="web_search", content="Score", data=None))
    with patch("app.modules.speech.live_talk_tools.WebSearchAdapter.invoke", invoke):
        await execute_tool(
            Settings(), redis, user=user, call_id="c", turn_id="t", name="web_search", query="score"
        )
    args, ctx = invoke.await_args.args
    assert args == {"query": "score"}
    assert (ctx.user, ctx.redis, ctx.chat_id) == (user, redis, None)
    assert (ctx.user_timezone, ctx.user_query) == ("Africa/Nairobi", "score")
    assert ctx.first_results == {}


@pytest.mark.asyncio
async def test_memory_disabled_does_not_call_memory_service():
    user = make_user(memory_enabled=False)
    with patch("app.modules.memory.retrieval.get_memory_block", AsyncMock()) as memory:
        result = await execute_tool(
            Settings(),
            fakeredis.aioredis.FakeRedis(),
            user=user,
            call_id="call",
            turn_id="turn",
            name="memory_lookup",
            query="my diet",
        )
    assert "disabled" in result["content"]
    memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_tools_fail_closed_if_reservation_store_is_down():
    redis = redis_mock()
    redis.get.side_effect = RuntimeError("offline")
    with patch("app.modules.speech.live_talk_tools.WebSearchAdapter.invoke", AsyncMock()) as search:
        result = await execute_tool(
            Settings(),
            redis,
            user=make_user(),
            call_id="call",
            turn_id="turn",
            name="web_search",
            query="latest score",
        )
    assert "unavailable" in result["content"]
    search.assert_not_awaited()


async def _sources_with(redis, caplog, user_id):
    with caplog.at_level("WARNING", logger="app.modules.speech.live_talk_tools"):
        sources = await search_sources_for_turn(redis, user_id, "call", "turn")
    return sources, [r for r in caplog.records if r.levelname == "WARNING"]


@pytest.mark.asyncio
async def test_turn_sources_redis_error_logs_and_saves_the_turn_without_sources(caplog):
    redis = redis_mock()
    redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
    sources, warnings = await _sources_with(redis, caplog, uuid4())
    assert sources == []
    assert len(warnings) == 1
    assert "ConnectionError" in warnings[0].getMessage()


@pytest.mark.parametrize("cached", ["{not json", '["a list, not an object"]'])
@pytest.mark.asyncio
async def test_turn_sources_unreadable_cache_logs_and_saves_the_turn_without_sources(
    caplog, cached
):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user_id = uuid4()
    await redis.set(_key(user_id, "call", "turn", "web_search"), cached)
    sources, warnings = await _sources_with(redis, caplog, user_id)
    assert sources == []
    assert len(warnings) == 1
    # Names the failure only: never the cached search results.
    assert cached not in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_turn_sources_without_a_search_are_quietly_empty(caplog):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    sources, warnings = await _sources_with(redis, caplog, uuid4())
    assert sources == []
    assert warnings == []
