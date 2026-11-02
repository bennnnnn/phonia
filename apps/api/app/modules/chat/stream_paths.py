"""How a turn's reply text is produced: an instant reply, the tool loop, the model stream.

``stream_pipeline.stream_and_finalize`` picks the paths for a turn and
finalizes the text they produce. A turn the tool loop leaves alone offers the reply's
own model call ``web_search`` (``tool_loop.reply_calls``): a call runs, and a second
model call writes the answer from its results.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis

from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.gateways.litellm_gateway import ModelUnavailableError
from app.models.orm import User
from app.modules.chat import tool_loop
from app.modules.chat.control_tokens import until_control_run
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.stream_events import clear_task_cancellation
from app.modules.chat.stream_health import ReplyHealth, probe_gate
from app.modules.chat.stream_status import StreamReasoningFn, StreamStatusFn, thinking_status
from app.modules.chat.tool_gate import should_classify_tool_web_search
from app.modules.chat.tool_loop import live_denial, reply_calls
from app.modules.chat.tool_loop.parts import open_parts, searchable_parts
from app.modules.chat.tool_loop.repeat_filter import without_repeats
from app.modules.chat.tool_loop.rounds import ToolRoundsOutcome
from app.modules.chat.tool_verified import with_tool_verified
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext, await_user_message_persist
from app.modules.chat.turn_prep.reading import plan_of
from app.modules.chat.worked_stream import ReplyFilter
from app.modules.chat.worked_turn import without_worked_contract
from app.modules.web_search.subject import collect_prior_user_messages, last_assistant_content

logger = logging.getLogger(__name__)

_STOP_CLOSE_TIMEOUT_SECONDS = 2.0


async def _close_stopped_stream(close: Callable[[], Any]) -> None:
    """Close a stopped provider stream without blocking the reply save."""
    with suppress(Exception, asyncio.CancelledError):
        await asyncio.wait_for(close(), _STOP_CLOSE_TIMEOUT_SECONDS)


# Provider finish_reason values that mean the reply stopped short of a
# complete answer. "stop" is a normal end; these are not.
_INCOMPLETE_FINISH_REASONS = frozenset({"length", "max_tokens", "content_filter"})


async def run_instant_reply_path(
    ctx: StreamContext,
    *,
    should_cancel: Callable[[], bool] | None,
    accum: StreamAccum,
) -> AsyncIterator[str]:
    if not (should_cancel and should_cancel()):
        if ctx.instant_reply is None:
            return
        await await_user_message_persist(ctx)
        if ctx.timing is not None:
            ctx.timing.mark_first_token()
        accum.parts.append(ctx.instant_reply)
        accum.shown.append(ctx.instant_reply)
        yield ctx.instant_reply
    else:
        accum.mark_user_stop()


@dataclass(frozen=True)
class _LoopGate:
    """What the tool-loop gate reads about a turn: its words, and what already answered it."""

    content: str
    lightweight: bool
    has_instant_reply: bool
    has_verified_math: bool
    has_search_sources: bool
    # Tools the turn's pre-work already ran without an answer.
    skip_tools: frozenset[str] = frozenset()

    @classmethod
    def of(cls, ctx: StreamContext) -> _LoopGate:
        sources = ctx.search_sources if isinstance(ctx.search_sources, list) else []
        return cls(
            content=ctx.user_message_content if isinstance(ctx.user_message_content, str) else "",
            lightweight=bool(ctx.lightweight_turn),
            has_instant_reply=ctx.instant_reply is not None,
            has_verified_math=ctx.verified_subject is not None,
            has_search_sources=bool(sources),
            skip_tools=tool_loop.spent_tools(
                solve_timed_out=getattr(ctx, "solve_timed_out", False) is True,
                photo_missed=getattr(ctx, "photo_missed", False) is True,
            ),
        )

    def needs_loop(
        self, settings: Settings, user: User | None, *, web_search: bool | None = None
    ) -> bool:
        return tool_loop.turn_needs_tool_loop(
            self.content,
            lightweight=self.lightweight,
            has_instant_reply=self.has_instant_reply,
            has_verified_math=self.has_verified_math,
            has_search_sources=self.has_search_sources,
            web_search=web_search,
            settings=settings,
            user=user,
            skip_tools=self.skip_tools,
        )

    def reply_tools(self, settings: Settings, prompt: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The tools the reply's model call may use, when the tool loop leaves the turn."""
        return reply_calls.reply_tools(
            settings,
            reply_calls.ReplyTurn(
                content=self.content,
                lightweight=self.lightweight,
                has_instant_reply=self.has_instant_reply,
                has_verified_math=self.has_verified_math,
                has_search_sources=self.has_search_sources,
                prior_user_messages=collect_prior_user_messages(prompt, self.content) or None,
                prior_assistant=last_assistant_content(prompt),
            ),
        )

    def may_classify(self, settings: Settings, user: User | None) -> bool:
        return should_classify_tool_web_search(
            self.content,
            settings,
            lightweight=self.lightweight,
            has_instant_reply=self.has_instant_reply,
            has_verified_math=self.has_verified_math,
            has_search_sources=self.has_search_sources,
            user=user,
        )


