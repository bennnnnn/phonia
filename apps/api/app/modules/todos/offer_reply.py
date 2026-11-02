"""A yes to the last reply's offer to set a reminder is that request.

Live (2026-10-25): the reply ended "Would you like me to set up that **Practice list
comprehensions** reminder for tomorrow (Monday) at 7:00 PM?" and the user said "yes". The
turn read "yes" alone: no To-do instructions reached the model, which wrote "Setting that
reminder for you now!" with no card, and nothing was saved. A short yes right after a
reply whose last question offers a reminder now loads the To-do block like the request
it answers, and the offer's own day and clock count as said: the user agreed to them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.todos.proposals import FENCE_LANG as CARD_FENCE
from app.services.md_fence_scan import iter_fences

# "Would you like me to set up that X reminder…?", "Want me to add it to your list?",
# "Shall I remind you at 9?". The reminder is what is set, not where something goes ("add
# error handling to the reminder service") or a thing about reminders ("a to-do list app",
# "a reminder of the key steps").
_ASKS = (
    r"(?:(?:would|do) you (?:like|want) me to|want me to|shall i|should i|can i)\s+"
    r"(?:(?:go ahead and|also|quickly)\s+)?"
)
_NOT_A_REMINDER = (
    r"(?!\s+(?:lists?\s+)?(?:of|on how|about how|app|apps|system|tool|service|services|feature"
    r"|features|function|component|module|class|code|template|logic|api|screen|page)\b)"
)
# Words between the verb and the reminder, none of them a preposition: "set up that
# Practice list comprehensions reminder", not "add error handling to the reminder".
_OBJECT_WORDS = r"(?:(?!(?:to|for|in|on|of|with|from|into|about)\b)[\w'-]+\s+){0,5}?"
_OFFER = re.compile(
    rf"\b{_ASKS}(?:set(?: up)?|add|create|schedule|make|save)\s+{_OBJECT_WORDS}"
    rf"(?:reminders?|to-?dos?){_NOT_A_REMINDER}\b"
    rf"|\b{_ASKS}(?:add|put|save)\s+[^?]{{0,80}}?\s+(?:to|on|in)\s+your\s+"
    r"(?:(?:to-?do|grocery|shopping)\s+)?(?:list|to-?dos|reminders)\b(?!\s+app\b)"
    rf"|\b{_ASKS}remind you\b(?!\s+(?:how|what|why|of|that|about how)\b)"
    rf"|\b(?:would|do) you (?:like|want) (?:a|that|this)\s+reminders?\b{_NOT_A_REMINDER}",
    re.IGNORECASE,
)
# The reply's sentences that ask; the offer is the last one, near the end.
_QUESTION = re.compile(r"[^.!?\n]*\?")
_TAIL_CHARS = 240


def accepted_reminder_offer(user_text: str | None, prior_assistant: str | None) -> str | None:
    """The offer ``user_text`` says yes to, or None.

    Only a bare yes counts ("yes", "sure", "go ahead"): "yes but make it 8" changes
    the offer and is read as its own words. A reply holding code offers code ("Should I
    add a reminder field to the form?"), whatever its words.
    """
    from app.modules.turn_reading.routing import is_short_confirmation

    if not user_text or not prior_assistant or not is_short_confirmation(user_text):
        return None
    if any(fence.lang != CARD_FENCE for fence in iter_fences(prior_assistant)):
        return None
    tail = prior_assistant.rstrip()[-_TAIL_CHARS:]
    questions = _QUESTION.findall(tail)
    if not questions:
        return None
    offer = questions[-1].strip().replace("*", "")
    return offer if _OFFER.search(offer) else None


def follows_reminder_card(recent: Sequence[Any] | None) -> bool:
    """The last reply held a reminder card, so this message is about that change.

    Live (2026-10-26): "Delete overdue" got a card and the user tapped it. Then "Did u remove
    it?" has no to-do word and nothing left overdue, so the turn carried no To-do text; a
    light model answered "I don't have access to your To-do list" and apologised for a delete
    that had happened, three turns running. A turn after a card keeps the To-do text.
    """
    for message in reversed(recent or ()):
        if getattr(message, "role", None) == "assistant":
            content = getattr(message, "content", None)
            return isinstance(content, str) and f"```{CARD_FENCE}" in content
    return False


def accepted_offer_in(user_text: str | None, recent: Sequence[Any] | None) -> str | None:
    """The same, with the last reply read from the recent window (a regenerate's window
    leaves out the reply it redoes: ``turn_load.load_regenerate_turn``)."""
    for message in reversed(recent or ()):
        if getattr(message, "role", None) == "assistant":
            content = getattr(message, "content", None)
            return accepted_reminder_offer(user_text, content if isinstance(content, str) else None)
    return None
