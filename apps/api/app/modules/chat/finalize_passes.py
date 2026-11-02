"""Finalizing a reply: an ordered list of passes over the finished text.

``FINALIZE_PASSES`` is the order. Each pass takes the reply so far and returns
it changed. What an exception in it does follows its kind, unless its own
``on_error`` says otherwise:

- A text pass (``kind=TEXT``) goes on: the failure is logged under the pass's
  name (a timeout as a warning, any other failure captured), the turn's trace
  lists it (``passes_failed``), and the next pass gets the failed pass's input.
  One broken text pass costs its own change, never the passes after it (ST-06).
- An effect pass (``kind=EFFECT``) falls back (``FALL_BACK``): the passes stop
  and the reply is the last committed text, the text as of the last side effect
  (a linked photo, source chips), or the raw reply made safe when nothing was
  committed (ES-03). Either way the safety passes that text has not been through
  then run on it, each failing closed (``FinalizePass.closed``).
- ``OnError(log_as=step)``: goes on like a text pass, logged as ``step``.
- ``OnError(log_as=step, rewrite=fn)``: logged the same way; the next pass gets
  what ``fn`` makes of that input.

A safety pass that goes on after failing hands on its closed strip of its input,
never the input itself.

Then the reminder pass (``finalize_reminders``) runs on whatever text the passes
leave: it is the one step with an effect outside the reply.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from redis.asyncio import Redis

from app.core.config import Settings
from app.modules.chat.claim_check import cut_unsupported_claims
from app.modules.chat.control_tokens import drop_control_tokens, strip_control_tokens
from app.modules.chat.emoji_placement import place_reply_emoji
from app.modules.chat.finalize_contracts import (
    CARD_PASSES,
    EFFECT,
    EVERY_OTHER,
    FENCE_READERS,
    SERVER_MEDIA,
    STOPPED_REPLY_PASSES,
    TEXT,
    PassKind,
)
from app.modules.chat.finalize_money import attach_money_card
from app.modules.chat.finalize_parts import (
    add_settings_card,
    attach_reply_picture,
    divide_request_sections,
)
from app.modules.chat.finalize_reminders import apply_reminder_pass, drop_cut_reminder_fence
from app.modules.chat.finalize_subjects import (
    append_unverified_notes,
    check_chemistry_fences,
    check_math_fences,
    check_physics_fences,
    check_working,
    draw_formula_charts,
    drop_check_lines,
    enrich_chemistry_fences,
    fallback_text,
    mark_server_cards,
    prepare_model_reply,
    recover_chemistry_fences,
    recover_math_fences,
    recover_physics_fences,
    strip_solve_markers,
    strip_text_plots,
)
from app.modules.chat.finalize_text import (
    add_search_sources,
    attach_answer_photo,
    close_open_fences,
    fix_clock,
    normalize_prose,
    present_markdown,
    record_instant_usage,
    restore_case,
    sanitize_fences,
    settle_clarify,
    strip_recipient_placeholders,
)
from app.modules.chat.generic_closer import strip_generic_closer
from app.modules.chat.json_output import check_requested_json
from app.modules.chat.lesson_again import keep_to_lesson_again_pass
from app.modules.chat.meta_notes import unwrap_meta_notes
from app.modules.chat.prompt_leaks import drop_prompt_leaks_pass, drop_prompt_lines
from app.modules.chat.reply_labels import one_answer_label
from app.modules.chat.reply_meta import local_today, without_turn_meta
from app.modules.chat.search_links import unlink_unretrieved_links
from app.modules.chat.stream_status import StreamStatusFn
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_trace import note_pass, note_pass_failed
from app.modules.chat.untrusted_media import drop_media_lines, neutralize_untrusted_media
from app.modules.chat.worked_lead import drop_guessed_lead

logger = logging.getLogger(__name__)


@dataclass
class FinalizeState:
    """One reply on its way through the passes."""

    deps: ChatTurnDeps
    settings: Settings
    ctx: StreamContext
    raw: str
    text: str
    usage: dict[str, int]
    outcome: TurnOutcome | None
    was_cancelled: bool
    assistant_parts: list[str]
    should_cancel: Callable[[], bool] | None
    # The text as of the last side effect (a linked photo, source chips). A failed
    # pass falls back to it, never to the raw reply (ES-03).
    committed: str | None = None
    # The user stopped the reply: it saves as they saw it (STOPPED_REPLY_PASSES).
    user_stopped: bool = False
    # Tells the client what a slow pass is doing while the reply waits on it.
    on_status: StreamStatusFn | None = None
    # Safety passes that raised: whatever commits after them, a fallback runs them again.
    failed_safety: set[str] = field(default_factory=set)

    @property
    def server_text(self) -> bool:
        """An instant reply is wholly server text: every card in it is the server's."""
        return self.ctx.instant_reply is not None


