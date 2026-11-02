"""Drop memory facts that are one-off reminders or cannot all be true.

A standing routine ("walks every evening") stays. A dentist visit, a flight,
or "create a todo" belongs in reminders, not a memory document. Two current
places, or 12th grade together with university, cannot both stay active: the
newest confirmation wins.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.text_normalize import straighten_apostrophes

_TASK = re.compile(
    r"\b(?:todos?|to-dos?|appointments?|pickups?|flights?|concerts?|dentist)\b",
    re.IGNORECASE,
)
_SOON = re.compile(r"\b(?:today|tomorrow|tonight)\b", re.IGNORECASE)
_WEEKDAY = re.compile(
    r"\bon (?:this |next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\bat \d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?\b",
    re.IGNORECASE,
)
_STANDING = re.compile(
    r"\b(?:every|each|usually|always|daily|routine|routines)\b",
    re.IGNORECASE,
)
_CURRENT_PLACE = re.compile(
    r"\b(?:is|lives|stays)(?: currently)? in ([a-z][\w .'-]{1,60})",
    re.IGNORECASE,
)
_NOT_A_PLACE = re.compile(
    r"^(?:a|an|the|his|her|their|this|that|some)\b|"
    r"\b(?:\d+(?:st|nd|rd|th) grade|high school|college|university|school)\b",
    re.IGNORECASE,
)
_K12 = re.compile(
    r"\b(?:\d+(?:st|nd|rd|th) grade|high school|secondary school)\b",
    re.IGNORECASE,
)
_HIGHER = re.compile(r"\b(?:university|college)\b", re.IGNORECASE)
_GRADE = re.compile(r"\b(\d+)(?:st|nd|rd|th) grade\b", re.IGNORECASE)
_EARLIEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class FactView:
    text: str
    confirmed_at: datetime | None = None


def is_one_off_schedule_fact(text: str) -> bool:
    """True for a dated errand or reminder, not a standing routine.

    "Works on Monday" stays. "Dentist on Thursday at 4" and "a todo for
    tomorrow" do not.
    """
    if _STANDING.search(text) and not _TASK.search(text):
        return False
    if _TASK.search(text):
        return True
    if _SOON.search(text):
        return True
    return bool(_WEEKDAY.search(text) and _CLOCK.search(text))


def _current_place(text: str) -> str | None:
    match = _CURRENT_PLACE.search(text)
    if match is None:
        return None
    place = match.group(1).strip(" .")
    if not place or _NOT_A_PLACE.search(place):
        return None
    return place.lower()


def _edu_bucket(text: str) -> str | None:
    k12 = bool(_K12.search(text))
    higher = bool(_HIGHER.search(text))
    if k12 and not higher:
        return "k12"
    if higher and not k12:
        return "higher"
    return None


def _when(fact: FactView) -> datetime:
    confirmed = fact.confirmed_at
    if confirmed is None:
        return _EARLIEST
    if confirmed.tzinfo is None:
        return confirmed.replace(tzinfo=UTC)
    return confirmed


def _newest(facts: Sequence[FactView]) -> FactView:
    return max(facts, key=lambda fact: (_when(fact), len(fact.text)))


def texts_to_drop(facts: Sequence[FactView]) -> list[str]:
    """Texts that should leave active memory. The newest conflicting fact stays."""
    drops: list[str] = []
    kept: list[FactView] = []
    for fact in facts:
        if is_one_off_schedule_fact(fact.text):
            drops.append(fact.text)
        else:
            kept.append(fact)
    drops.extend(_exclusive_drops(kept))
    return drops


def _exclusive_drops(facts: Sequence[FactView]) -> list[str]:
    drops: list[str] = []
    places = [(fact, place) for fact in facts if (place := _current_place(fact.text))]
    if len({place for _, place in places}) > 1:
        keeper = _newest([fact for fact, _ in places])
        drops.extend(fact.text for fact, _ in places if fact is not keeper)

    edu = [fact for fact in facts if _edu_bucket(fact.text)]
    buckets = {_edu_bucket(fact.text) for fact in edu}
    grades = {grade for fact in edu if (grade := _grade_number(fact.text))}
    if ("k12" in buckets and "higher" in buckets) or len(grades) > 1:
        keeper = _newest(edu)
        drops.extend(fact.text for fact in edu if fact is not keeper and fact.text not in drops)
    return drops


def _grade_number(text: str) -> str | None:
    match = _GRADE.search(text)
    return match.group(1) if match else None


# "Remember to buy milk", "don't forget to call mom": an errand to do, not a fact to keep.
_ERRAND = re.compile(r"\b(?:remember|don't\s+forget|do\s+not\s+forget)\s+to\s+\w", re.IGNORECASE)


def asks_to_keep(text: str) -> bool:
    """A remember command memory will keep: not an errand or a one-off dated item.

    Memory drops "my dentist appointment is tomorrow at 3pm" and "please remember to buy
    milk" (``is_one_off_schedule_fact``, the extractor's rules), so the chat must not
    promise it remembers them.
    """
    from app.modules.memory.commands import asks_to_remember

    return (
        asks_to_remember(text)
        and _ERRAND.search(straighten_apostrophes(text)) is None
        and not is_one_off_schedule_fact(text)
    )
