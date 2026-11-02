"""Settle a finished turn in the database: its reply row, today's usage and quota.

``finalize_stream_turn_db`` saves the assistant reply (swapping out the one a
regenerate replaces), adds the turn's weighted tokens to the day's aggregate and
settles the turn's reservation to its actual usage. ``seed_usage_from_db`` reads
that aggregate back when Redis lost today's counter.
The jobs that follow a saved turn are ``post_turn``.
"""

import asyncio
import logging
import math
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import pool_liveness
from app.core.config import Settings
from app.models import model_catalog
from app.modules.chat.context_window import estimate_tokens
from app.modules.chat.finalize_registry import clear_pending_finalize
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome, TurnUsage
from app.modules.chat.turn_prep import StreamContext
from app.repositories import usage as usage_repo
from app.services import quota as quota_service
from app.services.quota import utc_today

logger = logging.getLogger(__name__)


async def seed_usage_from_db(redis: Redis, session: AsyncSession, user_id: UUID) -> None:
    """Re-seed the Redis daily usage counter from the DB total.

    Also heals Redis/DB drift when a previous ``adjust_usage`` failed after
    commit (Redis flag). If Redis holds a stale value lower than the DB total,
    raise Redis to max(redis, db_total). Warm Redis with no heal flag skips
    Neon — do not pay get_total_for_date on every send.

    M9: errors are logged at warning (not debug) — a failed seed after Redis
    eviction means the turn proceeds with Redis at 0 despite prior usage in
    the DB, allowing the user to exceed daily limits. The caller may still
    proceed (best-effort), but this should be visible in logs.
    """
    try:
        # Hot path: Redis already has today's counter. Skip Neon so every turn
        # does not pay get_total_for_date. Missing key (eviction / new day)
        # still seeds from DB. Drift heal only runs when adjust_usage failed
        # after a commit and left a flag — not on every send.
        if await quota_service.has_daily_usage_key(redis, str(user_id)):
            if not await quota_service.usage_needs_heal(redis, str(user_id)):
                return
            db_total = await usage_repo.get_total_for_date(session, user_id, utc_today())
            await quota_service.heal_usage_drift(redis, str(user_id), db_total)
            await quota_service.clear_usage_needs_heal(redis, str(user_id))
            return
        db_total = await usage_repo.get_total_for_date(session, user_id, utc_today())
        await quota_service.seed_usage_if_missing(redis, str(user_id), db_total)
    except Exception:
        logger.warning(
            "Usage DB-seed failed user_id=%s — quota enforcement may start "
            "from 0 if Redis was evicted",
            user_id,
            exc_info=True,
        )


@dataclass(frozen=True)
class _TurnCharge:
    """What one turn costs, in the units each record keeps."""

    # Raw tokens: the message row shows these, and they price the turn.
    input_tokens: int
    output_tokens: int
    multiplier: float
    # The daily usage aggregate stores WEIGHTED tokens (the units Redis counts),
    # not raw: otherwise ``seed_usage_from_db`` re-seeds Redis with a raw total
    # after an eviction and the user silently gets ``multiplier``x more quota for
    # the rest of the day.
    weighted_input: int
    weighted_output: int
    weighted_total: int
    # Dollars from RAW tokens x catalog prices (not quota-weighted); None when
    # the catalog has no price for the model.
    est_cost: float | None
    # Of input_tokens: read from the provider's prompt cache, and written to it.
    # Logged so production can see cache hits; prices and quota ignore them.
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0


