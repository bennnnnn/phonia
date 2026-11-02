"""Percent extractors and verified blocks."""

from __future__ import annotations

import re
from dataclasses import replace
from fractions import Fraction

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import (
    _count_char,
    _exactly_n_numbers,
)
from app.modules.math.tools.school.percent_terms import leading_addend
from app.services.number_text import (
    DECIMAL,
    DECIMAL_LITERAL,
    finite_match_value,
    number_immediately_before,
)
from app.services.text_match import has_any_word, word_index
from app.services.workout import math_line

_PERCENT_INCREASE_WORDS = ("increase", "increased", "increasing", "markup", "marked up")
_PERCENT_DECREASE_WORDS = ("decrease", "decreased", "decreasing")


_PERCENT_OF = re.compile(r"\s*%\s*of\s+", re.IGNORECASE)
_CHAIN_NUMBER = re.compile(rf"\s*(?:(?:the|a\s+total\s+of)\s+)?\$?\s*(-?{DECIMAL})", re.IGNORECASE)
_CHAIN_ADDEND = re.compile(rf"\s*(plus|minus|\+|-|\u2212)\s*\$?\s*({DECIMAL})", re.IGNORECASE)
# Words that ask for more arithmetic than "a% of b": "plus tax of 8%",
# "and then double it". A unit or a noun after the base ("dollars",
# "of the students") is not another operation.
_MORE_ARITHMETIC = re.compile(
    r"[\d%+\-*/^=\u00d7\u00f7\u2212]|\b(?:plus|minus|times|divided|add|added|subtract|"
    r"subtracted|tax|tip|discount|off|increase[sd]?|decrease[sd]?|more|less|then|and|"
    r"twice|double|half|square[sd]?|cube[sd]?|percent|rounded|round)\b",
    re.IGNORECASE,
)
_OPERATION_BEFORE = re.compile(
    r"(?:[+\-*/^\u00d7\u00f7\u2212]|\b(?:plus|minus|times|divided\s+by|add|subtract))\s*$",
    re.IGNORECASE,
)


def _extract_percent_of(cleaned: str) -> MathIntent | None:
    """``a% of b``, ``a% of b% of c`` and ``a% of b plus c``: the whole request or nothing.

    "25% of 80 plus 10" used to verify 20 and "10% of 10% of 500" verified 1:
    the first ``a% of b`` was taken and the rest of the sentence dropped.
    """
    lower = cleaned.lower()
    pct = lower.find("% of ")
    if pct == -1:
        return None
    rate_m = number_immediately_before(cleaned, pct)
    if rate_m is None:
        return None
    if _OPERATION_BEFORE.search(cleaned[: rate_m.start()]):
        # "5 + 20% of 80": the percent is one term of a larger sum.
        return None
    readable, leading = leading_addend(cleaned, rate_m.start())
    if not readable:
        return None
    rate = finite_match_value(rate_m)
    if rate is None:
        return None
    rates = [rate]
    position = rate_m.end()
    base: float | None = None
    while True:
        link = _PERCENT_OF.match(cleaned, position)
        if link is None:
            break
        number = _CHAIN_NUMBER.match(cleaned, link.end())
        if number is None:
            return None
        value = finite_match_value(number, 1)
        if value is None:
            return None
        position = number.end()
        if _PERCENT_OF.match(cleaned, position):
            rates.append(value)
            continue
        base = value
        break
    if base is None or len(rates) > 4:
        return None
    addend = leading
    added = _CHAIN_ADDEND.match(cleaned, position)
    if added is not None:
        if leading is not None:
            # "Subtract 5 from 25% of 80 plus 10": two terms beside the percent.
            return None
        amount = float(added.group(2))
        addend = -amount if added.group(1).lower() in {"minus", "-", "\u2212"} else amount
        position = added.end()
    if _MORE_ARITHMETIC.search(cleaned[position:]):
        return None
    if len(rates) == 1 and addend is None:
        return MathIntent(
            kind="arithmetic",
            school_op="percent",
            percent_rate=rate,
            percent_base=base,
            operation="solve",
        )
    return MathIntent(
        kind="arithmetic",
        school_op="percent_chain",
        stats_numbers=rates,
        percent_base=base,
        x2=addend,
        operation="solve",
    )


