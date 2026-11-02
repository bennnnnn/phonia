# ruff: noqa: RUF001
"""Integrated rate laws: concentration and half-life for zero, first and second order."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import GAS_R_J
from app.modules.chemistry.solvers.display import const, inp, num, verified
from app.modules.chemistry.solvers.params import require_all
from app.modules.chemistry.solvers.types import ChemistryResult, format_number
from app.services.solving import SolveServiceError

# A rate per day or per year, not per "days".
_PER_TIME = {"days": "day", "years": "yr"}


def _first_order_rate_constant(intent: ChemistryIntent) -> ChemistryResult:
    """k = ln(2) / t₁/₂, per the time unit the half-life is written in."""
    (half_life,) = require_all(intent, "half_life")
    if half_life <= 0:
        raise SolveServiceError("half-life must be positive")
    time_unit = intent.units.get("half_life_time", "s")
    per = _PER_TIME.get(time_unit, time_unit)
    value = f"{num(math.log(2) / half_life)} {per}⁻¹"
    return verified(
        "Verified first-order rate constant",
        (f"t₁/₂ = {inp(half_life)} {time_unit}",),
        "Rate constant, k",
        *stated("first_order_half_life"),
        (f"k = ln(2) / t₁/₂ = {num(math.log(2))} / {inp(half_life)}",),
        f"k = {value}",
        value,
    )


def solve_kinetics(intent: ChemistryIntent) -> ChemistryResult:
    op = intent.chemistry_op
    if op == "first_order_half_life" and "half_life" in intent.params:
        return _first_order_rate_constant(intent)
    if op == "first_order_half_life":
        (rate_constant,) = require_all(intent, "rate_constant")
        if rate_constant <= 0:
            raise SolveServiceError("rate constant must be positive")
        half_life = math.log(2) / rate_constant
        time_unit = intent.units.get("rate_constant_time", "s")
        value = f"{num(half_life)} {time_unit}"
        return verified(
            "Verified first-order half-life",
            (f"k = {inp(rate_constant)} {time_unit}⁻¹",),
            "Half-life, t₁/₂",
            *stated("first_order_half_life"),
            (f"t₁/₂ = {num(math.log(2))} / {inp(rate_constant)}",),
            f"t₁/₂ = {value}",
            value,
        )
    if op == "first_order_time":
        rate_constant, remaining = require_all(intent, "rate_constant", "remaining")
        if rate_constant <= 0 or not 0 < remaining < 1:
            raise SolveServiceError("a first-order time needs k > 0 and a fraction left below 1")
        time_unit = intent.units.get("rate_constant_time", "s")
        elapsed = math.log(1 / remaining) / rate_constant
        value = f"{num(elapsed)} {time_unit}"
        percent = format_number(remaining * 100)
        return verified(
            "Verified first-order time",
            (
                f"k = {inp(rate_constant)} {time_unit}⁻¹",
                f"[A]ₜ / [A]₀ = {percent}% = {inp(remaining)}",
            ),
            "Time, t",
            *stated("first_order_time"),
            (f"t = ln(1 / {inp(remaining)}) / ({inp(rate_constant)} {time_unit}⁻¹)",),
            f"t = {value}",
            value,
        )
    if op == "first_order_concentration":
        initial, rate_constant, time = require_all(intent, "initial", "rate_constant", "time")
        if initial < 0 or rate_constant < 0 or time < 0:
            raise SolveServiceError("concentration, rate constant, and time cannot be negative")
        final = initial * math.exp(-rate_constant * time)
        time_unit = intent.units.get("time", "s")
        value = f"{num(final)} mol/L"
        substitution = f"[A]ₜ = ({inp(initial)})e^(−({inp(rate_constant)})({inp(time)}))"
        return verified(
            "Verified first-order concentration",
            (
                f"[A]₀ = {inp(initial)} mol/L",
                f"k = {inp(rate_constant)} {time_unit}⁻¹",
                f"t = {inp(time)} {time_unit}",
            ),
            "Concentration at time t, [A]ₜ",
            *stated("first_order_concentration"),
            (substitution,),
            f"[A]ₜ = {value}",
            value,
        )
    if op == "arrhenius":
        pre_exponential, activation_energy, temperature = require_all(
            intent, "pre_exponential", "activation_energy", "temperature"
        )
        if pre_exponential <= 0 or activation_energy < 0 or temperature <= 0:
            raise SolveServiceError("Arrhenius inputs must be physically valid")
        rate_constant = pre_exponential * math.exp(-activation_energy / (GAS_R_J * temperature))
        # k has the units of A. A question that gives A without a unit gets a bare number.
        rate_unit = intent.units.get("frequency_factor_time")
        suffix = f" {rate_unit}⁻¹" if rate_unit else ""
        value = f"{num(rate_constant)}{suffix}"
        substitution = (
            f"k = ({inp(pre_exponential)})e^[−{inp(activation_energy)} / "
            f"(({const(GAS_R_J)})({inp(temperature)}))]"
        )
        return verified(
            "Verified Arrhenius rate constant",
            (
                f"A = {inp(pre_exponential)}{suffix}",
                f"Eₐ = {inp(activation_energy / 1000)} kJ/mol ({inp(activation_energy)} J/mol)",
                f"T = {inp(temperature)} K",
            ),
            "Rate constant, k",
            *stated("arrhenius"),
            (substitution,),
            f"k = {value}",
            value,
        )
    raise SolveServiceError(f"unsupported kinetics operation: {op}")


_NEGATIVE = "kinetics inputs are missing or negative"


# The half-life question gives k without a time unit, so the answer is in that unit.
_TIME_OF_K = " (in the time unit of k)"


def solve_zero_order(intent: ChemistryIntent) -> ChemistryResult:
    initial, rate, time = require_all(
        intent, "initial", "rate_constant", "time", non_negative=True, message=_NEGATIVE
    )
    final = initial - rate * time
    if final < 0:
        raise SolveServiceError("zero-order concentration would be negative")
    shown = f"[A]ₜ = {num(final)} mol/L"
    return verified(
        "Verified zero-order concentration",
        (f"[A]₀ = {inp(initial)} mol/L", f"k = {inp(rate)}", f"t = {inp(time)}"),
        "[A]ₜ",
        *stated("zero_order"),
        (f"[A]ₜ = {inp(initial)} − ({inp(rate)})({inp(time)})",),
        shown,
        shown,
    )


def solve_second_order(intent: ChemistryIntent) -> ChemistryResult:
    initial, rate, time = require_all(
        intent, "initial", "rate_constant", "time", non_negative=True, message=_NEGATIVE
    )
    if initial <= 0:
        raise SolveServiceError("initial concentration must be positive")
    reciprocal = 1 / initial + rate * time
    final = 1 / reciprocal
    shown = f"[A]ₜ = {num(final)} mol/L"
    return verified(
        "Verified second-order concentration",
        (f"[A]₀ = {inp(initial)} mol/L", f"k = {inp(rate)}", f"t = {inp(time)}"),
        "[A]ₜ",
        *stated("second_order"),
        (
            f"1/[A]ₜ = 1/({inp(initial)}) + ({inp(rate)})({inp(time)}) = {num(reciprocal)}",
            f"[A]ₜ = 1 / {num(reciprocal)}",
        ),
        shown,
        shown,
    )


def solve_zero_half_life(intent: ChemistryIntent) -> ChemistryResult:
    initial, rate = require_all(
        intent,
        "initial",
        "rate_constant",
        positive=True,
        message="half-life inputs must be positive",
    )
    shown = f"t₁/₂ = {num(initial / (2 * rate))}{_TIME_OF_K}"
    return verified(
        "Verified zero-order half-life",
        (f"[A]₀ = {inp(initial)} mol/L", f"k = {inp(rate)}"),
        "Half-life",
        *stated("zero_order_half_life"),
        (f"t₁/₂ = {inp(initial)} / (2({inp(rate)}))",),
        shown,
        shown,
    )


def solve_second_half_life(intent: ChemistryIntent) -> ChemistryResult:
    initial, rate = require_all(
        intent,
        "initial",
        "rate_constant",
        positive=True,
        message="half-life inputs must be positive",
    )
    shown = f"t₁/₂ = {num(1 / (rate * initial))}{_TIME_OF_K}"
    return verified(
        "Verified second-order half-life",
        (f"[A]₀ = {inp(initial)} mol/L", f"k = {inp(rate)}"),
        "Half-life",
        *stated("second_order_half_life"),
        (f"t₁/₂ = 1 / (({inp(rate)})({inp(initial)}))",),
        shown,
        shown,
    )
