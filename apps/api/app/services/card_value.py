"""What an answer card holds: the final answer, never the calculation before it.

A checked line such as ``7 + 5 = 12`` or ``5! = 5 * 4 * 3 * 2 * 1 = 120`` is working: the
card shows ``12`` and ``120``, and a direct reply writes the working above the card
(``math.tools.direct_working``). Only arithmetic on plain numbers counts as working. A
named answer stays whole (``x = 1``, ``pH = 2.00``, ``x = 2 \\text{ or } x = 3``), and so
does one value written two ways (``\\frac{5}{6} \\approx 0.833``).

The phone reads every card, old ones too, with the same rule (``lib/answerNotation.ts``);
both are held to ``docs/fixtures/answer_card_cases.json``.
"""

from __future__ import annotations

import re

# A relation between two sides, outside any braces: = and ≈ (or \approx).
_APPROX = ("\\approx", "≈")
# Spacing and sizing commands that change nothing a reader computes.
_SPACING = re.compile(r"\\(?:left|right|[,;:! ])")
_OPERATOR_COMMANDS = re.compile(r"\\(?:times|div|cdot)(?![A-Za-z])")
# A fraction of two numbers is one value, like 0.5: an operand, not an operation.
_NUMBER_FRACTION = re.compile(r"\\[dt]?frac\{\s*\d+(?:\.\d+)?\s*\}\{\s*\d+(?:\.\d+)?\s*\}")
# The signs of arithmetic, as the solver writes them: minus, times, divide and dot.
_MINUS, _TIMES = "\u2212", "\u00d7"
_SIGNS = f"+\\-{_MINUS}{_TIMES}\u00f7\u00b7*/^!"
_ARITHMETIC = re.compile(rf"[0-9.()\[\]{{}}\s{_SIGNS}]+")
_OPERATION = re.compile(rf"[{_SIGNS}]")
# Several answers or a layout: never split.
_LIST = re.compile(r"[,;&]|\\\\|\\text|\\begin|\\quad")


def split_working(value: str) -> tuple[str | None, str]:
    """``(working, final answer)`` of a card value; ``(None, value)`` when it holds no working."""
    if "\n" in value or _LIST.search(value.replace("{,}", "")):
        return None, value
    sides, relations = _relations(value)
    dropped = 0
    while dropped < len(sides) - 1 and _is_arithmetic(sides[dropped]):
        dropped += 1
    if dropped == 0:
        return None, value
    working = sides[0] + "".join(
        f" {relation} {side}" for relation, side in zip(relations, sides[1:dropped], strict=False)
    )
    answer = sides[dropped] + "".join(
        f" {relation} {side}"
        for relation, side in zip(relations[dropped:], sides[dropped + 1 :], strict=True)
    )
    if relations[dropped - 1] in _APPROX:
        answer = f"\\approx {answer}"
    return working, answer


def final_answer_only(value: str) -> str:
    """The card's value without the calculation that led to it."""
    return split_working(value)[1]


def _relations(value: str) -> tuple[list[str], list[str]]:
    """The sides of ``a = b ≈ c`` and the relations between them, outside braces."""
    sides: list[str] = []
    relations: list[str] = []
    depth = 0
    start = index = 0
    while index < len(value):
        char = value[index]
        depth += char == "{"
        depth -= char == "}"
        relation = _relation_at(value, index) if depth == 0 else None
        if relation is None:
            index += 1
            continue
        sides.append(value[start:index].strip())
        relations.append(relation)
        index += len(relation)
        start = index
    sides.append(value[start:].strip())
    return sides, relations


def _relation_at(value: str, index: int) -> str | None:
    if value.startswith("\\approx", index) and not value[index + 7 : index + 8].isalpha():
        return "\\approx"
    char = value[index]
    if char == "≈":
        return char
    # Not the = of <=, >=, != or ==.
    if char == "=" and value[index - 1 : index] not in {"<", ">", "!", "="}:
        return None if value[index + 1 : index + 2] == "=" else char
    return None


def _is_arithmetic(side: str) -> bool:
    """Arithmetic on plain numbers: ``7 + 5``, ``5!``, ``\\frac{1}{2} + \\frac{1}{3}``."""
    plain = _SPACING.sub(" ", side).replace("{,}", "")
    text = _NUMBER_FRACTION.sub("1", _OPERATOR_COMMANDS.sub(_TIMES, plain))
    if not text.strip() or not _ARITHMETIC.fullmatch(text) or not any(c.isdigit() for c in text):
        return False
    # A leading sign is part of the number: -8 is a value.
    return _OPERATION.search(text.strip().lstrip(f"+-{_MINUS}")) is not None
