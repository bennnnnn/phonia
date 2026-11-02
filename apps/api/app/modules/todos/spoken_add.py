"""Create a reminder from the user's words, including a clock that answers 'when?'.

A model 'Set:' line is not a save. A day without a clock is not a save. A
reply that is only '6' finishes the reminder they just described, on that day,
not earlier today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from datetime import tzinfo as TzInfo
from typing import cast

from app.modules.todos.schemas import TODO_TEXT_MAX_CHARS, RecurrenceRule
from app.modules.todos.spoken_filler import FILLER_WORDS, without_lead_filler
from app.modules.todos.spoken_when import (
    due_on_day,
    find_repeat,
    find_when,
    without_spans,
)

_ALREADY_PASSED = "That time already passed. When should I remind you?"
_USER_CLOCK_RE = re.compile(
    r"\b(?:noon|midnight)\b"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b"
    r"|\b\d{1,2}(?::\d{2})?\s+in\s+the\s+(?:morning|afternoon|evening)\b",
    re.IGNORECASE,
)
# "Remind me how to convert Celsius" asks to be taught, not reminded.
_REMIND_ME_OF_A_FACT = r"(?!\s+(?:how|what|why|who|whom|whose|which|where|whether|if)\b)"
_LEAD = r"(?:(?:always|also|just|and|so|now|then)\s+)?"
ADD_REQUEST_RE = re.compile(
    rf"^\s*{_LEAD}(?:(?:please|pls|plz)\s+)?(?:can (?:you|u)\s+)?"
    rf"(?:add|buy|get|pick up|remind me{_REMIND_ME_OF_A_FACT}(?:\s+to)?)\b",
    re.IGNORECASE,
)
# The message opens by asking for a reminder: "remind me to …", "can you set a
# reminder to …", "add a reminder for …". "You forgot to remind me …" does not.
_REMINDER_REQUEST_RE = re.compile(
    rf"^{_LEAD}(?:(?:please|pls|plz)\s+)?(?:(?:can|could|will|would)\s+(?:you|u)\s+)?(?:please\s+)?"
    r"(?:remind\s+me" + _REMIND_ME_OF_A_FACT + r"|(?:set|create|add|make)\s+(?:me\s+)?"
    r"(?:a\s+)?(?:reminder|to-?do|task)\b|reminder\b)",
    re.IGNORECASE,
)
# Words of three letters or more ("gym", "run") that name something in a reply.
WORD_RE = re.compile(r"[^\W\d_]{3,}")
_QUESTION_TITLE_RE = re.compile(
    r"(?:that|how|what|why|who|whom|whose|which|where|whether|if)\b", re.IGNORECASE
)
_CALENDAR_RE = re.compile(r"\bcalendar\b", re.IGNORECASE)
_REMIND_ME_ANYWHERE_RE = re.compile(
    r"\b(?:(?:please|pls|plz)\s+)?(?:(?:can|could|will)\s+(?:you|u)\s+)?"
    r"remind\s+me\b(?:\s+(?:to|2)\b)?",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"[.!?]\s+|[.!?]$")
# Where a request ends before the next sentence: a question or exclamation mark, or a
# point before thanks.
_ASK_END_RE = re.compile(
    r"[?!](?:\s|$)|\.\s+(?=(?:thanks|thank you|thx|ty|cheers|please|pls)\b)", re.IGNORECASE
)
# Thanks after a comma, or a closing "please": "…at 9am, thank you". "Call Ty" and "say
# thanks" are the task.
_COURTESY_TAIL_RE = re.compile(
    r",\s*(?:thanks|thank you|thx|ty|cheers|please|pls)\W*$|\s+(?:please|pls)\W*$", re.I
)
FILLER_RE = re.compile(rf"^(?:{FILLER_WORDS}[,!.]?\s+)+")
# "Add a line …", "add a rest day", "add two more examples": a part of what
# the assistant just wrote.
_CONTENT_ADD_RE = re.compile(
    r"^\s*(?:please\s+|pls\s+)?(?:(?:can|could)\s+you\s+)?(?:also\s+)?add\s+(?:in\s+)?"
    r"(?:a|an|one|another|some|the|more|two|three|\d+)\s+(?:[\w'-]+\s+){0,2}?"
    r"(?:lines?|sentences?|paragraphs?|sections?|bullets?|points?|p\.?s\.?|emojis?|jokes?"
    r"|titles?|headings?|subheadings?|signature|greeting|examples?|comments?|columns?|rows?"
    r"|tests?|steps?|stops?|days?|nights?|breaks?|visits?|detours?|chorus|verses?|hashtags?"
    r"|captions?|quotes?|details?|links?|footnotes?|references?|citations?|questions?"
    r"|options?|slides?|ingredients?)\b",
    re.IGNORECASE,
)
_TYPOS = {
    "tommorrow": "tomorrow",
    "tommorow": "tomorrow",
    "tomorow": "tomorrow",
    "tomorrrow": "tomorrow",
    "wekkly": "weekly",
    "wekly": "weekly",
    "weekely": "weekly",
    "tmrw": "tomorrow",
    "tmr": "tomorrow",
    "tmrow": "tomorrow",
    "tomoro": "tomorrow",
    "tonite": "tonight",
    "remimd": "remind",
    "remaind": "remind",
    "remid": "remind",
    "rmind": "remind",
    # Amharic "tomorrow" and "today" in an otherwise English line.
    "\u1290\u1308": "tomorrow",
    "\u12db\u122c": "today",
}
_ADD_LEADS = (
    "please remind me to ",
    "please remind me ",
    "can you remind me to ",
    "can you remind me ",
    "could you remind me to ",
    "could you remind me ",
    "set a reminder for ",
    "set a reminder to ",
    "set a reminder ",
    "set reminder for ",
    "set reminder ",
    "create a reminder for ",
    "create a reminder to ",
    "create a reminder ",
    "reminder: ",
    "reminder - ",
    "reminder to ",
    "reminder for ",
    "please add a to-do ",
    "please add a todo ",
    "please add a reminder to ",
    "please add a reminder ",
    "add a to-do ",
    "add a todo ",
    "add a reminder to ",
    "add a reminder ",
    "add a task ",
    "add todo ",
    "add to ",
    "add ",
    "remind me to ",
    "remind me ",
)
_REPEATS: tuple[tuple[str, RecurrenceRule], ...] = (
    ("weekdays", "weekdays"),
    ("everyday", "daily"),
    ("every day", "daily"),
    ("weekly", "weekly"),
    ("daily", "daily"),
    ("monthly", "monthly"),
)
_TRAILING_FILLER = frozenset({"for", "on"})
_TITLE_LEADS = frozenset({"to", "2", "about", "-", "\u2013", "\u2014", ":"})
# "again" is when, not the task: "remind me about the python practice again".
_TITLE_TAILS = frozenset({"for", "on", "at", "by", "to", "again", "-", "\u2013", "\u2014", ":"})
_NEED_TO_RE = re.compile(
    r"^(?:i\s+)?(?:need|have|got|gotta|must|should)\s+(?:to\s+)?", re.IGNORECASE
)
_LIST_PHRASE_RE = re.compile(
    r"\b(?:to|on|in)\s+my\s+(?:reminders?(?:\s+list)?|to-?dos?(?:\s+list)?|to-do\s+list|list)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SpokenAdd:
    title: str
    day: str | None
    repeat: RecurrenceRule | None
    hour: int | None
    minute: int | None
    # "in 3 minutes": the reminder is due that long after the message.
    after_minutes: int | None = None


def user_named_a_clock(user_text: str | None) -> bool:
    """True when this message states a time. A model-picked hour does not count.

    "tonight at 9" states one; a bare "at 9" with no part of the day does not; "in 3
    minutes" does, as a time from now.
    """
    if not user_text:
        return False
    if _USER_CLOCK_RE.search(user_text):
        return True
    when = find_when(user_text)
    return when.hour is not None or when.after_minutes is not None


def chat_add_needs_a_stated_time(user_text: str | None, due_at: datetime | None) -> bool:
    """A chat create with no user clock is not saved.

    Callers that omit the user text keep the previous fence behavior.
    """
    if user_text is None:
        return False
    if due_at is None:
        return True
    return not user_named_a_clock(user_text)


def adds_content(user_text: str | None) -> bool:
    """ "Add a line saying the rent is paid", "add a rest day": an edit, not a task."""
    if not user_text or not _CONTENT_ADD_RE.search(user_text):
        return False
    from app.modules.todos.spoken_change import names_reminders

    return not names_reminders(user_text)


def parse_spoken_add(user_text: str | None) -> SpokenAdd | None:
    """An add that names a task, and maybe a day, a repeat, and a clock."""
    text = _fix_typos((user_text or "").strip())
    while text and text[-1] in ".!?":
        text = text[:-1].rstrip()
    lowered = text.lower()
    if not lowered:
        return None
    body = ""
    for lead in _ADD_LEADS:
        if lowered.startswith(lead):
            # The request is its own sentence: "remind me to call mom at 5pm? thanks" is
            # "call mom", not "call mom ? thanks". "Email Dr. Smith" keeps its point.
            body = _COURTESY_TAIL_RE.sub("", _request_sentence(text[len(lead) :])).strip()
            break
    if not body:
        body = _remind_me_body(text)
    if not body:
        return None
    when = find_when(body)
    spans = list(when.spans)
    repeat: RecurrenceRule | None = None
    found_repeat = find_repeat(body)
    if found_repeat is not None:
        repeat = cast(RecurrenceRule, found_repeat[0])
        spans.append(found_repeat[1])
    title = _title_of(without_spans(body, spans))
    # "Add that I'll be late" or "add a line …" adds to something, not a
    # task, "remind me how to …" asks to be taught, and "add lunch to my
    # calendar" is a calendar event.
    if (
        not title
        or _QUESTION_TITLE_RE.match(title)
        or adds_content(user_text)
        or _CALENDAR_RE.search(text)
    ):
        return None
    return SpokenAdd(
        title=title[:TODO_TEXT_MAX_CHARS],
        day=when.day,
        repeat=repeat,
        hour=when.hour,
        minute=when.minute,
        after_minutes=when.after_minutes,
    )


def _request_sentence(body: str) -> str:
    """The request up to the question or exclamation mark that ends it, unless what follows
    still says when: "remind me to stretch? Every day at 3pm" keeps its time."""
    parts = _ASK_END_RE.split(body, maxsplit=1)
    if len(parts) == 1:
        return body
    first, rest = parts
    if find_when(rest).spans or find_repeat(rest) is not None:
        return f"{first} {rest}"
    return first


def _remind_me_body(text: str) -> str:
    """ "pls remind me 2 call dad at 7 tonight", "sat 9am wash the car. remind me".

    The sentence that holds "remind me" is the request; when "remind me" ends
    the message, the sentence before it is.
    """
    match = _REMIND_ME_ANYWHERE_RE.search(text)
    if match is None:
        return ""
    before, after = text[: match.start()], text[match.end() :]
    lead = without_lead_filler(_SENTENCE_END_RE.split(before)[-1])
    near = " ".join((lead, _SENTENCE_END_RE.split(after, maxsplit=1)[0])).strip()
    if WORD_RE.search(near):
        return near
    return " ".join((without_lead_filler(before), after)).strip(" .!?")


def due_for_add(
    add: SpokenAdd,
    *,
    user_timezone: str | None,
    now: datetime | None = None,
    hour: int | None = None,
    minute: int | None = None,
) -> datetime | None:
    """The instant they named. None when the day or the clock is missing.

    "In 3 minutes" is three minutes after now, on the user's clock.
    """
    from app.services import time_context as time_context_service

    tz = time_context_service.resolve_timezone(user_timezone)
    when = now.astimezone(tz) if now is not None else _now(tz)
    if add.after_minutes is not None and hour is None and minute is None:
        return (when + timedelta(minutes=add.after_minutes)).replace(microsecond=0)
    clock_hour = add.hour if hour is None else hour
    clock_minute = add.minute if minute is None else minute
    if add.day is None or clock_hour is None or clock_minute is None:
        return None
    return due_on_day(add.day, clock_hour, clock_minute, when)


def relative_due(
    user_text: str | None, *, user_timezone: str | None, now: datetime | None = None
) -> datetime | None:
    """When "remind me to stretch in 3 minutes" is due, or None without a time from now."""
    add = parse_spoken_add(user_text)
    if add is None or add.after_minutes is None:
        return None
    return due_for_add(add, user_timezone=user_timezone, now=now)


def is_reminder_request(text: str | None) -> bool:
    """The message opens by asking for a reminder: "remind me to …", "set a reminder …"."""
    cleaned = FILLER_RE.sub("", _fix_typos((text or "").strip()).lower())
    return _REMINDER_REQUEST_RE.match(cleaned) is not None


def day_for_a_bare_clock(
    add: SpokenAdd,
    user_text: str | None,
    *,
    user_timezone: str | None,
    now: datetime | None = None,
) -> SpokenAdd:
    """ "Remind me to plate the dinner at 7pm" is the next 7pm: today, or tomorrow once past.

    Only for a message that opens by asking for a reminder and names a clock
    but no day or repeat. "At 9" with no part of the day is not a clock, and
    any other add comes back unchanged.
    """
    if add.day is not None or add.repeat is not None or add.hour is None:
        return add
    text = FILLER_RE.sub("", _fix_typos((user_text or "").strip()).lower())
    if not _REMINDER_REQUEST_RE.match(text):
        return add
    today = replace(add, day="today")
    due = due_for_add(today, user_timezone=user_timezone, now=now)
    if due is not None and due_is_past(due, user_timezone=user_timezone, now=now):
        return replace(add, day="tomorrow")
    return today


def due_is_past(
    due: datetime,
    *,
    user_timezone: str | None,
    now: datetime | None = None,
) -> bool:
    from app.services import time_context as time_context_service

    normalized = time_context_service.normalize_due_at(due, user_timezone)
    if normalized is None:
        return False
    current = now.astimezone(UTC) if now is not None else _now(UTC)
    return normalized <= current


def passed_time_reply() -> str:
    return _ALREADY_PASSED


def _now(tz: TzInfo) -> datetime:
    return datetime.now(tz)


def _fix_typos(text: str) -> str:
    parts: list[str] = []
    token: list[str] = []
    for char in text:
        if char.isalpha():
            token.append(char)
            continue
        if token:
            parts.append(_replace_token("".join(token)))
            token = []
        parts.append(char)
    if token:
        parts.append(_replace_token("".join(token)))
    return "".join(parts)


def _replace_token(token: str) -> str:
    fixed = _TYPOS.get(token.lower())
    return fixed if fixed is not None else token


def _title_of(rest: str) -> str:
    """ "to call mom", "submit the report to my reminders for", "- meet abel" → the task."""
    rest = _NEED_TO_RE.sub("", _LIST_PHRASE_RE.sub(" ", rest).strip())
    words = _title_before(rest, -1).split()
    while words and words[0].lower() in _TITLE_LEADS:
        words.pop(0)
    while words and words[-1].lower() in _TITLE_TAILS:
        words.pop()
    return " ".join(words)


def _title_before(body: str, day_at: int) -> str:
    chunk = body[:day_at] if day_at >= 0 else body
    words = []
    for word in chunk.split():
        bare = word.strip("\"'.,;:").lower()
        if not bare or any(bare == name for name, _rule in _REPEATS):
            continue
        words.append(word.strip("\"'.,;:"))
    while words and words[-1].lower() in _TRAILING_FILLER | {
        "everyday",
        "daily",
        "weekly",
        "monthly",
        "weekdays",
    }:
        words.pop()
    if (
        len(words) >= 2
        and words[-2].lower() == "every"
        and words[-1].lower()
        in {
            "day",
            "week",
            "weekday",
            "month",
        }
    ):
        del words[-2:]
    return " ".join(words).strip()
