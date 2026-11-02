# ruff: noqa: RUF001
"""Where a lesson stands: its step, its titles, the subject a message asks to learn."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.turn_reading.teaching import _TEACH_TURN, is_teaching_request
from app.services.md_fence_scan import iter_fences
from app.services.text_normalize import collapse_ws

# "### Lesson 2: Dictionaries": a heading with the word Lesson in an app
# language and the lesson's number. "Day 1", "Part 2" and "Step 3" are plans,
# parts and how-tos, not lessons.
_LESSON_WORDS = r"lesson|lecci[oó]n|le[cç]on|lektion|lezione|li[cç][aã]o|aula|урок|ders|ትምህርት"


_LESSON_TITLE = re.compile(
    r"^\s*(?:#{1,4}\s+|\*\*)\s*(?:" + _LESSON_WORDS + r")\s+(\d{1,2})\s*[:.\-—–]",
    re.MULTILINE | re.IGNORECASE,
)


# The same heading with its topic: "### Lesson 2: Dictionaries" -> (2, "Dictionaries").
_LESSON_HEADING = re.compile(
    r"^\s*(?:#{1,4}\s+|\*\*)\s*(?:" + _LESSON_WORDS + r")\s+(\d{1,2})\s*[:.\-—–]\s*(.+?)\s*\**\s*$",
    re.MULTILINE | re.IGNORECASE,
)


# Past this, the learner has slept on the last lesson: recall it before the next.
LESSON_RECAP_AFTER = timedelta(hours=20)


_QUESTION_MARKS = ("?", "？", "፧")


def lesson_step(text: str | None) -> int | None:
    """The number of the lesson an assistant reply taught, or None.

    A lesson ends on practice: a ```quiz card or a question after its title. A
    reply that only mentions "Lesson 2" in passing is not one.
    """
    if not text:
        return None
    found: int | None = None
    end = 0
    for match in _LESSON_TITLE.finditer(text):
        found, end = int(match.group(1)), match.end()
    if found is None or found < 1:
        return None
    rest = text[end:]
    quiz = any(fence.lang == "quiz" for fence in iter_fences(rest))
    if quiz or any(mark in rest for mark in _QUESTION_MARKS):
        return found
    return None


def active_lesson_step(messages: list[Any] | None) -> int | None:
    """The lesson the most recent assistant reply taught, in an oldest-first window."""
    for message in reversed(messages or []):
        if getattr(message, "role", None) != "assistant":
            continue
        content = getattr(message, "content", None)
        return lesson_step(content if isinstance(content, str) else None)
    return None


def outline_awaits_pick(messages: list[Any] | None) -> bool:
    """True when the last reply answered a "teach me" with a subject outline, not a lesson.

    It ends on a question (where to start) and has no lesson title, so the
    next message picks a topic, gives a level or says "start".
    """
    rows = [
        m
        for m in messages or []
        if getattr(m, "role", None) in {"user", "assistant"}
        and isinstance(getattr(m, "content", None), str)
    ]
    if len(rows) < 2 or rows[-1].role != "assistant" or rows[-2].role != "user":
        return False
    reply: str = rows[-1].content
    if lesson_step(reply) is not None or _LESSON_TITLE.search(reply):
        return False
    return is_teaching_request(rows[-2].content) and any(m in reply for m in _QUESTION_MARKS)


def lesson_after_gap(messages: list[Any] | None, now: datetime | None = None) -> bool:
    """True when the last reply in the window was sent ``LESSON_RECAP_AFTER`` or more ago."""
    for message in reversed(messages or []):
        if getattr(message, "role", None) != "assistant":
            continue
        sent = getattr(message, "created_at", None)
        if not isinstance(sent, datetime):
            return False
        sent = sent if sent.tzinfo else sent.replace(tzinfo=UTC)
        return (now or datetime.now(UTC)) - sent >= LESSON_RECAP_AFTER
    return False


def lesson_titles(text: str | None) -> list[tuple[int, str]]:
    """Each lesson heading in a reply, as (number, topic)."""
    return [
        (int(m.group(1)), m.group(2).strip(" *#"))
        for m in _LESSON_HEADING.finditer(text or "")
        if m.group(2).strip(" *#")
    ]


# What comes between "teach me" and the subject, and what ends the subject.
_SUBJECT_LEAD = re.compile(
    r"^(?:\s*(?:me|us|you|teach|learn|learning|study|to|about|on|in|more|some|"
    r"a\s+(?:bit|little)\s+(?:about|of)|the\s+basics\s+of|basics\s+of)\b)+",
    re.IGNORECASE,
)


_SUBJECT_END = re.compile(
    r"[.?!,;:(]|\s(?:because|so|since|please|for\s+my|i'?m|i\s+am|and\s+i|"
    r"step[- ]by[- ]step|from\s+scratch|in\s+detail)\b",
    re.IGNORECASE,
)


_SUBJECT_MAX_WORDS = 6


def teach_subject(text: str | None) -> str | None:
    """What a teach-me asks to learn: "can you teach me Python, please" -> "Python"."""
    cleaned = collapse_ws(text or "")
    match = _TEACH_TURN.search(cleaned)
    if match is None:
        return None
    end = match.end()
    # "I want to know American history" ends its match on the subject's first letter.
    if end >= 2 and cleaned[end - 1].isalpha() and cleaned[end - 2].isspace():
        end -= 1
    rest = _SUBJECT_LEAD.sub("", cleaned[end:]).strip()
    words = _SUBJECT_END.split(rest, maxsplit=1)[0].split()[:_SUBJECT_MAX_WORDS]
    subject = " ".join(words).strip()
    return subject[:1].upper() + subject[1:] if subject else None
