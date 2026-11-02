import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any, NamedTuple, Self

# Re-exported: the completion gateways call the provider through this module.
from litellm import acompletion as acompletion

from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.gateways import mock_llm
from app.gateways.prompt_cache import with_cache_breakpoint
from app.gateways.reasoning import reasoning_body
from app.gateways.stream_signals import (
    REQUEST_FAULT,
    FirstReplyWatch,
    StreamAttempt,
    first_reply_cap,
    prompt_shape,
    provider_fault,
    reasoning_delta,
)
from app.gateways.stream_tool_calls import StreamedToolCalls
from app.gateways.stream_usage import apply_usage, merge_attempt_usage

# The completion kinds split out of this module are part of its public surface
# (callers use ``litellm_gateway.complete_structured`` and friends). They make
# their provider calls through this module (``acompletion``, ``resolve_route``,
# ``_litellm_kwargs``), importing it at call time: at load it would be a cycle,
# and a test patches each seam once, here.
from app.gateways.structured_completion import complete_structured as complete_structured
from app.gateways.text_completion import complete_text as complete_text
from app.gateways.text_tool_calls import TextToolCalls
from app.gateways.think_stripper import STRAY_THINK_LEAD_HOLD, ThinkStripper
from app.gateways.tool_completion import complete_with_tools as complete_with_tools
from app.gateways.vision_completion import vision_completion as vision_completion
from app.models import model_catalog
from app.models.model_catalog import ChatModel

logger = logging.getLogger(__name__)


