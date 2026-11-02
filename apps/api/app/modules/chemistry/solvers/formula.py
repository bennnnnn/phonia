"""The one solver for every law in ``formula_laws``: evaluate its line, print its rows."""

from __future__ import annotations

import math

from pint.errors import PintError

import app.modules.chemistry.sig_figs as sig_figs
from app.modules.chemistry.formula_laws import FORMULA_LAWS
from app.modules.chemistry.given_units import CHEMISTRY_UNITS
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import (
    AVOGADRO,
    BOLTZMANN,
    FARADAY,
    GAS_R,
    GAS_R_J,
    PLANCK,
)
from app.modules.chemistry.solvers.display import (
    converted,
    inp,
    molar_mass_working,
    num,
    p_value,
    verified,
    with_unit,
)
from app.modules.chemistry.solvers.types import ChemistryResult, format_constant
from app.services.law_binding.expression import Notation, evaluate
from app.services.solving import SolveServiceError

# Constants a formula law may name: R in L·atm/(mol·K), Faraday's and Avogadro's constants.
CHEMISTRY_NOTATION = Notation(
    constants={
        "R_atm": (GAS_R, "R"),
        "R_J": (GAS_R_J, "R"),
        "F": (FARADAY, "F"),
        "N_A": (AVOGADRO, "Nₐ"),
        "k_B": (BOLTZMANN, "k_B"),
        "h": (PLANCK, "h"),
    },
    number=str,
)
# The unit a substitution row prints after a constant it names: "{R_J}" is "8.3145 J/(mol·K)".
_CONSTANT_UNITS = {
    "R_atm": "L·atm/(mol·K)",
    "R_J": "J/(mol·K)",
    "F": "C/mol",
    "N_A": "mol⁻¹",
    "k_B": "J/K",
    "h": "J·s",
}


# Inputs the element table gives when the question does not state them.
_TABLE_INPUTS = ("molar_mass", "atomic_mass")


def _is_logarithm(symbol: str) -> bool:
    """True for pH, pOH, pKa and pKb, whose precision is decimal places."""
    return len(symbol) > 1 and symbol[0] == "p" and symbol[1].isupper()


class _Given(str):
    """A given as a substitution shows it, "0.500 L"; ``.value`` is the bare number."""

    value: str

    def __new__(cls, value: str, unit: str) -> _Given:
        given = super().__new__(cls, with_unit(value, unit))
        given.value = value
        return given


# Each constant as a substitution row names it, the value the arithmetic uses to five figures.
_CONSTANTS_SHOWN = {
    name: _Given(format_constant(value), _CONSTANT_UNITS[name])
    for name, (value, _symbol) in CHEMISTRY_NOTATION.constants.items()
}


def _shown(name: str, value: float) -> str:
    """A given as typed; a molar mass from the table to the table's precision (18.015).

    An atom count comes from the formula, not the question, so it is a whole number even
    when the question typed the same value ("2.0 mol of CO2" holds 2 O, not 2.0).
    """
    if name == "count" and value.is_integer():
        return str(int(value))
    written = sig_figs.current()
    typed = written is not None and repr(value) in written.written
    if not typed and name.startswith(_TABLE_INPUTS):
        return molar_mass_working(value)
    return inp(value)


def convert_quantity(value: float, unit: str, target: str) -> float:
    """A value from one chemistry unit spelling to another, through Pint (K to °C included)."""
    from app.services.units import get_unit_registry

    source, wanted = CHEMISTRY_UNITS.expression(unit), CHEMISTRY_UNITS.expression(target)
    if source is None or wanted is None:
        raise ValueError(f"no conversion from {unit} to {target}")
    try:
        quantity = get_unit_registry().Quantity(value, source).to(wanted)
    except PintError as exc:
        # A display conversion Pint refuses must not abort a solve whose value is
        # already in the law's unit. "m" in this table is molal, not meter.
        raise ValueError(f"no conversion from {unit} to {target}") from exc
    return float(quantity.magnitude)


def _as_typed(value: float, unit: str, typed_unit: str | None) -> tuple[str, str] | None:
    """The given as the question wrote it (500 mL) and as the law reads it (0.500 L).

    None when no conversion happened, or the law's unit is only another spelling of the typed
    one (0.200 M is 0.200 mol/L). The converted value keeps the figures it was typed with.
    """
    if not typed_unit or not unit or typed_unit == unit:
        return None
    try:
        typed = convert_quantity(value, unit, typed_unit)
    except ValueError:
        return None
    if math.isclose(typed, value, rel_tol=1e-9):
        return None
    written = sig_figs.current()
    literal = None if written is None else written.converted.get(repr(value))
    if literal is None:
        # Undo the round trip's float noise (0.5 L is 500.00000000000006 mL) before echoing.
        return with_unit(inp(float(f"{typed:.12g}")), typed_unit), inp(value)
    return with_unit(sig_figs.as_written(literal), typed_unit), converted(value, literal)


