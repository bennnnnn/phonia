"""Interest extractors and verified blocks."""

from __future__ import annotations

import re

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import (
    _count_char,
)
from app.services.number_text import DECIMAL_LITERAL, finite_match_value, number_immediately_before
from app.services.text_match import word_index

_INTEREST_YEAR_MAX = 100
# Only yearly compounding is modelled; any other period is declined.
_OTHER_PERIODS = (
    "month",
    "months",
    "monthly",
    "quarter",
    "quarterly",
    "weekly",
    "daily",
    "continuous",
    "continuously",
    "semiannually",
    "semi-annually",
    "biannually",
    "half-yearly",
    "twice",
)
# Where the principal is named: "interest on $1200", "$5000 invested at 4%".
_PRINCIPAL_WORDS = ("invested", "invest", "invests", "deposited", "deposit", "deposits")
# The question asks for what the money grows to, not the interest earned.
_AMOUNT_QUESTION = re.compile(
    r"\bhow\s+much\s+(?:money\s+)?(?:will|would|do|does|did)\s+(?:i|you|we|he|she|they|it)\s+"
    r"(?:have|get|be\s+worth|end\s+up\s+with|be)\b"
    r"|\b(?:final|total)\s+amount\b|\bbalance\b|\bwhat\s+will\s+it\s+(?:be\s+worth|grow\s+to)\b",
    re.IGNORECASE,
)
_INTEREST_QUESTION = re.compile(r"\bhow\s+much\s+interest\b|\binterest\s+earned\b", re.IGNORECASE)


def _years_number(cleaned: str, lower: str) -> re.Match[str] | None:
    """The number written right before "year(s)", wherever "per year" also appears."""
    start = 0
    while (year_at := lower.find("year", start)) != -1:
        found = number_immediately_before(cleaned, year_at)
        if found is not None:
            return found
        start = year_at + 4
    return None


def _extract_interest_intent(cleaned: str, lower: str) -> MathIntent | None:
    compound = any(word_index(lower, word) != -1 for word in ("compound", "compounded"))
    simple = word_index(lower, "simple") != -1
    if compound == simple:
        return None
    if simple and "interest" not in lower:
        return None
    if compound and "interest" not in lower and "amount" not in lower:
        return None
    if _count_char(cleaned, "%") != 1:
        return None
    if any(word_index(lower, word) != -1 for word in _OTHER_PERIODS):
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 3:
        return None
    on_at = word_index(lower, "on")
    if on_at == -1:
        on_at = word_index(lower, "of")
    pct_at = cleaned.find("%")
    if pct_at == -1:
        return None
    rate_m = number_immediately_before(cleaned, pct_at)
    years_m = _years_number(cleaned, lower)
    if rate_m is None or years_m is None:
        return None
    if on_at != -1:
        principal_m = DECIMAL_LITERAL.search(cleaned, on_at + 2)
    elif any(word_index(lower, word) != -1 for word in _PRINCIPAL_WORDS):
        # "$5000 invested at 4% ... for 3 years": the one number left is the principal.
        principal_m = next(
            (m for m in nums if m.span() not in {rate_m.span(), years_m.span()}), None
        )
    else:
        return None
    if principal_m is None:
        return None
    if {principal_m.span(), rate_m.span(), years_m.span()} != {match.span() for match in nums}:
        return None
    asks_amount = _AMOUNT_QUESTION.search(cleaned) is not None
    asks_interest = _INTEREST_QUESTION.search(cleaned) is not None
    if asks_amount and (asks_interest or simple):
        # Two quantities, or the simple-interest total, which is not modelled.
        return None
    principal = finite_match_value(principal_m)
    rate = finite_match_value(rate_m)
    years_value = finite_match_value(years_m)
    if principal is None or rate is None or years_value is None:
        return None
    if principal <= 0 or rate < 0 or not years_value.is_integer():
        return None
    years = int(years_value)
    if years < 1 or years > _INTEREST_YEAR_MAX:
        return None
    if simple:
        op = "simple_interest"
    elif asks_amount or (word_index(lower, "amount") != -1 and "interest" not in lower):
        op = "compound_amount"
    else:
        op = "compound_interest"
    return MathIntent(
        kind="arithmetic",
        school_op=op,
        percent_base=principal,
        percent_rate=rate,
        combo_n=years,
        operation="solve",
    )


def extract_present_value(cleaned: str, lower: str) -> MathIntent | None:
    if "present value" not in lower:
        return None
    if cleaned.count("%") != 1 or "year" not in lower:
        return None
    if any(word_index(lower, word) != -1 for word in ("month", "weekly", "daily", "continuous")):
        return None
    nums = list(DECIMAL_LITERAL.finditer(cleaned))
    if len(nums) != 3:
        return None
    pct_at = cleaned.find("%")
    year_at = lower.find("year")
    rate_m = number_immediately_before(cleaned, pct_at)
    years_m = number_immediately_before(cleaned, year_at)
    if rate_m is None or years_m is None:
        return None
    amount_m = None
    for match in nums:
        if match.span() not in {rate_m.span(), years_m.span()}:
            amount_m = match
            break
    if amount_m is None:
        return None
    rate = finite_match_value(rate_m)
    years_value = finite_match_value(years_m)
    amount = finite_match_value(amount_m)
    if rate is None or years_value is None or amount is None or not years_value.is_integer():
        return None
    years = int(years_value)
    if years < 1 or years > 100:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="present_value",
        percent_base=amount,
        percent_rate=rate,
        combo_n=years,
        operation="solve",
    )


def _block_present_value(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if intent.percent_base is None or intent.percent_rate is None or intent.combo_n is None:
        return None
    answer = math_formulas.present_value(intent.percent_base, intent.percent_rate, intent.combo_n)
    lines.append(f"Present value = {answer}")
    return finish_with_answer(lines, answer)


def _block_interest(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None or intent.percent_rate is None or intent.combo_n is None:
        return None
    principal, rate, years = intent.percent_base, intent.percent_rate, intent.combo_n
    if intent.school_op == "simple_interest":
        answer = math_school.simple_interest(principal, rate, years)
        label = "Simple interest"
    elif intent.school_op == "compound_amount":
        answer = math_school.compound_amount(principal, rate, years)
        label = "Compound amount"
    else:
        answer = math_school.compound_interest(principal, rate, years)
        label = "Compound interest"
    lines.append(f"{label} on {principal:g} at {rate:g}% for {years} years = {answer}")
    return finish_with_answer(lines, answer)