def _web_verdict(
    settings: Settings, ctx: StreamContext, gate: _LoopGate
) -> tuple[bool | None, list[str] | None]:
    """Whether the turn needs live results when that alone decides the loop, and the
    requests to search: each request of the message read for itself
    (``tool_loop.parts``). ``(None, None)``: the verdict cannot change the gate."""
    if not gate.may_classify(settings, ctx.user):
        return None, None
    prompt = ctx.prompt_messages if isinstance(ctx.prompt_messages, list) else []
    found = searchable_parts(
        open_parts(gate.content, has_verified_math=gate.has_verified_math, settings=settings),
        settings,
        prior_user_messages=collect_prior_user_messages(prompt, gate.content) or None,
        prior_assistant=last_assistant_content(prompt),
    )
    return bool(found), found if plan_of(gate.content, settings).multi else None


def _apply_tool_rounds(ctx: StreamContext, rounds: ToolRoundsOutcome) -> None:
    """What the tool rounds found becomes the turn's: the messages the stream reads,
    a verified block, a terminal picture, search sources the prompt path lacked."""
    ctx.prompt_messages, tool_verified, terminal_image, tool_search_hits = rounds
    if tool_verified is not None:
        question = ctx.user_message_content or ""
        locale = ctx.user.locale if ctx.user is not None else None
        ctx.verified_subject = with_tool_verified(
            ctx.verified_subject, tool_verified, question, locale
        )
        if ctx.worked is not None and ctx.verified_subject is not None:
            # A tool checked the answer: the reply copies it, as any verified reply does.
            ctx.prompt_messages, ctx.worked = without_worked_contract(ctx.prompt_messages), None
    if terminal_image is not None:
        ctx.terminal_image_message_id = terminal_image.message_id
        ctx.terminal_image_content = terminal_image.final_content
        ctx.terminal_image_model = terminal_image.resolved_model
    if tool_search_hits and not ctx.search_sources:
        ctx.search_sources = tool_search_hits


async def _tool_spend_blocked(
    deps: ChatTurnDeps, redis: Redis, settings: Settings, ctx: StreamContext
) -> bool:
    """At the day's cap, or with the spend unreadable (Redis down), the turn answers without
    tools: it was admitted, so an outage here is no reason to fail it."""
    try:
        capped = await deps.quota.global_spend_exceeded(redis, settings)
        reason = "global spend cap"
    except RedisUnavailableError:
        capped, reason = True, "global spend unreadable (Redis down)"
    if capped:
        logger.warning(
            "skipping MCP tool loop: %s user_id=%s chat_id=%s", reason, ctx.user_id, ctx.chat_id
        )
    return capped


async def run_tool_loop_path(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    usage: dict[str, int],
    on_status: StreamStatusFn | None,
    should_cancel: Callable[[], bool] | None,
) -> None:
    gate = _LoopGate.of(ctx)
    web_search_flag: bool | None = None
    search_parts: list[str] | None = None
    if await _tool_spend_blocked(deps, redis, settings, ctx):
        return
    # Sync heuristic first (math / news). Classifier only when
    # that gate is weak so we do not add an LLM round to already-needed turns.
    if not gate.needs_loop(settings, ctx.user):
        web_search_flag, search_parts = _web_verdict(settings, ctx, gate)
        if not gate.needs_loop(settings, ctx.user, web_search=web_search_flag):
            prompt = ctx.prompt_messages if isinstance(ctx.prompt_messages, list) else []
            ctx.reply_tools = gate.reply_tools(settings, prompt)
            if not (ctx.reply_tools or gate.has_search_sources or gate.has_instant_reply):
                ctx.denial_retry_tools = reply_calls.web_search_tool(settings)
            return
    rounds = await tool_loop.run_tool_rounds(
        settings=settings,
        messages=ctx.prompt_messages,
        usage=usage,
        on_status=on_status,
        should_cancel=should_cancel,
        user=ctx.user,
        redis=redis,
        chat_id=ctx.chat_id,
        web_search=web_search_flag,
        user_timezone=ctx.user_timezone,
        user_text=gate.content,
        user_location=ctx.search_location,
        has_verified_math=gate.has_verified_math,
        search_parts=search_parts,
        skip_tools=gate.skip_tools,
    )
    _apply_tool_rounds(ctx, rounds)


