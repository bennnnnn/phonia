# ruff: noqa: RUF001
"""Gases: Dalton's law, partial pressures, a gas over water, Graham's law, Henry's law."""

from __future__ import annotations

import math

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.quantity import convert
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import water_vapor_mmhg
from app.modules.chemistry.solvers.display import inp, num, verified
from app.modules.chemistry.solvers.params import require
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _partial(name: str) -> str:
    """P(N2) for a named gas; P₁, P₂ for gases a question only numbers by their order."""
    return f"P{name.translate(_SUBSCRIPT)}" if name.isdigit() else f"P({name})"


def solve_dalton(intent: ChemistryIntent) -> ChemistryResult:
    if len(intent.species) < 2 or any(value < 0 for value in intent.species.values()):
        raise SolveServiceError("Dalton's law needs partial pressures")
    total = sum(intent.species.values())
    unit = intent.units.get("pressure", "atm")
    shown = f"Ptotal = {num(total)} {unit}"
    terms = " + ".join(inp(value) for value in intent.species.values())
    return verified(
        "Verified Dalton's law",
        tuple(f"{_partial(name)} = {inp(value)} {unit}" for name, value in intent.species.items()),
        "Total pressure",
        *stated("dalton"),
        (f"Ptotal = {terms}",),
        shown,
        shown,
    )


def _partial_from_moles(intent: ChemistryIntent) -> ChemistryResult:
    """Pi = (ni / Σn) Ptotal, each gas of the mixture stated in moles."""
    target = intent.target
    total = intent.params.get("total_pressure")
    amounts = intent.species
    if (
        target not in amounts
        or len(amounts) < 2
        or total is None
        or total < 0
        or any(value < 0 for value in amounts.values())
        or sum(amounts.values()) <= 0
    ):
        raise SolveServiceError("a partial pressure needs every gas's moles and the total pressure")
    unit = intent.units.get("pressure", "atm")
    fraction = amounts[target] / sum(amounts.values())
    shown = f"P({target}) = {num(fraction * total)} {unit}"
    every = " + ".join(inp(value) for value in amounts.values())
    return verified(
        "Verified partial pressure",
        (
            *(f"n({gas}) = {inp(value)} mol" for gas, value in amounts.items()),
            f"Ptotal = {inp(total)} {unit}",
        ),
        f"Partial pressure of {target}",
        *stated("partial_pressure"),
        (
            f"X({target}) = {inp(amounts[target])} / ({every}) = {num(fraction)}",
            f"P({target}) = ({num(fraction)})({inp(total)} {unit})",
        ),
        shown,
        shown,
    )


def solve_partial_pressure(intent: ChemistryIntent) -> ChemistryResult:
    if intent.species:
        return _partial_from_moles(intent)
    fraction = intent.params.get("mole_fraction")
    total = intent.params.get("total_pressure")
    if fraction is None or total is None or not 0 <= fraction <= 1 or total < 0:
        raise SolveServiceError("partial pressure needs a mole fraction and a total pressure")
    unit = intent.units.get("pressure", "atm")
    shown = f"Pi = {num(fraction * total)} {unit}"
    return verified(
        "Verified partial pressure",
        (f"Xi = {inp(fraction)}", f"Ptotal = {inp(total)} {unit}"),
        "Partial pressure",
        *stated("partial_pressure"),
        (f"Pi = ({inp(fraction)})({inp(total)})",),
        shown,
        shown,
    )


def solve_gas_over_water(intent: ChemistryIntent) -> ChemistryResult:
    total = intent.params.get("total_pressure")
    temperature = intent.params.get("temperature_c")
    if total is None or temperature is None or total <= 0:
        raise SolveServiceError("gas over water needs total pressure and temperature")
    vapor = water_vapor_mmhg(temperature)
    if vapor is None:
        raise SolveServiceError("water vapor pressure is only tabulated from 0 to 100 °C")
    unit = intent.units.get("pressure", "mmHg")
    try:
        vapor_same = convert(vapor, "mmHg", unit)
    except (ValueError, TypeError) as exc:
        raise SolveServiceError(f"unsupported pressure unit {unit}") from exc
    dry = total - vapor_same
    if dry <= 0:
        raise SolveServiceError("the dry-gas pressure is not positive")
    shown = f"Pdry = {num(dry)} {unit}"
    return verified(
        "Verified gas collected over water",
        (f"Ptotal = {inp(total)} {unit}", f"T = {inp(temperature)} °C"),
        "Dry-gas pressure",
        *stated("gas_over_water"),
        (
            f"Pwater = {num(vapor_same)} {unit} at {inp(temperature)} °C",
            f"Pdry = {inp(total)} − {num(vapor_same)}",
        ),
        shown,
        shown,
    )