@dataclass(frozen=True)
class OnError:
    """What an exception in one pass does to the reply (see the module docstring)."""

    # The step a failure is logged as; None falls back to the last committed text.
    log_as: str | None = None
    # Makes the failed pass's input into the next pass's; None hands it on as it was.
    rewrite: Callable[[FinalizeState], str] | None = None


FALL_BACK = OnError()


@dataclass(frozen=True)
class FinalizePass:
    """One pass: ``run`` returns the reply after it; ``name`` labels its timing."""

    name: str
    run: Callable[[FinalizeState], str | Awaitable[str]]
    # None: what its kind does (``failure``).
    on_error: OnError | None = None
    # Set on a safety pass, one that removes what no saved reply may keep (a forged
    # check, a URL that loads by itself, the prompt's own words). A fallback text runs
    # it too, and when it fails there this strip stands in, never the text it cleans.
    closed: Callable[[str], str] | None = None
    # Declared by every pass in FINALIZE_PASSES; test_finalize_passes holds the order to them.
    kind: PassKind | None = None
    after: frozenset[str] = frozenset()
    before: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.kind not in (None, TEXT, EFFECT):
            raise ValueError(f"pass {self.name!r}: kind is TEXT or EFFECT, not {self.kind!r}")

    @property
    def failure(self) -> OnError:
        """What an exception in it does: its own ``on_error``; else a text pass goes on,
        logged under its name, and any other falls back."""
        if self.on_error is not None:
            return self.on_error
        return OnError(log_as=self.name) if self.kind == TEXT else FALL_BACK


# A failed subject pass recovers its subject's fences (no model answer card
# survives it) and logs under the name the one subject step had.
_SUBJECT_FENCES_STEP = "validate_math_fences"

