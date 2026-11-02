from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from redis.asyncio import Redis

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.core.db import SessionLocal
from app.exceptions import ChatNotFoundError
from app.gateways.web_search_gateway import WebSearchHit
from app.models import model_catalog
from app.models.orm import User
from app.modules.billing import plan as plan_service
from app.modules.chat.prompt_builder import PromptStats, build_prompt_messages
from app.modules.chat.turn_prep.augment import Augmentation, augment_after_prompt
from app.modules.chat.turn_prep.instant import (
    recurring_pay_reply,
    resolve_instant_reply,
)
from app.modules.chat.turn_prep.mode import classify_turn_mode
from app.modules.chat.turn_prep.money import server_parts, with_money_block
from app.modules.chat.turn_prep.reading import read_turn, read_turn_message
from app.modules.chat.turn_prep.request import (
    ClientGeoContext,
    TurnIdentity,
    TurnRequest,
    resolve_client_geo,
)
from app.modules.chat.turn_timing import TurnTimingTracker
from app.modules.chat.turn_trace import note_lightweight, note_plan, note_subject, note_teaching
from app.modules.chat.worked_render import WorkedLayout
from app.modules.conversation import history as conversation_history
from app.modules.turn_reading.plan import TurnPlan
from app.repositories import users as users_repo
from app.services import model_health as model_health_service
from app.services import time_context as time_context_service
from app.services.solving import VerifiedSolveBlock

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from app.modules.images.answer_photo import AnswerPhoto
    from app.modules.images.reply_picture import ReplyPicture
    from app.services.subjects.registry import MoneyTurn


@dataclass
class RegenerateBackup:
    """The reply a regenerate replaces. Its row stays in the chat (left out of the
    prompt) until finalize swaps in the new one, so a failed regenerate keeps it."""

    content: str
    model: str | None
    message_id: UUID


@dataclass
class StreamContext:
    user_id: UUID
    chat_id: UUID
    model: str
    prompt_messages: list[dict[str, Any]]
    run_title: bool
    user_message_content: str
    reserved_tokens: int
    max_output_tokens: int
    # Effective timezone for this request (profile preference overridden by
    # the current client timezone). Finalization must use the same zone that
    # prompt construction used for relative dates and reminder clocks.
    user_timezone: str | None = None
    # The device location when this turn needs one ("coffee near me"); a
    # search for it names the place.
    search_location: str | None = None
    user: User | None = None
    # Pre-assigned id for the assistant row so `done` can be sent to the client
    # before the background DB insert commits.
    assistant_message_id: UUID | None = None
    recalled_count: int = 0
    memory_hints: list[str] = field(default_factory=list)
    context_summarized: int = 0
    instant_reply: str | None = None
    search_sources: list[WebSearchHit] = field(default_factory=list)
    local_places: bool = False
    skip_memory_jobs: bool = False
    prior_count: int = 0
    # The chat's last messages as this turn read them (``turn_load``), its user's
    # message last, as saved; None when the turn did not read them. Finalize reads
    # the chat from these instead of asking the database again.
    recent_messages: list[Any] | None = None
    regenerate_backup: RegenerateBackup | None = None
    fallback_models: list[str] = field(default_factory=list)
    # Recovering models (breaker half-open) among the model and its backups: the
    # turn tries one only once it claims its probe (``model_health.claim_probe``).
    probe_models: frozenset[str] = frozenset()
    # Work the turn already did without an answer, which its tool loop does not
    # repeat: SymPy ran out of time on its problem; its photo lookup found none.
    solve_timed_out: bool = False
    photo_missed: bool = False
    # One verified solve for the subject that owns this turn.
    verified_subject: VerifiedSolveBlock | None = None
    # A subject solver ran and declined. The reply gets one note, not a card.
    solver_unverified: bool = False
    unverified_subject: str | None = None
    timing: TurnTimingTracker | None = None
    lightweight_turn: bool = False
    # False = casual chat (skip memory/todos). Status theater
    # (preparing/remembering/thinking/composing) is never shown; activity
    # chips remain for search, files, math, image gen.
    rich_context_turn: bool = True
    # Background insert of the user row. The LLM stream must not wait on it;
    # finalize and stream teardown await it so the assistant insert cannot
    # commit first and so a failed prompt still keeps what the user sent.
    user_message_persist: asyncio.Task[None] | None = None
    # Set when the tool loop's generate_image persisted the assistant row —
    # stream_and_finalize skips the LLM + second insert.
    terminal_image_message_id: str | None = None
    terminal_image_content: str | None = None
    terminal_image_model: str | None = None
    # False sends the model's thinking-off payload. Hard jobs set this True.
    thinking: bool | str = False
    # A real photo above an answer about something worth seeing: the search
    # starts when the reply's ```photo fence closes; finalize links the ids.
    answer_photo: AnswerPhoto | None = None
    # What the reply shows above its text, linked to it when it saves: that photo, or
    # the picture a multi-part message asked for (``reply_picture``).
    answer_photo_ids: list[UUID] = field(default_factory=list)
    # A multi-part message's settings card and picture: the server's part of the reply.
    settings_card: str | None = None
    reply_picture: ReplyPicture | None = None
    # The tools the reply's own model call carries, when the tool loop leaves the
    # turn to it: ``web_search`` (``tool_loop.reply_calls``).
    reply_tools: list[dict[str, Any]] = field(default_factory=list)
    # Offered on a second call when the first, with no tool, says it can't see live
    # data (``tool_loop.live_denial``). Empty past the spend cap or after a search.
    denial_retry_tools: list[dict[str, Any]] = field(default_factory=list)
    # The last reply asked with a clarify card: this reply may not ask again.
    after_card: bool = False
    # A loan, card or savings question: finalize adds its note and calculator card.
    money: MoneyTurn | None = None
    # A calculation nothing verified: its ```worked block is laid out as it streams.
    worked: WorkedLayout | None = None


