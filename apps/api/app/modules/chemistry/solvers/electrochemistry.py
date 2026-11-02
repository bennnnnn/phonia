# ruff: noqa: RUF001, RUF002
"""Electrochemistry: cell potentials, ΔG from E°, the Nernst equation, and electrolysis."""

from __future__ import annotations

import math
from dataclasses import replace

from app.modules.chemistry.catalog import stated
from app.modules.chemistry.extractors.parsing import seconds_per
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.scene import CellScene
from app.modules.chemistry.solvers.constants import FARADAY, GAS_R_J, STANDARD_REDUCTION
from app.modules.chemistry.solvers.display import (
    const,
    given_row,
    inp,
    molar_mass_working,
    num,
    qty,
    typed_unit,
    used,
    verified,
)
from app.modules.chemistry.solvers.params import require_all
from app.modules.chemistry.solvers.types import ChemistryResult
from app.services.solving import SolveServiceError

# The times a reader converts to seconds, by their size in seconds.
_TIME_SIZES = tuple(
    (shown, float(seconds_per(unit)))
    for shown, unit in (("min", "min"), ("h", "h"), ("day", "days"), ("yr", "years"))
)


def solve_electrochemistry(intent: ChemistryIntent) -> ChemistryResult:
    op = intent.chemistry_op
    if op == "cell_gibbs":
        electrons, potential = require_all(intent, "electrons", "potential")
        if electrons <= 0:
            raise SolveServiceError("electron count must be positive")
        delta_g_j = -electrons * FARADAY * potential
        delta_g_kj = delta_g_j / 1000
        value = f"{num(delta_g_kj)} kJ/mol"
        rows = (
            f"ΔG° = −({inp(electrons)})({const(FARADAY)} C/mol)({qty(potential, 'V')})"
            f" = {num(delta_g_j)} J/mol",
            # A coulomb-volt is a joule; the answer is quoted per kilojoule.
            f"ΔG° = {num(delta_g_j)} J/mol = {value}",
        )
        return verified(
            "Verified electrochemical free energy",
            (f"n = {inp(electrons)} mol e-", f"E°cell = {inp(potential)} V"),
            "ΔG°",
            *stated("cell_gibbs"),
            rows,
            f"ΔG° = {value}",
            value,
        )
    if op == "nernst":
        standard, electrons, quotient, temperature = require_all(
            intent, "standard_potential", "electrons", "quotient", "temperature"
        )
        if electrons <= 0 or quotient <= 0 or temperature <= 0:
            raise SolveServiceError("Nernst inputs must be positive where required")
        potential = standard - (GAS_R_J * temperature / (electrons * FARADAY)) * math.log(quotient)
        value = f"{num(potential)} V"
        substitution = (
            f"E = {qty(standard, 'V')} − [({const(GAS_R_J)} J/(mol·K))({used(temperature)} K) / "
            f"(({inp(electrons)})({const(FARADAY)} C/mol))]ln({inp(quotient)})"
        )
        return verified(
            "Verified cell potential",
            (
                f"E° = {inp(standard)} V",
                f"n = {inp(electrons)}",
                f"Q = {inp(quotient)}",
                given_row("T", temperature, "K", "°C"),
            ),
            "Cell potential, E",
            *stated("nernst"),
            (substitution,),
            f"E = {value}",
            value,
        )
    if op == "electrolysis_mass":
        molar_mass, current, time, electrons = require_all(
            intent, "molar_mass", "current", "time", "electrons"
        )
        if min(molar_mass, current, time, electrons) <= 0:
            raise SolveServiceError("electrolysis inputs must be positive")
        mass = molar_mass * current * time / (electrons * FARADAY)
        value = f"{num(mass)} g"
        substitution = (
            f"m = ({molar_mass_working(molar_mass)} g/mol)({qty(current, 'A')})"
            f"({used(time)} s) / [({inp(electrons)})({const(FARADAY)} C/mol)]"
        )
        return verified(
            "Verified electrolysis mass",
            (
                f"M = {molar_mass_working(molar_mass)} g/mol",
                f"I = {inp(current)} A",
                given_row("t", time, "s", typed_unit(time, _TIME_SIZES)),
                f"n = {inp(electrons)}",
            ),
            "Deposited mass, m",
            *stated("electrolysis_mass"),
            (substitution,),
            f"m = {value}",
            value,
        )
    raise SolveServiceError(f"unsupported electrochemistry operation: {op}")


