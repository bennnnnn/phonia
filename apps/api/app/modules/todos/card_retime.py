"""A new time for the card the user has not tapped yet: "actually make it 8".

The reply before offered "Study bio — 7:00 PM" on a card. "Actually make it 8" fell to the
spoken-change reader, which moves the latest *saved* reminder: it offered to move "Take
chicken out of freezer" instead, and "no not that one, the study one. 8pm" found no saved
"study" reminder ("I didn't change your reminders"). A message that only gives a new time
(and maybe the card's own words) is that card's add again, at the new time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast, get_args
from uuid import UUID

from pydantic import ValidationError

from app.modules.todos.proposals import FENCE_LANG, CardItem
from app.modules.todos.recurrence import RecurrenceRule
from app.modules.todos.spoken_add import SpokenAdd
from app.modules.todos.spoken_when import read_clock
from app.services.md_fence_scan import iter_closed_fences, strip_closed_fences

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# What a re-time says besides the clock and the card's own words.
_RETIME_WORDS = frozenset(
    {
        "actually", "no", "nah", "nope", "not", "that", "this", "one", "the", "it", "its",
        "it's", "make", "change", "move", "set", "push", "put", "to", "for", "at", "instead",
        "please", "pls", "plz", "oh", "wait", "sorry", "ok", "okay", "then", "can", "you",
        "could", "would", "pm", "am", "a", "m", "p", "o'clock", "oclock", "rather", "i",
        "meant", "mean", "said", "and", "tonight", "today", "what", "about", "how",
    }
)  # fmt: skip
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
_BARE_CLOCK = re.compile(r"(?<![\w:])(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?(?![\w:])")
_REPEATS = frozenset(get_args(RecurrenceRule))
# The chat's last messages read for the reply the user's message answers.
_RECENT = 4


def _clock(text: str, card_hour: int) -> tuple[int, int] | None:
    """The one clock the message gives; a bare "8" is on the card's side of noon."""
    for at, char in enumerate(text):
        if char.isdigit() and (at == 0 or not text[at - 1].isalnum()):
            said = read_clock(text, at)
            if said is not None:
                return said.hour, said.minute
    bare = list(_BARE_CLOCK.finditer(text))
    if len(bare) != 1:
        return None
    hour, minute = int(bare[0].group("h")), int(bare[0].group("m") or 0)
    if not 1 <= hour <= 23:
        return None
    if hour < 12 and card_hour >= 12:
        hour += 12
    return hour, minute


def _untapped_adds(content: str) -> list[CardItem]:
    """The items of the reply's card when it is untapped and only adds dated items."""
    for _start, _end, body in iter_closed_fences(content, FENCE_LANG):
        try:
            card = json.loads(body)
            items = [CardItem.model_validate(item) for item in card.get("items", [])]
        except (json.JSONDecodeError, ValidationError, AttributeError):
            return []
        if card.get("status") == "saved":
            return []
        if items and all(item.action == "add" and item.due_at for item in items):
            return items
        return []
    return []


def retimed_adds(
    previous_reply: str | None, user_text: str | None, *, user_timezone: str | None
) -> list[SpokenAdd] | None:
    """The previous reply's untapped add card at the time ``user_text`` gives, else None."""
    from app.services import time_context as time_context_service

    items = _untapped_adds(previous_reply or "")
    text = " ".join((user_text or "").casefold().split())
    if not items or not text:
        return None
    # "When should I remind you to pay rent?" beside the card: "9am" answers that.
    if "?" in strip_closed_fences(previous_reply or "", FENCE_LANG):
        return None
    titles = {word for item in items for word in _WORD.findall(item.title.casefold())}
    if any(word not in _RETIME_WORDS and word not in titles for word in _WORD.findall(text)):
        return None
    tz = time_context_service.resolve_timezone(user_timezone)
    adds: list[SpokenAdd] = []
    for item in items:
        if item.due_at is None:
            return None
        due = item.due_at.astimezone(tz)
        clock = _clock(text, due.hour)
        if clock is None:
            return None
        repeat = item.repeat if item.repeat in _REPEATS else None
        adds.append(
            SpokenAdd(
                title=item.title,
                day=due.strftime("%m-%d"),
                repeat=cast("RecurrenceRule | None", repeat),
                hour=clock[0],
                minute=clock[1],
            )
        )
    return adds


async def retime_untapped_card(
    session: AsyncSession,
    chat_id: UUID,
    user_text: str | None,
    *,
    user_timezone: str | None,
    window: Sequence[object] | None = None,
) -> list[SpokenAdd] | None:
    """The card in the chat's last reply, re-timed by this message; None when it is not one.

    ``window`` is the chat's last messages as the turn read them, its user's message last.
    A card only goes from untapped to saved after that read, so when the reply there holds
    no untapped add card, the saved chat holds none either and nothing is read again.
    """
    from app.modules.conversation import history as chat_history

    if window is not None and not _untapped_adds(
        _reply_before_last_message(list(window)[-_RECENT:]) or ""
    ):
        return None
    rows = await chat_history.recent_messages(session, chat_id, limit=_RECENT)
    return retimed_adds(_reply_before_last_message(rows), user_text, user_timezone=user_timezone)


def _reply_before_last_message(rows: Sequence[object]) -> str | None:
    """The reply the user's latest message answers. On a regenerate the reply being
    replaced is still saved after that message, so it is skipped."""
    asked = False
    for row in reversed(rows):
        role = getattr(row, "role", None)
        if role == "user":
            if asked:
                return None
            asked = True
        elif role == "assistant" and asked:
            return getattr(row, "content", None)
    return None