FINALIZE_PASSES: tuple[FinalizePass, ...] = (
    # First: no other pass reads a leaked end-of-turn token as the reply's text.
    FinalizePass(
        "control_tokens",
        lambda s: strip_control_tokens(s.text, s.ctx.user_message_content or ""),
        closed=drop_control_tokens,
        kind=TEXT,
        before=EVERY_OTHER,
    ),
    # Before the fence repair below can close it for the reminder pass.
    FinalizePass(
        "drop_cut_reminder_fence",
        lambda s: drop_cut_reminder_fence(s.text),
        kind=TEXT,
        before=frozenset({"close_fences"}),
    ),
    # Model text before any server card is added to it.
    FinalizePass(
        "prepare_model_reply",
        prepare_model_reply,
        closed=drop_check_lines,
        kind=TEXT,
        before=CARD_PASSES | {"server_answer_cards", "settings_card", "money_card"},
    ),
    # Before a subject lands its card under the reply's Answer heading.
    FinalizePass(
        "answer_labels",
        lambda s: one_answer_label(s.text),
        kind=TEXT,
        before=CARD_PASSES,
    ),
    FinalizePass("worked_lead", lambda s: drop_guessed_lead(s.text), kind=TEXT),
    # A changed reply commits; before the server's own pictures and chips are added.
    FinalizePass(
        "untrusted_media",
        neutralize_untrusted_media,
        closed=drop_media_lines,
        kind=EFFECT,
        before=SERVER_MEDIA,
    ),
    # After untrusted_media, whose image-made links are no source claims.
    FinalizePass(
        "search_links",
        unlink_unretrieved_links,
        kind=TEXT,
        after=frozenset({"untrusted_media"}),
    ),
    FinalizePass("generic_closer", strip_generic_closer, kind=TEXT),
    FinalizePass("meta_notes", lambda s: unwrap_meta_notes(s.text), kind=TEXT),
    FinalizePass("prompt_leaks", drop_prompt_leaks_pass, closed=drop_prompt_lines, kind=TEXT),
    FinalizePass(
        "turn_meta",
        lambda s: without_turn_meta(
            s.text, s.ctx.user_message_content or "", local_today(s.ctx.user_timezone)
        ),
        kind=TEXT,
    ),
    FinalizePass("lesson_again", keep_to_lesson_again_pass, kind=TEXT),
    FinalizePass("emoji_use", place_reply_emoji, kind=TEXT),
    # A linked photo commits the text, so a later failure keeps its marker.
    FinalizePass("answer_photo", attach_answer_photo, kind=EFFECT),
    # After the answer photo's pass, which sets the list the picture joins.
    FinalizePass(
        "reply_picture",
        attach_reply_picture,
        kind=EFFECT,
        after=frozenset({"answer_photo"}),
    ),
    FinalizePass(
        "chemistry_fences",
        check_chemistry_fences,
        OnError(log_as=_SUBJECT_FENCES_STEP, rewrite=recover_chemistry_fences),
        kind=TEXT,
    ),
    FinalizePass(
        "physics_fences",
        check_physics_fences,
        OnError(log_as=_SUBJECT_FENCES_STEP, rewrite=recover_physics_fences),
        kind=TEXT,
    ),
    FinalizePass(
        "math_fences",
        check_math_fences,
        OnError(log_as=_SUBJECT_FENCES_STEP, rewrite=recover_math_fences),
        kind=EFFECT,  # the status callback: "checking", then "finishing"
    ),
    # After the maths pass: it strips a ```graph that no solver wrote.
    FinalizePass(
        "formula_charts",
        draw_formula_charts,
        kind=TEXT,
        after=frozenset({"math_fences"}),
    ),
    FinalizePass("server_answer_cards", mark_server_cards, kind=TEXT),
    FinalizePass("unverified_notes", append_unverified_notes, kind=TEXT),
    FinalizePass("working_check", check_working, kind=TEXT),
    # Before the source chips: it reads the reply's prose, and a failure keeps it whole.
    FinalizePass(
        "claim_check",
        cut_unsupported_claims,
        OnError(log_as="claim_check"),
        kind=EFFECT,  # a model call that adds to the turn's usage, and a status
        before=frozenset({"search_sources"}),
    ),
    FinalizePass("text_plots", strip_text_plots, kind=TEXT),
    FinalizePass("solve_markers", strip_solve_markers, kind=TEXT),
    FinalizePass(
        "chemistry_enrich",
        enrich_chemistry_fences,
        OnError(log_as="enrich_chemistry_fences"),
        kind=TEXT,
    ),
    FinalizePass("settings_card", add_settings_card, kind=EFFECT),
    FinalizePass("money_card", attach_money_card, kind=EFFECT),
    FinalizePass("request_sections", divide_request_sections, kind=TEXT),
    FinalizePass("search_sources", add_search_sources, kind=EFFECT),
    FinalizePass("instant_usage", record_instant_usage, kind=EFFECT),
    # Layout, after the passes that read the model's fences as it wrote them.
    FinalizePass("close_fences", close_open_fences, kind=TEXT, after=FENCE_READERS),
    # After the closer: a card the model left open is read once it is closed.
    FinalizePass(
        "clarify_card",
        settle_clarify,
        kind=EFFECT,
        after=frozenset({"close_fences"}),
    ),
    FinalizePass("requested_json", check_requested_json, kind=TEXT),
    FinalizePass("recipient_placeholders", strip_recipient_placeholders, kind=TEXT),
    # After all fence enrichment, so it never interferes with fence parsing.
    FinalizePass(
        "prose",
        normalize_prose,
        kind=TEXT,
        after=FENCE_READERS | SERVER_MEDIA | {"close_fences", "settings_card", "money_card"},
    ),
    FinalizePass("mermaid_and_places", sanitize_fences, kind=TEXT),
    FinalizePass("proper_case", restore_case, kind=TEXT),
    FinalizePass("presentation", present_markdown, kind=TEXT),
    FinalizePass("clock", fix_clock, kind=TEXT),
)


