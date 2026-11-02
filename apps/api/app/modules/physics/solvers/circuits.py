"""Circuit solvers: Ohm's law, power, charge, energy, resistor networks and capacitors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.modules.physics.constants import EPSILON_0
from app.modules.physics.display import latex_given, latex_unit
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.circuit_scenes import circuit_scene
from app.modules.physics.solvers.resistor_network import RESISTOR_KEY_RE
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_circuit(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or "current"
    solver = _OPERATIONS.get(op)
    if solver is None:
        raise SolveServiceError(f"unsupported circuit op: {op}")
    result = solver(intent, p)
    if result.quantities and not result.simulation_specs:
        scene = circuit_scene(op, p, result.quantities[0].value)
        if scene:
            result = replace(result, simulation_specs=scene)
    return result


def _parallel_plate_capacitance(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["area"] <= 0 or p["d"] <= 0:
        raise SolveServiceError("parallel-plate capacitance needs positive area and spacing")
    value = EPSILON_0 * p["area"] / p["d"]
    return PhysicsResult(
        answer=(
            rf"C = \frac{{\epsilon_0 A}}{{d}} = "
            rf"\frac{{{EPSILON_0:.5g} \cdot {p['area']:g}}}{{{p['d']:g}}} "
            rf"\approx {value:.4g} \text{{ F}}"
        ),
        formulas=(r"C = \frac{\epsilon_0 A}{d}",),
        substitutions=(rf"C = \frac{{{EPSILON_0:.5g} \cdot {p['area']:g}}}{{{p['d']:g}}}",),
        quantities=(QuantityResult("", value, "F"),),
    )


def _capacitor_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["capacitance"] < 0:
        raise SolveServiceError("capacitance cannot be negative")
    value = 0.5 * p["capacitance"] * p["V"] ** 2
    return PhysicsResult(
        answer=(
            rf"U = \frac{{1}}{{2}}CV^2 = \frac{{1}}{{2}} \cdot "
            rf"{p['capacitance']:g} \cdot {p['V']:g}^2 "
            rf"\approx {value:.4g} \text{{ J}}"
        ),
        formulas=(r"U = \frac{1}{2}CV^2",),
        substitutions=(rf"U = \frac{{1}}{{2}} \cdot {p['capacitance']:g} \cdot {p['V']:g}^2",),
        quantities=(QuantityResult("", value, "J"),),
    )


def _rc_time_constant(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["R"] < 0 or p["capacitance"] < 0:
        raise SolveServiceError("RC time constant needs nonnegative R and C")
    value = p["R"] * p["capacitance"]
    return PhysicsResult(
        answer=(
            rf"\tau = RC = {p['R']:g} \cdot {p['capacitance']:g} "
            rf"\approx {value:.4g} \text{{ s}}"
        ),
        formulas=(r"\tau = RC",),
        substitutions=(rf"\tau = {p['R']:g} \cdot {p['capacitance']:g}",),
        quantities=(QuantityResult("", value, "s"),),
    )


def _network(intent: PhysicsIntent, p: dict[str, float]) -> tuple[bool, list[float], float]:
    """Whether the network is in series, its resistances in order, and its total."""
    # Every R the extractor found, not the first two. Reading three and
    # using two is how "2, 3 and 5 ohms in series" answered 5 ohms.
    resistances = [p[key] for key in sorted(p) if RESISTOR_KEY_RE.fullmatch(key)]
    if len(resistances) < 2:
        raise SolveServiceError("a resistor network needs at least two resistances")
    if any(r <= 0 for r in resistances):
        raise SolveServiceError("resistances must be positive")
    series = (intent.physics_op or "").startswith("series")
    total = sum(resistances) if series else 1 / sum(1 / r for r in resistances)
    return series, resistances, total


def _network_law(series: bool, resistances: list[float]) -> tuple[str, str]:
    """The network's law and its substitution: R_s = 2 + 4, 1/R_p = 1/3 + 1/3."""
    if series:
        return r"R_s = \sum R_i", rf"R_s = {' + '.join(f'{r:g}' for r in resistances)}"
    symbols = " + ".join(rf"\frac{{1}}{{R_{index}}}" for index in range(1, len(resistances) + 1))
    reciprocals = " + ".join(rf"\frac{{1}}{{{r:g}}}" for r in resistances)
    return rf"\frac{{1}}{{R_p}} = {symbols}", rf"\frac{{1}}{{R_p}} = {reciprocals}"


