"""Closed Kirchhoff, inductor, and RL solvers."""

from __future__ import annotations

import math

from app.modules.physics.solvers.resistor_network import RESISTOR_KEY_RE
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.school_common import positive, result
from app.services.solving import SolveServiceError


def _junction(params: dict[str, float]) -> PhysicsResult:
    entering = params["i_enter"]
    leaving = params["i_leave"]
    if entering < 0 or leaving < 0:
        raise SolveServiceError("junction currents must not be negative")
    value = abs(entering - leaving)
    if value == 0:
        side = "balanced"
    elif entering > leaving:
        side = "leaving"
    else:
        side = "entering"
    return PhysicsResult(
        answer=(
            rf"\sum I_{{\mathrm{{in}}}} = \sum I_{{\mathrm{{out}}}} "
            rf"\Rightarrow I = |{entering:g} - {leaving:g}| \approx {value:.4g} \text{{ A}}"
        ),
        formulas=(r"\sum I_{\mathrm{in}} = \sum I_{\mathrm{out}}",),
        substitutions=(rf"I = |{entering:g} - {leaving:g}|",),
        quantities=(
            QuantityResult(
                "I",
                value,
                "A",
                detail=side,
                detail_style="suffix",
            ),
        ),
    )


def _loop(params: dict[str, float]) -> PhysicsResult:
    resistors = [params[key] for key in sorted(params) if RESISTOR_KEY_RE.fullmatch(key)]
    if not resistors or any(value <= 0 for value in resistors):
        raise SolveServiceError("a loop needs positive resistances")
    total = sum(resistors)
    current = params["V"] / total
    numeric = rf"\frac{{{params['V']:g}}}{{{total:g}}}"
    return result("I", r"\frac{V}{\sum R}", numeric, current, "A")


def _inductor_emf(params: dict[str, float]) -> PhysicsResult:
    positive(params, "inductance", "dt")
    value = params["inductance"] * abs(params["delta_i"]) / params["dt"]
    return result(
        r"|\mathcal{E}|",
        r"L\frac{|\Delta I|}{\Delta t}",
        rf"{params['inductance']:g}\cdot\frac{{{abs(params['delta_i']):g}}}{{{params['dt']:g}}}",
        value,
        "V",
    )


def _inductor_energy(params: dict[str, float]) -> PhysicsResult:
    positive(params, "inductance")
    value = 0.5 * params["inductance"] * params["I"] ** 2
    return result(
        "U",
        r"\frac{1}{2}LI^2",
        rf"\frac{{1}}{{2}}\cdot {params['inductance']:g}\cdot {params['I']:g}^2",
        value,
        "J",
    )


def _rl_tau(params: dict[str, float]) -> PhysicsResult:
    positive(params, "inductance", "R")
    value = params["inductance"] / params["R"]
    return result(
        r"\tau",
        r"\frac{L}{R}",
        rf"\frac{{{params['inductance']:g}}}{{{params['R']:g}}}",
        value,
        "s",
    )


def _rl_growth(params: dict[str, float]) -> PhysicsResult:
    positive(params, "R", "inductance")
    if params["t"] < 0:
        raise SolveServiceError("time cannot be negative")
    ratio = params["t"] * params["R"] / params["inductance"]
    value = (params["V"] / params["R"]) * (1 - math.exp(-ratio))
    return result(
        "I",
        r"\frac{V}{R}(1-e^{-tR/L})",
        rf"\frac{{{params['V']:g}}}{{{params['R']:g}}}(1-e^{{-{ratio:g}}})",
        value,
        "A",
    )


def _rl_decay(params: dict[str, float]) -> PhysicsResult:
    positive(params, "R", "inductance")
    if params["t"] < 0:
        raise SolveServiceError("time cannot be negative")
    ratio = params["t"] * params["R"] / params["inductance"]
    value = params["I0"] * math.exp(-ratio)
    return result(
        "I",
        r"I_0 e^{-Rt/L}",
        rf"{params['I0']:g}\cdot e^{{-{ratio:g}}}",
        value,
        "A",
    )


CIRCUIT_SOLVERS = {
    "kirchhoff_junction": _junction,
    "kirchhoff_loop": _loop,
    "inductor_emf": _inductor_emf,
    "inductor_energy": _inductor_energy,
    "rl_time_constant": _rl_tau,
    "rl_growth": _rl_growth,
    "rl_decay": _rl_decay,
}