@dataclass
class TurnPromptBundle:
    prompt_messages: list[dict[str, str]]
    stats: PromptStats
    instant_reply: str | None
    local_places: bool
    max_out: int
    fallback_models: list[str]
    lightweight: bool
    rich_context: bool
    geo: ClientGeoContext
    local_tz: str
    verified_subject: VerifiedSolveBlock | None = None
    solver_unverified: bool = False
    unverified_subject: str | None = None
    # A multi-part message's settings card, added under the model's reply.
    settings_card: str | None = None
    # Open models past their cool-down (``StreamContext.probe_models``).
    half_open_models: frozenset[str] = frozenset()
    solve_timed_out: bool = False
    money: MoneyTurn | None = None
    after_card: bool = False
    # The chat's last messages the prompt was built from (``StreamContext.recent_messages``).
    recent_messages: list[Any] | None = None
    worked: WorkedLayout | None = None


def _search_location(geo: ClientGeoContext) -> str | None:
    """The place a search for this turn names: only a turn that needs one."""
    return geo.user_location if geo.geo_query else None


def stream_context_from_bundle(
    bundle: TurnPromptBundle,
    *,
    user_id: UUID,
    chat_id: UUID,
    model: str,
    user_message_content: str,
    reserved_tokens: int,
    user: User,
    prior_count: int,
    timing: TurnTimingTracker | None = None,
    run_title: bool | None = None,
    skip_memory_jobs: bool | None = None,
    regenerate_backup: RegenerateBackup | None = None,
    user_message_persist: asyncio.Task[None] | None = None,
    thinking: bool | str = False,
    model_named: bool = False,
) -> StreamContext:
    """Map a TurnPromptBundle into StreamContext; overrides preserve call-site semantics.

    ``model_named``: the user (or the reply being regenerated) chose ``model``, so
    it runs whatever its health and claims no probe.
    """
    if run_title is None:
        run_title = prior_count == 0
    if skip_memory_jobs is None:
        skip_memory_jobs = False
    return StreamContext(
        user_id=user_id,
        chat_id=chat_id,
        model=model,
        prompt_messages=bundle.prompt_messages,
        run_title=run_title,
        user_message_content=user_message_content,
        reserved_tokens=reserved_tokens,
        max_output_tokens=bundle.max_out,
        user_timezone=bundle.local_tz,
        search_location=_search_location(bundle.geo),
        user=user,
        recalled_count=bundle.stats.recalled,
        memory_hints=list(bundle.stats.memory_hints),
        context_summarized=bundle.stats.context_summarized,
        instant_reply=bundle.instant_reply,
        local_places=bundle.local_places,
        skip_memory_jobs=skip_memory_jobs,
        prior_count=prior_count,
        recent_messages=bundle.recent_messages,
        regenerate_backup=regenerate_backup,
        fallback_models=bundle.fallback_models,
        probe_models=bundle.half_open_models - {model} if model_named else bundle.half_open_models,
        verified_subject=bundle.verified_subject,
        solver_unverified=bundle.solver_unverified,
        unverified_subject=bundle.unverified_subject,
        solve_timed_out=bundle.solve_timed_out,
        timing=timing,
        # Trust turn-mode: re-running is_lightweight_chat_turn without the
        # prior assistant would mark "yes"/"go" as greetings again.
        lightweight_turn=bundle.lightweight,
        rich_context_turn=bundle.rich_context,
        settings_card=bundle.settings_card,
        money=bundle.money,
        after_card=bundle.after_card,
        worked=bundle.worked,
        user_message_persist=user_message_persist,
        thinking=thinking,
    )