async def _run_pass(finalize_pass: FinalizePass, state: FinalizeState) -> str:
    on_error = finalize_pass.failure
    started = time.perf_counter()
    try:
        text = finalize_pass.run(state)
        done = text if isinstance(text, str) else await text
        note_pass(finalize_pass.name, state.text, done)
        return done
    except Exception as exc:
        note_pass_failed(finalize_pass.name)
        if finalize_pass.closed is not None:
            state.failed_safety.add(finalize_pass.name)
        if on_error.log_as is None:
            raise
        # A safety pass fails closed: its strip goes on, never the text it cleans.
        kept = "stripping closed" if finalize_pass.closed else "keeping the text before it"
        if isinstance(exc, TimeoutError):
            logger.warning("%s timed out; %s", on_error.log_as, kept)
        else:
            logger.exception("%s failed; %s", on_error.log_as, kept)
        if finalize_pass.closed is not None:
            return finalize_pass.closed(state.text)
        return on_error.rewrite(state) if on_error.rewrite is not None else state.text
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.debug("finalize pass %s took %.1f ms", finalize_pass.name, elapsed_ms)


async def run_finalize_passes(state: FinalizeState) -> bool:
    """Every pass in order (a stopped reply's own list). False when one failed and
    the text fell back."""
    # How many passes the committed text has been through: its fallback runs the
    # safety passes from there on, and any that failed before.
    passed = 0
    try:
        for index, finalize_pass in enumerate(FINALIZE_PASSES):
            if state.user_stopped and finalize_pass.name not in STOPPED_REPLY_PASSES:
                continue
            committed = state.committed
            try:
                state.text = await _run_pass(finalize_pass, state)
            finally:
                if state.committed is not committed:
                    passed = index + 1
    except Exception:
        logger.exception("Post-stream enrichment failed; persisting the last committed text")
        if state.committed is None:
            state.committed = fallback_text(state.raw, server_text=state.server_text)
            state.ctx.answer_photo_ids = []
        unclean = tuple(
            finalize_pass
            for index, finalize_pass in enumerate(FINALIZE_PASSES)
            if index >= passed or finalize_pass.name in state.failed_safety
        )
        state.committed = await _made_safe(state, state.committed, unclean)
        state.text = state.committed
        return False
    return True


async def _made_safe(state: FinalizeState, text: str, passes: tuple[FinalizePass, ...]) -> str:
    """``text`` through each safety pass in ``passes``; one that fails there gives way
    to its closed strip, and a strip that fails too leaves nothing."""
    for finalize_pass in passes:
        if finalize_pass.closed is None:
            continue
        state.text = text
        try:
            cleaned = finalize_pass.run(state)
            text = cleaned if isinstance(cleaned, str) else await cleaned
        except Exception:
            logger.exception("%s failed on the fallback text; stripping closed", finalize_pass.name)
            try:
                text = finalize_pass.closed(text)
            except Exception:
                logger.exception("%s closed strip failed; saving no text", finalize_pass.name)
                return ""
    return text


async def enrich_final_content(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    *,
    assistant_text: str,
    usage: dict[str, int],
    outcome: TurnOutcome | None,
    was_cancelled: bool,
    assistant_parts: list[str],
    should_cancel: Callable[[], bool] | None,
    user_stopped: bool = False,
    on_status: StreamStatusFn | None = None,
) -> str:
    """The reply as it persists: the finalize passes, then the reminder pass.

    A reply the user stopped runs only ``STOPPED_REPLY_PASSES`` and no reminder
    pass: it changes nothing outside itself, and ``done`` carries the text the
    user saw, made safe, never a longer one.
    """
    state = FinalizeState(
        deps=deps,
        settings=settings,
        ctx=ctx,
        raw=assistant_text,
        text=assistant_text,
        usage=usage,
        outcome=outcome,
        was_cancelled=was_cancelled,
        assistant_parts=assistant_parts,
        should_cancel=should_cancel,
        user_stopped=user_stopped,
        on_status=on_status,
    )
    await run_finalize_passes(state)
    # Last, on the finished text: no later pass can fail and lose its card.
    text = (
        state.text
        if user_stopped
        else await apply_reminder_pass(deps, redis, settings, ctx, state.text, outcome)
    )

    # One write: done.final_content must equal the string we persist. Skip on
    # an unchanged normal turn so done payloads stay small. The client settles
    # what it streamed unless done carries the text, so any text that differs
    # (a stripped forged marker, a marked instant card, a reply its safety passes
    # emptied) is always sent back, an empty one included.
    if outcome is not None:
        if was_cancelled and text:
            outcome.final_content = text
        elif text != assistant_text:
            outcome.final_content = text
    return text
