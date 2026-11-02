"""Series: a sum, or whether each series converges."""

from __future__ import annotations

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent, MathSeriesResult
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout


def _verified_block_series(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not (intent.expr and intent.series_start is not None and intent.series_end is not None):
        return None
    series_out = math_solve.evaluate_series_sum(
        intent.expr, intent.variable, intent.series_start, intent.series_end
    )
    if intent.school_op == "series_convergence":
        outcomes = [(intent.expr, series_out)]
        if intent.expr2:
            outcomes.append(
                (
                    intent.expr2,
                    math_solve.evaluate_series_sum(
                        intent.expr2,
                        intent.variable,
                        intent.series_start,
                        intent.series_end,
                    ),
                )
            )
        return _series_convergence(intent.variable, outcomes, lines)
    lines.append(f"Result: {series_out.latex}")
    if series_out.is_convergent is not None:
        lines.append(
            f"Convergent: {series_out.is_convergent}"
            + (
                f" (absolutely convergent: {series_out.is_absolutely_convergent})"
                if series_out.is_absolutely_convergent is not None
                else ""
            )
            + "."
        )
    if series_out.is_convergent is False and not series_out.is_infinite:
        lines.append("This series diverges; it has no ordinary sum. Do not present a finite value.")
        return VerifiedMathBlock(
            text="\n".join(lines),
            direct_reply="This series diverges; it has no ordinary sum.",
        )
    if not series_out.solved:
        lines.append("The sum was not evaluated. Do not claim a closed-form answer.")
        return VerifiedMathBlock(text="\n".join(lines))
    if series_out.is_infinite:
        lines.append(
            "This series diverges to infinity — preserve its sign, do not "
            "treat it as an ordinary finite number."
        )
    return finish_with_answer(lines, series_out.latex)


def _series_convergence(
    variable: str, outcomes: list[tuple[str, MathSeriesResult]], lines: list[str]
) -> VerifiedMathBlock:
    """Diverges, converges conditionally or absolutely: one row per series asked about."""
    from sympy import latex

    rendered: list[str] = []
    for expression, outcome in outcomes:
        if outcome.is_convergent is False:
            status = "diverges"
        elif outcome.is_convergent is True and outcome.is_absolutely_convergent is False:
            status = "converges conditionally"
        elif outcome.is_convergent is True:
            status = "converges absolutely"
        else:
            status = "could not be classified"
        lines.append(f"Series {expression}: {status}; sum={outcome.latex}")
        parsed = math_solve.parse_expression(expression, [variable], real=True)
        rendered.append(math_line(f"\\sum_{{{variable}=1}}^{{\\infty}} {latex(parsed)}", status))
    direct = render_workout(Workout(steps=tuple(rendered))).removesuffix("\n\n**Answer**")
    return VerifiedMathBlock(text="\n".join(lines), direct_reply=direct)