def solve_cell_potential(intent: ChemistryIntent) -> ChemistryResult:
    cathode = intent.params.get("cathode")
    anode = intent.params.get("anode")
    if cathode is None or anode is None:
        raise SolveServiceError("cell potential needs cathode and anode potentials")
    value = cathode - anode
    shown = f"E°cell = {num(value)} V"
    return verified(
        "Verified cell potential",
        (f"E°cathode = {inp(cathode)} V", f"E°anode = {inp(anode)} V"),
        "Standard cell potential",
        *stated("cell_potential"),
        (f"E°cell = {inp(cathode)} − ({inp(anode)})",),
        shown,
        shown,
    )


def _volts(value: float) -> str:
    """A potential from the reduction table, which lists hundredths of a volt: 1.10 V, not 1.1 V.

    The cell potential is a difference of two table values, so it keeps their two decimals.
    """
    return f"{value:.2f}"


def _ion(symbol: str, electrons: int) -> str:
    return f"{symbol}+" if electrons == 1 else f"{symbol}{electrons}+"


def _coeff(value: int) -> str:
    return "" if value == 1 else f"{value} "


def _half(symbol: str, electrons: int) -> tuple[str, int, str, int, int]:
    """One reduction half-reaction: ``(oxidized, count, reduced, count, electrons)``.

    Hydrogen is ``2 H+ + 2 e- → H2``; every metal is ``Mⁿ⁺ + n e- → M``.
    """
    if symbol == "H":
        return "H+", 2, "H2", 1, electrons
    return _ion(symbol, electrons), 1, symbol, 1, electrons


def solve_galvanic_cell(intent: ChemistryIntent) -> ChemistryResult:
    left = intent.formula or ""
    right = intent.target or ""
    if left not in STANDARD_REDUCTION or right not in STANDARD_REDUCTION or left == right:
        raise SolveServiceError("galvanic cell needs two different metals from the reduction table")
    e_left, n_left = STANDARD_REDUCTION[left]
    e_right, n_right = STANDARD_REDUCTION[right]
    if e_left >= e_right:
        cathode, anode, ec, ea, nc, na = left, right, e_left, e_right, n_left, n_right
    else:
        cathode, anode, ec, ea, nc, na = right, left, e_right, e_left, n_right, n_left
    electrons = math.lcm(nc, na)
    anode_ion, anode_ions, anode_form, anode_forms, _ = _half(anode, na)
    cathode_ion, cathode_ions, cathode_form, cathode_forms, _ = _half(cathode, nc)
    anode_scale = electrons // na
    cathode_scale = electrons // nc
    reaction = (
        f"{_coeff(anode_forms * anode_scale)}{anode_form}"
        f" + {_coeff(cathode_ions * cathode_scale)}{cathode_ion}"
        f" -> {_coeff(anode_ions * anode_scale)}{anode_ion}"
        f" + {_coeff(cathode_forms * cathode_scale)}{cathode_form}"
    )
    potential = ec - ea
    shown = "\n".join(
        (
            f"E°cell = {_volts(potential)} V",
            f"anode: {anode}",
            f"cathode: {cathode}",
            f"n = {electrons} electrons transferred",
            reaction,
            "spontaneous (E°cell > 0)",
        )
    )
    working = [
        f"oxidation at the anode: {anode_form} -> {_coeff(anode_ions)}{anode_ion} + {na} e-",
        f"reduction at the cathode: {_coeff(cathode_ions)}{cathode_ion} + {nc} e- -> "
        f"{cathode_form}",
    ]
    if anode_scale != 1 or cathode_scale != 1:
        working.append(
            f"multiply the anode half by {anode_scale} and the cathode half by "
            f"{cathode_scale} so {electrons} e- cancel"
        )
    working.append(f"E°cell = {_volts(ec)} − ({_volts(ea)})")
    result = verified(
        "Verified galvanic cell",
        (f"{left} E° = {_volts(e_left)} V", f"{right} E° = {_volts(e_right)} V"),
        "Cell potential, electrodes, and net reaction",
        *stated("galvanic_cell"),
        working,
        shown,
        shown,
    )
    return replace(
        result,
        scene=CellScene(
            title="Galvanic cell",
            anode=anode,
            cathode=cathode,
            potential=f"{_volts(potential)} V",
            electrons="anode to cathode",
        ),
    )


