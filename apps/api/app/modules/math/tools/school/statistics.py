"""Z-score extractor and verified block."""

from __future__ import annotations

import math
import re

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock
from app.services.number_text import SIGNED_DECIMAL
from app.services.workout import Workout, math_line, render_workout, text_line

_Z_VALUE = re.compile(rf"\bx\s*=\s*({SIGNED_DECIMAL})\b", re.IGNORECASE)
_Z_SCORED = re.compile(rf"\bscored\s+({SIGNED_DECIMAL})\b", re.IGNORECASE)
_Z_MEAN = re.compile(
    rf"\bmean(?:\s+score)?(?:\s+is|\s*=)?\s+({SIGNED_DECIMAL})\b",
    re.IGNORECASE,
)
_Z_STDEV = re.compile(
    rf"\b(?:standard\s+deviation|std(?:\s+dev)?|stdev)"
    rf"(?:\s+is|\s*=)?\s+({SIGNED_DECIMAL})\b",
    re.IGNORECASE,
)


def _extract_z_score_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "z-score" not in lower and "z score" not in lower:
        return None
    x_match = _Z_VALUE.search(cleaned) or _Z_SCORED.search(cleaned)
    mean_match = _Z_MEAN.search(cleaned)
    stdev_match = _Z_STDEV.search(cleaned)
    if x_match is None or mean_match is None or stdev_match is None:
        return None
    x_value = float(x_match.group(1))
    mean = float(mean_match.group(1))
    stdev = float(stdev_match.group(1))
    if not all(math.isfinite(value) for value in (x_value, mean, stdev)) or stdev <= 0:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="z_score",
        point_x=x_value,
        percent_base=mean,
        percent_rate=stdev,
        operation="solve",
    )


def _block_z_score(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    if intent.point_x is None or intent.percent_base is None or intent.percent_rate is None:
        return None
    x_value, mean, stdev = intent.point_x, intent.percent_base, intent.percent_rate
    z_score = (x_value - mean) / stdev
    answer = f"{z_score:g}"
    direction = "above" if z_score > 0 else "below" if z_score < 0 else "at"
    if direction == "at":
        interpretation = "The value is exactly at the mean."
    else:
        interpretation = f"The value is {abs(z_score):g} standard deviations {direction} the mean."
    interpretation += (
        " This describes relative position only; it does not assume a normal distribution."
    )
    direct = render_workout(
        Workout(
            given=(
                math_line(f"x = {x_value:g}"),
                math_line(f"\\mu = {mean:g}", "mean"),
                math_line(f"\\sigma = {stdev:g}", "standard deviation"),
            ),
            find=(math_line("z", "z-score"),),
            formula=(math_line("z = \\frac{x - \\mu}{\\sigma}"),),
            substitution=(
                math_line(f"z = \\frac{{{x_value:g} - {mean:g}}}{{{stdev:g}}} = {answer}"),
            ),
            steps=(text_line(interpretation),),
        ),
        f"z = {answer}",
    )
    lines.extend(
        [
            rf"z = \frac{{{x_value:g} - {mean:g}}}{{{stdev:g}}} = {answer}",
            interpretation,
        ]
    )
    return VerifiedMathBlock(text="\n".join(lines), direct_reply=direct)
