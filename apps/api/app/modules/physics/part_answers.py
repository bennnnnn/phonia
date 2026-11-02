"""A question in parts: each part's verified card under that part's own Answer heading.

One card holding every value ("v = 10 m/s; s = 25 m") under the last part's heading read
as that part's answer. When the reply answers part by part (``**Answer (a)**``,
``**Answer (b)**``) and the server solved the same parts, each heading gets its own
card, and the value lines a model wrote under it go: the card states them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.services.answer_check import stated_verdict
from app.services.answer_fence import verified_answer_fence
from app.services.part_answer_cards import PART_ANSWER_HEADING as _PART_ANSWER

# A line that only restates a value: maths, "t = 2.04 s", "Answer: 2.04 s".
_RESTATED = re.compile(
    r"^\s*(?:\$[^$]+\$|\\\(.+\\\)|[A-Za-z_\\{}' ]{1,20}\s*[=≈].{0,60}|(?:\*\*)?answer\s*:.*)$",
    re.IGNORECASE,
)


# The reply's closing "**Answer**" left with nothing under it once its card moved up.
_EMPTY_CLOSING_ANSWER = re.compile(r"\n+\s*(?:#{1,4}\s+)?\*\*Answer:?\*\*:?\s*$")


def _section_end(lines: list[str], start: int) -> int:
    """Where a part's answer lines end: the first line that is no restated value."""
    number = start
    while number < len(lines) and (not lines[number].strip() or _RESTATED.match(lines[number])):
        number += 1
    return number


def land_one_part_card(text: str, card: str) -> str | None:
    """``text`` with the one part the server solved carded under that part's own Answer
    heading, the part whose stated value is the card's; None unless exactly one is.

    "How long … How far …" was solved for the distance alone, and its card sat under the
    reply's closing **Answer**, below both parts, as if it answered the question
    (2026-10-29). The other parts keep the values the model wrote.
    """
    lines = text.split("\n")
    headings = [number for number, line in enumerate(lines) if _PART_ANSWER.match(line)]
    if len(headings) < 2:
        return None
    matching = [
        number
        for number in headings
        if stated_verdict("\n".join(lines[number + 1 : _section_end(lines, number + 1)]), card)
        in {"same", "rounded"}
    ]
    if len(matching) != 1:
        return None
    heading = matching[0]
    end = _section_end(lines, heading + 1)
    rest = "\n".join(lines[end:])
    landed = [*lines[:heading], lines[heading].strip(), "", verified_answer_fence(card)]
    joined = "\n".join(landed) + (f"\n\n{rest.lstrip(chr(10))}" if rest.strip() else "")
    return _EMPTY_CLOSING_ANSWER.sub("", joined)


def parts_conflict(text: str, cards: Sequence[str]) -> bool:
    """True when a part's own Answer lines state another value than its card: the card
    would replace a worked answer with a different one, unseen (review, 2026-10-29)."""
    lines = text.split("\n")
    headings = [number for number, line in enumerate(lines) if _PART_ANSWER.match(line)]
    return any(
        stated_verdict("\n".join(lines[heading + 1 : _section_end(lines, heading + 1)]), card)
        == "conflict"
        for heading, card in zip(headings, cards, strict=False)
    )


def land_part_cards(text: str, cards: Sequence[str]) -> str | None:
    """``text`` with each part's card under its Answer heading; None when its part answers
    are not the parts the server solved, one for one and in order."""
    lines = text.split("\n")
    found = [
        (number, match.group("letter"))
        for number, line in enumerate(lines)
        if (match := _PART_ANSWER.match(line)) is not None
    ]
    if [letter for _, letter in found] != list("abcdefgh"[: len(cards)]) or len(cards) < 2:
        return None
    headings = [number for number, _ in found]
    out: list[str] = []
    number = 0
    while number < len(lines):
        line = lines[number]
        number += 1
        if number - 1 not in headings:
            out.append(line)
            continue
        card = cards[headings.index(number - 1)]
        number = _section_end(lines, number)
        out.extend([line.strip(), "", verified_answer_fence(card)])
        if number < len(lines):
            out.append("")
    return "\n".join(out)
