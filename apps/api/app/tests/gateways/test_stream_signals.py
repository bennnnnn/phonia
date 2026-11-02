"""What a model stream shows before its answer: the think hold, thinking, first-reply caps."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.gateways.stream_signals import (
    PromptShape,
    StreamAttempt,
    first_reply_cap,
    prompt_shape,
    provider_fault,
)
from app.gateways.think_stripper import (
    STRAY_THINK_LEAD_HOLD,
    STRAY_THINK_SHORT_HOLD,
    THINK_CLOSE,
    ThinkStripper,
)

_SETTINGS = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")


def chunk(content: str | None = None, reasoning: str | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None)


class FakeStream:
    """A provider stream: each chunk after its delay, then it waits for ``finish``
    (or fails, when given an ``error``)."""

    def __init__(
        self,
        chunks: list[SimpleNamespace],
        *,
        delay: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self._chunks = list(chunks)
        self._delay = delay
        self._error = error
        self.finish = asyncio.Event()

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> SimpleNamespace:
        if not self._chunks:
            if self._error is not None:
                raise self._error
            await self.finish.wait()
            raise StopAsyncIteration
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._chunks.pop(0)


def stream_once(alias: str, provider: FakeStream, **kwargs: Any) -> AsyncIterator[str]:
    async def run() -> AsyncIterator[str]:
        with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=provider)):
            async for token in litellm_gateway._stream_chat_once(
                settings=kwargs.pop("settings", _SETTINGS),
                model_alias=alias,
                messages=[{"role": "user", "content": "what is 2 + 2?"}],
                max_tokens=50,
                **kwargs,
            ):
                yield token

    return run()


# ── the think hold ─────────────────────────────────────────────────────────────


def test_text_held_before_channel_reasoning_keeps_the_whole_hold() -> None:
    stripper = ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD)
    assert stripper.feed("Paris is the capital of France.") == ""
    stripper.reasoning_streamed()
    # Text that came before the reasoning may itself be leaked reasoning.
    assert stripper.holding_thought
    assert stripper.feed(" " * (STRAY_THINK_SHORT_HOLD + 1)) == ""


def test_channel_reasoning_before_any_text_shortens_the_hold() -> None:
    stripper = ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD)
    stripper.reasoning_streamed()
    assert stripper.feed("The answer is 4, since 2 + 2 = 4.") == ""
    tail = " It always has been." * 8
    released = stripper.feed(tail)
    assert released
    assert released + stripper.flush() == f"The answer is 4, since 2 + 2 = 4.{tail}"


def test_a_lone_closing_tag_inside_the_short_hold_still_drops_leaked_reasoning() -> None:
    stripper = ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD)
    stripper.reasoning_streamed()
    assert stripper.feed("Simple question.") == ""
    assert stripper.feed(f"{THINK_CLOSE}2 + 2 = 4") + stripper.flush() == "2 + 2 = 4"


def test_a_think_block_is_a_held_thought() -> None:
    stripper = ThinkStripper()
    assert stripper.feed("<think>the user wants a sum") == ""
    assert stripper.holding_thought
    assert stripper.feed("</think>4") + stripper.flush() == "4"
    assert not stripper.holding_thought


def test_without_a_hold_nothing_is_a_held_thought() -> None:
    stripper = ThinkStripper()
    stripper.reasoning_streamed()
    assert stripper.feed("Hello there") == "Hell"
    assert not stripper.holding_thought


async def _glm_reply(*chunks: SimpleNamespace) -> str:
    provider = _ready(*chunks)
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=provider)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="glm-5.3-flash",
                messages=[{"role": "user", "content": "what is 2 + 2?"}],
                max_tokens=50,
                thinking="off",
            )
        ]
    return "".join(tokens)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        # No reasoning channel: the whole reasoning leaked into the text.
        [chunk(content="Simple question."), chunk(content=f"{THINK_CLOSE}2 + 2 = 4")],
        # Reasoning on its channel first, then the rest of it leaked into the text.
        [
            chunk(reasoning="User asks a sum."),
            chunk(content="Simple question."),
            chunk(content=f"{THINK_CLOSE}2 + 2 = 4"),
        ],
        # Leaked text first, then reasoning on its channel.
        [
            chunk(content="Simple question."),
            chunk(reasoning="more thought"),
            chunk(content=f"{THINK_CLOSE}2 + 2 = 4"),
        ],
    ],
    ids=["no-channel", "reasoning-first", "text-first"],
)
async def test_a_guarded_model_never_shows_leaked_reasoning(chunks: list[SimpleNamespace]) -> None:
    assert await _glm_reply(*chunks) == "2 + 2 = 4"


@pytest.mark.asyncio
async def test_a_guarded_model_with_channel_reasoning_shows_its_answer_early() -> None:
    answer = "Paris is the capital of France, and it sits on the Seine. " * 3
    provider = FakeStream([chunk(reasoning="Capital of France."), chunk(content=answer)])
    tokens = stream_once("glm-5.3-flash", provider)
    # Past the short hold, the text arrives while the stream is still open.
    first = await asyncio.wait_for(anext(tokens), 1)
    assert answer.startswith(first) and first
    provider.finish.set()
    assert first + "".join([token async for token in tokens]) == answer


@pytest.mark.asyncio
async def test_a_guarded_model_holds_a_clean_start_until_the_stream_ends() -> None:
    provider = FakeStream([chunk(content="Paris is the capital of France.")])
    tokens = stream_once("glm-5.3-flash", provider)
    pending = asyncio.ensure_future(anext(tokens))
    await asyncio.sleep(0.05)
    assert not pending.done()
    provider.finish.set()
    assert await pending == "Paris is the capital of France."


# ── first-reply caps ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "alias, thinking, has_next, cap",
    [
        # Auto's everyday lane: no thinking, first text in about a second.
        ("qwen-3.7-flash", "off", True, 3.0),
        ("gpt-6-luna", "off", True, 3.0),
        ("free-chat", False, True, 3.0),
        # A fast model asked to think gets no cap: it may think silently.
        ("free-chat", "hard", True, None),
        # The free plan's hard and maths lane always thinks, and streams it.
        ("glm-5.3-flash", "off", True, 4.0),
        ("glm-5.3-flash", "escalate", True, 4.0),
        # Paid reasoning lanes: their first text, or the reasoning ahead of it.
        ("smart-chat", "hard", True, 8.0),
        ("glm-5.2", "hard", True, 8.0),
        # The photo lane reads an image first; it is not the everyday lane.
        ("vision-chat", "off", True, None),
        # The last model in the chain is never capped.
        ("qwen-3.7-flash", "off", False, None),
        ("glm-5.3-flash", "off", False, None),
        ("smart-chat", "hard", False, None),
    ],
)
def test_first_reply_cap_by_lane(
    alias: str, thinking: str | bool, has_next: bool, cap: float | None
) -> None:
    assert first_reply_cap(_SETTINGS, alias, thinking, has_next=has_next) == cap


def test_a_request_with_an_image_is_not_capped() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        }
    ]
    shape = prompt_shape(messages)
    assert shape == PromptShape(chars=len("what is this?"), has_image=True)
    assert first_reply_cap(_SETTINGS, "qwen-3.7-flash", "off", has_next=True, prompt=shape) is None


def test_a_long_prompt_gets_a_longer_cap() -> None:
    ordinary = prompt_shape([{"role": "system", "content": "x" * 24_000}])
    long = prompt_shape([{"role": "system", "content": "x" * 24_000}, {"content": "y" * 80_000}])
    assert first_reply_cap(_SETTINGS, "qwen-3.7-flash", "off", has_next=True, prompt=ordinary) == 3
    # A second more for each 40k characters past an ordinary prompt.
    assert first_reply_cap(_SETTINGS, "qwen-3.7-flash", "off", has_next=True, prompt=long) == 5


def _fast_caps(**overrides: Any) -> Settings:
    return Settings(
        **{
            "mock_llm_enabled": False,
            "openrouter_api_key": "sk-or-test",
            "chat_stream_first_text_timeout_seconds": 0.15,
            "chat_stream_first_thought_timeout_seconds": 0.15,
            "chat_stream_first_content_timeout_seconds": 0.15,
            "chat_stream_timeout_seconds": 30,
            **overrides,
        }
    )


def _chain(*providers: FakeStream) -> AsyncMock:
    queue = list(providers)

    async def acompletion(**_kwargs: Any) -> FakeStream:
        return queue.pop(0)

    return AsyncMock(side_effect=acompletion)


async def _reply(
    alias: str,
    fallbacks: list[str],
    fake: AsyncMock,
    settings: Settings,
    *,
    thinking: str = "off",
    attempts: list[StreamAttempt] | None = None,
    may_try: Any = None,
) -> str:
    meta: dict[str, str] = {}
    with patch.object(litellm_gateway, "acompletion", fake):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias=alias,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                fallback_aliases=fallbacks,
                stream_meta=meta,
                thinking=thinking,
                attempts=attempts,
                may_try=may_try,
            )
        ]
    return f"{meta['model_alias']}: {''.join(tokens)}"


def _ready(*chunks: SimpleNamespace, delay: float = 0.0) -> FakeStream:
    provider = FakeStream(list(chunks), delay=delay)
    provider.finish.set()
    return provider


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_silent_everyday_model_gives_way_after_the_first_text_cap() -> None:
    silent = FakeStream([])  # opens, then never sends a chunk
    fake = _chain(silent, _ready(chunk(content="Hello there, friend.")))
    started = time.monotonic()
    reply = await _reply("qwen-3.7-flash", ["free-chat"], fake, _fast_caps())
    assert reply == "free-chat: Hello there, friend."
    # The idle timeout is 30 s: the cap moved on in a fraction of a second.
    assert time.monotonic() - started < 2.0


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_slow_opening_counts_against_the_first_text_cap() -> None:
    async def hangs(**_kwargs: Any) -> FakeStream:
        await asyncio.sleep(5)
        raise AssertionError("never opens in time")

    queue: list[Any] = [hangs, _ready(chunk(content="Hello there, friend."))]

    async def acompletion(**kwargs: Any) -> FakeStream:
        step = queue.pop(0)
        return await step(**kwargs) if callable(step) else step

    started = time.monotonic()
    settings = _fast_caps(chat_stream_connect_timeout_seconds=15)
    reply = await _reply(
        "qwen-3.7-flash", ["free-chat"], AsyncMock(side_effect=acompletion), settings
    )
    assert reply == "free-chat: Hello there, friend."
    assert time.monotonic() - started < 2.0


def _opens_after(seconds: float, provider: FakeStream) -> Any:
    async def opening(**_kwargs: Any) -> FakeStream:
        await asyncio.sleep(seconds)
        return provider

    return opening


def _steps(*steps: Any) -> AsyncMock:
    queue = list(steps)

    async def acompletion(**kwargs: Any) -> FakeStream:
        step = queue.pop(0)
        return await step(**kwargs) if callable(step) else step

    return AsyncMock(side_effect=acompletion)


@pytest.mark.asyncio
async def test_the_last_model_waits_out_a_slow_opening() -> None:
    # No backup: a stream that opens past the connect timeout is a slow reply,
    # not a failed one (it left round-5 textbook replies empty).
    fake = _steps(_opens_after(1.3, _ready(chunk(content="Inertia resists change."))))
    settings = _fast_caps(chat_stream_connect_timeout_seconds=1, chat_stream_timeout_seconds=5)
    reply = await _reply("smart-chat", [], fake, settings)
    assert reply == "smart-chat: Inertia resists change."


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_slow_opening_with_a_backup_still_gives_way_at_the_connect_timeout() -> None:
    slow = _opens_after(3, _ready(chunk(content="late")))
    fake = _steps(slow, _ready(chunk(content="Inertia resists change.")))
    settings = _fast_caps(
        chat_stream_connect_timeout_seconds=1,
        chat_stream_timeout_seconds=5,
        chat_stream_first_content_timeout_seconds=30,
    )
    started = time.monotonic()
    reply = await _reply("smart-chat", ["glm-5.2"], fake, settings)
    assert reply == "glm-5.2: Inertia resists change."
    assert time.monotonic() - started < 2.0


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_the_last_model_still_gives_up_on_a_stream_that_never_opens() -> None:
    # It waits the idle timeout once, then the turn fails: a second wait kept a one-model
    # user on a hung provider 60 to 120 s (2026-11-01).
    never = _opens_after(5, _ready(chunk(content="never")))
    fake = _steps(never, never)
    settings = _fast_caps(chat_stream_connect_timeout_seconds=1, chat_stream_timeout_seconds=2)
    started = time.monotonic()
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, settings)
    assert 1.8 < time.monotonic() - started < 3.0
    assert fake.await_count == 1


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_the_last_model_that_opens_and_falls_silent_is_not_waited_on_twice() -> None:
    silent = FakeStream([])  # opens, then never sends a chunk
    fake = _chain(silent, _ready(chunk(content="never asked")))
    settings = _fast_caps(chat_stream_connect_timeout_seconds=1, chat_stream_timeout_seconds=2)
    started = time.monotonic()
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, settings)
    assert time.monotonic() - started < 3.0
    assert fake.await_count == 1


@pytest.mark.parametrize(
    "first",
    [
        # A dropped connection and a fast 408 fail at once: one more try costs nothing.
        Exception("connection reset"),
        type("Timeout408", (Exception,), {"status_code": 408})("request timeout"),
    ],
)
@pytest.mark.asyncio
async def test_a_quick_failure_of_the_only_model_is_tried_once_more(first: Exception) -> None:
    fake = AsyncMock(side_effect=[first, _ready(chunk(content="v = +6 cm, behind."))])
    reply = await _reply("smart-chat", [], fake, _fast_caps())
    assert reply == "smart-chat: v = +6 cm, behind."
    assert fake.await_count == 2


@pytest.mark.asyncio
async def test_the_only_model_that_answers_nothing_is_tried_once_more() -> None:
    # A Class 10 round's reply streamed 30 s and ended with no text: with no backup,
    # the user saw "That model isn't responding".
    attempts: list[StreamAttempt] = []
    fake = _chain(_ready(chunk(content="  ")), _ready(chunk(content="v = +6 cm, behind.")))
    reply = await _reply("smart-chat", [], fake, _fast_caps(), attempts=attempts)
    assert reply == "smart-chat: v = +6 cm, behind."
    assert [(a.alias, a.failed) for a in attempts] == [("smart-chat", True), ("smart-chat", False)]


@pytest.mark.asyncio
async def test_the_last_backup_is_tried_once_more_and_no_more() -> None:
    fake = _chain(_ready(), _ready(), _ready(), _ready(chunk(content="never asked")))
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", ["glm-5.2"], fake, _fast_caps())
    assert fake.await_count == 3  # smart-chat, glm-5.2, glm-5.2 again


@pytest.mark.asyncio
async def test_a_reply_the_provider_cut_off_is_not_tried_again() -> None:
    # Reasoning to the length limit ends the same way with the same request.
    cut = chunk(reasoning="step")
    cut.choices[0].finish_reason = "length"
    fake = _chain(_ready(cut), _ready(chunk(content="never asked")))
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, _fast_caps())
    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_a_rate_limited_request_is_not_tried_again() -> None:
    limited = Exception("slow down")
    limited.status_code = 429  # type: ignore[attr-defined]
    fake = AsyncMock(side_effect=limited)
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, _fast_caps())
    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_an_attempt_that_ran_long_is_not_tried_again() -> None:
    # Past the longest a stream that never starts can take, a retry only doubles the wait.
    # Reasoning for 2.4 s and no text, where a stalled start gives up at 1 s open + 1 s idle.
    thinking = [chunk(reasoning="step") for _ in range(6)]
    fake = _chain(_ready(*thinking, delay=0.4), _ready(chunk(content="late")))
    settings = _fast_caps(chat_stream_connect_timeout_seconds=1, chat_stream_timeout_seconds=1)
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, settings)
    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_a_refused_request_is_not_tried_again() -> None:
    refused = Exception("bad request")
    refused.status_code = 400  # type: ignore[attr-defined]
    fake = AsyncMock(side_effect=refused)
    with pytest.raises(litellm_gateway.ModelUnavailableError):
        await _reply("smart-chat", [], fake, _fast_caps())
    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_a_thinking_model_is_not_capped_once_it_streams_reasoning() -> None:
    # Reasoning for well past the cap, then the answer: the same model answers.
    thinking = [chunk(reasoning="step") for _ in range(6)]
    provider = _ready(*thinking, chunk(content="The answer is 4."), delay=0.05)
    fake = _chain(provider)
    reply = await _reply("glm-5.3-flash", ["free-chat"], fake, _fast_caps())
    assert reply == "glm-5.3-flash: The answer is 4."


@pytest.mark.asyncio
async def test_a_paid_reasoning_model_streaming_its_reasoning_is_not_abandoned() -> None:
    thinking = [chunk(reasoning="step") for _ in range(6)]
    provider = _ready(*thinking, chunk(content="So x = 4."), delay=0.05)
    reply = await _reply("smart-chat", ["glm-5.2"], _chain(provider), _fast_caps(), thinking="hard")
    assert reply == "smart-chat: So x = 4."


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_silent_paid_reasoning_model_gives_way_after_its_cap() -> None:
    fake = _chain(FakeStream([]), _ready(chunk(content="So x = 4.")))
    started = time.monotonic()
    reply = await _reply("smart-chat", ["glm-5.2"], fake, _fast_caps(), thinking="hard")
    assert reply == "glm-5.2: So x = 4."
    assert time.monotonic() - started < 2.0


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_silent_thinking_model_gives_way_after_the_first_thought_cap() -> None:
    fake = _chain(FakeStream([]), _ready(chunk(content="The answer is 4.")))
    started = time.monotonic()
    reply = await _reply("glm-5.3-flash", ["free-chat"], fake, _fast_caps())
    assert reply == "free-chat: The answer is 4."
    assert time.monotonic() - started < 2.0


@pytest.mark.asyncio
async def test_no_cap_fires_after_text_has_been_sent() -> None:
    # Text, then a pause longer than the cap (but not the idle timeout).
    provider = FakeStream([chunk(content="Hello there, friend. ")])
    fake = _chain(provider)

    async def finish_later() -> None:
        await asyncio.sleep(0.4)
        provider.finish.set()

    finisher = asyncio.create_task(finish_later())
    reply = await _reply("qwen-3.7-flash", ["free-chat"], fake, _fast_caps())
    await finisher
    assert reply == "qwen-3.7-flash: Hello there, friend. "


@pytest.mark.asyncio
async def test_the_last_model_in_the_chain_is_not_capped() -> None:
    provider = FakeStream([chunk(content="Late, but here.")], delay=0.4)
    provider.finish.set()
    reply = await _reply("qwen-3.7-flash", [], _chain(provider), _fast_caps())
    assert reply == "qwen-3.7-flash: Late, but here."


# ── a recovering model's probe ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_model_another_turn_is_trying_is_passed_by_untried() -> None:
    asked: list[str] = []

    async def may_try(alias: str) -> bool:
        asked.append(alias)
        return alias != "qwen-3.7-flash"

    attempts: list[StreamAttempt] = []
    fake = _chain(_ready(chunk(content="Hello there, friend.")))
    reply = await _reply(
        "qwen-3.7-flash", ["free-chat"], fake, _fast_caps(), attempts=attempts, may_try=may_try
    )
    assert reply == "free-chat: Hello there, friend."
    assert fake.await_count == 1
    assert [a.alias for a in attempts] == ["free-chat"]
    # The last model is tried whatever the gate says, so it is not asked.
    assert asked == ["qwen-3.7-flash"]


@pytest.mark.asyncio
async def test_the_last_model_is_tried_whatever_the_probe_says() -> None:
    async def may_try(_alias: str) -> bool:
        return False

    fake = _chain(_ready(chunk(content="Hello there, friend.")))
    reply = await _reply("qwen-3.7-flash", [], fake, _fast_caps(), may_try=may_try)
    assert reply == "qwen-3.7-flash: Hello there, friend."


# ── what each model tried did ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_each_model_tried_is_recorded_with_its_outcome() -> None:
    attempts: list[StreamAttempt] = []
    fake = _chain(FakeStream([]), _ready(chunk(content="Hello there, friend.")))
    with patch.object(litellm_gateway, "acompletion", fake):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_fast_caps(),
                model_alias="qwen-3.7-flash",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                fallback_aliases=["free-chat"],
                thinking="off",
                attempts=attempts,
            )
        ]
    assert "".join(tokens) == "Hello there, friend."
    assert [(a.alias, a.failed) for a in attempts] == [
        ("qwen-3.7-flash", True),
        ("free-chat", False),
    ]
    # The silent model never started; the one that answered did, quickly.
    assert attempts[0].first_delta_ms is None
    assert attempts[1].first_delta_ms is not None and attempts[1].first_delta_ms < 1000


@pytest.mark.asyncio
async def test_a_reply_that_fails_partway_is_recorded_as_failed() -> None:
    attempts: list[StreamAttempt] = []
    broken = FakeStream([chunk(content="The first half of it")], error=RuntimeError("reset"))
    with patch.object(litellm_gateway, "acompletion", _chain(broken)):
        with pytest.raises(litellm_gateway.ModelUnavailableError):
            async for _ in litellm_gateway.stream_chat_completion(
                settings=_fast_caps(),
                model_alias="qwen-3.7-flash",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                fallback_aliases=["free-chat"],
                thinking="off",
                attempts=attempts,
            ):
                pass
    assert [(a.alias, a.failed) for a in attempts] == [("qwen-3.7-flash", True)]


class _ProviderError(Exception):
    def __init__(self, status_code: int | None) -> None:
        super().__init__(f"provider said {status_code}")
        self.status_code = status_code


@pytest.mark.parametrize(
    "error, cause",
    [
        (_ProviderError(400), "request"),
        (_ProviderError(401), "request"),
        (_ProviderError(403), "request"),
        (_ProviderError(413), "request"),
        (_ProviderError(408), "timeout"),
        (TimeoutError(), "timeout"),
        (_ProviderError(429), "rate_limit"),
        (_ProviderError(500), "server"),
        (_ProviderError(503), "server"),
        (_ProviderError(None), "connection"),
        (ConnectionResetError(), "connection"),
    ],
)
def test_provider_fault(error: BaseException, cause: str) -> None:
    assert provider_fault(error) == cause


async def _attempts_for(*providers: Any, settings: Settings | None = None) -> list[StreamAttempt]:
    queue = list(providers)

    async def acompletion(**_kwargs: Any) -> FakeStream:
        step = queue.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    attempts: list[StreamAttempt] = []
    await _reply(
        "qwen-3.7-flash",
        ["free-chat"],
        AsyncMock(side_effect=acompletion),
        settings or _fast_caps(),
        attempts=attempts,
    )
    return attempts


@pytest.mark.asyncio
async def test_a_request_the_provider_refused_is_not_the_models_failure() -> None:
    attempts = await _attempts_for(_ProviderError(413), _ready(chunk(content="Hello there.")))
    refused, answered = attempts
    assert (refused.failed, refused.cause, refused.model_failed) == (True, "request", False)
    assert (answered.failed, answered.model_failed) == (False, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first, cause",
    [
        (_ProviderError(503), "server"),
        (_ProviderError(429), "rate_limit"),
        (FakeStream([]), "cap"),
        (_ready(chunk(content="   ")), "empty"),
    ],
    ids=["server", "rate-limit", "cap", "empty"],
)
async def test_the_models_own_failures_count_against_it(first: Any, cause: str) -> None:
    attempts = await _attempts_for(first, _ready(chunk(content="Hello there.")))
    assert (attempts[0].failed, attempts[0].cause, attempts[0].model_failed) == (True, cause, True)


# ── the thinking signal ────────────────────────────────────────────────────────


async def _signals(alias: str, *chunks: SimpleNamespace) -> list[str]:
    """What the caller sees, in order: each text, and "THINKING" when it is told."""
    seen: list[str] = []

    async def on_thinking() -> None:
        seen.append("THINKING")

    provider = _ready(*chunks)
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=provider)):
        async for token in litellm_gateway.stream_chat_completion(
            settings=_SETTINGS,
            model_alias=alias,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50,
            on_thinking=on_thinking,
        ):
            seen.append(token)
    return seen


@pytest.mark.asyncio
async def test_reasoning_on_its_own_channel_is_thinking_before_the_text() -> None:
    seen = await _signals(
        "smart-chat",
        chunk(reasoning="Try x = 4."),
        chunk(reasoning="Check: 4 + 4 = 8."),
        chunk(content="So x = 4, since 4 + 4 = 8."),
    )
    assert seen[0] == "THINKING"
    assert seen.count("THINKING") == 1
    assert "".join(seen[1:]) == "So x = 4, since 4 + 4 = 8."


@pytest.mark.asyncio
async def test_a_think_block_in_the_text_is_thinking() -> None:
    seen = await _signals(
        "smart-chat", chunk(content="<think>Try x = 4."), chunk(content="</think>x = 4, done.")
    )
    assert seen[0] == "THINKING"
    assert "".join(seen[1:]) == "x = 4, done."


@pytest.mark.asyncio
async def test_a_reply_that_never_thinks_sends_no_thinking() -> None:
    seen = await _signals("qwen-3.7-flash", chunk(content="Hello there, friend."))
    assert "THINKING" not in seen


@pytest.mark.asyncio
async def test_reasoning_after_the_text_has_started_is_not_thinking() -> None:
    seen = await _signals(
        "smart-chat",
        chunk(content="Hello there, friend. "),
        chunk(reasoning="an afterthought"),
        chunk(content="How can I help?"),
    )
    assert "THINKING" not in seen


@pytest.mark.asyncio
async def test_a_thinking_status_that_fails_is_not_the_models_failure() -> None:
    async def broken() -> None:
        raise OSError("socket gone")

    provider = _ready(chunk(reasoning="Try x = 4."), chunk(content="So x = 4, since 4 + 4 = 8."))
    attempts: list[Any] = []
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=provider)):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=_SETTINGS,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=50,
                fallback_aliases=["glm-5.2"],
                on_thinking=broken,
                attempts=attempts,
            )
        ]
    assert "".join(tokens) == "So x = 4, since 4 + 4 = 8."
    assert [(a.alias, a.failed) for a in attempts] == [("smart-chat", False)]


@pytest.mark.asyncio
async def test_a_held_start_on_a_model_that_always_thinks_is_thinking() -> None:
    # GLM 5.3 with no reasoning channel: its start may be leaked reasoning.
    seen = await _signals(
        "glm-5.3-flash", chunk(content="Simple question."), chunk(content="</think>4")
    )
    assert seen == ["THINKING", "4"]