def _extract_percent_change(cleaned: str, lower: str) -> MathIntent | None:
    increase = has_any_word(lower, _PERCENT_INCREASE_WORDS)
    decrease = has_any_word(lower, _PERCENT_DECREASE_WORDS)
    if increase == decrease:
        return None
    if _count_char(cleaned, "%") != 1:
        return None
    by_at = word_index(lower, "by")
    if by_at == -1:
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 2:
        return None
    pct_at = cleaned.find("%")
    rate_m = number_immediately_before(cleaned, pct_at)
    if rate_m is None:
        return None
    base_m = nums[0] if nums[0].span() != rate_m.span() else nums[1]
    if base_m.span() == rate_m.span() or base_m.end() > by_at or rate_m.start() < by_at:
        return None
    rate = finite_match_value(rate_m)
    base = finite_match_value(base_m)
    if rate is None or base is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="percent_increase" if increase else "percent_decrease",
        percent_rate=rate,
        percent_base=base,
        operation="solve",
    )


def _extract_percent_is(cleaned: str, lower: str) -> MathIntent | None:
    if _count_char(cleaned, "%") != 0:
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 2:
        return None
    part_m: re.Match[str] | None = None
    whole_m: re.Match[str] | None = None
    for cue in (" is what percent of ", " is what percentage of "):
        idx = lower.find(cue)
        if idx == -1:
            continue
        before = None
        for match in nums:
            if match.end() <= idx:
                before = match
        after = DECIMAL_LITERAL.search(cleaned, idx + len(cue))
        if before is None or after is None:
            return None
        part_m, whole_m = before, after
        break
    if part_m is None or whole_m is None:
        for cue in ("what percent of ", "what percentage of "):
            idx = lower.find(cue)
            if idx == -1:
                continue
            whole = DECIMAL_LITERAL.search(cleaned, idx + len(cue))
            if whole is None:
                return None
            rest = cleaned[whole.end() :].lstrip()
            if not rest.lower().startswith("is"):
                return None
            after_is = rest[2:]
            if after_is[:1].isalpha():
                return None
            part = DECIMAL_LITERAL.search(after_is)
            if part is None:
                return None
            part_m, whole_m = part, whole
            break
    if part_m is None or whole_m is None:
        return None
    if {part_m.group(0), whole_m.group(0)} != {nums[0].group(0), nums[1].group(0)}:
        return None
    part_value = finite_match_value(part_m)
    whole_value = finite_match_value(whole_m)
    if part_value is None or whole_value is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="percent_is",
        percent_rate=part_value,
        percent_base=whole_value,
        operation="solve",
    )


# The question asks for the amount before the change: "what was the original price".
_ORIGINAL_ASKED = re.compile(
    r"\b(?:what\s+(?:was|is|were)|find|work\s+out|calculate|how\s+much\s+(?:was|did))\b"
    r"[^.?!]*?\b(?:original|full|regular|usual|old|starting|initial)\s+"
    r"(?:price|cost|value|amount|salary|wage)\b"
    r"|\b(?:price|cost|value)\s+before\s+(?:the\s+)?(?:discount|sale|increase|rise|reduction)\b",
    re.IGNORECASE,
)
_ORIGINAL_DECREASE_WORDS = (
    "discount",
    "off",
    "decrease",
    "decreased",
    "reduced",
    "reduction",
    "fell",
    "dropped",
    "sale",
)
_ORIGINAL_INCREASE_WORDS = (
    "increase",
    "increased",
    "rise",
    "rose",
    "raised",
    "markup",
    "tax",
    "vat",
    "grew",
)


