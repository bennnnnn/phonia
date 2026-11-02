"""Thermal solvers: Carnot and engine efficiency, entropy, conduction, expansion,
latent heat and the first law.
"""

from __future__ import annotations

from collections.abc import Callable

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_thermal(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or ""
    solver = _OPERATIONS.get(op)
    if solver is None:
        raise SolveServiceError(f"unsupported thermal op: {op}")
    return solver(intent, p)


def _carnot_efficiency(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    hot, cold = p["temp"], p["temp_env"]
    if hot <= 0 or cold < 0 or cold >= hot:
        raise SolveServiceError("Carnot efficiency needs 0 <= T_c < T_h in kelvin")
    value = 1 - cold / hot
    return PhysicsResult(
        answer=(
            rf"\eta_C = 1 - \frac{{T_C}}{{T_H}} = 1 - "
            rf"\frac{{{cold:g}}}{{{hot:g}}} \approx {value:.4g} "
            rf"({value * 100:.4g}\%)"
        ),
        formulas=(r"\eta_C = 1 - \frac{T_C}{T_H}",),
        substitutions=(rf"\eta_C = 1 - \frac{{{cold:g}}}{{{hot:g}}}",),
        quantities=(
            QuantityResult(
                "",
                value,
                "",
                detail=f"{value * 100:.4g}%",
            ),
        ),
    )


def _entropy_change(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["temp"] <= 0:
        raise SolveServiceError("entropy change needs a positive absolute temperature")
    value = p["heat"] / p["temp"]
    return PhysicsResult(
        answer=(
            rf"\Delta S = \frac{{Q_{{rev}}}}{{T}} = "
            rf"\frac{{{p['heat']:g}}}{{{p['temp']:g}}} "
            rf"\approx {value:.4g} \text{{ J/K}}"
        ),
        formulas=(r"\Delta S = \frac{Q_{rev}}{T}",),
        substitutions=(rf"\Delta S = \frac{{{p['heat']:g}}}{{{p['temp']:g}}}",),
        quantities=(QuantityResult("", value, "J/K"),),
    )


def _heat_conduction_rate(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["thermal_conductivity"] < 0 or p["area"] <= 0 or p["L"] <= 0:
        raise SolveServiceError("heat conduction needs positive area and thickness")
    value = p["thermal_conductivity"] * p["area"] * abs(p["delta_temp"]) / p["L"]
    return PhysicsResult(
        answer=(
            rf"\frac{{Q}}{{t}} = kA\frac{{\Delta T}}{{L}} = "
            rf"{p['thermal_conductivity']:g} \cdot {p['area']:g} \cdot "
            rf"\frac{{{abs(p['delta_temp']):g}}}{{{p['L']:g}}} "
            rf"\approx {value:.4g} \text{{ W}}"
        ),
        formulas=(r"\frac{Q}{t} = kA\frac{\Delta T}{L}",),
        substitutions=(
            rf"Q/t = {p['thermal_conductivity']:g} \cdot {p['area']:g} \cdot "
            rf"\frac{{{abs(p['delta_temp']):g}}}{{{p['L']:g}}}",
        ),
        quantities=(QuantityResult("", value, "W"),),
    )


def _linear_expansion(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["L0"] <= 0 or p["alpha"] < 0:
        raise SolveServiceError("linear expansion needs positive length and nonnegative alpha")
    expansion = p["alpha"] * p["L0"] * p["delta_temp"]
    return PhysicsResult(
        answer=(
            rf"\Delta L = \alpha L_0 \Delta T = {p['alpha']:g} \cdot "
            rf"{p['L0']:g} \cdot {p['delta_temp']:g} "
            rf"\approx {expansion:g} \text{{ m}}"
        ),
        formulas=(r"\Delta L = \alpha L_0 \Delta T",),
        substitutions=(rf"\Delta L = {p['alpha']:g} \cdot {p['L0']:g} \cdot {p['delta_temp']:g}",),
        quantities=(QuantityResult("", expansion, "m"),),
    )


def _latent_heat(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["m"] < 0 or p["latent_heat"] < 0:
        raise SolveServiceError("latent heat needs nonnegative mass and specific latent heat")
    heat = p["m"] * p["latent_heat"]
    return PhysicsResult(
        answer=(
            rf"Q = mL = {p['m']:g} \cdot {p['latent_heat']:g} "
            rf"\approx {heat:g} \text{{ J}}"
        ),
        formulas=(r"Q = mL",),
        substitutions=(rf"Q = {p['m']:g} \cdot {p['latent_heat']:g}",),
        quantities=(QuantityResult("", heat, "J"),),
    )


def _first_law_internal_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    change = p["heat"] - p["W"]
    return PhysicsResult(
        answer=(
            rf"\Delta U = Q - W = {p['heat']:g} - {p['W']:g} "
            rf"\approx {change:g} \text{{ J}}"
        ),
        formulas=(r"\Delta U = Q - W",),
        substitutions=(rf"\Delta U = {p['heat']:g} - {p['W']:g}",),
        quantities=(QuantityResult("", change, "J"),),
    )


def _thermal_efficiency(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    supplied = p["Q_in"]
    if supplied <= 0:
        raise SolveServiceError("the energy supplied must be positive")
    eta = p["W_out"] / supplied
    return PhysicsResult(
        answer=(
            rf"\eta = \frac{{W}}{{Q_{{in}}}} = \frac{{{p['W_out']:g}}}{{{supplied:g}}} "
            rf"\approx {eta:.2f} \; ({eta * 100:.1f}\%)"
        ),
        formulas=(r"\eta = \frac{W}{Q_{in}}",),
        substitutions=(rf"\eta = \frac{{{p['W_out']:g}}}{{{supplied:g}}}",),
        quantities=(
            QuantityResult(
                "",
                eta,
                "",
                detail=f"{eta * 100:.1f}%",
            ),
        ),
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "carnot_efficiency": _carnot_efficiency,
    "entropy_change": _entropy_change,
    "heat_conduction_rate": _heat_conduction_rate,
    "linear_expansion": _linear_expansion,
    "latent_heat": _latent_heat,
    "first_law_internal_energy": _first_law_internal_energy,
    "thermal_efficiency": _thermal_efficiency,
}