@dataclass
class _ReplyRound:
    """One model call of the reply: the tools it carries, and what it leaves behind."""

    tools: list[dict[str, Any]]
    # Goes out before the call's first token: a break after the text the call
    # before it wrote ahead of its search.
    lead: str = ""
    # The text the call before wrote ahead of its search: this call never repeats it.
    before: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)


async def run_llm_token_stream(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    usage: dict[str, int],
    should_cancel: Callable[[], bool] | None,
    outcome: TurnOutcome | None,
    on_reasoning: StreamReasoningFn | None,
    accum: StreamAccum,
    on_status: StreamStatusFn | None = None,
) -> AsyncIterator[str]:
    """The model's reply. A call it makes to its tool runs, and one more call answers."""
    requested_model = ctx.model
    health = ReplyHealth()
    may_try = probe_gate(redis, settings, ctx.probe_models)
    scaffold = ReplyFilter(accum, ctx.worked)
    if on_status is not None:
        # The model is writing now: a tool or search label must not linger.
        await on_status("composing")
    if ctx.timing is not None:
        # Reserve top-up and the tool loop have finished. The interval from
        # here includes gateway routing/retries, not only upstream inference.
        ctx.timing.mark_phase("gateway_request_start")
    reply_round = _ReplyRound(tools=list(ctx.reply_tools))
    retry_tools = list(ctx.denial_retry_tools)
    try:
        while True:
            written, shown_from = len(accum.parts), len(accum.shown)
            async with aclosing(
                _stream_round(
                    deps,
                    settings,
                    ctx,
                    reply_round,
                    _RoundHooks(health, may_try, on_reasoning, on_status),
                    usage=usage,
                    should_cancel=should_cancel,
                    accum=accum,
                    scaffold=scaffold,
                )
            ) as tokens:
                async for visible in tokens:
                    yield visible
            if resolved := reply_round.meta.get("model_alias"):
                ctx.model = resolved
            # "I can't check live scores" with no tool offered: ask again, offering search.
            if retry_tools and live_denial.asks_again(ctx, reply_round.calls, accum, written):
                accum.retract(written, shown_from)
                # A held "!" or "[" was the denial's, never drawn: the new round starts clean.
                scaffold = ReplyFilter(accum, ctx.worked)
                reply_round, retry_tools = _ReplyRound(tools=retry_tools, lead="\n\n"), []
                continue
            # Only a call that carried tools leads to another: one search a turn.
            if not (reply_round.tools and reply_round.calls) or accum.was_cancelled:
                break
            text_before = "".join(accum.parts[written:])
            await _answer_reply_calls(
                settings,
                redis,
                ctx,
                reply_round.calls,
                text_before,
                on_status=on_status,
                should_cancel=should_cancel,
            )
            if should_cancel and should_cancel():
                accum.mark_user_stop()
                break
            lead = "\n\n" if text_before.strip() else ""
            reply_round = _ReplyRound(tools=[], lead=lead, before=text_before)
        if not accum.was_cancelled and (tail := scaffold.flush()):
            accum.shown.append(tail)
            yield tail
        finish = reply_round.meta.get("finish_reason")
        if finish in _INCOMPLETE_FINISH_REASONS and not accum.was_cancelled:
            accum.mark_truncated()
    except ModelUnavailableError:
        health.failed = True
        raise
    except asyncio.CancelledError:
        clear_task_cancellation()
        accum.mark_user_stop()
        raise
    finally:
        accum.restore_retracted()
        model = reply_round.meta.get("model_alias") or ctx.model
        await health.record(redis, model, stopped=accum.was_cancelled)
    if outcome is not None and ctx.model != requested_model:
        outcome.fallback_used = True


