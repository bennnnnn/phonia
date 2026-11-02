"""October 2026 model switch: thinking controls, the photo fallback, stray think tags."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.gateways.think_stripper import (
    STRAY_THINK_LEAD_HOLD,
    THINK_CLOSE,
    THINK_OPEN,
    ThinkStripper,
)
from app.models import model_catalog
from app.modules.memory.schemas import MemoryFactUpdateResult

_SETTINGS = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")


def _response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _stream(stripper: ThinkStripper, chunks: list[str]) -> str:
    return "".join(stripper.feed(chunk) for chunk in chunks) + stripper.flush()


# ── stray closing think tag ────────────────────────────────────────────────────


def test_a_stray_closing_tag_is_never_shown() -> None:
    out = _stream(ThinkStripper(), ["The answer is 4.", f"{THINK_CLOSE} Done."])
    assert out == "The answer is 4. Done."


def test_reasoning_ending_in_a_stray_closing_tag_is_dropped_inside_the_lead_hold() -> None:
    chunks = ["Simple question.", f"{THINK_CLOSE}2 + 2 = ", "**4**"]
    assert _stream(ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD), chunks) == "2 + 2 = **4**"


def test_without_the_lead_hold_text_already_out_stays_out() -> None:
    chunks = ["Simple question.", f"{THINK_CLOSE}2 + 2 = 4"]
    assert _stream(ThinkStripper(), chunks) == "Simple question.2 + 2 = 4"


def test_a_stray_tag_in_the_first_chunk_drops_its_reasoning_without_a_hold() -> None:
    assert _stream(ThinkStripper(), [f"Simple question.{THINK_CLOSE}4"]) == "4"


def test_the_lead_hold_releases_a_reply_with_no_tags() -> None:
    stripper = ThinkStripper(lead_hold=10)
    assert stripper.feed("short") == ""
    assert stripper.feed(" reply, then more") + stripper.flush() == "short reply, then more"
    held = ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD)
    assert _stream(held, ["Paris."]) == "Paris."


def test_a_stray_tag_after_a_closed_block_keeps_the_visible_text() -> None:
    chunks = [f"Hello {THINK_OPEN}plan{THINK_CLOSE} world", f"{THINK_CLOSE}!"]
    assert _stream(ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD), chunks) == "Hello  world!"


def test_a_closing_tag_split_across_chunks_does_not_leak() -> None:
    half = len(THINK_CLOSE) // 2
    chunks = ["The answer is 4.", THINK_CLOSE[:half], THINK_CLOSE[half:] + " Done."]
    assert _stream(ThinkStripper(), chunks) == "The answer is 4. Done."


def test_only_the_glm_5_3_models_hold_the_start_of_a_reply() -> None:
    guarded = {m.id for m in model_catalog.CATALOG if m.stray_think_guard}
    # The photo lane's backup runs GLM 5.3 Flash too, and can carry a chat reply.
    assert guarded == {"glm-5.3-flash", "fallback-vision-model"}


# ── thinking controls ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "alias, reasoning",
    [
        ("memory-model", {"enabled": False}),
        ("title-model", {"enabled": False}),
        ("fallback-memory-model", {"effort": "none"}),
        ("fallback-vision-model", {"effort": "low"}),
    ],
)
def test_background_aliases_answer_without_a_thinking_pass(
    alias: str, reasoning: dict[str, Any]
) -> None:
    kwargs = litellm_gateway._litellm_kwargs(
        _SETTINGS, litellm_gateway.resolve_route(alias), thinking=False
    )
    assert kwargs["extra_body"]["reasoning"] == reasoning


def test_vision_chat_reads_a_photo_without_a_thinking_pass() -> None:
    kwargs = litellm_gateway._litellm_kwargs(
        _SETTINGS, litellm_gateway.resolve_route("vision-chat"), thinking=False
    )
    assert kwargs["extra_body"]["reasoning"] == {"enabled": False}


@pytest.mark.asyncio
async def test_structured_background_call_turns_thinking_off() -> None:
    seen: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> MagicMock:
        seen.append(kwargs)
        return _response('{"actions": []}')

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        await litellm_gateway.complete_structured(
            settings=_SETTINGS,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=MemoryFactUpdateResult,
        )
    assert seen[0]["model"] == "openrouter/qwen/qwen3.7-flash"
    assert seen[0]["extra_body"]["reasoning"] == {"enabled": False}


@pytest.mark.asyncio
async def test_text_background_call_turns_thinking_off() -> None:
    seen: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> MagicMock:
        seen.append(kwargs)
        return _response("A title")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        text = await litellm_gateway.complete_text(
            settings=_SETTINGS,
            model_alias="title-model",
            messages=[{"role": "user", "content": "x"}],
        )
    assert text == "A title"
    assert seen[0]["extra_body"]["reasoning"] == {"enabled": False}


# ── photo fallback ─────────────────────────────────────────────────────────────


async def _vision(fake: Any) -> Any:
    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake)):
        return await litellm_gateway.vision_completion(
            settings=_SETTINGS,
            model_alias="vision-chat",
            messages=[{"role": "user", "content": "read this"}],
            max_tokens=64,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_a_failed_photo_read_retries_on_the_fallback_model() -> None:
    models: list[str] = []

    async def fake(**kwargs: Any) -> MagicMock:
        models.append(kwargs["model"])
        if len(models) == 1:
            raise RuntimeError("404 model retired")
        return _response("x = 3")

    response = await _vision(fake)
    assert response.choices[0].message.content == "x = 3"
    assert models == [
        "openrouter/qwen/qwen3.7-flash",
        "openrouter/z-ai/glm-5.3-flash",
    ]


@pytest.mark.asyncio
async def test_a_timed_out_photo_read_does_not_retry() -> None:
    models: list[str] = []

    async def fake(**kwargs: Any) -> MagicMock:
        models.append(kwargs["model"])
        await asyncio.sleep(5)
        return _response("late")

    assert await _vision(fake) is None
    assert models == ["openrouter/qwen/qwen3.7-flash"]


@pytest.mark.asyncio
async def test_both_photo_readers_failing_returns_none() -> None:
    models: list[str] = []

    async def fake(**kwargs: Any) -> MagicMock:
        models.append(kwargs["model"])
        raise RuntimeError("down")

    assert await _vision(fake) is None
    assert models == [
        "openrouter/qwen/qwen3.7-flash",
        "openrouter/z-ai/glm-5.3-flash",
    ]


@pytest.mark.asyncio
async def test_photo_reads_are_greedy_on_every_attempt() -> None:
    temperatures: list[float] = []

    async def fake(**kwargs: Any) -> MagicMock:
        temperatures.append(kwargs["temperature"])
        if len(temperatures) == 1:
            raise RuntimeError("down")
        return _response("x = 3")

    assert await _vision(fake) is not None
    assert temperatures == [0.0, 0.0]


@pytest.mark.asyncio
async def test_the_photo_fallback_shares_the_budget_instead_of_a_fresh_one() -> None:
    models: list[str] = []

    async def fake(**kwargs: Any) -> MagicMock:
        models.append(kwargs["model"])
        await asyncio.sleep(0.6)
        if len(models) == 1:
            raise RuntimeError("down")
        return _response("late")

    # 1 s budget: the fallback starts with ~0.4 s left, so it times out.
    assert await _vision(fake) is None
    assert len(models) == 2


# ── stored aliases (alembic 0108) ──────────────────────────────────────────────


def _migration(name: str = "0108_model_aliases_oct_2026.py") -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "alembic/versions" / name
    spec = importlib.util.spec_from_file_location(f"migration_{name[:4]}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_renames_and_drops_stored_switches_in_order() -> None:
    m = _migration()
    stored = ["auto", "qwen-plus", "gemini-flash", "glm-5.2", "gpt-6-luna", "gpt-5.5"]
    assert m._migrate_enabled(stored, m.RENAMED) == ["auto", "gpt-6-luna", "glm-5.2", "gpt-6-sol"]


def test_migration_turns_a_list_left_empty_into_the_plan_default() -> None:
    m = _migration()
    assert m._migrate_enabled(["qwen-plus", "mercury-2"], m.RENAMED) is None


def test_migration_maps_a_removed_default_to_auto() -> None:
    m = _migration()
    assert m._migrate_alias("minimax-m2", m.RENAMED) == "auto"
    assert m._migrate_alias("glm-4-flash", m.RENAMED) == "glm-5.3-flash"
    assert m._migrate_alias("free-chat", m.RENAMED) == "free-chat"


def test_migration_targets_are_catalog_aliases_and_sources_are_gone() -> None:
    m = _migration()
    trimmed = _migration("0109_trim_model_lineup.py")
    known = model_catalog.known_ids()
    # 0109 later retired gpt-6-sol, one of 0108's targets; it moves those users on.
    assert set(m.RENAMED.values()) <= known | trimmed.REMOVED
    assert not (set(m.RENAMED) | m.REMOVED) & known


# ── trimmed line-up (alembic 0109) ─────────────────────────────────────────────


def test_trimmed_models_are_gone_from_the_catalog() -> None:
    trimmed = _migration("0109_trim_model_lineup.py")
    assert not trimmed.REMOVED & model_catalog.known_ids()
    assert "gpt-6-luna" not in trimmed.REMOVED


def test_trimming_keeps_the_other_switches_in_order() -> None:
    trimmed = _migration("0109_trim_model_lineup.py")
    stored = ["auto", "gpt-6-sol", "glm-5.2", "kimi-k3", "gpt-6-luna"]
    assert trimmed._kept(stored) == ["auto", "glm-5.2", "gpt-6-luna"]
    # A list of only removed models becomes NULL: the plan default, Auto on.
    assert trimmed._kept(["gpt-6-sol", "minimax-m3"]) is None
