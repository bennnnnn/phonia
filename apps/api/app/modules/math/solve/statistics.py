"""Deterministic paired-data statistics using Python's standard library."""

from __future__ import annotations

import math
import statistics

from app.services.solving import SolveServiceError


def _format_stat(value: float) -> str:
    if not math.isfinite(value):
        raise SolveServiceError("statistic is not finite")
    if abs(value) < 5e-13:
        value = 0.0
    return f"{value:.10g}"


def _population_covariance(x_values: list[float], y_values: list[float]) -> float:
    x_mean = math.fsum(x_values) / len(x_values)
    y_mean = math.fsum(y_values) / len(y_values)
    products = (
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values, strict=True)
    )
    return math.fsum(products) / len(x_values)


def compute_bivariate_statistics(
    operation: str,
    x_values: list[float],
    y_values: list[float],
) -> tuple[str, list[str]]:
    """Return a verified answer plus short supporting steps for paired data."""
    if len(x_values) != len(y_values) or len(x_values) < 2:
        raise SolveServiceError("paired statistics need equal-length lists with at least 2 values")
    if len(x_values) > 200:
        raise SolveServiceError("paired statistics are capped at 200 values")
    if not all(math.isfinite(value) for value in (*x_values, *y_values)):
        raise SolveServiceError("statistics values must be finite numbers")

    try:
        if operation == "correlation":
            answer = _format_stat(statistics.correlation(x_values, y_values))
            return answer, [f"Pearson correlation: r = {answer}"]
        if operation == "covariance":
            answer = _format_stat(_population_covariance(x_values, y_values))
            return answer, [f"Population covariance: {answer}"]
        if operation == "sample_covariance":
            answer = _format_stat(statistics.covariance(x_values, y_values))
            return answer, [f"Sample covariance: {answer}"]
        if operation != "linear_regression":
            raise SolveServiceError("unsupported paired-statistics operation")
        regression = statistics.linear_regression(x_values, y_values)
    except statistics.StatisticsError as exc:
        raise SolveServiceError(str(exc)) from exc

    slope = _format_stat(regression.slope)
    intercept_value = 0.0 if abs(regression.intercept) < 5e-13 else regression.intercept
    if intercept_value == 0:
        answer = f"y = {slope}x"
    else:
        intercept = _format_stat(abs(intercept_value))
        sign = "+" if intercept_value > 0 else "-"
        answer = f"y = {slope}x {sign} {intercept}"
    return answer, [f"Least-squares line: {answer}"]
