"""A message that lists numbers: "Monthly rainfall in Addis Ababa: Jan 15, Feb 30, …".

Qwen3.7 Flash, the free plan's everyday model, answered that message "Hey bini! How's it
going?" four times in four (2026-10-24): a list with no question read to it as an opener.
Told what the message is, it answered about the numbers, but named November (6 mm) the
driest month once in five and summed the year wrong when asked for a total. So the highest
and lowest are read here, from the message, and the reply only words them.

The note is conditional ("if the message or the conversation asks for something, do that"),
because no reading of the words can tell every request apart from a list. The reading is
strict: each item is a name and one plain number ("Jan 15", "rent: $1,200", "week 1 80 kg"),
and anything it could misread gets no note: ranges and scores ("5-10", "2-1"), clock times,
fractions, sets ("100x5"), a dot or space between thousands ("1.200", "1 200"), units or
currencies that differ, dates ("math Jan 15"), years, phone numbers and a loan's terms.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.modules.turn_reading.personal import is_personal_disclosure_turn
from app.modules.turn_reading.teaching import is_standing_preference

logger = logging.getLogger(__name__)

# One item: a name ("rent", "week 1", "Q1", "2024") and one plain number with an optional
# sign, currency and unit. A name ending in a number takes no colon ("dentist 3:30").
_ITEM = re.compile(
    r"(?P<label>[^\W\d_]+(?:[ '&/.-][^\W\d_]+){0,4}(?: \d{1,2})?|[^\W\d_]{1,3}\d{1,2}"
    r"|(?:19|20)\d\d)"
    r"(?P<sep>\s*[:=]\s*|\s+)"
    r"(?P<sign>-?)(?P<currency>[$€£¥]?)(?P<number>\d{1,3}(?:,\d{3})+|\d{1,15})"
    r"(?:\.(?P<fraction>\d{1,6}))?(?:\s?(?P<unit>%|[^\W\d_]{1,6}))?"
)
# Items: a comma that is not a thousands separator, a semicolon, a line, a closing "and".
_ITEMS = re.compile(r",(?!\d{3}(?!\d))|;|\n|\s+and\s+")
_ITEM_CHARS = 80
# A request in English: the other rules' turn (the note's "if it asks for something" covers
# the rest).
_ASKS = re.compile(
    r"\b(?:make|plot|graph|chart|draw|show|calculate|compute|work\s+out|find|add|sum|total|"
    r"average|mean|sort|rank|compare|convert|remind|remember|forget|save|put|give|tell|explain|"
    r"analy[sz]e|summari[sz]e|help|can|could|would|should|please|pls|what|how|why|which|when|"
    r"where|who)\b",
    re.IGNORECASE,
)
# A question mark in Latin, CJK (fullwidth) and Arabic text.
_QUESTION_MARKS = ("?", "\uff1f", "\u061f")
_DIGIT = re.compile(r"\d")
# "My brother is 30": a sentence, not a name.
_CLAUSE = re.compile(r"(?:^|\s)(?:is|are|was|were|am|i'?m|have|has|had|got)$", re.IGNORECASE)
_MONTH = re.compile(
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?",
    re.IGNORECASE,
)
_WEEKDAY = re.compile(
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?"
    r"|sat(?:urday)?|sun(?:day)?",
    re.IGNORECASE,
)
_HALF_OR_QUARTER = re.compile(r"q[1-4]|h[12]", re.IGNORECASE)
_NUMBERED = re.compile(r"(?P<base>[^\W\d_]+(?: [^\W\d_]+)*) \d{1,2}")
# A loan or a card, two of its terms or more: the money reader's to work. One is a name
# ("Apr 85" is April).
_MONEY_TERMS = frozenset(
    {
        "rate",
        "interest",
        "interest rate",
        "apr",
        "term",
        "years",
        "months",
        "payment",
        "monthly payment",
        "balance",
        "principal",
        "down payment",
    }
)
_CLOCK_UNITS = frozenset({"am", "pm"})
# Units written against the number ("20k", "5%"); others take a space ("5 mm").
_TIGHT_UNITS = frozenset({"%", "k", "K", "M", "B", "bn"})
# A scale counts on its own item only: "Jan 800, Feb 950, Mar 1.1k" is not 950k.
_SCALES = frozenset({"k", "K", "M", "B", "bn"})
_YEAR = re.compile(r"(?:19|20)\d\d")
_MAX_CHARS = 2000
_MIN_ITEMS = 3

SHARED_NUMBERS_HINT = (
    "The user's message lists values. It is not a greeting: never greet them or ask how they "
    "are. If the message or the conversation asks for something, do that. Otherwise say in one "
    "or two short sentences what the values show, then offer one next step that fits, such as "
    "a chart; do not add them up or average them unless asked."
)


@dataclass(frozen=True)
class SharedValue:
    label: str
    value: float
    written: str  # the number as the user wrote it: "1,200", "-$300", "79.5"
    unit: str  # "mm", "%", "k", or "" (the last item may carry it for all: "Nov 6, Dec 5 mm")
    currency: str


def _item(text: str) -> SharedValue | None:
    """One "name number" item, or None for anything else."""
    text = text.strip().rstrip(".")
    match = _ITEM.fullmatch(text) if len(text) <= _ITEM_CHARS else None
    if match is None:
        return None
    label, number, fraction = match["label"], match["number"], match["fraction"] or ""
    if _CLAUSE.search(label) or (label[-1].isdigit() and match["sep"].strip()):
        return None
    # "1.200" is twelve hundred where a dot separates thousands: not ours to guess.
    if len(fraction) == 3 and "," not in number:
        return None
    # "0911234567" is a phone number.
    if number.startswith("0") and len(number) > 1:
        return None
    decimals = f".{fraction}" if fraction else ""
    value = float(number.replace(",", "") + decimals)
    written = f"{match['sign']}{match['currency']}{number}{decimals}"
    sign = -1 if match["sign"] else 1
    return SharedValue(label, sign * value, written, match["unit"] or "", match["currency"])


def _items(text: str) -> list[SharedValue] | None:
    """Every item a value, but for a first line or title with no number in it."""
    parts = [part for part in _ITEMS.split(text) if part.strip()]
    if not parts:
        return None
    title, colon, first = parts[0].partition(":")
    if colon and not _DIGIT.search(title) and first.strip():
        parts[0] = first
    elif not _DIGIT.search(parts[0]):
        parts = parts[1:]
    values = [read for part in parts if (read := _item(part)) is not None]
    return values if len(values) == len(parts) else None


def _a_series(labels: list[str]) -> bool:
    """Months, weekdays, quarters, years, or one name numbered ("week 1", "week 2"): the
    same quantity over time, so its highest and lowest mean something. "Glucose 95,
    cholesterol 210, HDL 45" are different things."""
    for kind in (_MONTH, _WEEKDAY, _HALF_OR_QUARTER, _YEAR):
        if all(kind.fullmatch(label) for label in labels):
            return True
    numbered = [_NUMBERED.fullmatch(label) for label in labels]
    bases = {match["base"].casefold() for match in numbered if match}
    return all(numbered) and len(bases) == 1