def _combined_resistance(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    series, resistances, total = _network(intent, p)
    formula, substitution = _network_law(series, resistances)
    if series:
        terms = " + ".join(f"{r:g}" for r in resistances)
        answer = rf"R = \sum R_i = {terms} \approx {total:.2f} \,\Omega"
    else:
        reciprocals = " + ".join(rf"\frac{{1}}{{{r:g}}}" for r in resistances)
        answer = (
            rf"\frac{{1}}{{R}} = {reciprocals} \Rightarrow R "
            rf"\approx {total:.2f} \,\Omega"
        )
    return PhysicsResult(
        answer=answer,
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(QuantityResult("", total, "ohm"),),
    )


def _reciprocal_rows(series: bool, total: float) -> tuple[str, ...]:
    """A parallel total's last steps, as the parallel-resistance working shows them:
    1/R_p = 0.833333, then R_p = 1/0.833333."""
    if series:
        return ()
    reciprocal = latex_given(1 / total)
    return (rf"\frac{{1}}{{R_p}} = {reciprocal}", rf"R_p = \frac{{1}}{{{reciprocal}}}")


def _network_current(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    """The network's equivalent resistance, then Ohm's law across it."""
    series, resistances, total = _network(intent, p)
    formula, substitution = _network_law(series, resistances)
    symbol = "R_s" if series else "R_p"
    shown = latex_given(total)
    current = p["V"] / total
    return PhysicsResult(
        answer=(
            rf"I = \frac{{V}}{{{symbol}}} = \frac{{{p['V']:g}}}{{{shown}}} "
            rf"\approx {current:.2f} \text{{ A}}"
        ),
        formulas=(formula, rf"I = \frac{{V}}{{{symbol}}}"),
        substitutions=(
            substitution,
            *_reciprocal_rows(series, total),
            rf"{symbol} = {shown}{latex_unit('ohm')}",
            rf"I = \frac{{{p['V']:g}}}{{{shown}}}",
        ),
        quantities=(QuantityResult("", current, "A"),),
    )


def _series_parallel(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    """R₁ in series with a parallel group: the group's total, the whole, then, when
    asked, the current a supply drives through it."""
    resistances = [p[key] for key in sorted(p) if RESISTOR_KEY_RE.fullmatch(key)]
    if len(resistances) < 3:
        raise SolveServiceError("a series-parallel network needs a resistor and a group of two")
    if any(r <= 0 for r in resistances):
        raise SolveServiceError("resistances must be positive")
    single, group = resistances[0], resistances[1:]
    parallel = 1 / sum(1 / r for r in group)
    total = single + parallel
    symbols = " + ".join(rf"\frac{{1}}{{R_{index}}}" for index in range(2, len(resistances) + 1))
    reciprocals = " + ".join(rf"\frac{{1}}{{{r:g}}}" for r in group)
    shown = latex_given(parallel)
    formulas = [rf"\frac{{1}}{{R_p}} = {symbols}", r"R = R_1 + R_p"]
    rows = [
        rf"\frac{{1}}{{R_p}} = {reciprocals}",
        *_reciprocal_rows(False, parallel),
        rf"R_p = {shown}{latex_unit('ohm')}",
        rf"R = {single:g} + {shown}",
    ]
    if intent.physics_op != "series_parallel_current":
        return PhysicsResult(
            answer=rf"R = R_1 + R_p = {single:g} + {shown} \approx {total:.2f} \,\Omega",
            formulas=tuple(formulas),
            substitutions=tuple(rows),
            quantities=(QuantityResult("", total, "ohm"),),
        )
    whole = latex_given(total)
    current = p["V"] / total
    return PhysicsResult(
        answer=(
            rf"I = \frac{{V}}{{R}} = \frac{{{p['V']:g}}}{{{whole}}} "
            rf"\approx {current:.2f} \text{{ A}}"
        ),
        formulas=(*formulas, r"I = \frac{V}{R}"),
        substitutions=(
            *rows,
            rf"R = {whole}{latex_unit('ohm')}",
            rf"I = \frac{{{p['V']:g}}}{{{whole}}}",
        ),
        quantities=(QuantityResult("", current, "A"),),
    )


def _charge(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    q_val = p["I"] * p["t"]
    return PhysicsResult(
        answer=(rf"Q = I t = {p['I']:g} \cdot {p['t']:g} \approx {q_val:.2f} \text{{ C}}"),
        formulas=(r"Q = I t",),
        substitutions=(rf"Q = {p['I']:g} \cdot {p['t']:g}",),
        quantities=(QuantityResult("", q_val, "C"),),
    )


def _electrical_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    e_val = p["power"] * p["t"]
    kwh = e_val / 3.6e6
    return PhysicsResult(
        answer=(
            rf"E = P t = {p['power']:g} \cdot {p['t']:g} \approx "
            rf"{e_val:.2f} \text{{ J}} \; ({kwh:.2f} \text{{ kWh}})"
        ),
        formulas=(r"E = P t",),
        substitutions=(rf"E = {p['power']:g} \cdot {p['t']:g}",),
        quantities=(QuantityResult("", e_val, "J"),),
    )


def _capacitance(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["V"] == 0:
        raise SolveServiceError("capacitance needs a nonzero voltage")
    c_val = p["Q"] / p["V"]
    return PhysicsResult(
        answer=(
            rf"C = \frac{{Q}}{{V}} = \frac{{{p['Q']:g}}}{{{p['V']:g}}} "
            rf"\approx {c_val:.2f} \text{{ F}}"
        ),
        formulas=(r"C = \frac{Q}{V}",),
        substitutions=(rf"C = \frac{{{p['Q']:g}}}{{{p['V']:g}}}",),
        quantities=(QuantityResult("", c_val, "F"),),
    )


def _terminal_voltage(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    v_val = p["E_emf"] - p["I"] * p["r_int"]
    return PhysicsResult(
        answer=(
            rf"V = \varepsilon - I r = {p['E_emf']:g} - {p['I']:g} \cdot "
            rf"{p['r_int']:g} \approx {v_val:.2f} \text{{ V}}"
        ),
        formulas=(r"V = \varepsilon - I r",),
        substitutions=(rf"V_{{terminal}} = {p['E_emf']:g} - {p['I']:g} \cdot {p['r_int']:g}",),
        quantities=(QuantityResult("", v_val, "V"),),
    )


def _electrical_power(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if "V" in p and "I" in p:
        val = p["V"] * p["I"]
        answer = rf"P = VI = {p['V']:g} \cdot {p['I']:g} \approx {val:.2f} \text{{ W}}"
        formula = r"P = VI"
        substitution = rf"P = {p['V']:g} \cdot {p['I']:g}"
    elif "I" in p and "R" in p:
        val = p["I"] ** 2 * p["R"]
        plugged = rf"{latex_num(p['I'], square=True)} \cdot {p['R']:g}"
        answer = rf"P = I^2 R = {plugged} \approx {val:.2f} \text{{ W}}"
        formula = r"P = I^2 R"
        substitution = rf"P = {plugged}"
    elif "V" in p and "R" in p:
        if p["R"] == 0:
            raise SolveServiceError("resistance must be nonzero")
        val = p["V"] ** 2 / p["R"]
        plugged = rf"\frac{{{latex_num(p['V'], square=True)}}}{{{p['R']:g}}}"
        answer = rf"P = \frac{{V^2}}{{R}} = {plugged} \approx {val:.2f} \text{{ W}}"
        formula = r"P = \frac{V^2}{R}"
        substitution = rf"P = {plugged}"
    else:
        raise SolveServiceError("electrical power needs two of V, I, R")
    return PhysicsResult(
        answer=answer,
        formulas=(formula,),
        substitutions=(substitution,),
        quantities=(QuantityResult("", val, "W"),),
    )


def _current(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["R"] == 0:
        raise SolveServiceError("resistance must be nonzero")
    val = p["V"] / p["R"]
    return PhysicsResult(
        answer=(
            rf"I = \frac{{V}}{{R}} = \frac{{{p['V']:g}}}{{{p['R']:g}}} "
            rf"\approx {val:.2f} \text{{ A}}"
        ),
        formulas=(r"I = \frac{V}{R}",),
        substitutions=(rf"I = \frac{{{p['V']:g}}}{{{p['R']:g}}}",),
        quantities=(QuantityResult("", val, "A"),),
    )


def _voltage(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    val = p["I"] * p["R"]
    return PhysicsResult(
        answer=rf"V = IR = {p['I']:g} \cdot {p['R']:g} \approx {val:.2f} \text{{ V}}",
        formulas=(r"V = IR",),
        substitutions=(rf"V = {p['I']:g} \cdot {p['R']:g}",),
        quantities=(QuantityResult("", val, "V"),),
    )


def _resistance(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["I"] == 0:
        raise SolveServiceError("current must be nonzero")
    val = p["V"] / p["I"]
    return PhysicsResult(
        answer=(
            rf"R = \frac{{V}}{{I}} = \frac{{{p['V']:g}}}{{{p['I']:g}}} "
            rf"\approx {val:.2f} \,\Omega"
        ),
        formulas=(r"R = \frac{V}{I}",),
        substitutions=(rf"R = \frac{{{p['V']:g}}}{{{p['I']:g}}}",),
        quantities=(QuantityResult("", val, "ohm"),),
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "parallel_plate_capacitance": _parallel_plate_capacitance,
    "capacitor_energy": _capacitor_energy,
    "rc_time_constant": _rc_time_constant,
    "series_resistance": _combined_resistance,
    "parallel_resistance": _combined_resistance,
    "series_current": _network_current,
    "parallel_current": _network_current,
    "series_parallel_resistance": _series_parallel,
    "series_parallel_current": _series_parallel,
    "charge": _charge,
    "electrical_energy": _electrical_energy,
    "capacitance": _capacitance,
    "terminal_voltage": _terminal_voltage,
    "electrical_power": _electrical_power,
    "current": _current,
    "voltage": _voltage,
    "resistance": _resistance,
}
