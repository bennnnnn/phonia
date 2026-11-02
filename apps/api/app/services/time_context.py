"""User-local time context for LLM prompts (foundation for due dates & reminders)."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.timezone import DEFAULT_TIMEZONE, resolve_timezone
from app.services.calendar_facts import calendar_lines
from app.services.calendar_facts import correct_weekday_dates as correct_weekday_dates
from app.services.number_text import count_word_pattern, number_word_value
from app.services.text_normalize import collapse_ws, straighten_apostrophes

__all__ = ["DEFAULT_TIMEZONE", "resolve_timezone"]

# Patterns assume input was passed through ``collapse_ws`` (single spaces only).
_TIME_QUESTION = re.compile(
    r"^(?:"
    r"what(?:'s| is) the time(?: now)?"
    r"|what time is it(?: now)?"
    r"|what time(?: now)?"
    r"|tell me the (?:current )?time"
    r"|current time\??"
    r"|do you know the time\??"
    r"|time(?: please)?\??"
    r")[.!?]*$",
    re.IGNORECASE,
)

# Prefix only — place name is checked without `.+` (CodeQL py/polynomial-redos).
# Input must be `collapse_ws`'d first (single spaces, trimmed).
_REMOTE_TIME_PREFIX = re.compile(
    r"^(?:"
    r"what(?:'s| is) the time(?: now)? in "
    r"|what time is it(?: now)? in "
    r"|what time(?: now)? in "
    r"|current time in "
    r"|time(?: please)? in "
    r")",
    re.IGNORECASE,
)

_SCHEDULED_EVENT = re.compile(
    r"\b(meeting|appointment|flight|event|class|call|interview|game|train|bus)\b",
    re.IGNORECASE,
)

# Paired with ``_SCHEDULED_EVENT`` — "what time is my flight", not "what time is it".
_EVENT_WHEN = re.compile(
    r"\b(what time(?:'s| is)|when(?:'s| is)|what time does)\b",
    re.IGNORECASE,
)

_LOCATION_QUESTION = re.compile(
    r"^(?:"
    r"where am i(?: (?:at|right now|right nwo|now|currently))?\??"
    r"|what(?:'s| is) my (?:current |currnet )?location(?: (?:right now|now))?\??"
    r"|where(?:'s| is) my (?:current |currnet )?location(?: (?:right now|now))?\??"
    r"|where(?:'re| are) we(?: (?:right now|now|currently))?\??"
    r"|my (?:current |currnet )?location\??"
    r"|location\??"
    r")[.!?]*$",
    re.IGNORECASE,
)

# Folded letter-runs of the phrases above so "Where am iI" still counts. Written folded
# (letters only, no doubled letter: "current" is "curent"), or an entry never matches.
_LOCATION_ASK_MAX_LEN = 80
_LOCATION_ASK_FOLDED = frozenset(
    {
        "whereami",
        "whereamiat",
        "whereamirightnow",
        "whereamirightnwo",
        "whereaminow",
        "whereamicurently",
        "whatsmylocation",
        "whatismylocation",
        "whatsmycurentlocation",
        "whatismycurentlocation",
        "wherismylocation",
        "wheresmylocation",
        "whereismylocation",
        "wherearewe",
        "wherearewenow",
        "wherearewerightnow",
        "wherearewecurently",
        "mylocation",
        "mycurentlocation",
        "location",
    }
)


def _fold_location_ask(text: str) -> str:
    """Letters only, consecutive duplicates collapsed — linear, length-capped."""
    if len(text) > _LOCATION_ASK_MAX_LEN:
        return ""
    out: list[str] = []
    prev = ""
    for ch in text.lower():
        if "a" <= ch <= "z":
            if ch != prev:
                out.append(ch)
                prev = ch
    return "".join(out)


def effective_timezone(profile_tz: str | None, client_tz: str | None = None) -> str:
    """Prefer device timezone from the client; fall back to stored profile.

    Invalid IANA names (client or profile) fall back via :func:`resolve_timezone`
    so callers never receive a string that later crashes ``ZoneInfo(...)``.
    """
    if isinstance(client_tz, str) and client_tz.strip():
        try:
            return ZoneInfo(client_tz.strip()).key
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return resolve_timezone(profile_tz).key


def prefers_12h_clock(locale: str | None) -> bool:
    code = (locale or "en").split("-")[0].lower()
    return code == "en"


def format_digital_clock(when: datetime, locale: str | None = None) -> str:
    if prefers_12h_clock(locale):
        return when.strftime("%I:%M:%S %p")
    return when.strftime("%H:%M:%S")


def is_remote_time_question(text: str) -> bool:
    """True when the user asks for the time in another place (not local)."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    match = _REMOTE_TIME_PREFIX.match(cleaned)
    if match is None:
        return False
    place = cleaned[match.end() :].rstrip(".!?").strip()
    return bool(place)


