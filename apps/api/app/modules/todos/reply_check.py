"""Whether a reply about reminders says only what the server saved.

A model "Set:" line or "I've set a reminder" is not a save. When nothing was
saved, ``reply_when_nothing_saved`` asks for the missing time or says nothing
changed; the classifiers here tell a reply about the user's reminders from one
that only mentions the word. ``reply_claims`` finds the claim sentences.
"""

from __future__ import annotations

import re

from app.modules.todos.reminder_fence_parse import explicitly_declines_reminder_creation
from app.modules.todos.reply_claims import (
    CLAIM_VERBS,
    COLON_CLAIM_RE,
    PROSE_CLAIM_RE,
    without_claim_lines,
)
from app.modules.todos.spoken_add import (
    ADD_REQUEST_RE,
    FILLER_RE,
    WORD_RE,
    adds_content,
    user_named_a_clock,
)
from app.modules.todos.spoken_change import parse_spoken_reminder_change
from app.services.draft_fences import has_draft
from app.services.md_fence_scan import iter_fences, without_fences

NEED_A_TIME = "When should I remind you?"
_DECLINE_SAVE_RE = re.compile(
    r"\b(?:i (?:set|added|saved|scheduled)|reminder (?:is |was )?set)\b",
    re.IGNORECASE,
)
_DECLINE_NEGATION_RE = re.compile(
    r"\b(?:no reminder|not set|didn(?:'|\u2019)t|did not|won(?:'|\u2019)t|will not|without)\b",
    re.IGNORECASE,
)
_CHANGE_LEADS = (
    "cancel ",
    "undo ",
    "make ",
    "change ",
    "set ",
    "put ",
    "mark ",
    "complete ",
    "finish ",
    "reopen ",
    "uncheck ",
    "delete ",
    "remove ",
    "move ",
    "reschedule ",
)
_COMMON_WORDS = frozenset(
    {
        "about",
        "after",
        "all",
        "and",
        "any",
        "are",
        "before",
        "but",
        "can",
        "did",
        "for",
        "from",
        "get",
        "got",
        "had",
        "has",
        "have",
        "her",
        "his",
        "how",
        "into",
        "its",
        "just",
        "let",
        "may",
        "more",
        "not",
        "now",
        "off",
        "one",
        "our",
        "out",
        "some",
        "that",
        "the",
        "this",
        "too",
        "use",
        "was",
        "who",
        "why",
        "with",
        "yes",
        "you",
        "your",
    }
)
_ASKS_WHEN_RE = re.compile(r"\b(?:when|what time|which day)\b", re.IGNORECASE)
# A reply is about the user's reminders when it says so, or confirms a dated
# one the way the app does ("Set: read — Monday, Oct 12, 8:00 AM.").
_REMINDER_TALK_RE = re.compile(
    r"\b(?:remind(?:er|ers)?|to-?dos?|to-do list|task list"
    r"|your (?:grocery list|shopping list|list|schedule|calendar))\b",
    re.IGNORECASE,
)
# "Quick reminder: it's 9/5 + 32" teaches a fact; it is not about saved reminders.
_FACT_REMINDER_RE = re.compile(
    r"\b(?:quick|friendly|gentle)\s+reminder\b\s*[\u2014\u2013:,-]", re.IGNORECASE
)
_SAVED_TALK_RE = re.compile(
    r"\b(?:your\s+(?:reminders?|to-?dos?|to-do\s+list|task\s+list|list|schedule)"
    r"|remind\s+you|reminder\s+(?:is\s+|was\s+)?set|(?:is|are|was)\s+set\s+for"
    r"|you\s+have\s+(?:\w+\s+)?(?:reminders?|to-?dos?|tasks?)"
    r"|due\s+(?:today|tomorrow|tonight)|next\s+up"
    r"|marked\s+\**[^*\n]{1,60}\**\s+as\s+(?:done|complete))\b",
    re.IGNORECASE,
)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_DATED_CLAIM_RE = re.compile(
    rf"(?:^|\n|!\s*)\s*{CLAIM_VERBS}\s*:\s+[^\n]+?\s[\u2014\u2013]\s+[^\n]*"
    r"(?:\d|today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|daily|weekly|weekdays|monthly)",
    re.IGNORECASE,
)