class ModelUnavailableError(Exception):
    """Primary (and optional fallback) chat models could not stream."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "model_unavailable",
        failed_alias: str | None = None,
        cause: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.failed_alias = failed_alias
        # Why the model call failed (``stream_signals.StreamAttempt.cause``).
        self.cause = cause

    @classmethod
    def for_alias(
        cls, alias: str, *, code: str = "model_unavailable", cause: str | None = None
    ) -> Self:
        """The user-facing "model isn't responding" error for one failed alias."""
        return cls(_CHAT_MODEL_UNAVAILABLE_MSG, code=code, failed_alias=alias, cause=cause)


_CHAT_MODEL_UNAVAILABLE_MSG = (
    "That model isn't responding right now. Try again — or pick a different model."
)


def resolve_route(alias: str) -> ChatModel:
    return model_catalog.get(alias)


def _litellm_kwargs(
    settings: Settings,
    route: ChatModel,
    *,
    latency_sensitive: bool = False,
    thinking: bool | str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    api_key = getattr(settings, route.api_key_field, "")
    if not api_key:
        raise ModelUnavailableError.for_alias(route.id, cause=REQUEST_FAULT)
    kwargs["api_key"] = api_key
    if route.api_base:
        kwargs["api_base"] = route.api_base
    if route.model.startswith("openrouter/"):
        kwargs.setdefault(
            "extra_headers",
            {
                "HTTP-Referer": "https://github.com/bennnnnn/recall",
                "X-Title": "Recall",
            },
        )
        # OpenRouter's default route is price-weighted. The user-visible token
        # stream values TTFT more than small provider-price differences, so ask
        # OpenRouter to prefer the endpoint with the lowest observed latency.
        # Background jobs keep the default routing; tool selection is also
        # on the critical path before the user-visible stream.
        if latency_sensitive:
            kwargs["extra_body"] = {"provider": {"sort": "latency"}}
    # Ordinary questions must not wait on a thinking pass; a hard one gets the
    # cheapest level that thinks, and a disputed answer one level more. Each
    # value is one the model lists, so an unsupported level is never sent.
    reasoning = reasoning_body(route, thinking)
    if reasoning is not None:
        kwargs.setdefault("extra_body", {})
        kwargs["extra_body"]["reasoning"] = reasoning
    return kwargs


async def stream_chat_completion(
    *,
    settings: Settings,
    model_alias: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    usage: dict[str, int] | None = None,
    fallback_aliases: list[str] | None = None,
    stream_meta: dict[str, str] | None = None,
    on_reasoning: Callable[[str], Awaitable[None]] | None = None,
    thinking: bool | str | None = None,
    attempts: list[StreamAttempt] | None = None,
    on_thinking: Callable[[], Awaitable[None]] | None = None,
    may_try: Callable[[str], Awaitable[bool]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Stream one reply, moving down ``fallback_aliases`` until a model answers.

    ``attempts`` gets one record per model tried, in order: which failed (before
    its text, or partway), and how fast each provider started. ``on_thinking``
    runs when a model is seen reasoning before any of its text. ``may_try`` is
    asked before each model but the last; False passes it by untried. ``tools``
    go to a model that takes them, and the calls its reply makes land on
    ``tool_calls``: a call answers too.
    """
    if mock_llm.should_mock_llm(settings):
        logger.info("Using mock LLM stream for alias=%s", model_alias)
        if stream_meta is not None:
            stream_meta["model_alias"] = model_alias
        async for token in mock_llm.mock_stream(messages=messages):
            yield token
        return

    aliases = [model_alias, *(fallback_aliases or [])]
    shape = prompt_shape(messages)
    last_error: ModelUnavailableError | None = None

    for index, alias in enumerate(aliases):
        has_next = index < len(aliases) - 1
        if has_next and may_try is not None and not await may_try(alias):
            # A recovering model that another turn is trying (model health's probe).
            logger.info("Chat stream %s passed over: another turn is trying it", alias)
            continue
        # Buffer until the first non-whitespace token: a whitespace-only "success" stream
        # (a flaky provider's quirk) falls through instead of locking in an empty reply.
        pending: list[str] = []
        started = False
        # Discarded attempts add no provider tokens to the caller's daily quota: only the
        # attempt that produced content merges (tool-loop usage is already on `usage`).
        attempt_usage: dict[str, int] = {}
        attempt_calls: list[dict[str, Any]] = []
        cap = first_reply_cap(settings, alias, thinking, has_next=has_next, prompt=shape)
        attempt = StreamAttempt(alias)
        if attempts is not None:
            attempts.append(attempt)
        try:
            if stream_meta is not None:
                stream_meta.pop("finish_reason", None)
            async for token in _stream_chat_once(
                settings=settings,
                model_alias=alias,
                messages=messages,
                max_tokens=max_tokens,
                usage=attempt_usage,
                on_reasoning=on_reasoning,
                stream_meta=stream_meta,
                thinking=thinking,
                first_content_timeout_seconds=cap,
                open_timeout_seconds=_open_wait(settings, has_next=has_next),
                attempt=attempt,
                on_thinking=on_thinking,
                tools=tools,
                tool_calls=attempt_calls,
            ):
                if not started:
                    pending.append(token)
                    if not "".join(pending).strip():
                        continue
                    started = True
                    for piece in pending:
                        yield piece
                    pending.clear()
                    continue
                yield token
            if started or attempt_calls:
                attempt.end(failed=False)
                merge_attempt_usage(usage, attempt_usage)
                if tool_calls is not None:
                    tool_calls.extend(attempt_calls)
                if stream_meta is not None:
                    stream_meta["model_alias"] = alias
                return
            raise _answered_nothing(alias, aliases[index + 1] if has_next else None)
        except ModelUnavailableError as exc:
            last_error = exc
            attempt.end(failed=True, cause=exc.cause)
            # Mid-stream failure: client already has partial tokens — falling
            # back would concatenate partial + full into one persisted reply.
            if started:
                merge_attempt_usage(usage, attempt_usage)
                raise
            if has_next:
                logger.warning("Chat stream %s unavailable; trying %s", alias, aliases[index + 1])
                continue
            if _try_again(aliases, exc, attempt, settings, stream_meta):
                continue
            failed = exc.failed_alias or alias
            if stream_meta is not None:
                stream_meta["model_alias"] = failed
            raise ModelUnavailableError.for_alias(failed, cause=exc.cause) from exc

    if last_error is not None:
        raise last_error


# A reply the provider ended itself, at the length limit or a filter: the same request
# ends the same way.
_FINAL_FINISH_REASONS = frozenset({"length", "max_tokens", "content_filter"})
# A retry gives a reply that never got going a second chance, not a second full reply.
_NO_RETRY_CAUSES = frozenset({REQUEST_FAULT, "rate_limit"})


def _try_again(
    aliases: list[str],
    exc: ModelUnavailableError,
    attempt: StreamAttempt,
    settings: Settings,
    stream_meta: dict[str, str] | None,
) -> bool:
    """The last model failed before any text: it is tried once more (appended to
    ``aliases``): a one-model user has no backup, and one empty or stalled stream left the
    reply empty. Not when the provider refused or rate-limited the request, ended the reply
    itself, or a wait timed out past the connect timeout (a hung provider kept a one-model
    user 60 to 120 s, 2026-11-01), or the attempt ran longer than a stalled start can."""
    alias = attempt.alias
    if exc.cause in _NO_RETRY_CAUSES or (len(aliases) > 1 and aliases[-2] == alias):
        return False
    if stream_meta is not None and stream_meta.get("finish_reason") in _FINAL_FINISH_REASONS:
        return False
    elapsed = (attempt.elapsed_ms or 0) / 1000
    stalled_start = _open_wait(settings, has_next=False) + settings.chat_stream_timeout_seconds
    timed_out = exc.cause == "timeout" and elapsed > settings.chat_stream_connect_timeout_seconds
    if timed_out or elapsed > stalled_start:
        return False
    logger.warning("Chat stream %s answered nothing; trying it once more", alias)
    aliases.append(alias)
    return True