def _binary_fractions(fraction_a: float, fraction_b: float) -> None:
    """An ideal binary solution's mole fractions lie on [0, 1] and sum to 1."""
    if not 0 <= fraction_a <= 1 or not 0 <= fraction_b <= 1:
        raise SolveServiceError("each mole fraction must be between 0 and 1")
    if not math.isclose(fraction_a + fraction_b, 1, abs_tol=1e-6):
        raise SolveServiceError("the two mole fractions must sum to 1")


def solve_formula_law(intent: ChemistryIntent) -> ChemistryResult:
    law = FORMULA_LAWS.get(intent.chemistry_op)
    if law is None:
        raise SolveServiceError(f"{intent.chemistry_op} is not a formula law")
    values: dict[str, float] = {}
    for name, _label, _unit in law.given:
        value = intent.params.get(name)
        if value is None:
            raise SolveServiceError(f"{law.law_name} needs {name}")
        if value < 0 and name not in law.signed:
            raise SolveServiceError(f"{name} must be positive")
        if value == 0 and name not in law.signed and name not in law.non_negative:
            raise SolveServiceError(f"{name} must be positive")
        values[name] = value
    for smaller, ceiling in law.not_above:
        if values[smaller] > values[ceiling]:
            raise SolveServiceError("solute mass must be between zero and solution mass")
    if law.op == "binary_vapor_pressure":
        _binary_fractions(values["mole_fraction_a"], values["mole_fraction_b"])
    if law.op == "absorbance_transmittance" and not 0 < values["transmittance"] <= 1:
        raise SolveServiceError("transmittance must be between 0 and 1")
    if law.op == "absorbance_percent_transmittance" and not (
        0 < values["percent_transmittance"] <= 100
    ):
        raise SolveServiceError("percent transmittance must be between 0 and 100")
    if law.op == "solute_mass_from_percent" and values["percent"] > 100:
        raise SolveServiceError("a mass percent cannot exceed 100")
    if law.op == "van_der_waals_pressure" and values["volume"] <= values["n"] * values["b"]:
        raise SolveServiceError("volume must be greater than n b")
    if law.op == "carothers" and values["extent"] >= 1:
        raise SolveServiceError("the extent of reaction must be below 1")
    if law.op in {"lever_alpha", "lever_beta"} and math.isclose(
        values["alpha_composition"], values["beta_composition"]
    ):
        raise SolveServiceError("the two phase compositions must differ")
    try:
        result = evaluate(law.expression, values, CHEMISTRY_NOTATION)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise SolveServiceError(f"{law.law_name} has no real answer here") from exc
    if law.op == "neutron_count" and result < 0:
        raise SolveServiceError("the mass number is smaller than the atomic number")
    if law.op in {"lever_alpha", "lever_beta"} and not 0 <= result <= 1:
        raise SolveServiceError("those compositions are not a tie line")
    # pH, pOH and pK are logarithms: 4.20 + log10(0.25) is 3.60, not 3.6.
    number = p_value(result) if _is_logarithm(law.result) else num(result)
    shown = with_unit(number, law.unit)
    names = {"formula": intent.formula or "", "target": intent.target or ""}
    # "How many mg ...": the law's grams, then the unit the question asked in.
    asked_unit = intent.units.get("answer")
    in_asked: str | None = None
    if asked_unit and asked_unit != law.unit and law.unit:
        try:
            converted_value = convert_quantity(result, law.unit, asked_unit)
        except ValueError as exc:
            raise SolveServiceError(f"cannot answer {law.law_name} in {asked_unit}") from exc
        in_asked = with_unit(num(converted_value), asked_unit)
    units = {name: unit for name, _label, unit in law.given}
    typed = {name: _Given(_shown(name, value), units[name]) for name, value in values.items()}
    given = []
    for name, label, _unit in law.given:
        row = f"{label.format(**names)} = "
        converted = _as_typed(values[name], units[name], intent.units.get(name))
        if converted is not None:
            typed[name] = _Given(converted[1], units[name])
            row = f"{row}{converted[0]} = "
        given.append(f"{row}{typed[name]}")
    rows = [row.format(**names, **_CONSTANTS_SHOWN, **typed) for row in law.substitution]
    if in_asked is not None:
        rows.append(f"{law.result.format(**names)} = {shown} = {in_asked}")
        shown = in_asked
    return verified(
        f"Verified {law.law_name[0].lower()}{law.law_name[1:]}",
        tuple(given),
        law.find,
        law.law_name,
        law.formula,
        tuple(rows),
        f"{law.result.format(**names)} = {shown}",
        shown,
    )