def is_scheduled_event_time_question(text: str) -> bool:
    """True when they ask when a personal event is (flight, meeting, …)."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    if _SCHEDULED_EVENT.search(cleaned) is None:
        return False
    return _EVENT_WHEN.search(cleaned) is not None


def _normalize_now_ask(text: str) -> str:
    """Lowercased, punctuation-stripped ask. Linear — no regex."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned:
        return ""
    while cleaned and cleaned[-1] in ".!?":
        cleaned = cleaned[:-1].rstrip()
    normalized = cleaned.lower()
    # Courtesy wrappers do not change a local clock/calendar question. Strip
    # them as grammar so "please/could you tell me..." uses the same local
    # owner instead of being sent to the web classifier.
    # "ok what time is it", "wait whats the date today": a filler first word too.
    courtesy_prefixes = (
        "please ",
        "can you ",
        "could you ",
        "would you ",
        "ok ",
        "okay ",
        "hey ",
        "hi ",
        "wait ",
        "um ",
        "so ",
        "btw ",
        "quick question ",
    )
    for _ in range(3):
        for prefix in courtesy_prefixes:
            if normalized.startswith(prefix) or normalized.startswith(prefix.rstrip() + ", "):
                normalized = normalized[len(prefix) :].lstrip(" ,")
                break
        else:
            break
    return normalized


_YEAR_ASKS = frozenset(
    {
        "what year is it",
        "what's the year",
        "whats the year",
        "what is the year",
        "what year is it now",
        "what year now",
        "current year",
        "what year is this",
        "what year are we in",
        "what year is it today",
        "what's the current year",
        "whats the current year",
        "what is the current year",
        "tell me the year",
        "tell me the current year",
    }
)

_DATE_ASKS = frozenset(
    {
        "what's the date",
        "whats the date",
        "what is the date",
        "what's today's date",
        "whats today's date",
        "whats todays date",
        "what is today's date",
        "what is todays date",
        "today's date",
        "todays date",
        "what date is it",
        "what date is it today",
        "what date is it now",
        "what's the date today",
        "whats the date today",
        "what is the date today",
        "what's the date now",
        "whats the date now",
        "what is the date now",
        "what's todays date",
        "current date",
        "tell me the current date",
        "tell me current date",
        "tell me today's date",
        "what day is it",
        "what day is it today",
        "what day is today",
        "what's the day",
    }
)


def is_year_question(text: str) -> bool:
    """True for the user's *current* year question only (not 'what year did …')."""
    return _normalize_now_ask(text) in _YEAR_ASKS


def is_current_date_question(text: str) -> bool:
    """True for today's date / what day is it — not 'what date is Christmas'."""
    return _normalize_now_ask(text) in _DATE_ASKS


# The user is disputing a clock we already showed. Substring marks stay linear.
# "I don't have time" is availability, not this.
_TIME_DENIAL_MARKS = (
    "don't know the time",
    "dont know the time",
    "do not know the time",
    "don't know what time",
    "dont know what time",
    "do not know what time",
    "didn't know the time",
    "didnt know the time",
    "did not know the time",
    "can't tell the time",
    "cant tell the time",
    "cannot tell the time",
    "can't tell what time",
    "cant tell what time",
    "cannot tell what time",
    "don't have a clock",
    "dont have a clock",
    "do not have a clock",
    "don't have access to real-time",
    "dont have access to real-time",
    "do not have access to real-time",
    "don't have access to a clock",
    "dont have access to a clock",
    "no access to real-time",
    "no access to a clock",
    "no access to the clock",
)
_TIME_DENIAL_REPLY = "No. I didn't say that. The clock above is the current time."

# Pointing at the clock already on screen. Not a request for a second widget.
_SHOWN_CLOCK_MARKS = (
    "time above",
    "time is above",
    "time up there",
    "time on the clock",
    "time is the clock",
    "time does the clock",
    "time does it say",
    "time does that say",
    "clock say",
    "clock above",
)
_SHOWN_CLOCK_MAX_LEN = 80


def is_time_denial(text: str) -> bool:
    """True when the user says we do not know the current time."""
    cleaned = _normalize_now_ask(text)
    if not cleaned or _SCHEDULED_EVENT.search(cleaned):
        return False
    return any(mark in cleaned for mark in _TIME_DENIAL_MARKS)