def _comparable(values: list[SharedValue]) -> bool:
    """A series in one unit and one currency: a unit on the last item alone is everyone's
    ("Nov 6, Dec 5 mm"), a scale only its own ("Mar 1.1k")."""
    if not _a_series([value.label for value in values]):
        return False
    units = [value.unit for value in values]
    if len(set(filter(None, units))) > 1 or len({value.currency for value in values}) > 1:
        return False
    if any(units) and not all(units):
        return not any(units[:-1]) and units[-1] not in _SCALES
    return True


def _dates(values: list[SharedValue]) -> bool:
    """'Math Jan 15' is a date; so is a list of months whose numbers are all 1 to 31."""
    if any(" " in value.label and _MONTH.fullmatch(value.label.split()[-1]) for value in values):
        return True
    if not all(_MONTH.fullmatch(value.label) for value in values):
        return False
    return all(value.value.is_integer() and 1 <= value.value <= 31 for value in values)


def shared_numbers(text: str) -> list[SharedValue] | None:
    """The values a message lists, in order, or None for anything it could misread."""
    if len(text) > _MAX_CHARS or any(mark in text for mark in _QUESTION_MARKS):
        return None
    if _ASKS.search(text):
        return None
    values = _items(text)
    if values is None or len(values) < _MIN_ITEMS:
        return None
    if {value.unit.lower() for value in values} & _CLOCK_UNITS or _dates(values):
        return None
    # "Week 1 80 kg, week 2 79 kg" numbers its names; one name ending in a number alone is
    # a number split by a space ("loyer 1 200" is twelve hundred).
    numbered = [value.label[-1].isdigit() for value in values]
    if any(numbered) and not all(numbered):
        return None
    if sum(value.label.lower() in _MONEY_TERMS for value in values) >= 2:
        return None
    # "Born 1990, married 2015, moved 2020" are years, not amounts to compare.
    if all(_YEAR.fullmatch(value.written) for value in values):
        return None
    return values


def _named(values: list[SharedValue], end: float) -> str:
    """'Aug (290 mm)': the labels at that end, and its value with the series' unit."""
    at_end = [value for value in values if value.value == end]
    unit = values[-1].unit
    joint = "" if unit in _TIGHT_UNITS else " "
    shown = f"{at_end[0].written}{joint}{unit}" if unit else at_end[0].written
    return " and ".join(value.label for value in at_end) + f" ({shown})"


def shared_numbers_hint(text: str | None) -> str | None:
    """The note for a message that lists values, with their highest and lowest when they
    are one quantity over time (a series in one unit).

    Not for a personal disclosure ("My expenses: rent $1,500, …"): its own note says how
    to acknowledge it, and stays the one nearest the user's turn.
    """
    if not text or (is_personal_disclosure_turn(text) and not is_standing_preference(text)):
        return None
    try:
        values = shared_numbers(text)
    # It runs on every turn's prompt: a message it misreads gets no note, never an error.
    except Exception:
        logger.warning("shared_numbers: could not read a message", exc_info=True)
        return None
    if values is None:
        return None
    if not _comparable(values):
        return SHARED_NUMBERS_HINT
    numbers = [value.value for value in values]
    return (
        f"{SHARED_NUMBERS_HINT} Read from their message: the highest is "
        f"{_named(values, max(numbers))} and the lowest is {_named(values, min(numbers))}."
    )