def extract_original_before_percent(cleaned: str, lower: str) -> MathIntent | None:
    """``after a 20% discount it costs 48, what was the original price`` -> 48 / 0.8.

    Taking 20% off 48 answers a different question; the 48 is already reduced.
    """
    if not _ORIGINAL_ASKED.search(cleaned) or cleaned.count("%") != 1:
        return None
    decrease = any(word_index(lower, word) != -1 for word in _ORIGINAL_DECREASE_WORDS)
    increase = any(word_index(lower, word) != -1 for word in _ORIGINAL_INCREASE_WORDS)
    if decrease == increase:
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 2:
        return None
    rate_m = number_immediately_before(cleaned, cleaned.find("%"))
    if rate_m is None:
        return None
    after_m = nums[0] if nums[0].span() != rate_m.span() else nums[1]
    if after_m.span() == rate_m.span():
        return None
    rate = finite_match_value(rate_m)
    after = finite_match_value(after_m)
    if rate is None or after is None or not 0 < rate < (100 if decrease else 1000):
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="original_before_decrease" if decrease else "original_before_increase",
        percent_rate=rate,
        percent_base=after,
        operation="solve",
    )


def extract_discount(cleaned: str, lower: str) -> MathIntent | None:
    if "% of " in lower:
        return None
    if cleaned.count("%") != 1:
        return None
    if word_index(lower, "discount") == -1 and word_index(lower, "off") == -1:
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 2:
        return None
    pct_at = cleaned.find("%")
    rate_m = number_immediately_before(cleaned, pct_at)
    if rate_m is None:
        return None
    base_m = nums[0] if nums[0].span() != rate_m.span() else nums[1]
    if base_m.span() == rate_m.span():
        return None
    rate = finite_match_value(rate_m)
    base = finite_match_value(base_m)
    if rate is None or base is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="discount",
        percent_rate=rate,
        percent_base=base,
        operation="solve",
    )


def extract_with_percent_total(cleaned: str, lower: str) -> MathIntent | None:
    if "% of " in lower or cleaned.count("%") != 1:
        return None
    if word_index(lower, "with") == -1 and word_index(lower, "plus") == -1:
        return None
    if word_index(lower, "tax") == -1 and word_index(lower, "tip") == -1:
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 2:
        return None
    pct_at = cleaned.find("%")
    rate_m = number_immediately_before(cleaned, pct_at)
    if rate_m is None:
        return None
    base_m = nums[0] if nums[0].span() != rate_m.span() else nums[1]
    if base_m.span() == rate_m.span():
        return None
    rate = finite_match_value(rate_m)
    base = finite_match_value(base_m)
    if rate is None or base is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="percent_increase",
        percent_rate=rate,
        percent_base=base,
        operation="solve",
    )


# "percentage increase from 40 to 50", "rose from 40 to 50 ... percentage increase".
_PERCENT_CHANGE_FROM = re.compile(
    r"\bpercent(?:age)?\s+(?:change|increase|decrease)\s+from\b"
    r"|\b(?:rose|rises|risen|increased|went\s+up|grew|fell|dropped|decreased|went\s+down|"
    r"changed)\s+from\b[^.?!]*\bpercent(?:age)?\b",
    re.IGNORECASE,
)


def extract_percent_change_from(cleaned: str, lower: str) -> MathIntent | None:
    if "%" in cleaned:
        return None
    if not _PERCENT_CHANGE_FROM.search(cleaned):
        return None
    values = _exactly_n_numbers(cleaned, 2)
    if values is None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="percent_change_from",
        percent_base=values[0],
        percent_rate=values[1],
        operation="solve",
    )


