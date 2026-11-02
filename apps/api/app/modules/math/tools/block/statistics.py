"""Statistics verified blocks: one list's summaries, or two paired lists."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent, StatisticsInput
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock

_BIVARIATE_STATS_OPS = {
    "correlation",
    "covariance",
    "sample_covariance",
    "linear_regression",
}
_STAT_SYMBOLS: dict[str, str] = {
    "mean": r"\bar{x}",
    "median": r"\text{median}",
    "mode": r"\text{mode}",
    "range": r"\text{range}",
    "variance": r"\sigma^{2}",
    "stdev": r"\sigma",
    "sample_variance": r"s^{2}",
    "sample_stdev": "s",
}
_SPREAD_OPS = frozenset({"variance", "stdev", "sample_variance", "sample_stdev"})


def _summary_value(result: Any, op: str) -> str:
    if op == "variance":
        return f"{result.variance_population:g}"
    if op == "sample_variance":
        return f"{result.variance_sample:g}" if result.variance_sample is not None else "n/a"
    if op == "stdev":
        return result.labels["population_stdev"]
    if op == "sample_stdev":
        return result.labels.get("sample_stdev", "n/a")
    return result.labels[op]


def _verified_block_statistics(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.stats_numbers or len(intent.stats_numbers) < 2:
        return None
    if intent.stats_op in _BIVARIATE_STATS_OPS:
        return _verified_bivariate(
            intent.stats_op, intent.stats_numbers, intent.stats_numbers_b, lines
        )

    result = math_solve.compute_statistics(StatisticsInput(numbers=intent.stats_numbers))
    lines.append(f"Data ({result.count} values): {', '.join(f'{v:g}' for v in result.numbers)}")
    sample_stdev = (
        f"{result.stdev_sample:g}" if result.stdev_sample is not None else "n/a (needs 2+ values)"
    )
    lines.append(
        f"mean={result.mean:g} median={result.median:g} mode={result.labels.get('mode', 'none')} "
        f"range={result.range:g} population variance={result.variance_population:g} "
        f"population stdev={result.stdev_population:g} sample stdev={sample_stdev}"
    )
    if intent.stats_ops and len(intent.stats_ops) >= 2:
        # One chip states every requested summary, each with its symbol, so
        # "mean and standard deviation" never certifies only the mean.
        answer = r",\quad ".join(
            f"{_STAT_SYMBOLS[op]} = {_summary_value(result, op)}" for op in intent.stats_ops
        )
        return finish_with_answer(lines, answer)
    if intent.stats_op in {"iqr", "quartiles", "percentile"}:
        from app.modules.math import formulas as math_formulas

        if intent.stats_op == "iqr":
            answer = math_formulas.interquartile_range(intent.stats_numbers)
        elif intent.stats_op == "quartiles":
            answer = math_formulas.quartiles(intent.stats_numbers)
        elif intent.combo_n is None:
            return None
        else:
            answer = math_formulas.percentile(intent.stats_numbers, intent.combo_n)
    else:
        answer = _summary_value(result, intent.stats_op or "mean")
    block = finish_with_answer(
        lines,
        answer,
    )
    if intent.stats_op in _SPREAD_OPS and block is not None and block.canonical_answer:
        # Population and sample spreads differ; the chip says which one this is.
        block = replace(
            block, display_answer=f"{_STAT_SYMBOLS[intent.stats_op]} = {block.canonical_answer}"
        )
    if intent.stats_op == "quartiles" and intent.stats_numbers:
        from app.modules.math.solve.teaching_data import box_plot_spec
        from app.modules.math.tools.direct_teaching import attach_teaching

        payload = ",".join(f"{value:.12g}" for value in intent.stats_numbers)
        plot = box_plot_spec(payload, answer)
        if plot is not None:
            return attach_teaching(block, plot, direct=False, request_text=None)
    return block


def _verified_bivariate(
    op: str, numbers: list[float], paired: list[float] | None, lines: list[str]
) -> VerifiedMathBlock:
    """Correlation, covariance or a regression line of two equal-length lists."""
    if not paired or len(paired) != len(numbers):
        message = (
            "The two data lists must have the same number of values before "
            f"{op.replace('_', ' ')} can be calculated "
            f"({len(numbers)} values versus {len(paired or [])})."
        )
        lines.append(message)
        return VerifiedMathBlock(text="\n".join(lines), direct_reply=message)
    answer, steps = math_solve.compute_bivariate_statistics(op, numbers, paired)
    lines.extend(steps)
    return finish_with_answer(lines, answer)
