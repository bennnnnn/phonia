"""Closed sinusoidal AC solvers: rms, reactance, series impedance, and resonance."""

from __future__ import annotations

import math

from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.school_common import positive, result


def _rms_voltage(params: dict[str, float]) -> PhysicsResult:
    given = params["V"]
    if params.get("to_peak"):
        value = given * math.sqrt(2)
        return result("V_0", r"V_{\mathrm{rms}}\sqrt{2}", rf"{given:g}\sqrt{{2}}", value, "V")
    value = given / math.sqrt(2)
    numeric = rf"\frac{{{given:g}}}{{\sqrt{{2}}}}"
    return result("V_{rms}", r"\frac{V_0}{\sqrt{2}}", numeric, value, "V")


def _rms_current(params: dict[str, float]) -> PhysicsResult:
    given = params["I"]
    if params.get("to_peak"):
        value = given * math.sqrt(2)
        return result("I_0", r"I_{\mathrm{rms}}\sqrt{2}", rf"{given:g}\sqrt{{2}}", value, "A")
    value = given / math.sqrt(2)
    numeric = rf"\frac{{{given:g}}}{{\sqrt{{2}}}}"
    return result("I_{rms}", r"\frac{I_0}{\sqrt{2}}", numeric, value, "A")


def _xl(params: dict[str, float]) -> PhysicsResult:
    positive(params, "freq", "inductance")
    value = 2 * math.pi * params["freq"] * params["inductance"]
    numeric = rf"2\pi\cdot {params['freq']:g}\cdot {params['inductance']:g}"
    return result("X_L", r"2\pi f L", numeric, value, "ohm")


def _xc(params: dict[str, float]) -> PhysicsResult:
    positive(params, "freq", "capacitance")
    value = 1 / (2 * math.pi * params["freq"] * params["capacitance"])
    numeric = rf"\frac{{1}}{{2\pi\cdot {params['freq']:g}\cdot {params['capacitance']:g}}}"
    return result("X_C", r"\frac{1}{2\pi f C}", numeric, value, "ohm")


def _impedance(params: dict[str, float]) -> PhysicsResult:
    positive(params, "R")
    if "reactance_l" in params and "reactance_c" in params:
        inductive = params["reactance_l"]
        capacitive = params["reactance_c"]
    else:
        positive(params, "freq", "inductance", "capacitance")
        inductive = 2 * math.pi * params["freq"] * params["inductance"]
        capacitive = 1 / (2 * math.pi * params["freq"] * params["capacitance"])
    gap = inductive - capacitive
    value = math.sqrt(params["R"] ** 2 + gap**2)
    return result(
        "Z",
        r"\sqrt{R^2+(X_L-X_C)^2}",
        rf"\sqrt{{{params['R']:g}^2+({inductive:.4g}-{capacitive:.4g})^2}}",
        value,
        "ohm",
    )


def _resonance(params: dict[str, float]) -> PhysicsResult:
    positive(params, "inductance", "capacitance")
    value = 1 / (2 * math.pi * math.sqrt(params["inductance"] * params["capacitance"]))
    return result(
        "f",
        r"\frac{1}{2\pi\sqrt{LC}}",
        rf"\frac{{1}}{{2\pi\sqrt{{{params['inductance']:g}\cdot {params['capacitance']:g}}}}}",
        value,
        "Hz",
    )


def _ac_power(params: dict[str, float]) -> PhysicsResult:
    positive(params, "R")
    value = params["I"] ** 2 * params["R"]
    return result("P", "I^2 R", rf"{params['I']:g}^2\cdot {params['R']:g}", value, "W")


AC_SOLVERS = {
    "rms_voltage": _rms_voltage,
    "rms_current": _rms_current,
    "inductive_reactance": _xl,
    "capacitive_reactance": _xc,
    "series_impedance": _impedance,
    "lc_resonance": _resonance,
    "ac_average_power": _ac_power,
}
