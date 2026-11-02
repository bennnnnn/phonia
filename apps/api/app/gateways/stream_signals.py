"""What a streamed reply shows before its answer, and how long it may show nothing.

LiteLLM puts a provider's reasoning in ``delta.reasoning_content`` (OpenRouter's
``reasoning``). Its text is never forwarded (the chat UI must not show CoT); that
it arrives is what the stream reads: the model is thinking.

When another model can take over, an attempt that shows nothing for too long
is abandoned for it instead of waiting out the idle timeout (``first_reply_cap``).
The cap ends with the attempt's first text or first sign of thinking, which is
when the phone hears of it: a fallback after that would start the reply over.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.gateways.reasoning import thinking_value
from app.models import model_catalog
from app.models.model_catalog import ChatModel

# The catalog values that mean the model does not think.
_NO_THOUGHT = frozenset({"off", "none"})
# A cap shorter than this would end an attempt before its request is sent.
_MIN_CAP_SECONDS = 0.1
# The caps are sized for an ordinary prompt. A provider reads a longer one before
# it can answer, so the cap grows a second for each ``_PROMPT_CHARS_PER_SECOND``
# past ``_ORDINARY_PROMPT_CHARS`` (the slow end of prompt reading, ~10k tokens/s).
_ORDINARY_PROMPT_CHARS = 24_000
_PROMPT_CHARS_PER_SECOND = 40_000
# Why an attempt failed, when that was the request or our setup and not the model:
# a 4xx the provider answered (bad input, too large, a policy, auth), a missing key.
REQUEST_FAULT = "request"


def reasoning_delta(delta: Any) -> bool:
    """True when this chunk carries reasoning text on the provider's own channel."""
    text = getattr(delta, "reasoning_content", None) if delta is not None else None
    return isinstance(text, str) and bool(text.strip())


def always_thinks(route: ChatModel) -> bool:
    """The model thinks even when asked not to (its "off" level is an effort)."""
    return route.thinking_off is not None and route.thinking_off not in _NO_THOUGHT


@dataclass(frozen=True)
class PromptShape:
    """What a provider reads before its first reply: how much text, and any image."""

    chars: int = 0
    has_image: bool = False


def prompt_shape(messages: Sequence[Mapping[str, Any]]) -> PromptShape:
    chars = 0
    has_image = False
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
            continue
        for part in content if isinstance(content, list) else ():
            if not isinstance(part, Mapping):
                continue
            if part.get("type") == "image_url":
                has_image = True
            elif isinstance(text := part.get("text"), str):
                chars += len(text)
    return PromptShape(chars=chars, has_image=has_image)


def first_reply_cap(
    settings: Settings,
    alias: str,
    thinking: bool | str | None,
    *,
    has_next: bool,
    prompt: PromptShape | None = None,
) -> float | None:
    """How long one attempt may show nothing (no text, no thinking) before the next
    model takes over; None waits it out.

    The last model in the chain has no cap: waiting is all that is left, and a cap
    would only fail the turn sooner. Nor does a request that shows the model an
    image: how long reading it takes is not a sign of a failing provider.
    """
    shape = prompt or PromptShape()
    if not has_next or shape.has_image:
        return None
    route = model_catalog.get(alias)
    if always_thinks(route):
        # The free plan's hard and maths lane: its reasoning streams from the start.
        seconds = settings.chat_stream_first_thought_timeout_seconds
    elif route.tier == "fast" and thinking_value(route, thinking) in _NO_THOUGHT:
        # Auto's everyday lane: no thinking, first text in about a second.
        seconds = settings.chat_stream_first_text_timeout_seconds
    elif model_catalog.is_reasoning_alias(alias):
        # A paid reasoning lane: its first text, or the reasoning ahead of it.
        seconds = settings.chat_stream_first_content_timeout_seconds
    else:
        return None
    extra = max(0, shape.chars - _ORDINARY_PROMPT_CHARS) / _PROMPT_CHARS_PER_SECOND
    return seconds + extra


class FirstReplyWatch:
    """One attempt's first-reply cap, and what it has shown so far."""

    def __init__(self, cap: float | None) -> None:
        # (seconds, deadline), or None without a cap.
        self._cap = None if cap is None else (cap, time.monotonic() + max(_MIN_CAP_SECONDS, cap))
        self.shown_text = False
        self.shown_thinking = False

    def _live(self) -> tuple[float, float] | None:
        if self._cap is None or self.shown_text or self.shown_thinking:
            return None
        return self._cap

    def bound(self, limit: float) -> float:
        """``limit`` cut to the time left on the cap, while it runs."""
        if (live := self._live()) is not None:
            limit = min(limit, live[1] - time.monotonic())
        return max(0.0, limit)

    def expired(self) -> str | None:
        """The cap that ran out ("first reply 3.0s"), or None."""
        live = self._live()
        if live is None or time.monotonic() < live[1]:
            return None
        return f"first reply {live[0]:.1f}s"

    def saw(self, *, text: str, thinking: bool) -> bool:
        """Record one chunk: visible ``text`` or ``thinking`` ends the cap.

        True the first time the model is seen thinking before any visible text,
        which is when the phone can be told it is thinking.
        """
        if text.strip():
            self.shown_text = True
        if not thinking or self.shown_text or self.shown_thinking:
            return False
        self.shown_thinking = True
        return True


def provider_fault(exc: BaseException) -> str:
    """Why a provider call failed: "timeout", "rate_limit", "server", "connection",
    or ``REQUEST_FAULT`` for a 4xx the provider answered."""
    status = getattr(exc, "status_code", None)
    if isinstance(exc, TimeoutError) or status == 408:
        return "timeout"
    if not isinstance(status, int):
        return "connection"
    if status == 429:
        return "rate_limit"
    if 400 <= status < 500:
        return REQUEST_FAULT
    return "server"


@dataclass
class StreamAttempt:
    """One model's try at a reply, as the caller's health record reads it."""

    alias: str
    failed: bool = False
    # Why it failed: a provider fault ("timeout", "server", …), "cap" (it showed
    # nothing in time), "empty" (it answered nothing) or ``REQUEST_FAULT``.
    cause: str | None = None
    # From the request to the provider's first reasoning or text; None if none came.
    first_delta_ms: int | None = None
    # From the request to the end of the try; None while it streams, or after a stop.
    elapsed_ms: int | None = None
    _started: float = field(default_factory=time.monotonic, init=False, repr=False)

    def _ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    @property
    def model_failed(self) -> bool:
        """It failed, and not over the request: the failure counts against the model."""
        return self.failed and self.cause != REQUEST_FAULT

    def delta(self) -> None:
        """The provider sent reasoning or text."""
        if self.first_delta_ms is None:
            self.first_delta_ms = self._ms()

    def end(self, *, failed: bool, cause: str | None = None) -> None:
        self.failed = failed
        self.cause = cause if failed else None
        self.elapsed_ms = self._ms()
