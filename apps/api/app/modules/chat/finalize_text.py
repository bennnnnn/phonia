"""Finalize passes over the reply's photo, source chips, layout and clock.

``chat/finalize_passes.py`` lists these passes in order. The photo and source
passes commit the text: ``done`` already carries what they added, so a later
failure keeps it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.chat.chart_sanitize import sanitize_chart_fences
from app.modules.chat.clarify_card import CLARIFY_FENCE, NEVER_WITH_CARD, settle_clarify_cards
from app.modules.chat.clock_denial import model_denies_clock
from app.modules.chat.finalize_subjects import fallback_text
from app.modules.chat.formula_fences import unfence_formulas, unwrap_code_maths
from app.modules.chat.mermaid_sanitize import sanitize_mermaid_fences
from app.modules.chat.presentation import drop_orphan_leading_answer, present_assistant_markdown
from app.modules.chat.proper_case import restore_proper_case
from app.modules.chat.prose_normalizer import (
    fill_sender_name_slots,
    normalize_prose_artifacts,
    prose_changed,
    strip_unrequested_recipient_placeholders,
)
from app.modules.chat.quiz_cards import repair_quiz_fences
from app.modules.chat.stream_status import announced_if_slow
from app.modules.images.answer_photo import strip_photo_fences
from app.services.md_fence_scan import close_unclosed_fences, iter_fences
from app.services.places_fence import sanitize_places_fences
from app.services.time_context import correct_weekday_dates, format_shown_clock_answer

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState
    from app.modules.chat.turn_prep import StreamContext


async def attach_answer_photo(state: FinalizeState) -> str:
    """Swap the reply's ```photo fence for the photo found while it streamed.

    A linked photo commits the text, so a later failure keeps its marker. A Stop,
    even one after the last token, does not wait (up to 6s) for the photo.
    """
    ctx = state.ctx
    photo = ctx.answer_photo
    stopped = state.should_cancel is not None and state.should_cancel()
    if photo is None or state.was_cancelled or stopped:
        if photo is not None:
            photo.cancel()
        return strip_photo_fences(state.text)
    text, ctx.answer_photo_ids = await announced_if_slow(
        photo.attach(state.text), state.on_status, "answer_photo", then="finishing"
    )
    if ctx.answer_photo_ids:
        state.committed = fallback_text(text, server_text=state.server_text)
    return text


def add_search_sources(state: FinalizeState) -> str:
    """Source chips for a searched turn, and the places card for a local search."""
    ctx = state.ctx
    text = state.text
    if not ctx.search_sources:
        return text
    web_search = state.deps.web_search
    text = web_search.strip_sources_from_text(text)
    if state.outcome is not None:
        state.outcome.search_sources = web_search.sources_payload(ctx.search_sources)
    sources_fence = web_search.format_sources_fence(ctx.search_sources)
    if sources_fence and not (state.should_cancel and state.should_cancel()):
        text = f"{text}{sources_fence}".strip()
    if ctx.local_places and "```places" not in text.lower():
        text = web_search.strip_duplicate_venue_list(text)
        places_fence = web_search.format_places_fence(ctx.search_sources)
        if places_fence and not (state.should_cancel and state.should_cancel()):
            state.assistant_parts[:] = [text] if text.strip() else []
            state.assistant_parts.append(places_fence)
            text = "".join(state.assistant_parts).strip()
    state.committed = text  # done already carries these chips
    return text


def record_instant_usage(state: FinalizeState) -> str:
    """An instant reply used no model: its usage is zero, not missing."""
    if state.ctx.instant_reply and not state.usage:
        state.usage["output"] = 0
        state.usage["input"] = 0
    return state.text


def close_open_fences(state: FinalizeState) -> str:
    """A provider can report a normal finish while still omitting a fence
    closer. Always repair odd fence parity so settled rendering never leaves raw
    backticks or an open streaming-style block behind."""
    return close_unclosed_fences(state.text)


def strip_recipient_placeholders(state: FinalizeState) -> str:
    """A draft greets an unknown recipient with "Hi," and is signed with the user's name."""
    request = state.ctx.user_message_content
    text = strip_unrequested_recipient_placeholders(state.text, request)
    user = state.ctx.user
    names = ((user.name if user is not None else None) or "").split()
    return fill_sender_name_slots(text, request, names[0] if names else None)


def normalize_prose(state: FinalizeState) -> str:
    """Prose artifact cleanup, after the fence passes so it never interferes with
    fence parsing: orphan colon lines go and 3+ blank lines collapse."""
    normalized = normalize_prose_artifacts(state.text)
    return normalized if prose_changed(state.text, normalized) else state.text


def sanitize_fences(state: FinalizeState) -> str:
    text = sanitize_places_fences(sanitize_mermaid_fences(sanitize_chart_fences(state.text)))
    return repair_quiz_fences(text)


def restore_case(state: FinalizeState) -> str:
    """A formula out of its plain code block or code span, then formulas, units and dates
    capitalized where a casual reply wrote them lowercase."""
    asked = f"{_prior_user(state.ctx)}\n{state.ctx.user_message_content}"
    text = unwrap_code_maths(unfence_formulas(state.text), asked)
    return restore_proper_case(text)


def present_markdown(state: FinalizeState) -> str:
    return drop_orphan_leading_answer(
        present_assistant_markdown(state.text), state.ctx.user_message_content
    )


def fix_clock(state: FinalizeState) -> str:
    """A reply that says it cannot see the clock gets the clock, and a date's
    weekday is corrected."""
    ctx = state.ctx
    text = state.text
    if model_denies_clock(text, ctx.user_message_content or ""):
        locale = ctx.user.locale if ctx.user is not None else None
        text = format_shown_clock_answer(ctx.user_timezone, locale)
    return correct_weekday_dates(text)


def _turn_may_ask(state: FinalizeState) -> bool:
    """Whether this turn may end with a card (docs/clarify.md, "Never")."""
    ctx = state.ctx
    # The turn after a card answers; asking again ignored the user's picks.
    if ctx.after_card:
        return False
    # A maths, physics or chemistry problem, solved or declined, is answered, not asked.
    if state.server_text or ctx.verified_subject is not None or ctx.solver_unverified:
        return False
    # A multi-part reply's settings card or picture, or a photo above the answer.
    if ctx.settings_card or ctx.reply_picture is not None or ctx.answer_photo_ids:
        return False
    return not any(fence.lang in NEVER_WITH_CARD for fence in iter_fences(state.text))


def settle_clarify(state: FinalizeState) -> str:
    """The finalize pass: one checked card, or none."""
    # A card the model wrote as bare JSON names no fence, only its questions.
    if CLARIFY_FENCE not in state.text and '"questions"' not in state.text:
        return state.text
    allowed = _turn_may_ask(state)
    text = settle_clarify_cards(state.text, allowed=allowed, after_card=state.ctx.after_card)
    if text != state.text:
        state.committed = fallback_text(text, server_text=state.server_text)
    return text


def _prior_user(ctx: StreamContext) -> str:
    """The user's line before this one: "and a square root?" asks within a LaTeX chat."""
    for message in reversed(ctx.prompt_messages[:-1]):
        if message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""