def _turn_charge(ctx: StreamContext, assistant_text: str, usage: dict[str, int]) -> _TurnCharge:
    """The provider's reported usage, or an estimate where it reported none."""
    usage_input = usage.get("input")
    input_tokens = (
        usage_input
        if usage_input is not None
        else sum(estimate_tokens(m["content"]) for m in ctx.prompt_messages)
    )
    usage_output = usage.get("output")
    output_tokens = usage_output if usage_output is not None else estimate_tokens(assistant_text)
    multiplier = model_catalog.quota_multiplier(ctx.model)
    return _TurnCharge(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        multiplier=multiplier,
        weighted_input=math.ceil(input_tokens * multiplier),
        weighted_output=math.ceil(output_tokens * multiplier),
        weighted_total=math.ceil((input_tokens + output_tokens) * multiplier),
        est_cost=model_catalog.estimate_cost_usd(
            ctx.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        cached_input_tokens=usage.get("cached_input", 0),
        cache_write_tokens=usage.get("cache_write", 0),
    )


def _log_turn_cost(ctx: StreamContext, charge: _TurnCharge) -> None:
    est_cost = f"{charge.est_cost:.6f}" if charge.est_cost is not None else "unknown"
    logger.info(
        "turn_cost user_id=%s model=%s input_tokens=%s output_tokens=%s "
        "cached_input_tokens=%s cache_write_tokens=%s est_cost_usd=%s quota_multiplier=%s",
        ctx.user_id,
        ctx.model,
        charge.input_tokens,
        charge.output_tokens,
        charge.cached_input_tokens,
        charge.cache_write_tokens,
        est_cost,
        charge.multiplier,
    )


async def _write_reply_rows(
    deps: ChatTurnDeps,
    session: AsyncSession,
    ctx: StreamContext,
    assistant_text: str,
    charge: _TurnCharge,
    outcome: TurnOutcome | None,
) -> list[str]:
    """The reply, its photo links, the chat's touch and the day's usage, uncommitted.

    Returns the storage keys of a replaced reply's attachments: their bytes are
    deleted only after the commit.
    """
    pending_storage_keys: list[str] = []
    # Replace the prior assistant atomically with the new reply so a
    # crash cannot leave zero assistant messages after regenerate.
    if ctx.regenerate_backup is not None:
        old = await deps.messages.get_by_id(session, ctx.regenerate_backup.message_id, ctx.chat_id)
        if old is not None:
            # Detach rows in this transaction; delete bytes only after
            # commit so a failed finalize cannot orphan storage keys
            # that still have DB rows (or vice versa).
            pending_storage_keys = await deps.attachments.detach_attachments_for_messages(
                session, [old.id], commit=False
            )
            await session.delete(old)

    assistant_message = await deps.messages.create(
        session,
        chat_id=ctx.chat_id,
        user_id=ctx.user_id,
        role="assistant",
        content=assistant_text,
        model=ctx.model,
        input_tokens=charge.input_tokens,
        output_tokens=charge.output_tokens,
        message_id=ctx.assistant_message_id,
        # A stopped or cut-off reply says so after a reload too.
        completion=outcome.completion if outcome is not None else None,
        commit=False,  # batch with touch + usage into one commit
    )
    if ctx.answer_photo_ids:
        # The reply's photo was stored while it streamed; it belongs to this row.
        await deps.attachment_links.link_to_message(
            session,
            user_id=ctx.user_id,
            attachment_ids=ctx.answer_photo_ids,
            message_id=assistant_message.id,
            commit=False,
        )
    if outcome is not None:
        # stream_and_finalize preassigns these; direct callers also
        # receive the flushed row's identity before commit returns.
        if outcome.message_id is None:
            outcome.message_id = str(assistant_message.id)
        if outcome.resolved_model is None:
            outcome.resolved_model = ctx.model
        outcome.recalled = outcome.recalled or ctx.recalled_count
        outcome.memory_hints = outcome.memory_hints or list(ctx.memory_hints)
        outcome.context_summarized = outcome.context_summarized or ctx.context_summarized

    await deps.chats.touch_by_id(session, ctx.chat_id, commit=False)

    # Usage write is NOT swallowed: if the daily aggregate misses this
    # turn, a later Redis eviction re-seeds from the DB total and the
    # user gets free quota. Let the exception propagate so the caller
    # refunds the reservation and the commit never runs (the message
    # insert rolls back with the usage row).
    await deps.usage.add_tokens(
        session,
        ctx.user_id,
        utc_today(),
        # Weighted so the daily aggregate matches Redis units and
        # re-seeds correctly after an eviction (see _TurnCharge).
        input_tokens=charge.weighted_input,
        output_tokens=charge.weighted_output,
        # Cost is raw-token based; 0 when catalog prices are missing.
        est_cost_usd=charge.est_cost if charge.est_cost is not None else 0.0,
        commit=False,
    )
    return pending_storage_keys


async def _settle_quota(
    deps: ChatTurnDeps, redis: Redis, ctx: StreamContext, settings: Settings, charge: _TurnCharge
) -> TurnUsage | None:
    """Settle the reservation to the turn's weighted usage, after the reply committed.

    Returns the day's usage after it, which ``done`` carries: the phone read it with a
    GET after every turn (code-health audit NET-14). None when the settle failed.

    The overshoot is capped at the user's daily limit so one turn's actual >
    reserved delta can't push the counter past the cap (which would make later
    reserve_usage_up_to calls under-report remaining quota). A failure here must not
    refund the whole reservation: the reply already persisted.
    """
    daily_limit = (
        deps.quota.daily_limit_for_user(ctx.user, settings) if ctx.user is not None else None
    )
    used = None
    try:
        # H2: retry adjust_usage with short backoff so a transient Redis
        # blip doesn't leave the reservation inflated (user loses quota
        # on subsequent turns). On persistent failure, the next turn's
        # heal_usage_drift will correct the drift from the DB total.
        for _attempt in range(3):
            try:
                used = await deps.quota.adjust_usage(
                    redis,
                    str(ctx.user_id),
                    ctx.reserved_tokens,
                    charge.weighted_total,
                    daily_limit=daily_limit,
                )
                break
            except Exception:
                if _attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (_attempt + 1))
    except Exception:
        logger.warning(
            "adjust_usage failed after finalize commit; Redis may drift "
            "from the DB total — heal_usage_drift on next turn will correct",
            exc_info=True,
        )
        try:
            await deps.quota.mark_usage_needs_heal(redis, str(ctx.user_id))
        except Exception:
            logger.warning(
                "mark_usage_needs_heal failed after adjust_usage; heal may not run",
                exc_info=True,
            )
    if charge.est_cost:
        try:
            await deps.quota.record_global_spend(redis, charge.est_cost)
        except Exception:
            logger.exception("record_global_spend failed after successful finalize")
    if used is None or daily_limit is None:
        return None
    return TurnUsage(used_tokens=used, daily_limit=daily_limit)


