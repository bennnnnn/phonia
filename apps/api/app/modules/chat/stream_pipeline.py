"""One turn's reply: produce it, finalize it, then register its save and post-turn jobs.

The text comes from ``stream_paths`` (instant reply, tool loop, model stream);
``finalize_passes`` turns it into the reply that persists.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core import shutdown
from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.core.ids import uuid7
from app.gateways.litellm_gateway import ModelUnavailableError
from app.models import model_catalog
from app.modules.chat.finalize_passes import enrich_final_content
from app.modules.chat.finalize_registry import mark_pending_finalize, register_pending_finalize
from app.modules.chat.post_turn import enqueue_post_turn_jobs
from app.modules.chat.prompt_inject import conversation_turns
from app.modules.chat.quality import detect_quality_issues
from app.modules.chat.related_prompts import schedule_related_prompts
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.stream_events import await_ignoring_cancel, clear_task_cancellation
from app.modules.chat.stream_paths import (
    run_instant_reply_path,
    run_llm_token_stream,
    run_tool_loop_path,
)
from app.modules.chat.stream_status import StreamReasoningFn, StreamStatusFn
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext, await_user_message_persist
from app.modules.chat.turn_resources import TurnResources
from app.modules.chat.turn_settle import finalize_stream_turn_db
from app.modules.chat.turn_trace import emit_turn_trace
from app.modules.images.answer_photo import AnswerPhoto
from app.services import quota as quota_service

logger = logging.getLogger(__name__)


def log_background_task_failure(task: asyncio.Task[Any], message: str) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception(message, exc_info=exc)


def _prior_window(prompt_messages: Any) -> list[Any]:
    """The conversation before this turn's own user line.

    Tool and web results can follow that line, so the cut is at the last user
    message, not the last message. The system messages before it (the rules, the
    turn's context) are left out: what a "why?" refers to is the exchange itself.
    """
    if not isinstance(prompt_messages, list):
        return []
    for index in range(len(prompt_messages) - 1, -1, -1):
        message = prompt_messages[index]
        if isinstance(message, dict) and message.get("role") == "user":
            return conversation_turns(prompt_messages[:index])
    return []


async def register_and_enqueue_finalize(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    assistant_text: str,
    usage: dict[str, int],
    outcome: TurnOutcome | None,
) -> None:
    if ctx.assistant_message_id is None:
        ctx.assistant_message_id = uuid7()
    if outcome is not None:
        outcome.resolved_model = ctx.model
        outcome.message_id = str(ctx.assistant_message_id)
        outcome.recalled = ctx.recalled_count
        outcome.memory_hints = list(ctx.memory_hints)
        outcome.context_summarized = ctx.context_summarized
        # Settings → Personalization can turn the suggestions, and their model call, off.
        wants_follow_ups = ctx.user is None or ctx.user.follow_up_suggestions_enabled is not False
        outcome.related_task = (
            None
            if not wants_follow_ups
            else schedule_related_prompts(
                redis,
                settings,
                message_id=str(ctx.assistant_message_id),
                question=ctx.user_message_content or "",
                answer=assistant_text,
                prior=_prior_window(ctx.prompt_messages),
                allow_general=not ctx.lightweight_turn and ctx.instant_reply is None,
                completion=outcome.completion,
                chat=(str(ctx.user_id), str(ctx.chat_id)),
            )
        )
    await mark_pending_finalize(redis, ctx.chat_id)
    finalize_db_task = create_background_task(
        finalize_stream_turn_db(
            deps, redis, settings, ctx, assistant_text=assistant_text, usage=usage, outcome=outcome
        ),
        name="finalize_stream_turn_db",
    )
    register_pending_finalize(ctx.chat_id, finalize_db_task)
    finalize_db_task.add_done_callback(
        lambda task: log_background_task_failure(task, "Background DB finalization failed")
    )

    async def run_jobs_after_db() -> None:
        try:
            await finalize_db_task
            detect_quality_issues(ctx, assistant_text)
            await enqueue_post_turn_jobs(redis, settings, ctx, assistant_text)
        except Exception:
            logger.exception("Background job enqueue failed")

    jobs_task = create_background_task(run_jobs_after_db(), name="post_turn_jobs")
    jobs_task.add_done_callback(
        lambda task: log_background_task_failure(task, "Background finalization failed")
    )
    if outcome is not None:
        outcome.finalize_task = jobs_task
        outcome.finalize_db_task = finalize_db_task


async def _record_tool_round_spend(redis: Redis, ctx: StreamContext, usage: dict[str, int]) -> None:
    """The tool rounds that led to a generated picture count toward the global
    spend cap; the turn's quota is refunded and the picture is the image service's."""
    cost = model_catalog.estimate_cost_usd(
        ctx.model,
        input_tokens=usage.get("input", 0),
        output_tokens=usage.get("output", 0),
    )
    if not cost:
        return
    try:
        await quota_service.record_global_spend(redis, cost)
    except Exception:
        logger.exception("record_global_spend failed for terminal-image tool rounds")


async def finalize_terminal_image_turn(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    outcome: TurnOutcome | None,
    usage: dict[str, int],
) -> None:
    try:
        ctx.assistant_message_id = UUID(ctx.terminal_image_message_id)
    except (ValueError, TypeError):
        logger.warning(
            "terminal_image_message_id not a UUID: %r",
            ctx.terminal_image_message_id,
        )
    assistant_text = ctx.terminal_image_content or ""

    async def slim_finalize() -> None:
        # The picture's row moved the chat up when it was saved (``turn_record``).
        try:
            await enqueue_post_turn_jobs(redis, settings, ctx, assistant_text)
        except Exception:
            logger.exception("Slim finalize for terminal image failed")
        await _record_tool_round_spend(redis, ctx, usage)

    task = create_background_task(slim_finalize(), name="finalize_terminal_image")
    task.add_done_callback(
        lambda done: log_background_task_failure(done, "Terminal-image finalize failed")
    )
    if outcome is not None:
        outcome.finalize_task = task


async def _refund_turn(
    deps: ChatTurnDeps, redis: Redis, ctx: StreamContext, resources: TurnResources | None
) -> None:
    """Give back the turn's reservation: no model reply is saved for it."""
    if resources is not None:
        await resources.refund()
    else:
        await deps.quota.refund_usage(redis, str(ctx.user_id), ctx.reserved_tokens)


def _is_terminal_image(ctx: StreamContext) -> bool:
    """A tool round generated a picture and saved its reply: the turn streams nothing.

    Only the tool loop sets this, and an instant reply never runs the tool loop.
    """
    return not ctx.instant_reply and bool(
        ctx.terminal_image_content and ctx.terminal_image_message_id
    )


async def _produce_reply(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    usage: dict[str, int],
    accum: StreamAccum,
    should_cancel: Callable[[], bool] | None,
    outcome: TurnOutcome | None,
    on_status: StreamStatusFn | None,
    on_reasoning: StreamReasoningFn | None,
) -> AsyncIterator[str]:
    """The reply's text: an instant reply, or the tool loop and then the model's stream.

    After the tool loop the turn may have become an instant reply, or a terminal
    picture that yields nothing (``_is_terminal_image``).
    """
    if ctx.instant_reply:
        async for token in run_instant_reply_path(ctx, should_cancel=should_cancel, accum=accum):
            yield token
        return
    if ctx.timing is not None:
        ctx.timing.mark_phase("tool_loop_start")
    try:
        await run_tool_loop_path(
            deps,
            redis,
            settings,
            ctx,
            usage=usage,
            on_status=on_status,
            should_cancel=should_cancel,
        )
    finally:
        if ctx.timing is not None:
            ctx.timing.mark_phase("tool_loop_done")
    if _is_terminal_image(ctx):
        return
    if ctx.instant_reply:
        async for token in run_instant_reply_path(ctx, should_cancel=should_cancel, accum=accum):
            yield token
        return
    if settings.image_search_enabled and ctx.user is not None:
        ctx.answer_photo = AnswerPhoto(settings, ctx.user)
    async for token in run_llm_token_stream(
        deps,
        redis,
        settings,
        ctx,
        usage=usage,
        should_cancel=should_cancel,
        outcome=outcome,
        on_reasoning=on_reasoning,
        accum=accum,
        on_status=on_status,
    ):
        yield token


async def _finish_terminal_image_turn(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    usage: dict[str, int],
    outcome: TurnOutcome | None,
    resources: TurnResources | None,
) -> None:
    """The picture's reply is already saved: report it, refund the turn, run its jobs."""
    if outcome is not None:
        outcome.message_id = ctx.terminal_image_message_id
        outcome.final_content = ctx.terminal_image_content
        outcome.resolved_model = ctx.terminal_image_model or "image-gen-model"
    await _refund_turn(deps, redis, ctx, resources)
    await await_user_message_persist(ctx)
    await finalize_terminal_image_turn(deps, redis, settings, ctx, outcome, usage)


async def _settle_reply(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    usage: dict[str, int],
    accum: StreamAccum,
    should_cancel: Callable[[], bool] | None,
    outcome: TurnOutcome | None,
    resources: TurnResources | None,
    on_status: StreamStatusFn | None = None,
) -> None:
    """Save the streamed reply: finalize its text, then commit it and queue its jobs.

    A reply the user stopped before the client drew any of it saves and charges
    nothing; a turn that produced no text at all is the model's failure.
    """
    if accum.was_cancelled and shutdown.stopping():
        accum.mark_server_stop()
    user_stopped = accum.completion == "user_stop"
    assistant_text = accum.reply_text(outcome.client_shown_chars if outcome else None)
    if not assistant_text and user_stopped:
        # Stopped before the client drew any of it: nothing is saved or charged,
        # and a regenerate keeps the answer it was replacing (as a stop before
        # the first token does).
        if outcome is not None:
            outcome.completion = accum.completion
        await _refund_turn(deps, redis, ctx, resources)
        return
    if not assistant_text:
        raise ModelUnavailableError(
            "That model isn't responding right now. Try again — or pick a different model.",
            failed_alias=ctx.model,
        )
    if outcome is not None and accum.completion != "complete":
        outcome.completion = accum.completion

    async def persist_reply() -> None:
        final_text = await enrich_final_content(
            deps,
            redis,
            settings,
            ctx,
            assistant_text=assistant_text,
            usage=usage,
            outcome=outcome,
            was_cancelled=accum.was_cancelled,
            assistant_parts=accum.parts,
            should_cancel=should_cancel,
            user_stopped=user_stopped,
            on_status=on_status,
        )
        # The phone drew a first answer this one replaced, or text the reply no longer
        # starts with: done must carry the text.
        replaced = accum.retracted or accum.rewritten
        if replaced and outcome is not None and outcome.final_content is None:
            outcome.final_content = final_text
        await await_user_message_persist(ctx)
        await register_and_enqueue_finalize(
            deps,
            redis,
            settings,
            ctx,
            assistant_text=final_text,
            usage=usage,
            outcome=outcome,
        )
        if resources is not None:
            # finalize_stream_turn_db settles ctx.reserved_tokens from here.
            resources.mark_settled()

    # Once the model stream has ended the reply is saved, whatever cancels
    # this task: a Stop during the finalize passes (photo, SymPy, reminder
    # write), the provider-socket close a Stop causes, or a server stop.
    # The save runs on its own task so no cancel can drop it.
    await await_ignoring_cancel(persist_reply())


async def _close_turn(
    ctx: StreamContext, outcome: TurnOutcome | None, failure: BaseException | None
) -> None:
    """Whatever happened: the user's row has saved (or failed loudly), and the turn's
    timing and its trace are logged (the trace even when a second cancel ends the wait)."""
    try:
        if ctx.user_message_persist is not None:
            try:
                await await_user_message_persist(ctx)
            except Exception:
                logger.exception(
                    "User message persist failed chat_id=%s",
                    ctx.chat_id,
                )
        if ctx.timing is not None:
            ctx.timing.log_summary(
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                model=ctx.model,
                lightweight=ctx.lightweight_turn,
                content_chars=len(ctx.user_message_content or ""),
            )
    finally:
        emit_turn_trace(ctx, outcome=outcome, failure=failure)


async def stream_and_finalize(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    should_cancel: Callable[[], bool] | None,
    outcome: TurnOutcome | None = None,
    on_status: StreamStatusFn | None = None,
    on_reasoning: StreamReasoningFn | None = None,
    resources: TurnResources | None = None,
) -> AsyncIterator[str]:
    """Stream the turn's reply, then save it; a Stop or a provider failure mid-reply
    still saves the part already streamed."""
    usage: dict[str, int] = {}
    accum = StreamAccum()
    failure: BaseException | None = None
    try:
        try:
            async for token in _produce_reply(
                deps,
                redis,
                settings,
                ctx,
                usage=usage,
                accum=accum,
                should_cancel=should_cancel,
                outcome=outcome,
                on_status=on_status,
                on_reasoning=on_reasoning,
            ):
                yield token
        except asyncio.CancelledError:
            if not accum.parts:
                raise
            clear_task_cancellation()
            accum.mark_user_stop()
            logger.info(
                "Hard cancel with partial reply; finalizing chat_id=%s parts=%d",
                ctx.chat_id,
                len(accum.parts),
            )
        except ModelUnavailableError:
            if not accum.parts:
                raise
            accum.mark_interrupted()
            logger.info(
                "Provider fail with partial reply; finalizing chat_id=%s parts=%d",
                ctx.chat_id,
                len(accum.parts),
            )
        if _is_terminal_image(ctx):
            await _finish_terminal_image_turn(
                deps, redis, settings, ctx, usage=usage, outcome=outcome, resources=resources
            )
            return
        await _settle_reply(
            deps,
            redis,
            settings,
            ctx,
            usage=usage,
            accum=accum,
            should_cancel=should_cancel,
            outcome=outcome,
            resources=resources,
            on_status=on_status,
        )
    except BaseException as exc:
        failure = exc
        raise
    finally:
        await _close_turn(ctx, outcome, failure)