def is_shown_clock_question(text: str) -> bool:
    """True when the user is asking for the time already on screen."""
    cleaned = _normalize_now_ask(text)
    if (
        not cleaned
        or len(cleaned) > _SHOWN_CLOCK_MAX_LEN
        or _SCHEDULED_EVENT.search(cleaned)
        or is_remote_time_question(cleaned)
    ):
        return False
    return any(mark in cleaned for mark in _SHOWN_CLOCK_MARKS)


# Whole message only, after collapse_ws. No `.+` (CodeQL py/polynomial-redos).
_RELATIVE_DAY = re.compile(
    r"^(?:and |what about )?"
    rf"(?P<count>\d{{1,3}}|{count_word_pattern()}) "
    r"days? "
    r"(?P<direction>ago|before|after(?: today)?|later|from now|from today)$",
    re.IGNORECASE,
)
_IN_DAYS = re.compile(
    rf"^in (?P<count>\d{{1,3}}|{count_word_pattern()}) days?$",
    re.IGNORECASE,
)
_PAST_DIRECTIONS = frozenset({"ago", "before"})


def _day_count(raw: str) -> int | None:
    if raw.isdigit():
        count = int(raw)
        return count if 1 <= count <= 366 else None
    return number_word_value(raw)


def relative_day_offset(text: str) -> int | None:
    """Signed day offset for a short 'N days ago/after' ask. None otherwise."""
    cleaned = _normalize_now_ask(text)
    if not cleaned or _SCHEDULED_EVENT.search(cleaned):
        return None
    match = _RELATIVE_DAY.match(cleaned) or _IN_DAYS.match(cleaned)
    if match is None:
        return None
    count = _day_count(match.group("count"))
    if count is None:
        return None
    direction = match.groupdict().get("direction") or "after"
    if direction in _PAST_DIRECTIONS:
        return -count
    return count


def format_relative_day_answer(offset: int, timezone: str | None) -> str:
    tz = resolve_timezone(timezone)
    when = datetime.now(tz) + timedelta(days=offset)
    written = when.strftime(f"%A, %B {when.day}, %Y")
    span = abs(offset)
    unit = "day" if span == 1 else "days"
    if offset < 0:
        return f"{span} {unit} ago was {written}."
    return f"{span} {unit} after today is {written}."


def is_local_now_question(text: str) -> bool:
    """Current local time, year, or date — facts we already know without the LLM."""
    return (
        is_time_question(text)
        or is_year_question(text)
        or is_current_date_question(text)
        or is_time_denial(text)
        or is_shown_clock_question(text)
        or relative_day_offset(text) is not None
    )


def format_year_answer(timezone: str | None) -> str:
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    return f"It's {now.year}."


def format_date_answer(timezone: str | None) -> str:
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    return f"{now.strftime('%A, %B')} {now.day}, {now.year}."


def format_shown_clock_answer(timezone: str | None, locale: str | None = None) -> str:
    """Read the same local instant the clock widget is showing."""
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    clock = format_digital_clock(now, locale)
    if clock.startswith("0"):
        clock = clock[1:]
    tzname = now.tzname() or ""
    date = f"{now.strftime('%A, %B')} {now.day}, {now.year}"
    return f"{date}, {clock} {tzname}".rstrip() + "."


def maybe_local_now_reply(
    text: str,
    timezone: str | None,
    locale: str | None = None,
) -> str | None:
    """Server-owned answers for current time / year / date. Skip the LLM."""
    if is_time_denial(text):
        return _TIME_DENIAL_REPLY
    if is_shown_clock_question(text):
        return format_shown_clock_answer(timezone, locale)
    if is_time_question(text):
        return format_time_answer(timezone, locale)
    if is_year_question(text):
        return format_year_answer(timezone)
    if is_current_date_question(text):
        return format_date_answer(timezone)
    offset = relative_day_offset(text)
    if offset is not None:
        return format_relative_day_answer(offset, timezone)
    return None


def is_time_question(text: str) -> bool:
    """True for the user's *local* current-time question only."""
    cleaned = _normalize_now_ask(text)
    if not cleaned:
        return False
    if is_remote_time_question(cleaned):
        return False
    if _TIME_QUESTION.match(cleaned):
        return _SCHEDULED_EVENT.search(cleaned) is None
    return False


def is_location_question(text: str) -> bool:
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned:
        return False
    if _LOCATION_QUESTION.match(cleaned):
        return True
    return _fold_location_ask(cleaned) in _LOCATION_ASK_FOLDED


