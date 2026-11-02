"""Electrostatics and magnetism solvers: Coulomb's law, magnetic force, flux, solenoids
and motional emf.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.modules.physics.constants import COULOMB_K, MU_0
from app.modules.physics.display import latex_given
from app.modules.physics.schemas import PhysicsIntent, SimulationBlockSpec
from app.modules.physics.solvers.arithmetic import latex_num
from app.modules.physics.solvers.field_scenes import charges_scene
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def _angle_label(intent: PhysicsIntent) -> str:
    raw = (intent.physics_params or {}).get("angle", 0.0)
    unit = (intent.physics_units or {}).get("angle", "deg")
    if unit in {"rad", "radian", "radians"}:
        return f"{raw:g}"
    return rf"{raw:g}^\circ"


def solve_magnetism(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or ""
    solver = _OPERATIONS.get(op)
    if solver is None:
        raise SolveServiceError(f"unsupported magnetism op: {op}")
    return solver(intent, p)


def _electric_field(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["r"] <= 0:
        raise SolveServiceError("distance from the point charge must be positive")
    value = COULOMB_K * abs(p["Q"]) / p["r"] ** 2
    return PhysicsResult(
        answer=(
            rf"E = k_e\frac{{\lvert Q\rvert}}{{r^2}} = {COULOMB_K:.7g} \cdot "
            rf"\frac{{\lvert {p['Q']:g}\rvert}}{{{p['r']:g}^2}} "
            rf"\approx {value:.4g} \text{{ N/C}}"
        ),
        formulas=(r"E = k_e\frac{\lvert Q\rvert}{r^2}",),
        substitutions=(
            rf"E = {COULOMB_K:.7g} \cdot \frac{{\lvert {p['Q']:g}\rvert}}{{{p['r']:g}^2}}",
        ),
        quantities=(QuantityResult("", value, "N/C"),),
    )


def _electric_potential(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["r"] <= 0:
        raise SolveServiceError("distance from the point charge must be positive")
    value = COULOMB_K * p["Q"] / p["r"]
    return PhysicsResult(
        answer=(
            rf"V = k_e\frac{{Q}}{{r}} = {COULOMB_K:.7g} \cdot "
            rf"\frac{{{p['Q']:g}}}{{{p['r']:g}}} \approx {value:.4g} \text{{ V}}"
        ),
        formulas=(r"V = k_e\frac{Q}{r}",),
        substitutions=(rf"V = {COULOMB_K:.7g} \cdot \frac{{{p['Q']:g}}}{{{p['r']:g}}}",),
        quantities=(QuantityResult("", value, "V"),),
    )


def _electric_potential_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["r"] <= 0:
        raise SolveServiceError("charge separation must be positive")
    value = COULOMB_K * p["q1"] * p["q2"] / p["r"]
    return PhysicsResult(
        answer=(
            rf"U = k_e\frac{{q_1q_2}}{{r}} = {COULOMB_K:.7g} \cdot "
            rf"\frac{{{p['q1']:g} \cdot {p['q2']:g}}}{{{p['r']:g}}} "
            rf"\approx {value:.4g} \text{{ J}}"
        ),
        formulas=(r"U = k_e\frac{q_1q_2}{r}",),
        substitutions=(
            rf"U = {COULOMB_K:.7g} \cdot \frac{{{p['q1']:g} \cdot {p['q2']:g}}}{{{p['r']:g}}}",
        ),
        quantities=(QuantityResult("", value, "J"),),
    )


def _charged_particle_radius(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    denominator = abs(p["Q"]) * p["b_field"]
    if p["m"] <= 0 or p["v"] < 0 or denominator <= 0:
        raise SolveServiceError("magnetic radius needs positive mass, charge, and field")
    value = p["m"] * p["v"] / denominator
    return PhysicsResult(
        answer=(
            rf"r = \frac{{mv}}{{\lvert q\rvert B}} = "
            rf"\frac{{{p['m']:g} \cdot {p['v']:g}}}"
            rf"{{{abs(p['Q']):g} \cdot {p['b_field']:g}}} "
            rf"\approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"r = \frac{mv}{\lvert q\rvert B}",),
        substitutions=(
            rf"r = \frac{{{p['m']:g} \cdot {p['v']:g}}}{{{abs(p['Q']):g} \cdot "
            rf"{p['b_field']:g}}}",
        ),
        quantities=(QuantityResult("", value, "m"),),
    )


def _motional_emf(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["b_field"] * p["wire_L"] * p["v"]
    return PhysicsResult(
        answer=(
            rf"\mathcal{{E}} = BLv = {p['b_field']:g} \cdot {p['wire_L']:g} "
            rf"\cdot {p['v']:g} \approx {value:.4g} \text{{ V}}"
        ),
        formulas=(r"\mathcal{E} = BLv",),
        substitutions=(
            rf"\mathcal{{E}} = {p['b_field']:g} \cdot {p['wire_L']:g} \cdot {p['v']:g}",
        ),
        quantities=(QuantityResult("", value, "V"),),
    )


def _magnetic_field_wire(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["r"] <= 0:
        raise SolveServiceError("distance from the wire must be positive")
    value = MU_0 * p["I"] / (2 * math.pi * p["r"])
    return PhysicsResult(
        answer=(
            rf"B = \frac{{\mu_0 I}}{{2\pi r}} = "
            rf"\frac{{{MU_0:.7g} \cdot {p['I']:g}}}{{2\pi \cdot {p['r']:g}}} "
            rf"\approx {value:.4g} \text{{ T}}"
        ),
        formulas=(r"B = \frac{\mu_0 I}{2\pi r}",),
        substitutions=(rf"B = \frac{{{MU_0:.7g} \cdot {p['I']:g}}}{{2\pi \cdot {p['r']:g}}}",),
        quantities=(QuantityResult("", value, "T"),),
    )


def _electric_force(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    separation = p["r"]
    if separation <= 0:
        raise SolveServiceError("charge separation must be positive")
    value = COULOMB_K * abs(p["q1"] * p["q2"]) / separation**2
    return PhysicsResult(
        answer=(
            rf"F_e = k_e \frac{{\lvert q_1q_2\rvert}}{{r^2}} = "
            rf"{latex_given(COULOMB_K)} \cdot "
            rf"\frac{{\lvert {latex_given(p['q1'])} \cdot "
            rf"{latex_given(p['q2'])}"
            rf"\rvert}}{{{latex_num(separation, square=True)}}} "
            rf"\approx {value:.4g} \text{{ N}}"
        ),
        formulas=(r"F_e = k_e \frac{\lvert q_1q_2\rvert}{r^2}",),
        substitutions=(
            rf"F_e = {latex_given(COULOMB_K)} \cdot \frac{{\lvert "
            rf"{latex_given(p['q1'])} \cdot {latex_given(p['q2'])}"
            rf"\rvert}}{{{latex_num(separation, square=True)}}}",
        ),
        quantities=(QuantityResult("", value, "N"),),
        simulation_specs=[_charges(intent, value)],
    )


def _charges(intent: PhysicsIntent, force: float) -> SimulationBlockSpec:
    """The two charges as the question wrote them: their own units and signs."""
    given = intent.physics_params or {}
    units = intent.physics_units or {}
    return charges_scene(
        (given["q1"], units.get("q1") or "C"),
        (given["q2"], units.get("q2") or "C"),
        (given["r"], units.get("r") or "m"),
        force,
    )


def _magnetic_force_wire(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["b_field"] * p["I"] * p["wire_L"]
    if "angle" in p:
        value *= math.sin(p["angle"])
        return PhysicsResult(
            answer=(
                rf"F = BIL\sin\theta = {p['b_field']:g} \cdot {p['I']:g} \cdot "
                rf"{p['wire_L']:g} \cdot \sin({_angle_label(intent)}) "
                rf"\approx {value:.4g} \text{{ N}}"
            ),
            formulas=(r"F = BIL\sin\theta",),
            substitutions=(
                rf"F = {p['b_field']:g} \cdot {p['I']:g} \cdot {p['wire_L']:g} \cdot "
                rf"\sin({_angle_label(intent)})",
            ),
            quantities=(QuantityResult("", value, "N"),),
        )
    return PhysicsResult(
        answer=(
            rf"F = BIL = {p['b_field']:g} \cdot {p['I']:g} \cdot {p['wire_L']:g} "
            rf"\approx {value:.2f} \text{{ N}}"
        ),
        formulas=(r"F = BIL",),
        substitutions=(rf"F = {p['b_field']:g} \cdot {p['I']:g} \cdot {p['wire_L']:g}",),
        quantities=(QuantityResult("", value, "N"),),
    )


def _magnetic_force_charge(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["Q"] * p["v"] * p["b_field"]
    if "angle" in p:
        value *= math.sin(p["angle"])
        return PhysicsResult(
            answer=(
                rf"F = qvB\sin\theta = {p['Q']:g} \cdot {p['v']:g} \cdot "
                rf"{p['b_field']:g} \cdot \sin({_angle_label(intent)}) "
                rf"\approx {value:.4g} \text{{ N}}"
            ),
            formulas=(r"F = qvB\sin\theta",),
            substitutions=(
                rf"F = {p['Q']:g} \cdot {p['v']:g} \cdot {p['b_field']:g} \cdot "
                rf"\sin({_angle_label(intent)})",
            ),
            quantities=(QuantityResult("", value, "N"),),
        )
    number_format = ".4g" if 0 < abs(value) < 0.01 else ".2f"
    return PhysicsResult(
        answer=(
            rf"F = qvB = {p['Q']:g} \cdot {p['v']:g} \cdot {p['b_field']:g} "
            rf"\approx {format(value, number_format)} \text{{ N}}"
        ),
        formulas=(r"F = qvB",),
        substitutions=(rf"F = {p['Q']:g} \cdot {p['v']:g} \cdot {p['b_field']:g}",),
        # The full form carries sin(theta); this is the perpendicular case.
        quantities=(
            QuantityResult(
                "",
                value,
                "N",
                detail="field perpendicular to the motion",
            ),
        ),
    )


def _magnetic_flux(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["b_field"] * p["area"]
    if "angle" in p:
        value *= math.cos(p["angle"])
        return PhysicsResult(
            answer=(
                rf"\Phi = BA\cos\theta = {p['b_field']:g} \cdot {p['area']:g} "
                rf"\cdot \cos({_angle_label(intent)}) \approx {value:.4g} \text{{ Wb}}"
            ),
            formulas=(r"\Phi = BA\cos\theta",),
            substitutions=(
                rf"\Phi = {p['b_field']:g} \cdot {p['area']:g} \cdot "
                rf"\cos({_angle_label(intent)})",
            ),
            quantities=(QuantityResult("", value, "Wb"),),
        )
    return PhysicsResult(
        answer=(
            rf"\Phi = BA = {p['b_field']:g} \cdot {p['area']:g} "
            rf"\approx {value:.4g} \text{{ Wb}}"
        ),
        formulas=(r"\Phi = BA",),
        substitutions=(rf"\Phi = {p['b_field']:g} \cdot {p['area']:g}",),
        quantities=(QuantityResult("", value, "Wb"),),
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "electric_field": _electric_field,
    "electric_potential": _electric_potential,
    "electric_potential_energy": _electric_potential_energy,
    "charged_particle_radius": _charged_particle_radius,
    "motional_emf": _motional_emf,
    "magnetic_field_wire": _magnetic_field_wire,
    "electric_force": _electric_force,
    "magnetic_force_wire": _magnetic_force_wire,
    "magnetic_force_charge": _magnetic_force_charge,
    "magnetic_flux": _magnetic_flux,
}
