"""Timing stays complete on failure and separates gateway wait from prep."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.stream_paths import run_llm_token_stream
from app.modules.chat.stream_pipeline import stream_and_finalize
from app.modules.chat.turn_prep.context import StreamContext
from app.modules.chat.turn_timing import TurnTimingTracker
from app.tests.modules.chat.chat_test_support import turn_deps


def _context(timing):
    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "test"}],
        run_title=False,
        user_message_content="test",
        reserved_tokens=100,
        max_output_tokens=100,
        timing=timing,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("failed"), asyncio.CancelledError()])
async def test_tool_loop_completion_phase_is_recorded_on_error_or_cancel(error):
    timing = TurnTimingTracker()
    ctx = _context(timing)
    with patch("app.modules.chat.stream_pipeline.run_tool_loop_path", AsyncMock(side_effect=error)):
        with pytest.raises(type(error)):
            async for _ in stream_and_finalize(
                MagicMock(),
                AsyncMock(),
                Settings(_env_file=None),
                ctx,
                should_cancel=None,
            ):
                pass
    assert timing._phases_ms["tool_loop_done"] >= timing._phases_ms["tool_loop_start"]
    assert "gateway_request_start" not in timing._phases_ms


@pytest.mark.asyncio
async def test_gateway_interval_starts_after_prep_and_ends_at_first_visible_token(
    monkeypatch, caplog
):
    clock = {"ms": 10.0}
    timing = TurnTimingTracker()
    monkeypatch.setattr(timing, "_elapsed_ms", lambda: clock["ms"])
    timing.mark_prompt_ready()
    ctx = _context(timing)

    async def visible_stream(**_kwargs):
        assert timing._phases_ms["gateway_request_start"] == 100.0
        clock["ms"] = 125.0
        yield "visible"
        clock["ms"] = 150.0
        yield " reply"

    deps = turn_deps(llm=SimpleNamespace(stream_chat_completion=visible_stream))
    clock["ms"] = 100.0  # Quota top-up and tool work happened after prompt_ready.
    with patch("app.services.model_health.record_samples", AsyncMock()):
        tokens = [
            token
            async for token in run_llm_token_stream(
                deps,
                AsyncMock(),
                Settings(_env_file=None),
                ctx,
                usage={},
                should_cancel=None,
                outcome=None,
                on_reasoning=None,
                accum=StreamAccum(),
            )
        ]
    with caplog.at_level("INFO"):
        timing.log_summary(user_id=ctx.user_id, chat_id=ctx.chat_id, model=ctx.model)
    assert tokens == ["visible", " reply"]
    assert "post_prompt_first_token_ms=115.0" in caplog.text
    assert "gateway_to_first_token_ms=25.0" in caplog.text


@pytest.mark.asyncio
async def test_instant_reply_does_not_report_tool_or_gateway_wait():
    timing = TurnTimingTracker()
    ctx = _context(timing)
    ctx.instant_reply = "instant"
    stream = stream_and_finalize(
        MagicMock(), AsyncMock(), Settings(_env_file=None), ctx, should_cancel=None
    )
    assert await anext(stream) == "instant"
    await stream.aclose()
    assert "tool_loop_start" not in timing._phases_ms
    assert "gateway_request_start" not in timing._phases_ms