_GRAHAM = ("rate1", "rate2", "molar1", "molar2")


_GRAHAM_MESSAGE = "Graham's law needs exactly three positive rates or molar masses"


def solve_graham(intent: ChemistryIntent) -> ChemistryResult:
    present = [key for key in _GRAHAM if intent.params.get(key) is not None]
    if len(present) != 3:
        raise SolveServiceError(_GRAHAM_MESSAGE)
    values = {key: require(intent, key, positive=True, message=_GRAHAM_MESSAGE) for key in present}
    missing = next(key for key in _GRAHAM if key not in values)
    rate1, rate2, molar1, molar2, shown, working = _graham_unknown(missing, values)
    return verified(
        "Verified Graham's law",
        (
            f"rate1 = {inp(rate1)}",
            f"rate2 = {inp(rate2)}",
            f"M1 = {inp(molar1)}",
            f"M2 = {inp(molar2)}",
        ),
        "Graham's law",
        *stated("graham"),
        (working,),
        shown,
        shown,
    )


def _graham_unknown(
    missing: str, values: dict[str, float]
) -> tuple[float, float, float, float, str, str]:
    if missing == "rate2":
        rate2 = values["rate1"] * math.sqrt(values["molar1"] / values["molar2"])
        working = (
            f"rate2 = {inp(values['rate1'])} × √({inp(values['molar1'])} / "
            f"{inp(values['molar2'])}) = {num(rate2)}"
        )
        return (
            values["rate1"],
            rate2,
            values["molar1"],
            values["molar2"],
            f"rate2 = {num(rate2)}",
            working,
        )
    if missing == "rate1":
        rate1 = values["rate2"] * math.sqrt(values["molar2"] / values["molar1"])
        working = (
            f"rate1 = {inp(values['rate2'])} × √({inp(values['molar2'])} / "
            f"{inp(values['molar1'])}) = {num(rate1)}"
        )
        return (
            rate1,
            values["rate2"],
            values["molar1"],
            values["molar2"],
            f"rate1 = {num(rate1)}",
            working,
        )
    if missing == "molar1":
        molar1 = values["molar2"] * (values["rate2"] / values["rate1"]) ** 2
        working = (
            f"M1 = {inp(values['molar2'])} × ({inp(values['rate2'])} / "
            f"{inp(values['rate1'])})^2 = {num(molar1)}"
        )
        return (
            values["rate1"],
            values["rate2"],
            molar1,
            values["molar2"],
            f"M1 = {num(molar1)}",
            working,
        )
    molar2 = values["molar1"] * (values["rate1"] / values["rate2"]) ** 2
    working = (
        f"M2 = {inp(values['molar1'])} × ({inp(values['rate1'])} / "
        f"{inp(values['rate2'])})^2 = {num(molar2)}"
    )
    return (
        values["rate1"],
        values["rate2"],
        values["molar1"],
        molar2,
        f"M2 = {num(molar2)}",
        working,
    )


def solve_henry(intent: ChemistryIntent) -> ChemistryResult:
    message = "Henry's law needs exactly two of concentration, kH, and pressure"
    keys = ("concentration", "henry_constant", "pressure")
    present = [key for key in keys if intent.params.get(key) is not None]
    if len(present) != 2:
        raise SolveServiceError(message)
    values = {key: require(intent, key, positive=True, message=message) for key in present}
    missing = next(key for key in keys if key not in values)
    concentration, constant, pressure, shown, working = _henry_unknown(missing, values)
    return verified(
        "Verified Henry's law",
        (
            f"C = {inp(concentration)}",
            f"kH = {inp(constant)}",
            f"P = {inp(pressure)}",
        ),
        "Henry's law",
        *stated("henry"),
        (working,),
        shown,
        shown,
    )


def _henry_unknown(missing: str, values: dict[str, float]) -> tuple[float, float, float, str, str]:
    if missing == "concentration":
        concentration = values["henry_constant"] * values["pressure"]
        working = (
            f"C = {inp(values['henry_constant'])} × {inp(values['pressure'])}"
            f" = {num(concentration)}"
        )
        return (
            concentration,
            values["henry_constant"],
            values["pressure"],
            f"C = {num(concentration)}",
            working,
        )
    if missing == "pressure":
        pressure = values["concentration"] / values["henry_constant"]
        working = (
            f"P = {inp(values['concentration'])} / {inp(values['henry_constant'])}"
            f" = {num(pressure)}"
        )
        return (
            values["concentration"],
            values["henry_constant"],
            pressure,
            f"P = {num(pressure)}",
            working,
        )
    constant = values["concentration"] / values["pressure"]
    working = f"kH = {inp(values['concentration'])} / {inp(values['pressure'])} = {num(constant)}"
    return values["concentration"], constant, values["pressure"], f"kH = {num(constant)}", working
