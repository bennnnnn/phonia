"""A direct reply's working goes above its answer card; the card holds the answer alone.

The solver's checked line reads ``1 ÷ 2 + 1 ÷ 4 = \\frac{3}{4}``. The card shows
``\\frac{3}{4}`` (``services.card_value``), and the reply writes the working above it,
typeset: ``$\\frac{1}{2} + \\frac{1}{4}$``. A reply that was only its card still shows
what was worked out.
"""

from __future__ import annotations

import re

from app.services.answer_fence import answer_header_and_value
from app.services.card_value import split_working
from app.services.md_fence_scan import iter_closed_fences, replace_first_closed_fence_body

_ANSWER_HEADING = re.compile(r"^\*\*Answer\b", re.MULTILINE)
_OPERATORS = (("\u00d7", "\\times"), ("\u00f7", "\\div"), ("\u00b7", "\\cdot"), ("\u2212", "-"))
# 1 ÷ 2 between whole numbers, not part of a chain like 12 ÷ 3 ÷ 2.
_DIVISION = re.compile(r"(?<!÷ )(?<![\d.])(\d+) ÷ (\d+)(?![\d.])(?! ÷)")


def working_above_card(reply: str, user_text: str) -> str:
    """``reply`` with its card's working moved above the card, typeset."""
    start, _end, body = next(iter_closed_fences(reply, "answer"), (0, 0, None))
    # A worked layout (column sums, Given and Required) already shows its working.
    if body is None or _ANSWER_HEADING.search(reply, 0, start):
        return reply
    headers, value = answer_header_and_value(body)
    working, answer = split_working(value)
    carded = replace_first_closed_fence_body(reply, "answer", "\n".join([*headers, answer]))
    if working is None or carded is None:
        return reply
    before = carded[:start].rstrip("\n")
    lead = f"{before}\n\n" if before else ""
    return f"{lead}${typeset_working(working, user_text)}$\n\n{carded[start:]}"


def typeset_working(working: str, user_text: str) -> str:
    """The working as maths: ``1 ÷ 2`` is the fraction ½ where the user wrote ``1/2``."""

    def division(match: re.Match[str]) -> str:
        numerator, denominator = match.groups()
        wrote = re.search(rf"(?<![\d.]){numerator}\s*/\s*{denominator}(?![\d.])", user_text)
        return rf"\frac{{{numerator}}}{{{denominator}}}" if wrote else match.group()

    text = _DIVISION.sub(division, working)
    for char, command in _OPERATORS:
        text = text.replace(char, command)
    return text
