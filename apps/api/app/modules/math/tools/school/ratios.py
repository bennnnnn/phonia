"""Ratio and proportion extractors and verified blocks."""

from __future__ import annotations

import re

from app.modules.math import school as math_school
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import (
    _colon_ratio_parts,
    _exactly_n_numbers,
)
from app.services.number_text import DECIMAL_LITERAL, finite_match_value
from app.services.text_match import has_any_word, word_index

_RATIO_SPLIT_WORDS = ("split", "share", "divide")


def _extract_ratio_split(cleaned: str, lower: str) -> MathIntent | None:
    if not has_any_word(lower, _RATIO_SPLIT_WORDS) or "ratio" not in lower:
        return None
    grouped = _colon_ratio_parts(cleaned)
    if grouped is None:
        return None
    parts, spans = grouped
    if any(part < 0 for part in parts) or sum(parts) <= 0:
        return None
    leftover: list[re.Match[str]] = []
    used = set(spans)
    for match in DECIMAL_LITERAL.finditer(cleaned):
        if (match.start(), match.end()) in used:
            continue
        leftover.append(match)
    if len(leftover) != 1:
        return None
    total = finite_match_value(leftover[0])
    if total is None or total <= 0:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="ratio_split",
        percent_base=total,
        stats_numbers=parts,
        operation="solve",
    )


def _extract_colon_ratio(cleaned: str, lower: str) -> MathIntent | None:
    if ":" in cleaned and ("ratio" in lower or "simplify" in lower):
        first = DECIMAL_LITERAL.search(cleaned)
        if first:
            second = DECIMAL_LITERAL.search(cleaned, first.end())
            if second:
                left = finite_match_value(first)
                right = finite_match_value(second)
                if left is None or right is None:
                    return None
                extra = DECIMAL_LITERAL.search(cleaned, second.end())
                if extra is not None:
                    return None
                return MathIntent(
                    kind="arithmetic",
                    school_op="ratio",
                    percent_rate=left,
                    percent_base=right,
                    operation="solve",
                )
    return None


def extract_proportion(cleaned: str, lower: str) -> MathIntent | None:
    values = _exactly_n_numbers(cleaned, 3)
    if values is None:
        return None
    inverse = word_index(lower, "inverse") != -1
    direct = (
        word_index(lower, "cost") != -1
        or word_index(lower, "costs") != -1
        or "direct proportion" in lower
    )
    if inverse and ("proportion" in lower or word_index(lower, "inversely") != -1):
        return MathIntent(
            kind="arithmetic",
            school_op="inverse_proportion",
            stats_numbers=values,
            operation="solve",
        )
    if inverse or not direct:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="direct_proportion",
        stats_numbers=values,
        operation="solve",
    )


def _block_proportion(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if intent.stats_numbers is None or len(intent.stats_numbers) != 3:
        return None
    a, b, c = intent.stats_numbers
    if intent.school_op == "direct_proportion":
        answer = math_formulas.direct_proportion(a, b, c)
    else:
        answer = math_formulas.inverse_proportion(a, b, c)
    lines.append(f"{intent.school_op}: {answer}")
    return finish_with_answer(lines, answer)


def _block_ratio(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_rate is None or intent.percent_base is None:
        return None
    answer = math_school.simplify_ratio(intent.percent_rate, intent.percent_base)
    lines.append(f"Simplified ratio: {answer}")
    return finish_with_answer(lines, answer)


def _block_ratio_split(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None or intent.stats_numbers is None:
        return None
    answer = math_school.split_ratio(intent.percent_base, intent.stats_numbers)
    lines.append(f"{intent.percent_base:g} in ratio split = {answer}")
    return finish_with_answer(lines, answer)