def solve_galvanic_nernst(intent: ChemistryIntent) -> ChemistryResult:
    """E = E°cell − (RT/nF) ln Q for a cell of two table metals at stated ion concentrations."""
    left, right = intent.formula or "", intent.target or ""
    if left not in STANDARD_REDUCTION or right not in STANDARD_REDUCTION or left == right:
        raise SolveServiceError("a cell needs two different metals from the reduction table")
    temperature = intent.params.get("temperature")
    if temperature is None or temperature <= 0:
        raise SolveServiceError("temperature must be positive Kelvin")
    (e_left, n_left), (e_right, n_right) = STANDARD_REDUCTION[left], STANDARD_REDUCTION[right]
    if e_left == e_right:
        raise SolveServiceError("two metals with one potential make no cell")
    if e_left > e_right:
        cathode, anode, ec, ea, nc, na = left, right, e_left, e_right, n_left, n_right
    else:
        cathode, anode, ec, ea, nc, na = right, left, e_right, e_left, n_right, n_left
    electrons = math.lcm(nc, na)
    anode_ion, cathode_ion = _ion(anode, na), _ion(cathode, nc)
    anode_c = intent.species.get(anode_ion)
    cathode_c = intent.species.get(cathode_ion)
    if anode_c is None or cathode_c is None or anode_c <= 0 or cathode_c <= 0:
        raise SolveServiceError("both ion concentrations must be stated and positive")
    anode_power, cathode_power = electrons // na, electrons // nc
    quotient = anode_c**anode_power / cathode_c**cathode_power
    standard = ec - ea
    potential = standard - GAS_R_J * temperature / (electrons * FARADAY) * math.log(quotient)

    def power(label: str, exponent: int) -> str:
        return f"[{label}]" if exponent == 1 else f"[{label}]^{exponent}"

    def raised(value: float, exponent: int) -> str:
        return inp(value) if exponent == 1 else f"({inp(value)})^{exponent}"

    shown = f"E = {_volts(potential)} V"
    return verified(
        "Verified cell potential",
        (
            f"anode {anode}: E° = {_volts(ea)} V",
            f"cathode {cathode}: E° = {_volts(ec)} V",
            f"[{anode_ion}] = {inp(anode_c)} mol/L",
            f"[{cathode_ion}] = {inp(cathode_c)} mol/L",
            given_row("T", temperature, "K", "°C"),
        ),
        "Cell potential, E",
        *stated("galvanic_nernst"),
        (
            f"E°cell = {_volts(ec)} − ({_volts(ea)}) = {_volts(standard)} V",
            f"n = {electrons} electrons transferred",
            f"Q = {power(anode_ion, anode_power)} / {power(cathode_ion, cathode_power)}"
            f" = {raised(anode_c, anode_power)} / {raised(cathode_c, cathode_power)}"
            f" = {num(quotient)}",
            f"E = {_volts(standard)} V − [({const(GAS_R_J)} J/(mol·K))({used(temperature)} K) / "
            f"(({electrons})({const(FARADAY)} C/mol))]ln({num(quotient)})",
        ),
        shown,
        shown,
    )