def format_location_answer(location: str | None, timezone: str | None) -> str:
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    time_str = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
    if location:
        return f"You're in **{location}**. Local time: {time_str}."
    return (
        "I don't have your location yet. Turn on Location in Recall Settings "
        "(Preferences), allow access if prompted, then ask again."
    )


def format_now_awareness(
    timezone: str | None, locale: str | None = None, message: str | None = None
) -> str:
    """Facts every reply can use, with the calendar for the dates *message* names."""
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    clock = format_digital_clock(now, locale)
    if clock.startswith("0"):
        clock = clock[1:]
    month = now.strftime("%B")
    tzname = now.tzname() or ""
    return (
        f"Current local time: {now.strftime('%A')}, {month} {now.day}, {now.year}, "
        f"{clock} {tzname}. Year {now.year}. Month {month}. "
        "You know them: say them only when asked or the answer needs them, never as filler. "
        "Never say you lack a clock. Told today is another day? Give today's date once, no sorry. "
        # A weekday by its full date is checked before the reply is saved:
        # "Christmas falls on a Monday" was wrong (2026's is a Friday).
        "When you name the weekday of a date, write the full date with it "
        '("Friday, December 25, 2026"). '
        # Read, not counted: "what is Tuesday" and "Christmas's weekday" were miscounted.
        f"{calendar_lines(now, message)}"
    )


def format_time_answer(timezone: str | None, locale: str | None = None) -> str:
    del locale  # live widget reads timezone from the user profile on device
    return "```clock\n```"


def format_time_context(
    timezone: str | None,
    locale: str | None = None,
    location: str | None = None,
) -> str:
    tz = resolve_timezone(timezone)
    now = datetime.now(tz)
    digital = format_digital_clock(now, locale)
    parts = [
        f"User local date & time ({now.tzname()}): "
        f"{now.strftime('%A, %B %d, %Y %H:%M %Z')}. "
        f"Digital clock now: {digital}.",
    ]
    if location:
        parts.append(f"User approximate location (from device GPS): {location}.")
    else:
        parts.append("User location is not synced yet.")
    parts.append(
        "When the user asks what time it is *here* (no other city/place), reply with "
        "only an empty ```clock``` fence. The app renders a live circular analog clock "
        "for their local timezone — never paste timezone names, HH:MM text, or any "
        "other content inside that empty fence. "
        "When they ask the time in another city or place, do NOT use an empty clock "
        "fence (that would show the user's local time). Put the place's IANA timezone "
        "alone inside the fence, e.g. ```clock\\nAmerica/New_York\\n``` for Washington "
        "DC / US Eastern, or answer in short prose with the local time there. "
        "When they ask where they are, use the location above if set. "
        "Use this when answering questions about today, deadlines, overdue reminders, "
        "or how long until something is due. "
        "A clock hour keeps the part of day they used. Morning is AM. Afternoon, "
        "evening, and night are not the morning: 4 in the evening is 16:00, never "
        "04:00 or 4 AM."
    )
    return " ".join(parts)


def normalize_due_at(due_at: datetime | None, user_timezone: str | None) -> datetime | None:
    if due_at is None:
        return None
    tz = resolve_timezone(user_timezone)
    if due_at.tzinfo is None:
        localized = due_at.replace(tzinfo=tz)
    else:
        localized = due_at.astimezone(tz)
    return localized.astimezone(UTC)


def describe_due_at(
    due_at: datetime | None,
    user_timezone: str | None,
    *,
    checked: bool = False,
) -> str:
    if due_at is None or checked:
        return ""
    tz = resolve_timezone(user_timezone)
    now = datetime.now(tz)
    if due_at.tzinfo:
        due_local = due_at.astimezone(tz)
    else:
        due_local = due_at.replace(tzinfo=UTC).astimezone(tz)
    delta = due_local - now
    if delta.total_seconds() < 0:
        if due_local.date() == now.date():
            return "overdue today"
        days = max(1, abs(delta.days))
        return f"overdue by {days} day{'s' if days != 1 else ''}"
    if due_local.date() == now.date():
        return f"due today {due_local.strftime('%H:%M')}"
    days = delta.days
    if days == 0:
        hours = max(1, int(delta.total_seconds() // 3600))
        return f"due in {hours} hour{'s' if hours != 1 else ''}"
    if days <= 7:
        return f"due in {days} day{'s' if days != 1 else ''} ({due_local.strftime('%a %b %d')})"
    return f"due {due_local.strftime('%a %b %d, %Y')}"
