"""Apply a clear done, reopen, delete, or move from the user's own words.

The model often confirms those changes without a reminder fence, or labels
"mark done" as a delete. The words the user typed decide the change. A later
extractor must not run again and rewrite the row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from datetime import tzinfo as TzInfo

from app.modules.todos.schemas import RecurrenceRule
from app.modules.todos.spoken_target import SpokenAction, title_words
from app.modules.todos.spoken_when import DAY_NAMES, Clock, due_on_day, find_clock, read_clock

_BULK = frozenset(
    {"overdue", "all", "them", "everything", "these", "those", "first", "last", "second", "third"}
)
_JUST_DONE_RE = re.compile(
    r"(?:done|did it|all done|finished it|completed it)(?!\s+with\b)(?:\s|$|[!.,])"
)
_PRONOUNS = frozenset({"it", "this", "that"})
_FILLERS = frozenset({"for", "to", "at", "on", "the", "a", "an"})
_DONE_TAILS = (" as completed", " as complete", " as done", " completed", " complete", " done")
_TRAILING = (" reminders", " reminder", " todos", " todo", " tasks", " task", " call")
_REPEAT_MARKS: tuple[tuple[str, RecurrenceRule], ...] = (
    ("weekday", "weekdays"),
    ("everyday", "daily"),
    ("every day", "daily"),
    ("daily", "daily"),
    ("every week", "weekly"),
    ("weekly", "weekly"),
    ("every month", "monthly"),
    ("monthly", "monthly"),
)
_ADJUST_LEADS = ("make ", "change ", "set ", "put ", "move ")
_FILLER_LEADS = (
    "please ",
    "pls ",
    "can you ",
    "could you ",
    "actually ",
    "ok so ",
    "okay so ",
    "ok ",
    "okay ",
    "oh ",
    "yes ",
    "yeah ",
    "also ",
    "and ",
    "wait ",
    "so ",
)
_FILLER_TAILS = (" instead", " please", " then", " thanks", " thank you", " pls")
_CLAUSE_SPLIT = re.compile(r"[,;]|\s[\u2014\u2013-]\s")


@dataclass(frozen=True)
class SpokenReminderChange:
    action: SpokenAction
    title_hint: str
    due_at: datetime | None = None
    repeat: RecurrenceRule | None = None
    use_latest: bool = False
    keep_date: bool = False
    hour: int | None = None
    minute: int | None = None
    topic: str | None = None
    needs_time: bool = False
    # "Move it to Sunday, same time": the day changes and the clock stays.
    day: str | None = None
    # "Push it to next week": the same day and clock, this many days later.
    shift_days: int = 0
    # "I paid rent, check it off": the other clause says what "it" is.
    context_hint: str = ""


def parse_spoken_reminder_change(
    user_text: str | None,
    *,
    user_timezone: str | None = None,
    now: datetime | None = None,
) -> SpokenReminderChange | None:
    """Parse one named done, reopen, delete, or move. Bulk and undated moves stay out.

    "I paid rent, check it off" and "delete it, my roommate does it now" carry
    the change in one clause; each clause is tried when the whole is not one.
    """
    parsed = _parse_change(user_text, user_timezone=user_timezone, now=now)
    if parsed is not None or not user_text:
        return parsed
    clauses = [part.strip() for part in _CLAUSE_SPLIT.split(user_text)]
    if len(clauses) < 2:
        return None
    for index, clause in enumerate(clauses):
        parsed = _parse_change(clause, user_timezone=user_timezone, now=now)
        if parsed is None:
            continue
        if parsed.use_latest:
            context = " ".join(clauses[:index] + clauses[index + 1 :])
            return replace(parsed, context_hint=context)
        return parsed
    return None


def _parse_change(
    user_text: str | None,
    *,
    user_timezone: str | None,
    now: datetime | None,
) -> SpokenReminderChange | None:
    text = _checked_off(prepare_words(user_text))
    if not text:
        return None
    lowered = text.lower()
    # "Done ✅ just talked to her", "did it": the reminder that was just discussed.
    if _JUST_DONE_RE.match(lowered):
        return SpokenReminderChange(action="complete", title_hint="", use_latest=True)
    if lowered.startswith("remove ") and _rest(text, "remove ").lower().startswith("the date"):
        return None
    verbs: tuple[tuple[str, SpokenAction], ...] = (
        ("mark ", "complete"),
        ("complete ", "complete"),
        ("finish ", "complete"),
        ("reopen ", "uncheck"),
        ("uncheck ", "uncheck"),
        ("delete ", "delete"),
        ("remove ", "delete"),
        ("done with ", "complete"),
        ("move ", "set_due"),
        ("reschedule ", "set_due"),
        ("push ", "set_due"),
        ("postpone ", "set_due"),
        ("bump ", "set_due"),
    )
    for verb, action in verbs:
        if not lowered.startswith(verb):
            continue
        rest = _rest(text, verb)
        if action == "set_due":
            parsed = _parse_move(rest, user_timezone=user_timezone, now=now)
            if parsed is not None:
                return parsed
            continue
        # "Delete it, my roommate does it now": the reason is not the name.
        rest = _CLAUSE_SPLIT.split(rest, maxsplit=1)[0]
        if action == "complete":
            rest = _strip_done_tail(rest)
        hint = _clean_title(rest)
        if title_words(hint) & _BULK:
            return None
        if _is_only_pronoun(hint):
            return SpokenReminderChange(action=action, title_hint="", use_latest=True)
        if not title_words(hint):
            return None
        return SpokenReminderChange(action=action, title_hint=hint)
    return _parse_adjust(text, user_timezone=user_timezone, now=now)


def _parse_move(
    rest: str,
    *,
    user_timezone: str | None,
    now: datetime | None,
) -> SpokenReminderChange | None:
    lowered = rest.lower()
    to_at = lowered.find(" to ")
    if to_at < 0:
        return None
    hint = _clean_title(rest[:to_at])
    use_latest = _is_only_pronoun(hint)
    if not title_words(hint) and not use_latest:
        return None
    after = rest[to_at + len(" to ") :]
    title_hint = "" if use_latest else hint
    if after.lower().startswith("next week"):
        return SpokenReminderChange(
            action="set_due", title_hint=title_hint, use_latest=use_latest, shift_days=7
        )
    following = ""
    if after.lower().startswith("next "):
        following = "next "
        after = after[len(following) :]
    day_end = 0
    while day_end < len(after) and after[day_end].isalpha():
        day_end += 1
    day_name = after[:day_end].lower()
    if day_name not in DAY_NAMES:
        return None
    at_rel = after.lower().find(" at ", day_end)
    if at_rel < 0:
        if "same time" not in after.lower():
            return None
        return SpokenReminderChange(
            action="set_due",
            title_hint=title_hint,
            use_latest=use_latest,
            day=following + day_name,
        )
    clock = read_clock(after, at_rel + len(" at "))
    if clock is None:
        return None
    due = _due_on_day(following + day_name, clock, user_timezone=user_timezone, now=now)
    if due is None:
        return None
    return SpokenReminderChange(
        action="set_due",
        title_hint="" if use_latest else hint,
        due_at=due,
        repeat=_repeat(after[at_rel:].lower()),
        use_latest=use_latest,
    )


def _now(tz: TzInfo) -> datetime:
    return datetime.now(tz)


def _repeat(tail: str) -> RecurrenceRule | None:
    for mark, rule in _REPEAT_MARKS:
        if mark in tail:
            return rule
    return None


def prepare_words(user_text: str | None) -> str:
    """Drop "actually", "ok", "please", a trailing "instead" or emoji around the change."""
    words = (user_text or "").split()
    while words and not any(char.isalnum() for char in words[-1]):
        words.pop()
    text = " ".join(words)
    while text and text[-1] in ".!?":
        text = text[:-1].rstrip()
    changed = True
    while changed:
        changed = False
        lowered = text.lower()
        for lead in _FILLER_LEADS:
            if lowered.startswith(lead):
                text = text[len(lead) :].lstrip(" ,")
                changed = True
                break
        lowered = text.lower()
        for tail in _FILLER_TAILS:
            if lowered.endswith(tail):
                text = text[: -len(tail)].rstrip(" ,")
                changed = True
                break
    return text


def _checked_off(text: str) -> str:
    """ "check it off", "tick the rent off", "cross off gym" → "complete …"."""
    lowered = text.lower()
    for verb in ("check ", "tick ", "cross "):
        if not lowered.startswith(verb):
            continue
        rest = text[len(verb) :].strip()
        if rest.lower().startswith("off "):
            return "complete " + rest[len("off ") :]
        if rest.lower().endswith(" off"):
            return "complete " + rest[: -len(" off")]
    return text


def _rest(text: str, verb: str) -> str:
    return text[len(verb) :].strip()


def _strip_done_tail(text: str) -> str:
    lowered = text.lower()
    for tail in _DONE_TAILS:
        if lowered.endswith(tail):
            return text[: -len(tail)].rstrip()
    return text


def _clean_title(text: str) -> str:
    title = text.strip().strip("\"'").rstrip(".,;:")
    lowered = title.lower()
    for lead in ("the ", "my ", "a "):
        if lowered.startswith(lead):
            title = title[len(lead) :].strip()
            lowered = title.lower()
            break
    changed = True
    while changed and title:
        changed = False
        lowered = title.lower()
        for tail in _TRAILING:
            if lowered.endswith(tail):
                title = title[: -len(tail)].rstrip()
                changed = True
                break
    return title.strip()


# "Mark the dentist reminder as done" names reminders; "finish the story",
# "delete the last paragraph", "remove duplicates from a list" or "make me a
# study schedule" does not.
_NAMES_REMINDERS = re.compile(
    r"\b(?:remind(?:er|ers)?|to-?dos?|tasks?|(?:my|your)\s+schedule"
    r"|as\s+(?:done|complete|completed|finished))\b",
    re.IGNORECASE,
)


_MY_REMINDERS = re.compile(
    r"\b(?:my|your)\s+(?:reminders?|to-?dos?|to-do\s+list|tasks?|schedule)\b|\bremind\s+me\b",
    re.IGNORECASE,
)


def asks_about_my_reminders(user_text: str | None) -> bool:
    """ "Whats next on my reminders", "delete one of my reminders" — not "a todo app"."""
    return bool(user_text and _MY_REMINDERS.search(user_text))


def names_reminders(user_text: str | None) -> bool:
    """True when the message itself says it is about a reminder or task."""
    return bool(user_text and _NAMES_REMINDERS.search(user_text))


def _parse_adjust(
    text: str,
    *,
    user_timezone: str | None,
    now: datetime | None,
) -> SpokenReminderChange | None:
    """'Make it daily', 'make it 8:00 AM', or 'put it in Health'."""
    lowered = text.lower()
    body = ""
    for lead in _ADJUST_LEADS:
        if lowered.startswith(lead):
            body = text[len(lead) :].strip()
            break
    if not body or _is_fresh_reminder(body):
        return None
    clock = find_clock(body)
    day = _marked_day(body)
    repeat = _repeat(body.lower())
    topic = None
    if clock is None and repeat is None and day is None:
        topic = _topic_name(body)
    hint, use_latest = _subject(body, clock=clock, day=day, repeat=repeat, topic=topic)
    if day is not None and clock is not None:
        due = _due_on_day(day[0], clock, user_timezone=user_timezone, now=now)
        if due is None:
            return None
        return SpokenReminderChange(
            action="set_due",
            title_hint=hint,
            due_at=due,
            repeat=repeat,
            use_latest=use_latest,
        )
    if day is not None:
        return SpokenReminderChange(
            action="set_due",
            title_hint=hint,
            use_latest=use_latest,
            needs_time=True,
        )
    if clock is not None:
        return SpokenReminderChange(
            action="set_due",
            title_hint=hint,
            repeat=repeat,
            use_latest=use_latest,
            keep_date=True,
            hour=clock.hour,
            minute=clock.minute,
        )
    if repeat is not None:
        return SpokenReminderChange(
            action="set_due",
            title_hint=hint,
            repeat=repeat,
            use_latest=use_latest,
        )
    if topic is not None:
        return SpokenReminderChange(
            action="set_due",
            title_hint=hint,
            use_latest=use_latest,
            topic=topic,
        )
    return None


def _is_fresh_reminder(body: str) -> bool:
    """ "Make a reminder …" or "make me a study schedule …" creates; it changes nothing."""
    lowered = body.lower()
    return lowered.startswith(("a ", "an ", "me ", "us ", "reminder ", "some ", "another ", "new "))


def _subject(
    body: str,
    *,
    clock: Clock | None,
    day: tuple[str, int] | None,
    repeat: RecurrenceRule | None,
    topic: str | None,
) -> tuple[str, bool]:
    cut = len(body)
    lowered = body.lower()
    if repeat is not None:
        for mark, rule in _REPEAT_MARKS:
            if rule != repeat:
                continue
            at = lowered.find(mark)
            if at >= 0:
                cut = min(cut, at)
    if clock is not None:
        cut = min(cut, clock.start)
    if day is not None:
        cut = min(cut, day[1])
    if topic is not None:
        for mark in (" in the ", " in ", " under the ", " under ", "category", "topic"):
            at = lowered.find(mark)
            if at >= 0:
                cut = min(cut, at)
    hint = _clean_title(_strip_fillers(body[:cut]))
    if _is_only_pronoun(hint) or not title_words(hint):
        return "", True
    return hint, False


def _due_on_day(
    day_name: str,
    clock: Clock,
    *,
    user_timezone: str | None,
    now: datetime | None,
) -> datetime | None:
    from app.services import time_context as time_context_service

    tz = time_context_service.resolve_timezone(user_timezone)
    when = now.astimezone(tz) if now is not None else _now(tz)
    return due_on_day(day_name, clock.hour, clock.minute, when)


def _marked_day(text: str) -> tuple[str, int] | None:
    lowered = text.lower()
    for mark in (" to ", " on ", " for "):
        start = 0
        while start < len(lowered):
            at = lowered.find(mark, start)
            if at < 0:
                break
            rest_at = at + len(mark)
            while rest_at < len(lowered) and lowered[rest_at] == " ":
                rest_at += 1
            end = rest_at
            while end < len(lowered) and lowered[end].isalpha():
                end += 1
            name = lowered[rest_at:end]
            if name in DAY_NAMES:
                return name, rest_at
            start = at + len(mark)
    return None


def _topic_name(body: str) -> str | None:
    lowered = body.lower()
    for mark in ("category to ", "topic to ", " in the ", " in ", " under the ", " under ", " to "):
        at = lowered.rfind(mark)
        if at < 0:
            continue
        name = body[at + len(mark) :].strip().strip(".,!?").strip()
        if name.lower().endswith(" category"):
            name = name[: -len(" category")].strip()
        if _ok_topic(name):
            return name
    return None


def _ok_topic(name: str) -> bool:
    if not name or len(name) > 40:
        return False
    words = name.split()
    if not 1 <= len(words) <= 3 or not all(word.isalpha() for word in words):
        return False
    lowered = name.lower()
    if lowered in DAY_NAMES or lowered in _PRONOUNS:
        return False
    if lowered in {"morning", "afternoon", "evening", "night", "daily", "weekly", "monthly"}:
        return False
    return "everyday" not in lowered and "week" not in lowered


def _strip_fillers(text: str) -> str:
    parts = text.split()
    while parts and parts[-1].strip(".,!?").lower() in _FILLERS:
        parts.pop()
    while parts and parts[0].strip(".,!?").lower() in _FILLERS:
        parts.pop(0)
    return " ".join(parts)


def _is_only_pronoun(text: str) -> bool:
    parts = [
        part
        for part in (word.strip(".,!?").lower() for word in text.split())
        if part and part not in _FILLERS
    ]
    return len(parts) == 1 and parts[0] in _PRONOUNS
