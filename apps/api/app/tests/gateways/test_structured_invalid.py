"""Structured output that does not validate is logged, counted and, where asked, retried."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings
from app.gateways import litellm_gateway
from app.gateways.structured_completion import invalid_output_key
from app.modules.memory.schemas import MemoryFactUpdateResult
from app.modules.todos.schemas import TodoActionItem

_SETTINGS = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
_TODO = '{"actions": [{"action": "add", "topic": "T", "content": "C"}]}'


class _ActionList(BaseModel):
    actions: list[TodoActionItem]


def _completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = None
    return response


async def _ask(
    replies: list[object],
    *,
    schema: type[BaseModel],
    allow_fallback: bool = True,
    fallback_on_invalid: bool = False,
) -> tuple[BaseModel | None, list[str]]:
    models: list[str] = []

    async def acompletion(**call: object) -> object:
        models.append(str(call["model"]))
        reply = replies[len(models) - 1]
        if isinstance(reply, Exception):
            raise reply
        return _completion(str(reply))

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=_SETTINGS,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=schema,
            allow_fallback=allow_fallback,
            fallback_on_invalid=fallback_on_invalid,
        )
    return result, models


@pytest.mark.asyncio
async def test_memory_model_bad_output_twice_is_logged_counted_and_dropped(
    caplog: pytest.LogCaptureFixture, structured_invalid_redis
) -> None:
    """V10.2: the memory model returns {"ops": "oops"} on both tries."""
    caplog.set_level(logging.WARNING, logger="app.gateways.structured_completion")
    result, models = await _ask(
        ['{"ops": "oops"}', '{"ops": "oops"}'],
        schema=MemoryFactUpdateResult,
        fallback_on_invalid=True,
    )
    await drain_background_tasks()
    assert result is None
    assert [model.rsplit("/", 1)[-1] for model in models] == ["qwen3.7-flash", "claude-haiku-5.5"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "alias=memory-model" in line and "schema=MemoryFactUpdateResult" in line
        for line in warnings
    )
    assert any("alias=fallback-memory-model" in line for line in warnings)
    counts = await structured_invalid_redis.hgetall(invalid_output_key())
    assert counts == {
        "memory-model:MemoryFactUpdateResult": "1",
        "fallback-memory-model:MemoryFactUpdateResult": "1",
    }


@pytest.mark.asyncio
async def test_bad_json_is_retried_without_an_outage_fallback() -> None:
    """A foreground call: a bad reply is asked again; a provider outage is not."""
    result, models = await _ask(
        ["not json {{", _TODO],
        schema=_ActionList,
        allow_fallback=False,
        fallback_on_invalid=True,
    )
    assert result is not None and len(models) == 2
    result, models = await _ask(
        [RuntimeError("provider down"), _TODO],
        schema=_ActionList,
        allow_fallback=False,
        fallback_on_invalid=True,
    )
    assert result is None and len(models) == 1


@pytest.mark.asyncio
async def test_a_bare_list_for_a_schema_without_one_is_counted(structured_invalid_redis) -> None:
    class Title(BaseModel):
        title: str

    result, _models = await _ask(["[1, 2]"], schema=Title)
    await drain_background_tasks()
    assert result is None
    assert await structured_invalid_redis.hgetall(invalid_output_key()) == {
        "memory-model:Title": "1"
    }


@pytest.mark.asyncio
async def test_memory_extraction_retries_bad_output() -> None:
    """Memory extraction asks once more on bad JSON."""
    from app.modules.memory import llm as memory_llm

    calls: list[dict[str, object]] = []

    async def complete(**kwargs: object) -> None:
        calls.append(kwargs)
        return None

    with patch.object(litellm_gateway, "complete_structured", complete):
        await memory_llm.revise_memory_facts(_SETTINGS, "user: I moved to Lisbon")
    by_schema = {getattr(call["schema"], "__name__", ""): call for call in calls}
    assert by_schema["MemoryFactUpdateResult"]["fallback_on_invalid"] is True


async def test_a_salvaged_reply_logs_how_many_items_it_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.gateways.structured_completion")
    reply = (
        '{"ops": [{"op": "add", "type": "fact", "text": "User likes tea", "confidence": 0.9},'
        ' {"op": "add", "text": "Private words"}], "reply": "Done"}'
    )
    result, _ = await _ask([reply], schema=MemoryFactUpdateResult)
    assert isinstance(result, MemoryFactUpdateResult) and len(result.ops) == 1
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("kept part of a reply" in w and "dropped=1" in w for w in warnings)
    # The count only: the dropped op's text never reaches the log.
    assert not any("Private words" in w for w in warnings)