def _open_wait(settings: Settings, *, has_next: bool) -> float:
    """How long one attempt waits for its stream to open. The short connect timeout
    is there so the next model can take over; the last model has no next, and a
    slow opening is a slow reply, so it gets the idle timeout a stalled stream gets."""
    if has_next:
        return settings.chat_stream_connect_timeout_seconds
    return max(settings.chat_stream_connect_timeout_seconds, settings.chat_stream_timeout_seconds)


def _answered_nothing(alias: str, fallback: str | None) -> ModelUnavailableError:
    logger.warning(
        "Chat stream %s returned no content%s",
        alias,
        f"; retrying with fallback {fallback}" if fallback else "",
    )
    return ModelUnavailableError.for_alias(alias, cause="empty")


def _call_kwargs(
    settings: Settings,
    route: ChatModel,
    thinking: bool | str | None,
    tools: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], StreamedToolCalls | None]:
    """The streamed call's provider arguments, and where its tool calls fold: None when
    the model was offered none (one that takes no tools gets none)."""
    kwargs = _litellm_kwargs(settings, route, latency_sensitive=True, thinking=thinking)
    calls = StreamedToolCalls() if tools and route.supports_tools else None
    if calls is not None:
        kwargs.update(tools=tools, tool_choice="auto")
    return kwargs, calls


_PROVIDER_CLOSE_TIMEOUT_SECONDS = 2.0


async def _close_provider_stream(close: Callable[[], Awaitable[None]]) -> None:
    """Close the provider socket after a stop without blocking the caller."""
    with suppress(Exception, asyncio.CancelledError):
        await asyncio.wait_for(close(), _PROVIDER_CLOSE_TIMEOUT_SECONDS)


class _ChunkRead(NamedTuple):
    # Reply text the chunk releases (the think filter may hold some back).
    text: str
    # The model is seen thinking: reasoning on its own channel, or text held as one.
    thinking: bool
    # The provider sent reasoning or text at all.
    delta: bool
    # The chunk carried a tool call.
    called: bool = False


def _read_chunk(
    chunk: Any,
    *,
    usage: dict[str, int] | None,
    stream_meta: dict[str, str] | None,
    stripper: ThinkStripper,
    calls: StreamedToolCalls | None = None,
    text_calls: TextToolCalls | None = None,
) -> _ChunkRead:
    """What one provider chunk shows. ``calls`` is None when the request offered no
    tools: a stray call is not read. ``text_calls`` holds a call written as text."""
    apply_usage(usage, chunk)
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return _ChunkRead("", thinking=False, delta=False)
    reason = getattr(choices[0], "finish_reason", None)
    if reason and stream_meta is not None:
        stream_meta["finish_reason"] = str(reason)
    delta = getattr(choices[0], "delta", None)
    reasoning = reasoning_delta(delta)
    if reasoning:
        # Text after reasoning on its own channel is most likely the answer.
        stripper.reasoning_streamed()
    content = getattr(delta, "content", None) or "" if delta is not None else ""
    text = stripper.feed(content) if content else ""
    if text and text_calls is not None:
        found_before = text_calls.found
        text = text_calls.feed(text)
        called_in_text = text_calls.found and not found_before
    else:
        called_in_text = False
    called = calls is not None and calls.fold(getattr(delta, "tool_calls", None))
    called = called or (called_in_text and calls is not None)
    return _ChunkRead(
        text, reasoning or stripper.holding_thought, reasoning or bool(content) or called, called
    )


async def _tell_thinking(on_thinking: Callable[[], Awaitable[None]], model_alias: str) -> None:
    """Best-effort: a status that fails to reach the client is not the model's failure."""
    try:
        await on_thinking()
    except Exception:
        logger.warning("Thinking status failed for alias=%s", model_alias, exc_info=True)