def _block_percent(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_rate is None or intent.percent_base is None:
        return None
    answer = math_school.percent_of(intent.percent_rate, intent.percent_base)
    lines.append(f"{intent.percent_rate:g}% of {intent.percent_base:g} = {answer}")
    return finish_with_answer(lines, answer)


def _block_percent_chain(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    """``10% of 10% of 500`` and ``25% of 80 plus 10``, worked left to right."""
    rates = intent.stats_numbers or []
    if not rates or intent.percent_base is None:
        return None
    base = Fraction(str(intent.percent_base))
    value = base
    for rate in reversed(rates):
        value = Fraction(str(rate)) / 100 * value
    words = r" \text{ of } ".join(f"{rate:g}\\%" for rate in rates)
    shown = [f"{words} \\text{{ of }} {intent.percent_base:g}"]
    factors = r" \times ".join(f"{float(Fraction(str(rate)) / 100):g}" for rate in rates)
    product = f"{factors} \\times {intent.percent_base:g}"
    if intent.x2 is not None:
        addend = Fraction(str(intent.x2))
        sign = "-" if addend < 0 else "+"
        shown[0] += f" {sign} {abs(intent.x2):g}"
        product += f" {sign} {abs(intent.x2):g}"
        partial = f"{float(value):g} {sign} {abs(intent.x2):g}"
        value += addend
        steps = [shown[0], product, partial]
    else:
        steps = [shown[0], product]
    answer = math_school._format_school_number(float(value))
    working = " = ".join([*steps, answer])
    return _with_working(lines, working, answer)


def _block_percent_change(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None or intent.percent_rate is None:
        return None
    if intent.school_op == "percent_increase":
        answer = math_school.percent_increase(intent.percent_base, intent.percent_rate)
        verb = "increased"
    else:
        answer = math_school.percent_decrease(intent.percent_base, intent.percent_rate)
        verb = "decreased"
    lines.append(f"{intent.percent_base:g} {verb} by {intent.percent_rate:g}% = {answer}")
    return finish_with_answer(lines, answer)


def _block_percent_is(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_rate is None or intent.percent_base is None:
        return None
    answer = math_school.percent_is(intent.percent_rate, intent.percent_base)
    lines.append(f"{intent.percent_rate:g} is {answer}% of {intent.percent_base:g}")
    return finish_with_answer(lines, answer)


def _with_working(lines: list[str], working: str, answer: str) -> VerifiedMathBlock:
    """The working on one line, then the answer alone."""
    lines.append(f"Working: ${working}$")
    block = finish_with_answer(lines, answer)
    return replace(block, worked_reply=f"{math_line(working)}\n\n```answer\n{answer}\n```\n")


def _fraction_of_one(rate: float, *, sign: str) -> tuple[str, str]:
    """``(1 - 0.2, 0.8)`` for 20% off; ``(1 + 0.15, 1.15)`` for a 15% rise."""
    factor = 1 - rate / 100 if sign == "-" else 1 + rate / 100
    return f"1 {sign} {rate / 100:g}", f"{round(factor, 10):g}"


def _block_discount(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if intent.percent_base is None or intent.percent_rate is None:
        return None
    answer = math_formulas.sale_price(intent.percent_base, intent.percent_rate)
    lines.append(f"{intent.percent_rate:g}% off {intent.percent_base:g} = {answer}")
    written, factor = _fraction_of_one(intent.percent_rate, sign="-")
    base = f"{intent.percent_base:g}"
    working = (
        rf"\text{{sale price}} = {base} \times \left({written}\right) = {base} \times {factor}"
    )
    return _with_working(lines, working, answer)


def _block_original_before_percent(
    intent: MathIntent, lines: list[str]
) -> VerifiedMathBlock | None:
    """The amount before a percent change: ``48 / (1 - 0.2) = 48 / 0.8 = 60``."""
    if intent.percent_base is None or intent.percent_rate is None:
        return None
    sign = "-" if intent.school_op == "original_before_decrease" else "+"
    written, factor = _fraction_of_one(intent.percent_rate, sign=sign)
    if float(factor) <= 0:
        return None
    answer = f"{round(intent.percent_base / float(factor), 10):g}"
    after = f"{intent.percent_base:g}"
    change = "less" if sign == "-" else "more"
    lines.append(
        f"{after} is {intent.percent_rate:g}% {change} than the original, so it is "
        f"{factor} of the original. Original = {after} / {factor} = {answer}"
    )
    working = rf"\text{{original}} = \frac{{{after}}}{{{written}}} = \frac{{{after}}}{{{factor}}}"
    return _with_working(lines, working, answer)


def _block_percent_change_from(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if intent.percent_base is None or intent.percent_rate is None:
        return None
    answer = math_formulas.percent_change_from(intent.percent_base, intent.percent_rate)
    lines.append(
        f"Percent change from {intent.percent_base:g} to {intent.percent_rate:g} = {answer}"
    )
    start, end = f"{intent.percent_base:g}", f"{intent.percent_rate:g}"
    change = f"{intent.percent_rate - intent.percent_base:g}"
    working = (
        rf"\text{{change}} = \frac{{{end} - {start}}}{{{start}}} \times 100\% = "
        rf"\frac{{{change}}}{{{start}}} \times 100\%"
    )
    return _with_working(lines, working, answer)
