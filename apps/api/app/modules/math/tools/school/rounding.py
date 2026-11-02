"""Rounding to decimal places or significant figures: extractor and verified block.

The value to round rides in ``percent_base`` and the places in ``combo_n``.
"""

from __future__ import annotations

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import _exactly_n_numbers
from app.services.text_match import word_index

ROUNDING_OPS = frozenset({"round_decimal", "round_sigfigs"})


def extract_rounding(cleaned: str, lower: str) -> MathIntent | None:
    if word_index(lower, "round") == -1:
        return None
    values = _exactly_n_numbers(cleaned, 2)
    if values is None:
        return None
    places = values[1]
    if not places.is_integer() or places < 0:
        return None
    if "decimal" in lower:
        op = "round_decimal"
    elif "significant" in lower:
        op = "round_sigfigs"
        if places < 1:
            return None
    else:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op=op,
        percent_base=values[0],
        combo_n=int(places),
        operation="solve",
    )


def rounding_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.percent_base is None or intent.combo_n is None:
        return None
    from app.modules.math import formulas as math_formulas

    if intent.school_op == "round_decimal":
        answer = math_formulas.round_decimal_places(intent.percent_base, intent.combo_n)
    else:
        answer = math_formulas.round_significant_figures(intent.percent_base, intent.combo_n)
    lines.append(f"Rounded: {answer}")
    return finish_with_answer(lines, answer)
