"""Real progress the phone can show: thinking (from its start), checking, a slow tool round.

A label for a step after the reply's text (the answer check, its photo) is cleared
with ``finishing`` once that step ends, so it never outlives it."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat import stream_events
from app.modules.chat.stream_status import announced_if_slow, thinking_status
from app.modules.chat.turn_outcome import TurnOutcome
from app.tests.modules.chat.chat_test_support import offline_deps

pytest_plugins = ("app.tests.modules.chat.chat_test_support",)


class Statuses:
    """A status emitter that keeps what it was sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None, int | None]] = []

    async def __call__(
        self, phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        self.sent.append((phase, detail, elapsed_ms))

    @property
    def phases(self) -> list[str]:
        return [phase for phase, _detail, _elapsed in self.sent]


# ── the event and its emitters ─────────────────────────────────────────────────


def test_a_status_carries_how_long_its_phase_has_run() -> None:
    assert stream_events.build_status_event("thinking", elapsed_ms=1840) == {
        "type": "status",
        "phase": "thinking",
        "elapsed_ms": 1840,
    }
    assert stream_events.build_status_event("searching", "weather") == {
        "type": "status",
        "phase": "searching",
        "detail": "weather",
    }


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_thinking_is_sent_once_with_how_long_the_model_has_worked() -> None:
    statuses = Statuses()
    emit = thinking_status(statuses, time.perf_counter() - 2.0)
    assert emit is not None
    await emit()
    await emit()  # a backup model that thinks too
    assert len(statuses.sent) == 1
    phase, _detail, elapsed = statuses.sent[0]
    assert phase == "thinking"
    assert elapsed is not None and 1900 <= elapsed < 4000
    assert thinking_status(None, time.perf_counter()) is None


@pytest.mark.asyncio
async def test_a_quick_step_is_never_announced() -> None:
    statuses = Statuses()

    async def quick() -> str:
        await asyncio.sleep(0)
        return "done"

    assert await announced_if_slow(quick(), statuses, "planning", after_seconds=0.2) == "done"
    assert statuses.sent == []


@pytest.mark.asyncio
async def test_a_slow_step_is_announced_once_while_it_runs() -> None:
    statuses = Statuses()

    async def slow() -> str:
        await asyncio.sleep(0.15)
        assert statuses.phases == ["planning"]
        return "done"

    assert await announced_if_slow(slow(), statuses, "planning", after_seconds=0.05) == "done"
    assert statuses.phases == ["planning"]


@pytest.mark.asyncio
async def test_an_announced_step_is_cleared_when_it_ends() -> None:
    statuses = Statuses()

    async def slow() -> str:
        await asyncio.sleep(0.15)
        return "done"

    async def fails() -> str:
        await asyncio.sleep(0.15)
        raise RuntimeError("no photo")

    got = await announced_if_slow(
        slow(), statuses, "answer_photo", after_seconds=0.05, then="finishing"
    )
    assert got == "done"
    with pytest.raises(RuntimeError):
        await announced_if_slow(
            fails(), statuses, "answer_photo", after_seconds=0.05, then="finishing"
        )
    assert statuses.phases == ["answer_photo", "finishing", "answer_photo", "finishing"]


@pytest.mark.asyncio
async def test_a_quick_step_sends_no_clearing_status() -> None:
    statuses = Statuses()

    async def quick() -> str:
        return "done"

    await announced_if_slow(quick(), statuses, "answer_photo", after_seconds=0.2, then="finishing")
    assert statuses.sent == []


@pytest.mark.asyncio
async def test_a_slow_answer_photo_is_its_own_phase_and_is_cleared() -> None:
    from app.modules.chat.finalize_text import attach_answer_photo

    statuses = Statuses()

    class SlowPhoto:
        watching = False

        async def attach(self, text: str) -> tuple[str, list[Any]]:
            await asyncio.sleep(0.15)
            return text, []

    state = MagicMock(
        ctx=MagicMock(answer_photo=SlowPhoto()),
        text="An ear has three parts.",
        was_cancelled=False,
        should_cancel=None,
        on_status=statuses,
    )
    with patch("app.modules.chat.stream_status.SLOW_STEP_SECONDS", 0.05):
        assert await attach_answer_photo(state) == "An ear has three parts."
    # Not "finding_photo": that names the tool round, which analytics counts as a tool.
    assert statuses.phases == ["answer_photo", "finishing"]


@pytest.mark.asyncio
async def test_a_stopped_turn_stops_the_announced_step() -> None:
    stopped = asyncio.Event()

    async def forever() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stopped.set()
            raise

    task = asyncio.create_task(announced_if_slow(forever(), Statuses(), "planning"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_the_socket_sends_a_statuss_elapsed_time() -> None:
    from app.modules.chat import ws_api

    websocket = MagicMock()
    with patch.object(ws_api, "safe_send_json", AsyncMock(return_value=True)) as send:
        emit_status, _emit_reasoning = ws_api._status_emitters(websocket)
        await emit_status("thinking", elapsed_ms=1200)
        await emit_status("searching", "weather")
    assert send.await_args_list[0].args[1] == {
        "type": "status",
        "phase": "thinking",
        "elapsed_ms": 1200,
    }
    assert "elapsed_ms" not in send.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_sse_sends_a_statuss_elapsed_time() -> None:
    from app.modules.chat.stream_api import _stream_tokens_sse

    async def factory(_outcome: Any, on_status: Any, _on_reasoning: Any, _cancel: Any) -> Any:
        await on_status("thinking", elapsed_ms=1200)
        yield "Hello"

    request = AsyncMock()
    request.is_disconnected.return_value = False
    with patch("app.modules.chat.stream_api.register_inflight_stream"):
        chunks = [
            chunk
            async for chunk in _stream_tokens_sse(
                chat_id=uuid4(), stream_factory=factory, request=request
            )
        ]
    events = [json.loads(chunk.removeprefix("data: ")) for chunk in chunks]
    status = next(event for event in events if event["type"] == "status")
    assert status == {"type": "status", "phase": "thinking", "elapsed_ms": 1200}


# ── a turn ─────────────────────────────────────────────────────────────────────


def _ctx(**fields: Any) -> Any:
    from app.modules.chat.turn_prep import StreamContext

    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="glm-5.3-flash",
        prompt_messages=[{"role": "user", "content": "integrate x^2 sin x"}],
        run_title=False,
        user_message_content="integrate x^2 sin x",
        reserved_tokens=100,
        max_output_tokens=50,
        skip_memory_jobs=True,
        **fields,
    )


async def _turn(fake_stream: Any, statuses: Statuses, **ctx_fields: Any) -> list[str]:
    from app.modules.chat.stream_pipeline import stream_and_finalize

    outcome = TurnOutcome()
    tokens: list[str] = []
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.gateways.litellm_gateway.stream_chat_completion", fake_stream)
        )
        stack.enter_context(patch("app.services.model_health.record_samples", AsyncMock()))
        stack.enter_context(
            patch("app.modules.chat.stream_pipeline.finalize_stream_turn_db", AsyncMock())
        )
        stack.enter_context(patch("app.repositories.users.get_by_id", AsyncMock(return_value=None)))
        async for token in stream_and_finalize(
            offline_deps(),
            AsyncMock(),
            Settings(max_output_tokens=100, mcp_tool_loop_enabled=False),
            _ctx(**ctx_fields),
            should_cancel=None,
            outcome=outcome,
            on_status=statuses,
        ):
            tokens.append(token)
        if outcome.finalize_db_task is not None:
            await outcome.finalize_db_task
    return tokens


@pytest.mark.asyncio
async def test_a_thinking_model_shows_thinking_from_when_it_was_asked(
    stream_offline_io: None,
) -> None:
    async def fake_stream(**kwargs: Any) -> Any:
        await asyncio.sleep(0.05)
        await kwargs["on_thinking"]()
        await kwargs["on_thinking"]()
        yield "The integral is shown below."

    statuses = Statuses()
    tokens = await _turn(fake_stream, statuses)
    assert tokens == ["The integral is shown below."]
    assert statuses.phases == ["composing", "thinking"]
    _phase, _detail, elapsed = statuses.sent[1]
    assert elapsed is not None and elapsed >= 40


@pytest.mark.asyncio
async def test_a_turn_that_never_thinks_shows_no_thinking(stream_offline_io: None) -> None:
    async def fake_stream(**_kwargs: Any) -> Any:
        yield "Hello!"

    statuses = Statuses()
    await _turn(fake_stream, statuses)
    assert statuses.phases == ["composing"]


@pytest.mark.asyncio
async def test_the_answer_check_is_announced_while_it_runs_and_cleared_after(
    stream_offline_io: None, thread_sympy_executor: None
) -> None:
    statuses = Statuses()

    async def fake_stream(**_kwargs: Any) -> Any:
        yield "So $x = 4$.\n\n```answer\nx = 4\n```"

    await _turn(fake_stream, statuses)
    assert statuses.phases == ["composing", "checking", "finishing"]


@pytest.mark.asyncio
async def test_a_reply_with_nothing_to_check_is_not_announced(
    stream_offline_io: None, thread_sympy_executor: None
) -> None:
    statuses = Statuses()

    async def fake_stream(**_kwargs: Any) -> Any:
        yield "Paris is the capital of France."

    await _turn(fake_stream, statuses)
    assert "checking" not in statuses.phases
