"""One roll or one draw: the probability is favourable outcomes over all outcomes.

Two dice (36 outcomes), one die (6), one card from a standard deck (52).
``probability of rolling a sum of 7 with two dice`` -> 6/36 = 1/6, with the six
pairs listed. ``single_draw_events`` reads the event whole or not at all.
"""

from __future__ import annotations

import re
from dataclasses import replace
from fractions import Fraction

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school.single_draw_events import (
    DrawEvent,
    card_event,
    card_label,
    one_die_event,
    two_dice_event,
)
from app.services.workout import math_line

_CHANCE = re.compile(r"\b(?:probability|chance|likelihood)\b", re.IGNORECASE)
_TWO_DICE = re.compile(
    r"\b(?:two|2|a\s+pair\s+of)\s+(?:fair\s+)?(?:(?:six|6)[- ]sided\s+)?(?:dice|die)\b",
    re.IGNORECASE,
)
_ONE_DIE = re.compile(
    r"\b(?:a|one|single)\s+(?:fair\s+|six-sided\s+|standard\s+)?die\b", re.IGNORECASE
)
_DECK = re.compile(
    r"\b(?:standard\s+|ordinary\s+|well-shuffled\s+)?(?:deck|pack)(?:\s+of\s+(?:52\s+)?cards)?\b"
    r"|\b52\s+cards\b",
    re.IGNORECASE,
)


def extract_single_draw_intent(cleaned: str) -> MathIntent | None:
    if len(cleaned) > 300 or not _CHANCE.search(cleaned):
        return None
    lower = cleaned.lower()
    if re.search(r"\b(?:and\s+then|then|twice|again|without\s+replacement|times)\b", lower):
        return None
    event: DrawEvent | None = None
    if _TWO_DICE.search(cleaned):
        event = two_dice_event(cleaned)
    elif _DECK.search(cleaned):
        event = card_event(cleaned)
    elif _ONE_DIE.search(cleaned) or re.search(r"\broll(?:ing)?\s+(?:a|an)\s+[1-6]\b", lower):
        event = one_die_event(cleaned)
    if event is None:
        return None
    # The event travels as numbers, never as a label that could outgrow its field.
    return MathIntent(
        kind="probability",
        school_op="single_draw",
        combo_k=event.favourable,
        combo_n=event.total,
        trial_outcome=f"not|{event.kind}" if event.negated else event.kind,
        stats_numbers=[float(value) for value in event.values] or None,
        stats_numbers_b=[float(number) for code in event.cards for number in code] or None,
        operation="solve",
    )


def probability_answer(probability: Fraction) -> str:
    """``\\frac{1}{4} = 0.25`` when the decimal ends, ``\\frac{1}{6} \\approx 0.1667`` when not."""
    exact = fraction_tex(probability)
    if probability.denominator == 1:
        return exact
    denominator = probability.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    decimal = float(probability)
    if denominator == 1:
        return f"{exact} = {decimal:g}"
    return rf"{exact} \approx {decimal:.4g}"


def fraction_tex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def _dice_pairs(target: int) -> str:
    pairs = [f"({a}, {target - a})" for a in range(1, 7) if 1 <= target - a <= 6]
    return ", ".join(pairs)


def _event_rows(intent: MathIntent, favourable: int, total: int) -> list[str]:
    """The favourable outcomes, counted: the pairs for each sum, the faces, or the cards."""
    negated, _, kind = (intent.trial_outcome or "").rpartition("|")
    values = [int(value) for value in intent.stats_numbers or []]
    count = total - favourable if negated else favourable
    rows: list[str] = []
    if kind == "sum" and len(values) == 1:
        rows.append(
            math_line(
                rf"\text{{{_dice_pairs(values[0])}}}",
                f"the {count} ways two dice make {values[0]}, of 36",
            )
        )
    elif kind == "sum":
        rows.extend(
            math_line(
                rf"\text{{{_dice_pairs(value)}}}", f"the {6 - abs(value - 7)} ways to make {value}"
            )
            for value in values
        )
        listed = ", ".join(str(value) for value in values[:-1]) + f" or {values[-1]}"
        rows.append(math_line(rf"{count} \text{{ of 36}}", f"rolls that make {listed}"))
    elif kind == "doubles":
        rows.append(math_line(r"\text{(1, 1), (2, 2), ..., (6, 6)}", "6 doubles of 36"))
    elif kind == "faces":
        shown = ", ".join(str(value) for value in values)
        rows.append(math_line(rf"\text{{{shown}}}", f"{favourable} of the 6 faces"))
    else:
        numbers = [int(number) for number in intent.stats_numbers_b or []]
        codes = [
            (numbers[index], numbers[index + 1], numbers[index + 2])
            for index in range(0, len(numbers), 3)
        ]
        named = " or ".join(card_label(code) for code in codes)
        rows.append(math_line(rf"{count} \text{{ {named}}}", "in a deck of 52"))
    if negated:
        rows.append(math_line(rf"{total} - {count} = {favourable}", "every outcome but those"))
    return rows


def single_draw_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    favourable, total = intent.combo_k, intent.combo_n
    if favourable is None or not total:
        return None
    probability = Fraction(favourable, total)
    answer = probability_answer(probability)
    rows = _event_rows(intent, favourable, total)
    # The simplified value is the answer's, on its own line.
    rows.append(math_line(rf"P = \frac{{{favourable}}}{{{total}}}", "favourable over all outcomes"))
    lines.append(f"P = {favourable}/{total} = {probability}")
    block = finish_with_answer(lines, answer)
    shown = "  \n".join(rows)
    return replace(block, worked_reply=f"{shown}\n\n```answer\n{answer}\n```\n")