async def await_user_message_persist(ctx: StreamContext) -> None:
    """Finish the background user-row insert. Safe to call more than once.

    Shielded: a Stop cancels the waiting turn, and cancelling the insert with it
    would roll the user's message back. A cancelled wait keeps the task for the
    next call; a finished one (saved or failed) is let go.
    """
    task = ctx.user_message_persist
    if task is None:
        return
    try:
        await asyncio.shield(task)
    finally:
        if task.done():
            ctx.user_message_persist = None


async def _load_turn_identity(request: TurnRequest, settings: Settings) -> TurnIdentity:
    """The user, chat and turn mode, with the turn's geo and clock resolved in memory.

    Prepare and regenerate pass all three, so a turn skips a Neon checkout; one
    left out is read in a single short session.
    """
    user, chat, mode = request.user, request.chat, request.turn_mode
    if user is None or chat is None or mode is None:
        async with SessionLocal() as session:
            if user is None:
                user = await users_repo.get_by_id(session, request.user_id)
                if user is None:
                    raise ChatNotFoundError("User not found.")
            if chat is None:
                chat = await conversation_history.get_chat(
                    session, request.chat_id, request.user_id
                )
                if chat is None:
                    raise ChatNotFoundError("Chat not found.")
            if mode is None:
                recent = request.recent_messages
                if recent is None:
                    recent = await conversation_history.recent_messages(
                        session, request.chat_id, limit=settings.recent_message_window
                    )
                mode = classify_turn_mode(recent, request.content)
    if request.force_rich_context and not mode.rich_context:
        mode = replace(mode, rich_context=True)
    geo = resolve_client_geo(
        user,
        request.content,
        client_location=request.client_location,
        client_latitude=request.client_latitude,
        client_longitude=request.client_longitude,
    )
    local_tz = time_context_service.effective_timezone(user.timezone, request.client_timezone)
    note_lightweight(mode.lightweight_reason)
    return TurnIdentity(user=user, chat=chat, mode=mode, geo=geo, local_tz=local_tz)


async def _fallback_models(
    user: User,
    settings: Settings,
    redis: Redis,
    model: str,
    *,
    needs_vision: bool = False,
    unhealthy: frozenset[str] | None = None,
    half_open: frozenset[str] = frozenset(),
) -> tuple[list[str], frozenset[str]]:
    """Backups for the turn's model, and the half-open models; model health is
    read here when the load did not (``unhealthy`` None)."""
    if unhealthy is None:
        unhealthy = frozenset()
        try:
            aliases = [*plan_service.model_pool(user, settings)]
            aliases += [model_catalog.vision_alias(), model_catalog.vision_backup_alias()]
            health = await model_health_service.read_breakers(redis, settings, aliases)
            unhealthy, half_open = health.cooling, health.half_open
        except Exception:
            logger.debug("model health read failed during fallback selection", exc_info=True)
    fallbacks = plan_service.chat_fallback_models(
        user, settings, model, unhealthy=unhealthy, needs_vision=needs_vision
    )
    return fallbacks, half_open


def _bundle(
    identity: TurnIdentity,
    settings: Settings,
    augmented: Augmentation,
    *,
    stats: PromptStats,
    instant_reply: str | None,
    fallback_models: list[str],
) -> TurnPromptBundle:
    return TurnPromptBundle(
        prompt_messages=augmented.prompt_messages,
        stats=stats,
        instant_reply=instant_reply,
        local_places=identity.geo.local_places,
        # One high ceiling for every turn — brevity is driven by the STYLE_HINTS
        # prompt guidance, not a hard token cap. Capping by style truncated large
        # deliverables (HTML pages, graph JSON) mid-fence.
        max_out=settings.max_output_tokens,
        fallback_models=fallback_models,
        lightweight=identity.mode.lightweight,
        rich_context=identity.mode.rich_context,
        geo=identity.geo,
        local_tz=identity.local_tz,
        verified_subject=augmented.verified_subject,
        solver_unverified=augmented.solver_unverified,
        unverified_subject=augmented.unverified_subject,
        solve_timed_out=augmented.solve_timed_out,
        after_card=identity.mode.after_card,
        worked=augmented.worked,
    )