def reply_when_nothing_saved(
    text: str, user_text: str | None, *, about_reminders: bool = False
) -> str:
    """The model must not confirm a reminder the server did not save.

    Only a reply about reminders is checked: one with a reminder fence
    (``about_reminders``), or one that talks about reminders or confirms a
    dated one. "Can you add 3 + 4?" answered with "3 + 4 = 7", or an answer
    with a "Created: 1991" line, is not one.
    """
    if not (
        about_reminders
        or mentions_reminders(text)
        or explicitly_declines_reminder_creation(user_text)
    ):
        return text
    words = _without_code(text)
    asked = _asked_to_change_or_add(user_text)
    colon = bool(COLON_CLAIM_RE.search(words))
    prose = bool(asked and PROSE_CLAIM_RE.search(words))
    needs_time = bool(
        user_text
        and ADD_REQUEST_RE.search(user_text)
        and not user_named_a_clock(user_text)
        and not adds_content(user_text)
    )
    lines = text.splitlines()
    kept = without_claim_lines(lines)
    changed = len(kept) != len(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() if changed else text
    asks_when = bool(_ASKS_WHEN_RE.search(cleaned))
    if needs_time:
        if asks_when and not colon and not prose:
            return cleaned
        return NEED_A_TIME
    if explicitly_declines_reminder_creation(user_text) and _DECLINE_SAVE_RE.search(cleaned):
        if not _DECLINE_NEGATION_RE.search(cleaned):
            return "I didn't set a reminder."
    if colon or prose:
        return "I didn't change your reminders."
    if changed and not cleaned.strip():
        return "I didn't change your reminders."
    if not changed:
        return text
    return cleaned


def mentions_reminders(text: str | None) -> bool:
    """A reply that talks about reminders or confirms a dated one.

    Code is not talk: a React ``todos`` array or ``done: false`` is not a reminder.
    """
    if not text:
        return False
    words = _FACT_REMINDER_RE.sub(" ", _without_code(text))
    return bool(_REMINDER_TALK_RE.search(words) or _DATED_CLAIM_RE.search(words))


def claims_a_reminder_change(text: str | None) -> bool:
    """A reply line in the app's own result shape, such as "Reopened: buy milk."."""
    if not text:
        return False
    lines = _without_code(text).splitlines()
    return len(without_claim_lines(lines)) != len(lines)


def edits_prior_reply(subject: str, *, prior_assistant: str | None, reply: str | None) -> bool:
    """ "Add a stop in Bahir Dar on Saturday at 9am" right after a trip plan edits the plan.

    So does "remove the gym on Monday" after a workout plan: the saved "gym"
    reminder is not touched. True when the reply before this turn is not
    about saved reminders, this reply says nothing about them, and what the
    message names is part of that earlier reply. The caller checks that the
    message itself does not say reminder or task.
    """
    if not prior_assistant or about_saved_reminders(prior_assistant):
        return False
    if mentions_reminders(reply) or claims_a_reminder_change(reply):
        return False
    earlier = {word.lower() for word in WORD_RE.findall(prior_assistant)}
    named = {word.lower() for word in WORD_RE.findall(subject)} - _COMMON_WORDS
    return bool(named & earlier)


def about_saved_reminders(text: str | None) -> bool:
    """A reply about the user's saved reminders, as the app writes one.

    "Set: gym — Thursday, 6:00 PM.", "your reminders", "is set for Friday".
    An email headed "Reminder: assignment due Friday" is someone else's deadline.
    """
    if not text or has_draft(text):
        return False
    if any(fence.lang == "reminder_proposal" for fence in iter_fences(text)):
        return True
    words = _FACT_REMINDER_RE.sub(" ", _without_code(text))
    return bool(
        _SAVED_TALK_RE.search(words)
        or _DATED_CLAIM_RE.search(words)
        or claims_a_reminder_change(text)
    )


def _without_code(text: str) -> str:
    return _INLINE_CODE_RE.sub(" ", without_fences(text, " "))


def _asked_to_change_or_add(user_text: str | None) -> bool:
    if not user_text or adds_content(user_text):
        return False
    if ADD_REQUEST_RE.search(user_text):
        return True
    if FILLER_RE.sub("", user_text.strip().lower()).startswith(_CHANGE_LEADS):
        return True
    return parse_spoken_reminder_change(user_text) is not None
