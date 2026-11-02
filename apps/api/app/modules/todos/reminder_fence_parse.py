"""Read a reminder draft: the model's ```reminder fence, or the user's own words.

The fence is JSON the model writes, validated before anything is saved. When
the model left it out or wrote an invalid one, an explicit "remind me to call
mom tomorrow at 6pm" stands in for it. A clock is never invented.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.modules.todos.schemas import TODO_TEXT_MAX_CHARS, RecurrenceRule
from app.modules.todos.spoken_when import DAY_NAMES, due_on_day, read_clock
from app.services import time_context as time_context_service
from app.services.md_fence_scan import block_end, iter_fences

_DECLINES_REMINDER_CREATE_RE = re.compile(
    r"\b(?:do\s+not|don(?:'|\u2019)?t|dont|never)\s+"
    r"(?:(?:create|set|add|make|save|schedule)\s+(?:me\s+)?(?:a\s+|the\s+|any\s+)?reminder"
    r"|remind\s+me)\b"
    r"|\bwithout\s+(?:creating|setting|adding|making|saving|scheduling)\s+"
    r"(?:a\s+|the\s+|any\s+)?reminder\b",
    re.IGNORECASE,
)


def explicitly_declines_reminder_creation(user_text: str | None) -> bool:
    """True when this turn explicitly asks Recall not to save a reminder."""
    return bool(user_text and _DECLINES_REMINDER_CREATE_RE.search(user_text))


class ReminderFence(BaseModel):
    """One reminder change: the model's fence, or a draft built from the user's words."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    action: Literal["add", "complete", "uncheck", "delete", "set_due", "clear_due"] = "add"
    title: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("title", "content", "task", "name"),
    )
    due_at: datetime | None = None
    repeat: RecurrenceRule | None = Field(default=None, alias="recurrence_rule")

    @field_validator("due_at", mode="before")
    @classmethod
    def _coerce_due_at(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith(("Z", "z")):
            raw = raw[:-1] + "+00:00"
        if "T" not in raw and " " in raw[:19]:
            raw = raw.replace(" ", "T", 1)
        date_only = len(raw) == 10 and raw[4] == "-" and raw[7] == "-"
        if date_only:
            raise ValueError("due_at must include a time")
        # The user's own clock, whatever offset the model wrote: models copied an
        # example's -04:00 (9am became 1 PM in UTC) or added Z to a local time. The
        # writer applies the user's time zone to this wall-clock time.
        try:
            return datetime.fromisoformat(raw).replace(tzinfo=None)
        except ValueError:
            return raw

    @model_validator(mode="after")
    def validate_date_and_repeat(self) -> Self:
        if self.action == "set_due" and self.due_at is None:
            raise ValueError("set_due requires due_at")
        if self.repeat is not None and self.due_at is None:
            raise ValueError("repeat requires due_at")
        return self


def _load_fence_json(raw: str) -> dict[str, object] | None:
    text = raw.strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        if snippet != text:
            candidates.append(snippet)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_fence(raw: str) -> ReminderFence | None:
    data = _load_fence_json(raw)
    if data is None:
        return None
    try:
        return ReminderFence.model_validate(data)
    except ValidationError:
        return None


def find_reminder_fences(text: str) -> list[tuple[int, int, str]]:
    """Each closed ```reminder fence: (start, end before its closer's line break, body).

    Read with the one fence grammar, linear (the regex before it was a CodeQL
    py/polynomial-redos finding), which closes a fence only on a closer line: the scan
    before it closed on the first triple backtick anywhere (code-health audit DUP-03).
    """
    return [
        (fence.start, block_end(text, fence), text[fence.body_start : fence.body_end])
        for fence in iter_fences(text)
        if fence.closed and fence.lang == "reminder"
    ]


def _find_phrase(haystack: str, needle: str, *, start: int = 0) -> int:
    """Return the index of ``needle`` as a whole-word phrase, or -1."""
    pos = start
    needle_len = len(needle)
    while True:
        idx = haystack.find(needle, pos)
        if idx < 0:
            return -1
        before_ok = idx == 0 or not haystack[idx - 1].isalpha()
        after = idx + needle_len
        after_ok = after >= len(haystack) or not haystack[after].isalpha()
        if before_ok and after_ok:
            return idx
        pos = idx + 1


def _skip_spaces(text: str, index: int) -> int:
    length = len(text)
    while index < length and text[index].isspace():
        index += 1
    return index


def _last_at_separator(haystack: str, start: int) -> int:
    """Index of the last `` at `` separator at or after ``start``, or -1."""
    last = -1
    pos = start
    while True:
        idx = haystack.find(" at ", pos)
        if idx < 0:
            return last
        last = idx
        pos = idx + 1


def parse_spoken_remind(
    user_text: str | None,
    *,
    user_timezone: str | None = None,
    now: datetime | None = None,
) -> tuple[str, datetime] | None:
    """Linear parse of ``remind me [to] TITLE DAY at H[:MM] am/pm``.

    DAY is today, tomorrow, or a weekday name. Missing clocks are not invented.
    """
    if not user_text:
        return None
    if explicitly_declines_reminder_creation(user_text):
        return None
    lowered = user_text.lower()
    remind_at = _find_phrase(lowered, "remind me")
    if remind_at < 0:
        return None
    cursor = _skip_spaces(user_text, remind_at + len("remind me"))
    if lowered.startswith("to", cursor) and (
        cursor + 2 >= len(lowered) or not lowered[cursor + 2].isalpha()
    ):
        cursor = _skip_spaces(user_text, cursor + 2)
    title_start = cursor
    last_at = _last_at_separator(lowered, title_start)
    if last_at < 0:
        return None
    clock = read_clock(user_text, last_at + len(" at "))
    if clock is None:
        return None
    before = user_text[title_start:last_at].rstrip()
    if not before:
        return None
    split = before.rfind(" ")
    day_raw = before[split + 1 :] if split >= 0 else before
    day_token = day_raw.strip().strip("\"'").rstrip(".,;:").lower()
    if day_token not in DAY_NAMES:
        return None
    title = (before[:split] if split >= 0 else "").strip().strip("\"'").rstrip(".,;:")
    if not title:
        return None
    tz = time_context_service.resolve_timezone(user_timezone)
    when = now.astimezone(tz) if now is not None else datetime.now(tz)
    due = due_on_day(day_token, clock.hour, clock.minute, when)
    if due is None:
        return None
    return title[:TODO_TEXT_MAX_CHARS], due


def explicit_user_remind(user_text: str | None, user_timezone: str | None) -> ReminderFence | None:
    """Parse 'remind me … today/tomorrow/weekday at 6pm' from the user — never invent a clock."""
    parsed = parse_spoken_remind(user_text, user_timezone=user_timezone)
    if parsed is None:
        return None
    title, due = parsed
    return ReminderFence(action="add", title=title, due_at=due)