@dataclass(frozen=True)
class _RoundHooks:
    """What every model call of one reply reports to, and asks before it tries a model."""

    health: ReplyHealth
    may_try: Callable[[str], Awaitable[bool]] | None
    on_reasoning: StreamReasoningFn | None
    on_status: StreamStatusFn | None


async def _stream_round(
    deps: ChatTurnDeps,
    settings: Settings,
    ctx: StreamContext,
    reply_round: _ReplyRound,
    hooks: _RoundHooks,
    *,
    usage: dict[str, int],
    should_cancel: Callable[[], bool] | None,
    accum: StreamAccum,
    scaffold: ReplyFilter,
) -> AsyncGenerator[str]:
    """One model call's tokens, added to the reply; its tool calls land on the round."""
    llm_stream = deps.llm.stream_chat_completion(
        settings=settings,
        model_alias=ctx.model,
        messages=ctx.prompt_messages,
        max_tokens=ctx.max_output_tokens,
        usage=usage,
        fallback_aliases=ctx.fallback_models,
        stream_meta=reply_round.meta,
        on_reasoning=hooks.on_reasoning,
        thinking=ctx.thinking,
        attempts=hooks.health.attempts,
        on_thinking=thinking_status(hooks.on_status, hooks.health.started),
        may_try=hooks.may_try,
        tools=reply_round.tools or None,
        tool_calls=reply_round.calls,
    )
    guarded = until_control_run(llm_stream)
    repeats = without_repeats(guarded, reply_round.before) if reply_round.before else None
    tokens = repeats or guarded
    try:
        async for token in tokens:
            if should_cancel and should_cancel():
                accum.mark_user_stop()
                break
            if not accum.parts:
                # The user's row commits beside the provider's time to first
                # token. No token goes out before it has: a reply to a message
                # that never saved would be neither stored nor charged. The
                # model did answer, so a failed save is not its health sample.
                hooks.health.first_token()
                await await_user_message_persist(ctx)
                if ctx.timing is not None:
                    ctx.timing.mark_first_token()
            if reply_round.lead:
                token, reply_round.lead = reply_round.lead + token, ""
            accum.parts.append(token)
            if ctx.answer_photo is not None and ctx.answer_photo.watching:
                ctx.answer_photo.feed("".join(accum.parts))
            visible = scaffold.feed(token)
            if not visible:
                continue
            accum.shown.append(visible)
            yield visible
            # Stop can land while we are parked on this yield. The consumer
            # resumes us so we halt before the next provider read and save.
            if should_cancel and should_cancel():
                accum.mark_user_stop()
                break
    except asyncio.CancelledError:
        clear_task_cancellation()
        accum.mark_user_stop()
        raise
    finally:
        if repeats is not None:
            await repeats.aclose()
        await guarded.aclose()
        close = getattr(llm_stream, "aclose", None)
        if close is not None:
            if accum.was_cancelled:
                # Closing the provider socket can outlive the stop. Do not
                # make the partial-reply save wait on it.
                create_background_task(
                    _close_stopped_stream(close),
                    name="close_stopped_stream",
                )
            else:
                await close()


async def _answer_reply_calls(
    settings: Settings,
    redis: Redis,
    ctx: StreamContext,
    calls: list[dict[str, Any]],
    text_before: str,
    *,
    on_status: StreamStatusFn | None,
    should_cancel: Callable[[], bool] | None,
) -> None:
    """Run the reply's tool calls; the next model call reads their results.

    The pages a search found become the turn's sources, so the reply gets their chips.
    A search that breaks leaves the prompt as it was: the reply answers without it.
    """
    try:
        answered = await reply_calls.answer_reply_calls(
            settings=settings,
            messages=ctx.prompt_messages,
            calls=calls,
            text_before=text_before,
            user=ctx.user,
            redis=redis,
            chat_id=ctx.chat_id,
            user_timezone=ctx.user_timezone,
            user_text=ctx.user_message_content,
            user_location=ctx.search_location,
            on_status=on_status,
            should_cancel=should_cancel,
        )
    except Exception:
        logger.exception("Reply tool calls failed chat_id=%s; answering without them", ctx.chat_id)
        return
    ctx.prompt_messages = answered.messages
    if answered.search_hits and not ctx.search_sources:
        ctx.search_sources = answered.search_hits