async def _stream_chat_once(
    *,
    settings: Settings,
    model_alias: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    usage: dict[str, int] | None = None,
    on_reasoning: Callable[[str], Awaitable[None]] | None = None,
    stream_meta: dict[str, str] | None = None,
    first_content_timeout_seconds: float | None = None,
    open_timeout_seconds: float | None = None,
    thinking: bool | str | None = None,
    attempt: StreamAttempt | None = None,
    on_thinking: Callable[[], Awaitable[None]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """One model's stream. ``first_content_timeout_seconds`` caps the wait for its
    first text or reasoning (``stream_signals.first_reply_cap``); a tool call ends
    it too. ``open_timeout_seconds`` (default the connect timeout) bounds the open."""
    open_seconds = open_timeout_seconds or settings.chat_stream_connect_timeout_seconds
    route = resolve_route(model_alias)
    kwargs, calls = _call_kwargs(settings, route, thinking, tools)
    stripper = ThinkStripper(lead_hold=STRAY_THINK_LEAD_HOLD if route.stray_think_guard else 0)
    text_calls = TextToolCalls(calls)
    # Signature kept so WS/SSE callers stay unchanged; CoT is not forwarded.
    _ = on_reasoning
    watch = FirstReplyWatch(first_content_timeout_seconds)
    response = None
    try:
        # A first-reply cap also bounds the wait for the stream to open.
        async with asyncio.timeout(watch.bound(open_seconds)):
            response = await acompletion(
                model=route.model,
                messages=with_cache_breakpoint(
                    messages, route, enabled=settings.prompt_cache_breakpoints_enabled
                ),
                stream=True,
                max_tokens=max_tokens,
                stream_options={"include_usage": True},
                **kwargs,
            )
        # Idle timeout per chunk, plus a hard wall-clock cap on the whole reply.
        idle_seconds = settings.chat_stream_timeout_seconds
        max_seconds = max(1, settings.chat_stream_max_seconds)
        deadline = time.monotonic() + max_seconds
        stream_iter = response.__aiter__()

        async def _next_chunk() -> Any | None:
            try:
                return await stream_iter.__anext__()
            except StopAsyncIteration:
                return None

        def stop_reason() -> tuple[str, str] | None:
            """(what ran out, the failure's cause), or None while the stream may go on."""
            if time.monotonic() >= deadline:
                return f"wall-clock {max_seconds}s", "timeout"
            cap = watch.expired()
            return (cap, "cap") if cap is not None else None

        while True:
            if (stop := stop_reason()) is not None:
                raise _gave_up(model_alias, *stop)
            remaining = deadline - time.monotonic()
            try:
                chunk = await asyncio.wait_for(
                    _next_chunk(),
                    timeout=watch.bound(min(idle_seconds, remaining)),
                )
            except TimeoutError as exc:
                stop = stop_reason() or (f"idle {idle_seconds}s", "timeout")
                raise _gave_up(model_alias, *stop) from exc
            if chunk is None:
                break
            read = _read_chunk(
                chunk,
                usage=usage,
                stream_meta=stream_meta,
                stripper=stripper,
                calls=calls,
                text_calls=text_calls,
            )
            if read.delta and attempt is not None:
                attempt.delta()
            watch.shown_text = watch.shown_text or read.called  # a call begins the reply
            if watch.saw(text=read.text, thinking=read.thinking) and on_thinking is not None:
                await _tell_thinking(on_thinking, model_alias)
            if read.text:
                yield read.text
        tail = text_calls.feed(stripper.flush()) + text_calls.flush()
        if tail:
            yield tail
        if tool_calls is not None and calls is not None:
            tool_calls.extend(calls.calls())
    except TimeoutError as exc:
        # Only the wait for the stream to open raises one here.
        raise _did_not_open(model_alias, watch.expired(), open_seconds) from exc
    except ModelUnavailableError:
        raise
    except Exception as exc:
        logger.exception("LiteLLM streaming failed for alias=%s", model_alias)
        raise ModelUnavailableError.for_alias(model_alias, cause=provider_fault(exc)) from exc
    finally:
        await _close_response(response)


async def _close_response(response: Any) -> None:
    """Close a provider stream. A stop cancels the reply's task: awaiting the socket close
    then either raises again at once or waits out the provider, and the partial reply
    never gets saved, so it closes in the background."""
    close = getattr(response, "aclose", None)
    if close is None:
        return
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        create_background_task(_close_provider_stream(close), name="close_provider_stream")
    else:
        with suppress(Exception):
            await close()


def _did_not_open(model_alias: str, cap: str | None, open_seconds: float) -> ModelUnavailableError:
    """The stream never opened: within the first-reply ``cap``, when one ran out."""
    reason = cap or f"connect {open_seconds}s"
    logger.warning("LiteLLM stream for alias=%s did not open: %s", model_alias, reason)
    cause = "cap" if cap is not None else "timeout"
    return ModelUnavailableError.for_alias(model_alias, cause=cause)


def _gave_up(model_alias: str, ran_out: str, cause: str) -> ModelUnavailableError:
    logger.warning("LiteLLM stream for alias=%s gave up: %s", model_alias, ran_out)
    return ModelUnavailableError.for_alias(model_alias, cause=cause)
