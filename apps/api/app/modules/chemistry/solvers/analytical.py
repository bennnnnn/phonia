# ruff: noqa: RUF001
"""Analytical chemistry: calibration, gravimetric analysis, standard addition, statistics."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError


def solve_calibration(intent: ChemistryIntent) -> ChemistryResult:
    slope = intent.params.get("slope")
    intercept = intent.params.get("intercept")
    signal = intent.params.get("signal")
    if slope is None or intercept is None or signal is None or slope == 0:
        raise SolveServiceError("calibration needs a nonzero slope, intercept, and signal")
    value = (signal - intercept) / slope
    shown = f"c = {num(value)}"
    return verified(
        "Verified calibration",
        (f"slope = {inp(slope)}", f"intercept = {inp(intercept)}", f"signal = {inp(signal)}"),
        "Concentration",
        *stated("calibration"),
        (f"c = ({inp(signal)} − {inp(intercept)}) / {inp(slope)}",),
        shown,
        shown,
    )


def solve_gravimetric(intent: ChemistryIntent) -> ChemistryResult:
    mass = intent.params.get("precipitate_mass")
    factor = intent.params.get("factor")
    if mass is None or factor is None or mass < 0 or factor <= 0:
        raise SolveServiceError("gravimetric analysis needs a precipitate mass and a factor")
    shown = f"mass = {num(mass * factor)} g"
    return verified(
        "Verified gravimetric analysis",
        (f"precipitate = {inp(mass)} g", f"factor = {inp(factor)}"),
        "Analyte mass",
        *stated("gravimetric"),
        (f"mass = ({inp(mass)})({inp(factor)})",),
        shown,
        shown,
    )


def solve_standard_addition(intent: ChemistryIntent) -> ChemistryResult:
    message = "standard addition inputs are incomplete"
    sample = require(intent, "sample_signal", message=message)
    spiked = require(intent, "spiked_signal", message=message)
    standard = require(intent, "standard_concentration", message=message)
    standard_volume = require(intent, "standard_volume", message=message)
    sample_volume = require(intent, "sample_volume", positive=True, message=message)
    if spiked <= sample:
        raise SolveServiceError(message)
    value = (sample / (spiked - sample)) * standard * (standard_volume / sample_volume)
    shown = f"c = {num(value)}"
    return verified(
        "Verified standard addition",
        (
            f"Ix = {inp(sample)}",
            f"Ispike = {inp(spiked)}",
            f"Cstd = {inp(standard)}",
            f"Vstd = {inp(standard_volume)}",
            f"Vsample = {inp(sample_volume)}",
        ),
        "Sample concentration",
        *stated("standard_addition"),
        (
            f"C = ({inp(sample)} / ({inp(spiked)} − {inp(sample)})) × {inp(standard)} × "
            f"{inp(standard_volume)} / {inp(sample_volume)}",
        ),
        shown,
        shown,
    )


def _spread(values: list[float]) -> tuple[float, float, float]:
    """``(mean, sum of squared deviations, sample standard deviation)``."""
    mean = sum(values) / len(values)
    squares = sum((value - mean) ** 2 for value in values)
    return mean, squares, math.sqrt(squares / (len(values) - 1))


def _data_lines(values: list[float]) -> tuple[str, ...]:
    return (f"data: {', '.join(inp(value) for value in values)}", f"n = {len(values)}")


def solve_standard_deviation(intent: ChemistryIntent) -> ChemistryResult:
    values = _samples(intent)
    mean, squares, deviation = _spread(values)
    shown = f"s = {num(deviation)}"
    return verified(
        "Verified sample standard deviation",
        _data_lines(values),
        "Sample standard deviation",
        *stated("standard_deviation"),
        (
            f"x̄ = ({' + '.join(inp(value) for value in values)}) / {len(values)} = {num(mean)}",
            f"Σ(x − x̄)^2 = {num(squares)}",
            f"s = √({num(squares)} / {len(values) - 1})",
        ),
        shown,
        shown,
    )


def solve_standard_error(intent: ChemistryIntent) -> ChemistryResult:
    values = _samples(intent)
    mean, squares, deviation = _spread(values)
    error = deviation / math.sqrt(len(values))
    shown = f"SE = {num(error)}"
    return verified(
        "Verified standard error",
        _data_lines(values),
        "Standard error of the mean",
        *stated("standard_error"),
        (
            f"x̄ = {num(mean)}, Σ(x − x̄)^2 = {num(squares)}",
            f"s = √({num(squares)} / {len(values) - 1}) = {num(deviation)}",
            f"SE = {num(deviation)} / √{len(values)}",
        ),
        shown,
        shown,
    )


def solve_percent_error(intent: ChemistryIntent) -> ChemistryResult:
    experimental = intent.params.get("experimental")
    accepted = intent.params.get("accepted")
    if experimental is None or accepted is None or accepted == 0:
        raise SolveServiceError(
            "percent error needs an experimental value and a nonzero accepted value"
        )
    value = abs(experimental - accepted) / abs(accepted) * 100
    shown = f"percent error = {num(value)}%"
    return verified(
        "Verified percent error",
        (f"experimental = {inp(experimental)}", f"accepted = {inp(accepted)}"),
        "Percent error",
        *stated("percent_error"),
        (f"|{inp(experimental)} − {inp(accepted)}| / |{inp(accepted)}| × 100",),
        shown,
        shown,
    )


def solve_relative_uncertainty(intent: ChemistryIntent) -> ChemistryResult:
    left = intent.params.get("a")
    left_uncertainty = intent.params.get("da")
    right = intent.params.get("b")
    right_uncertainty = intent.params.get("db")
    if (
        left is None
        or right is None
        or left_uncertainty is None
        or right_uncertainty is None
        or left == 0
        or right == 0
    ):
        raise SolveServiceError(
            "relative uncertainty needs both measurements and their uncertainties"
        )
    value = math.sqrt((left_uncertainty / left) ** 2 + (right_uncertainty / right) ** 2)
    shown = f"relative uncertainty = {num(value)}"
    return verified(
        "Verified relative uncertainty",
        (
            f"a = {inp(left)}",
            f"Δa = {inp(left_uncertainty)}",
            f"b = {inp(right)}",
            f"Δb = {inp(right_uncertainty)}",
        ),
        "Relative uncertainty of a product or quotient",
        *stated("relative_uncertainty"),
        (
            f"√(({inp(left_uncertainty)}/{inp(left)})^2 + "
            f"({inp(right_uncertainty)}/{inp(right)})^2)",
        ),
        shown,
        shown,
    )


def solve_chromatography_rf(intent: ChemistryIntent) -> ChemistryResult:
    spot = intent.params.get("spot")
    front = intent.params.get("front")
    if spot is None or front is None or spot < 0 or front <= 0 or spot > front:
        raise SolveServiceError("Rf needs a spot distance that does not pass the solvent front")
    value = spot / front
    shown = f"Rf = {num(value)}"
    return verified(
        "Verified retention factor",
        (f"spot distance = {inp(spot)}", f"solvent front = {inp(front)}"),
        "Retention factor",
        *stated("chromatography_rf"),
        (f"Rf = {inp(spot)} / {inp(front)}",),
        shown,
        shown,
    )


def _detection_limit(
    intent: ChemistryIntent, factor: int, operation: str, label: str
) -> ChemistryResult:
    slope = require(intent, "slope", positive=True)
    deviation = require(intent, "sd", positive=True)
    value = factor * deviation / slope
    shown = f"{label} = {num(value)}"
    return verified(
        f"Verified {label}",
        (f"s = {inp(deviation)}", f"m = {inp(slope)}"),
        label,
        *stated(operation),
        (f"{label} = {factor} * {inp(deviation)} / {inp(slope)}",),
        shown,
        shown,
    )


def solve_lod(intent: ChemistryIntent) -> ChemistryResult:
    return _detection_limit(intent, 3, "lod", "LOD")


def solve_loq(intent: ChemistryIntent) -> ChemistryResult:
    return _detection_limit(intent, 10, "loq", "LOQ")


def solve_capacity_factor(intent: ChemistryIntent) -> ChemistryResult:
    retention = require(intent, "tr", positive=True)
    dead = require(intent, "tm", positive=True)
    if retention <= dead:
        raise SolveServiceError("the retention time must be after the dead time")
    value = (retention - dead) / dead
    shown = f"k' = {num(value)}"
    return verified(
        "Verified capacity factor",
        (f"tR = {inp(retention)}", f"tM = {inp(dead)}"),
        "Capacity factor",
        *stated("capacity_factor"),
        (f"k' = ({inp(retention)} - {inp(dead)}) / {inp(dead)}",),
        shown,
        shown,
    )


def solve_selectivity(intent: ChemistryIntent) -> ChemistryResult:
    given: tuple[str, ...]
    steps: tuple[str, ...]
    if "k1" in intent.params or "k2" in intent.params:
        first = require(intent, "k1", positive=True)
        second = require(intent, "k2", positive=True)
        given = (f"k1 = {inp(first)}", f"k2 = {inp(second)}")
        steps = (f"α = {inp(second)} / {inp(first)}",)
    else:
        earlier = require(intent, "tr1", positive=True)
        later = require(intent, "tr2", positive=True)
        dead = require(intent, "tm", positive=True)
        if earlier <= dead or later <= dead:
            raise SolveServiceError("each retention time must be after the dead time")
        first = (earlier - dead) / dead
        second = (later - dead) / dead
        given = (f"tR1 = {inp(earlier)}", f"tR2 = {inp(later)}", f"tM = {inp(dead)}")
        steps = (
            f"k1 = ({inp(earlier)} - {inp(dead)}) / {inp(dead)} = {num(first)}",
            f"k2 = ({inp(later)} - {inp(dead)}) / {inp(dead)} = {num(second)}",
            f"α = {num(second)} / {num(first)}",
        )
    shown = f"α = {num(second / first)}"
    return verified(
        "Verified selectivity",
        given,
        "Selectivity",
        *stated("selectivity"),
        steps,
        shown,
        shown,
    )


def solve_resolution(intent: ChemistryIntent) -> ChemistryResult:
    earlier = require(intent, "tr1", positive=True)
    later = require(intent, "tr2", positive=True)
    first_width = require(intent, "w1", positive=True)
    second_width = require(intent, "w2", positive=True)
    if later <= earlier:
        raise SolveServiceError("the later peak must follow the earlier one")
    value = 2 * (later - earlier) / (first_width + second_width)
    shown = f"Rs = {num(value)}"
    return verified(
        "Verified resolution",
        (
            f"tR1 = {inp(earlier)}",
            f"tR2 = {inp(later)}",
            f"w1 = {inp(first_width)}",
            f"w2 = {inp(second_width)}",
        ),
        "Resolution",
        *stated("resolution"),
        (f"Rs = 2 * ({inp(later)} - {inp(earlier)}) / ({inp(first_width)} + {inp(second_width)})",),
        shown,
        shown,
    )


def solve_plate_number(intent: ChemistryIntent) -> ChemistryResult:
    retention = require(intent, "tr", positive=True)
    width = require(intent, "width", positive=True)
    value = 16 * (retention / width) ** 2
    shown = f"N = {num(value)}"
    return verified(
        "Verified plate number",
        (f"tR = {inp(retention)}", f"w = {inp(width)}"),
        "Plate number",
        *stated("plate_number"),
        (f"N = 16 * ({inp(retention)} / {inp(width)})^2",),
        shown,
        shown,
    )


def solve_plate_height(intent: ChemistryIntent) -> ChemistryResult:
    length = require(intent, "length", positive=True)
    plates = require(intent, "plates", positive=True)
    value = length / plates
    shown = f"H = {num(value)}"
    return verified(
        "Verified plate height",
        (f"L = {inp(length)}", f"N = {inp(plates)}"),
        "Plate height",
        *stated("plate_height"),
        (f"H = {inp(length)} / {inp(plates)}",),
        shown,
        shown,
    )


def _samples(intent: ChemistryIntent) -> list[float]:
    if len(intent.samples) < 2:
        raise SolveServiceError("at least two measurements are required")
    return list(intent.samples)