def _mark_prompt_ready(timing: TurnTimingTracker | None) -> None:
    """A reply that needs no prompt work is ready at once."""
    if timing is not None:
        timing.mark_phase("prompt_assembled")
        timing.mark_phase("augment_done")
        timing.mark_prompt_ready()


def _turn_plan(content: str, settings: Settings) -> TurnPlan:
    """The turn's plan, from its reading, and why, for the turn's trace line."""
    reading = read_turn(content, settings)
    note_plan((part.kind for part in reading.plan.parts), reading.plan_reason)
    note_teaching(reading.teaching_reason)
    note_subject(reading.subject_reason)
    return reading.plan


async def build_stream_prompt_context(
    request: TurnRequest, settings: Settings, redis: Redis
) -> TurnPromptBundle:
    """Shared prompt assembly for new turns and regenerate."""
    timing = request.timing
    if timing is not None:
        timing.mark_phase("prepare_start")
    await read_turn_message(
        request.content,
        request.recent_messages or [],
        settings,
        has_image_attachment=request.has_image_attachment,
    )
    identity = await _load_turn_identity(request, settings)
    pay_reply = recurring_pay_reply(request, identity.local_tz)
    if pay_reply is not None:
        _mark_prompt_ready(timing)
        prompt = [{"role": "user", "content": request.content}]
        return _bundle(
            identity,
            settings,
            Augmentation(prompt),
            stats=PromptStats(),
            instant_reply=pay_reply,
            fallback_models=[],
        )

    # No outer session during prompt gather (RAG/memory embeds use short-lived
    # sessions inside build_prompt_messages). Do not emit preparing/remembering
    # theater — casual chat should look like TTS: tap, then tokens. Real work
    # (search, files, math) still emits its own activity chip.
    user, chat, mode, geo = identity.user, identity.chat, identity.mode, identity.geo
    stats = PromptStats()
    # More than one request: each is answered (``intents``), and the prompt says how.
    plan = _turn_plan(request.content, settings)
    # Phase A: prompt + instant-reply + fallback-health share no data.
    prompt_messages, instant_reply, (fallback_models, half_open), extras = await gather_or_cancel(
        build_prompt_messages(
            user,
            chat.id,
            settings,
            summary=chat.summary,
            chat=chat,
            stats=stats,
            query_text=request.content,
            minimal_personal_context=mode.minimal_personal,
            lightweight=mode.lightweight,
            rich_context=mode.rich_context,
            advice_memory=mode.advice_memory,
            accepted_offer=mode.accepted_offer,
            client_timezone=request.client_timezone,
            prompt_location=geo.user_location if geo.geo_query and geo.has_geo_fix else None,
            omit_message_ids=request.omit_message_ids,
            probe_attachment_rag=request.probe_attachment_rag,
            recent_messages=request.recent_messages,
            current_user_message_id=request.current_user_message_id,
            prior_count=request.prior_count,
            turn_plan=plan if plan.multi else None,
        ),
        resolve_instant_reply(request, identity, settings, redis, plan),
        _fallback_models(
            user,
            settings,
            redis,
            request.model,
            needs_vision=request.has_image_attachment,
            unhealthy=request.unhealthy_models,
            half_open=request.half_open_models,
        ),
        server_parts(request, identity, settings, redis, plan),
    )
    if timing is not None:
        timing.mark_phase("prompt_assembled")
    card, money = extras
    if instant_reply is not None:
        money = None
    augmented, instant_reply = await augment_after_prompt(
        request,
        identity,
        settings,
        redis,
        with_money_block(prompt_messages, money),
        instant_reply,
        # A turn about the chat's earlier loan is no money turn: a sum it asks is solved.
        None if money is not None and money.standing else money,
    )
    bundle = _bundle(
        identity,
        settings,
        augmented,
        stats=stats,
        instant_reply=instant_reply,
        fallback_models=fallback_models,
    )
    bundle.settings_card = card
    bundle.half_open_models = half_open
    bundle.money = money
    bundle.recent_messages = request.recent_messages
    return bundle