async def finalize_stream_turn_db(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    assistant_text: str,
    usage: dict[str, int],
    outcome: TurnOutcome | None,
) -> None:
    """Save the reply and the day's usage in one commit, then settle the reservation.

    A failed write refunds the whole reservation and raises; the finalize marker
    is cleared either way.
    """
    charge = _turn_charge(ctx, assistant_text, usage)
    _log_turn_cost(ctx, charge)
    pending_storage_keys: list[str] = []
    committed = False

    async def save(session: AsyncSession) -> None:
        nonlocal pending_storage_keys, committed
        pending_storage_keys = await _write_reply_rows(
            deps, session, ctx, assistant_text, charge, outcome
        )
        # The create flush already supplies the row identity. No refresh
        # is needed after commit: a failed read must not report a saved
        # reply as failed or refund its charged quota.
        await session.commit()
        committed = True

    try:
        # Saved on a new connection when the first statement finds the pooled one dead.
        await pool_liveness.run_unit(deps.session_factory, save)
        day_usage = await _settle_quota(deps, redis, ctx, settings, charge)
        if outcome is not None:
            outcome.usage = day_usage
    except Exception:
        logger.exception("Stream-turn finalize failed; refunding reserved quota")
        try:
            await deps.quota.refund_usage(redis, str(ctx.user_id), ctx.reserved_tokens)
        except Exception:
            logger.exception("refund_usage failed after finalize error")
        raise
    finally:
        await clear_pending_finalize(redis, ctx.chat_id)
        if committed and pending_storage_keys:
            # The replaced reply's rows are gone: a failed delete only the queue retries.
            failed = await deps.attachments.delete_storage_keys(settings, pending_storage_keys)
            await deps.attachments.enqueue_failed_storage_deletes(failed)
