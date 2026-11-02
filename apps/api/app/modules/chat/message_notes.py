"""What the latest message is, said beside it: a list of values, "What?" or "How?" at the
last reply, the user's Emoji setting, and the language it is written in.

These sit nearest the user's turn (``prompt_sections.CONTEXT_SECTIONS``): a small model
follows the note closest to the message. A lesson, its outline and a clarify card read
"I don't get it" their own way (a new explanation under the lesson's title, the request
answered now), so the "say it again" note stays out of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.modules.chat.clarify_turn import clarify_reply_hint
from app.modules.chat.continuation_subject import exchange_pairs
from app.modules.chat.prompt_constants.reply_missed import reply_how_hint, reply_missed_hint
from app.modules.chat.prompt_constants.school_question import question_hint
from app.modules.chat.prompt_constants.shared_numbers import shared_numbers_hint
from app.modules.chat.reply_language import reply_language_hint
from app.modules.chat.response_tone import emoji_note
from app.modules.turn_reading.lesson_flow import active_lesson_step, outline_awaits_pick
from app.modules.turn_reading.turn import teaching_of


def _own_way(query: str, exchange: list[Any], pairs: Sequence[tuple[str, str]]) -> bool:
    """A lesson, an outline awaiting a pick, or the turn after a clarify card."""
    if active_lesson_step(exchange) or outline_awaits_pick(exchange):
        return True
    return clarify_reply_hint(query, pairs) is not None


def message_notes(query: str, exchange: list[Any], user: Any, memory_block: str = "") -> list[str]:
    """The notes that apply to this message, in order; its language last, nearest it."""
    pairs = exchange_pairs(exchange)
    own_way = _own_way(query, exchange, pairs)
    missed = None if own_way else reply_missed_hint(query, pairs) or reply_how_hint(query, pairs)
    # A lesson (its first one too), outline or clarify card places its own emoji.
    lesson_like = own_way or teaching_of(query)
    emoji = None if lesson_like else emoji_note(user.emoji_use, memory_block)
    language = reply_language_hint(query, pairs, user.locale, user.custom_instructions)
    # A lesson teaches its own way; a school exercise asked in it is still the lesson's.
    # Any other question gets a school exercise's note or a factual question's.
    school = None if lesson_like else question_hint(query)
    notes = (shared_numbers_hint(query), missed, school, emoji, language)
    return [note for note in notes if note]
