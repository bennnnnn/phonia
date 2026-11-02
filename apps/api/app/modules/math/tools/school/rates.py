"""Work, mixture, and twice-as-many extractors and verified blocks."""

from __future__ import annotations

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.number_text import DECIMAL_LITERAL
from app.services.text_match import word_index


def _hour_quantities(text: str) -> list[float]:
    lower = text.lower()
    found: list[float] = []
    for match in DECIMAL_LITERAL.finditer(text):
        after = lower[match.end() :]
        k = 0
        while k < len(after) and after[k].isspace():
            k += 1
        if after.startswith("hour", k):
            found.append(float(match.group(0)))
    return found


def _extract_work_together_intent(cleaned: str, lower: str) -> MathIntent | None:
    if word_index(lower, "together") == -1 and "combined" not in lower:
        return None
    hours = _hour_quantities(cleaned)
    if len(hours) != 2 or hours[0] <= 0 or hours[1] <= 0:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="work_together",
        percent_base=hours[0],
        percent_rate=hours[1],
        operation="solve",
    )


def _extract_mixture_intent(cleaned: str, lower: str) -> MathIntent | None:
    if "% of " in lower:
        return None
    if not any(word_index(lower, word) != -1 for word in ("mix", "mixed", "mixture")):
        return None
    if cleaned.count("%") != 2:
        return None
    volumes: list[float] = []
    percents: list[float] = []
    for match in DECIMAL_LITERAL.finditer(cleaned):
        after = cleaned[match.end() :].lstrip()
        value = float(match.group(0))
        if after.startswith("%"):
            percents.append(value)
        else:
            volumes.append(value)
    if len(volumes) != 2 or len(percents) != 2:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="mixture",
        vec_a=volumes,
        vec_b=percents,
        operation="solve",
    )


def _extract_twice_as_many_intent(cleaned: str, lower: str) -> MathIntent | None:
    if "twice as many" not in lower and "2 times as many" not in lower:
        return None
    if word_index(lower, "together") == -1:
        return None
    nums = [float(match.group(0)) for match in DECIMAL_LITERAL.finditer(cleaned)]
    total: float | None = None
    if "twice as many" in lower and len(nums) == 1:
        total = nums[0]
    elif len(nums) == 2 and 2.0 in nums:
        total = nums[0] if nums[1] == 2.0 else nums[1]
        if total == 2.0:
            return None
    if total is None or total <= 0:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="twice_as_many",
        percent_base=total,
        operation="solve",
    )


def _extract_word_problem_intent(cleaned: str, lower: str) -> MathIntent | None:
    work = _extract_work_together_intent(cleaned, lower)
    if work is not None:
        return work
    mix = _extract_mixture_intent(cleaned, lower)
    if mix is not None:
        return mix
    return _extract_twice_as_many_intent(cleaned, lower)


def _block_work_together(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None or intent.percent_rate is None:
        return None
    answer = math_school.work_together(intent.percent_base, intent.percent_rate)
    lines.append(f"Together: {intent.percent_base:g} h and {intent.percent_rate:g} h → {answer}")
    return finish_with_answer(lines, answer)


def _block_mixture(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.vec_a is None or intent.vec_b is None or len(intent.vec_b) != 2:
        return None
    answer = math_school.mixture_percent(
        intent.vec_a[0], intent.vec_b[0], intent.vec_a[1], intent.vec_b[1]
    )
    lines.append(f"Mixture: {answer}%")
    return finish_with_answer(lines, answer)


def _block_twice_as_many(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None:
        return None
    answer = math_school.twice_as_many(intent.percent_base)
    lines.append(f"Parts: {answer}")
    return finish_with_answer(lines, answer)
