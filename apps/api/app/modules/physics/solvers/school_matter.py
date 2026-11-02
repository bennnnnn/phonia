"""Closed fluids, gravitation, and thermal solvers."""

from __future__ import annotations

import math

from app.modules.physics.constants import BIG_G, GAS_CONSTANT
from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.school_common import positive, result
from app.services.solving import SolveServiceError


def _poiseuille(params: dict[str, float]) -> PhysicsResult:
    positive(params, "r", "L", "viscosity")
    value = (
        math.pi
        * params["r"] ** 4
        * params["delta_pressure"]
        / (8 * params["viscosity"] * params["L"])
    )
    return result(
        "Q",
        r"\frac{\pi r^4\Delta P}{8\eta L}",
        rf"\frac{{\pi {params['r']:g}^4\cdot {params['delta_pressure']:g}}}"
        rf"{{8\cdot {params['viscosity']:g}\cdot {params['L']:g}}}",
        value,
        "m^3/s",
    )


def _potential(params: dict[str, float]) -> PhysicsResult:
    positive(params, "M", "r")
    value = -BIG_G * params["M"] / params["r"]
    numeric = rf"-\frac{{{BIG_G:.5g}\cdot {params['M']:g}}}{{{params['r']:g}}}"
    return result("V", r"-\frac{GM}{r}", numeric, value, "J/kg")


def _potential_energy(params: dict[str, float]) -> PhysicsResult:
    positive(params, "M", "r")
    value = -BIG_G * params["M"] * params["m"] / params["r"]
    numeric = rf"-\frac{{{BIG_G:.5g}\cdot {params['M']:g}\cdot {params['m']:g}}}{{{params['r']:g}}}"
    return result("U", r"-\frac{GMm}{r}", numeric, value, "J")


def _orbital_energy(params: dict[str, float]) -> PhysicsResult:
    positive(params, "M", "r")
    value = -BIG_G * params["M"] * params["m"] / (2 * params["r"])
    numeric = (
        rf"-\frac{{{BIG_G:.5g}\cdot {params['M']:g}\cdot {params['m']:g}}}"
        rf"{{2\cdot {params['r']:g}}}"
    )
    return result("E", r"-\frac{GMm}{2r}", numeric, value, "J")


def _kepler(params: dict[str, float]) -> PhysicsResult:
    positive(params, "M", "r")
    value = 2 * math.pi * math.sqrt(params["r"] ** 3 / (BIG_G * params["M"]))
    return result(
        "T",
        r"2\pi\sqrt{\frac{r^3}{GM}}",
        rf"2\pi\sqrt{{\frac{{{params['r']:g}^3}}{{{BIG_G:.5g}\cdot {params['M']:g}}}}}",
        value,
        "s",
    )


def _monatomic(params: dict[str, float]) -> PhysicsResult:
    positive(params, "moles", "temp")
    value = 1.5 * params["moles"] * GAS_CONSTANT * params["temp"]
    numeric = (
        rf"\frac{{3}}{{2}}\cdot {params['moles']:g}"
        rf"\cdot {GAS_CONSTANT:.4f}\cdot {params['temp']:g}"
    )
    return result("U", r"\frac{3}{2}nRT", numeric, value, "J")


def _isobaric(params: dict[str, float]) -> PhysicsResult:
    positive(params, "pres", "vol1", "vol2")
    value = params["pres"] * (params["vol2"] - params["vol1"])
    return result(
        "W",
        r"P\Delta V",
        rf"{params['pres']:g}\cdot ({params['vol2']:g}-{params['vol1']:g})",
        value,
        "J",
    )


def _adiabatic_pressure(params: dict[str, float]) -> PhysicsResult:
    positive(params, "pres1", "vol1", "vol2")
    if params["gamma_gas"] <= 1:
        raise SolveServiceError("adiabatic gamma must be greater than 1")
    value = params["pres1"] * (params["vol1"] / params["vol2"]) ** params["gamma_gas"]
    ratio = f"{params['vol1']:g}/{params['vol2']:g}"
    numeric = rf"{params['pres1']:g}\cdot ({ratio})^{{{params['gamma_gas']:g}}}"
    return result("P_2", r"P_1(V_1/V_2)^\gamma", numeric, value, "Pa")


def _adiabatic_volume(params: dict[str, float]) -> PhysicsResult:
    positive(params, "pres1", "pres2", "vol1")
    if params["gamma_gas"] <= 1:
        raise SolveServiceError("adiabatic gamma must be greater than 1")
    value = params["vol1"] * (params["pres1"] / params["pres2"]) ** (1 / params["gamma_gas"])
    numeric = (
        rf"{params['vol1']:g}\cdot ({params['pres1']:g}/{params['pres2']:g})"
        rf"^{{1/{params['gamma_gas']:g}}}"
    )
    return result("V_2", r"V_1(P_1/P_2)^{1/\gamma}", numeric, value, "m^3")


def _refrigerator(params: dict[str, float]) -> PhysicsResult:
    return _cop("refrigerator_cop", params)


def _heat_pump(params: dict[str, float]) -> PhysicsResult:
    return _cop("heat_pump_cop", params)


def _cop(kind: str, params: dict[str, float]) -> PhysicsResult:
    hot = params["temp"]
    cold = params["temp_env"]
    if cold <= 0 or hot <= cold:
        raise SolveServiceError("need absolute temperatures with the hot side warmer")
    if kind == "heat_pump_cop":
        value = hot / (hot - cold)
        numeric = rf"\frac{{{hot:g}}}{{{hot:g}-{cold:g}}}"
        return result("COP", r"\frac{T_H}{T_H-T_C}", numeric, value, "")
    value = cold / (hot - cold)
    numeric = rf"\frac{{{cold:g}}}{{{hot:g}-{cold:g}}}"
    return result("COP", r"\frac{T_C}{T_H-T_C}", numeric, value, "")


MATTER_SOLVERS = {
    "poiseuille_flow": _poiseuille,
    "gravitational_potential": _potential,
    "gravitational_potential_energy": _potential_energy,
    "orbital_energy": _orbital_energy,
    "kepler_period": _kepler,
    "monatomic_energy": _monatomic,
    "isobaric_work": _isobaric,
    "adiabatic_pressure": _adiabatic_pressure,
    "adiabatic_volume": _adiabatic_volume,
    "refrigerator_cop": _refrigerator,
    "heat_pump_cop": _heat_pump,
}
