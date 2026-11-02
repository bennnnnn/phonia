"""Modern-physics solvers: photons, de Broglie, relativity, uncertainty, hydrogen levels,
Compton, black bodies, half-lives and E = mc^2.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.modules.physics.constants import (
    ELECTRON_MASS,
    ELEMENTARY_CHARGE,
    HBAR,
    PLANCK_H,
    SPEED_OF_LIGHT,
    STEFAN_BOLTZMANN,
    WIEN_B,
)
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_modern(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or ""
    solver = _OPERATIONS.get(op)
    if solver is None:
        raise SolveServiceError(f"unsupported modern op: {op}")
    return solver(intent, p)


def _relativity(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    op = intent.physics_op or ""
    speed = abs(p["v"])
    if speed >= SPEED_OF_LIGHT:
        raise SolveServiceError("special relativity requires a speed below c")
    gamma = 1 / math.sqrt(1 - (speed / SPEED_OF_LIGHT) ** 2)
    if op == "lorentz_factor":
        return PhysicsResult(
            answer=(
                rf"\gamma = \frac{{1}}{{\sqrt{{1-v^2/c^2}}}} = "
                rf"\frac{{1}}{{\sqrt{{1-({speed:g}/{SPEED_OF_LIGHT:g})^2}}}} "
                rf"\approx {gamma:.4g}"
            ),
            formulas=(r"\gamma = \frac{1}{\sqrt{1-v^2/c^2}}",),
            substitutions=(rf"\gamma = \frac{{1}}{{\sqrt{{1-({speed:g}/{SPEED_OF_LIGHT:g})^2}}}}",),
            quantities=(QuantityResult("", gamma, ""),),
        )
    if op == "time_dilation":
        value = gamma * p["proper_time"]
        return PhysicsResult(
            answer=(
                rf"\Delta t = \gamma\Delta t_0 = {gamma:.4g} \cdot "
                rf"{p['proper_time']:g} \approx {value:.4g} \text{{ s}}"
            ),
            formulas=(r"\Delta t = \gamma\Delta t_0",),
            substitutions=(rf"\Delta t = {gamma:.4g} \cdot {p['proper_time']:g}",),
            quantities=(QuantityResult("", value, "s"),),
        )
    value = p["proper_length"] / gamma
    return PhysicsResult(
        answer=(
            rf"L = \frac{{L_0}}{{\gamma}} = \frac{{{p['proper_length']:g}}}"
            rf"{{{gamma:.4g}}} \approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"L = \frac{L_0}{\gamma}",),
        substitutions=(rf"L = \frac{{{p['proper_length']:g}}}{{{gamma:.4g}}}",),
        quantities=(QuantityResult("", value, "m"),),
    )


def _photoelectric_kinetic_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["freq"] <= 0 or p["work_function"] < 0:
        raise SolveServiceError("photoelectric energy needs positive frequency and work function")
    value = PLANCK_H * p["freq"] - p["work_function"]
    if value < 0:
        raise SolveServiceError("the photon energy is below the work function")
    ev = value / ELEMENTARY_CHARGE
    return PhysicsResult(
        answer=(
            rf"K_{{max}} = hf - \phi = {PLANCK_H:.7g} \cdot {p['freq']:g} - "
            rf"{p['work_function']:g} \approx {value:.4g} \text{{ J}}"
        ),
        formulas=(r"K_{max} = hf - \phi",),
        substitutions=(
            rf"K_{{max}} = {PLANCK_H:.7g} \cdot {p['freq']:g} - {p['work_function']:g}",
        ),
        quantities=(
            QuantityResult("", value, "J"),
            QuantityResult("", ev, "eV"),
        ),
        joiner="paren-second",
    )


def _uncertainty_momentum(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["uncertainty_x"] <= 0:
        raise SolveServiceError("position uncertainty must be positive")
    value = HBAR / (2 * p["uncertainty_x"])
    return PhysicsResult(
        answer=(
            rf"\Delta p_{{min}} = \frac{{\hbar}}{{2\Delta x}} = "
            rf"\frac{{{HBAR:.7g}}}{{2 \cdot {p['uncertainty_x']:g}}} "
            rf"\approx {value:.4g} \text{{ kg}}\cdot\text{{m/s}}"
        ),
        formulas=(r"\Delta p_{min} = \frac{\hbar}{2\Delta x}",),
        substitutions=(
            rf"\Delta p_{{min}} = \frac{{{HBAR:.7g}}}{{2 \cdot {p['uncertainty_x']:g}}}",
        ),
        quantities=(QuantityResult("", value, "kg*m/s"),),
    )


def _particle_box_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    level = p["quantum_n"]
    if p["L"] <= 0 or p["m"] <= 0 or level < 1 or not level.is_integer():
        raise SolveServiceError("box energy needs positive m and L and an integer n >= 1")
    value = level**2 * PLANCK_H**2 / (8 * p["m"] * p["L"] ** 2)
    ev = value / ELEMENTARY_CHARGE
    return PhysicsResult(
        answer=(
            rf"E_n = \frac{{n^2h^2}}{{8mL^2}} = "
            rf"\frac{{{level:g}^2 \cdot ({PLANCK_H:.7g})^2}}"
            rf"{{8 \cdot {p['m']:g} \cdot {p['L']:g}^2}} "
            rf"\approx {value:.4g} \text{{ J}}"
        ),
        formulas=(r"E_n = \frac{n^2h^2}{8mL^2}",),
        substitutions=(
            rf"E_n = \frac{{{level:g}^2 \cdot ({PLANCK_H:.7g})^2}}{{8 \cdot {p['m']:g} \cdot "
            rf"{p['L']:g}^2}}",
        ),
        quantities=(
            QuantityResult("", value, "J"),
            QuantityResult("", ev, "eV"),
        ),
        joiner="paren-second",
    )


def _hydrogen_energy_level(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    level = p["quantum_n"]
    if level < 1 or not level.is_integer():
        raise SolveServiceError("hydrogen energy needs an integer n >= 1")
    value = -13.6 / level**2
    return PhysicsResult(
        answer=(
            rf"E_n = -\frac{{13.6\ \text{{eV}}}}{{n^2}} = "
            rf"-\frac{{13.6}}{{{level:g}^2}} \approx {value:.4g} \text{{ eV}}"
        ),
        formulas=(r"E_n = -\frac{13.6\ \text{eV}}{n^2}",),
        substitutions=(rf"E_n = -\frac{{13.6}}{{{level:g}^2}}",),
        quantities=(QuantityResult("", value, "eV"),),
    )


def _compton_shift(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = PLANCK_H / (ELECTRON_MASS * SPEED_OF_LIGHT) * (1 - math.cos(p["angle"]))
    return PhysicsResult(
        answer=(
            rf"\Delta\lambda = \frac{{h}}{{m_ec}}(1-\cos\theta) = "
            rf"\frac{{{PLANCK_H:.7g}}}{{{ELECTRON_MASS:.7g} \cdot {SPEED_OF_LIGHT:g}}}"
            rf"(1-\cos {math.degrees(p['angle']):g}^\circ) "
            rf"\approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"\Delta\lambda = \frac{h}{m_ec}(1-\cos\theta)",),
        substitutions=(
            rf"\Delta\lambda = \frac{{{PLANCK_H:.7g}}}{{{ELECTRON_MASS:.7g} \cdot "
            rf"{SPEED_OF_LIGHT:g}}}(1-\cos {math.degrees(p['angle']):g}^\circ)",
        ),
        quantities=(QuantityResult("", value, "m"),),
    )


def _wien_peak(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["temp"] <= 0:
        raise SolveServiceError("blackbody temperature must be positive")
    value = WIEN_B / p["temp"]
    return PhysicsResult(
        answer=(
            rf"\lambda_{{max}} = \frac{{b}}{{T}} = "
            rf"\frac{{{WIEN_B:.7g}}}{{{p['temp']:g}}} "
            rf"\approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"\lambda_{max} = \frac{b}{T}",),
        substitutions=(rf"\lambda_{{max}} = \frac{{{WIEN_B:.7g}}}{{{p['temp']:g}}}",),
        quantities=(QuantityResult("", value, "m"),),
    )


def _stefan_boltzmann_power(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["temp"] <= 0 or p["area"] <= 0 or not 0 <= p["emissivity"] <= 1:
        raise SolveServiceError("radiated power needs positive T and A and 0 <= emissivity <= 1")
    value = p["emissivity"] * STEFAN_BOLTZMANN * p["area"] * p["temp"] ** 4
    return PhysicsResult(
        answer=(
            rf"P = \epsilon\sigma AT^4 = {p['emissivity']:g} \cdot "
            rf"{STEFAN_BOLTZMANN:.7g} \cdot {p['area']:g} \cdot {p['temp']:g}^4 "
            rf"\approx {value:.4g} \text{{ W}}"
        ),
        formulas=(r"P = \epsilon\sigma AT^4",),
        substitutions=(
            rf"P = {p['emissivity']:g} \cdot {STEFAN_BOLTZMANN:.7g} \cdot {p['area']:g} \cdot "
            rf"{p['temp']:g}^4",
        ),
        quantities=(QuantityResult("", value, "W"),),
    )


def _photon_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if "freq" in p:
        freq = p["freq"]
        if freq <= 0:
            raise SolveServiceError("photon frequency must be positive")
        value = PLANCK_H * freq
        substitution = rf"{PLANCK_H:.5g} \cdot {freq:.4g}"
        formula = "E = hf"
    else:
        wavelength = p["wavelength"]
        if wavelength <= 0:
            raise SolveServiceError("photon wavelength must be positive")
        value = PLANCK_H * SPEED_OF_LIGHT / wavelength
        substitution = (
            rf"\frac{{{PLANCK_H:.5g} \cdot {SPEED_OF_LIGHT:.0f}}}"
            rf"{{{wavelength:.4g}}}"
        )
        formula = r"E = \frac{hc}{\lambda}"
    ev = value / ELEMENTARY_CHARGE
    return PhysicsResult(
        answer=(
            rf"{formula} = {substitution} "
            rf"\approx {value:.4g} \text{{ J}}"
        ),
        quantities=(
            QuantityResult("", value, "J"),
            QuantityResult("", ev, "eV"),
        ),
        joiner="paren-second",
        formulas=(formula,),
        substitutions=(f"E = {substitution}",),
    )


def _de_broglie_wavelength(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    momentum = p["m"] * p["v"]
    if momentum <= 0:
        raise SolveServiceError("momentum must be positive")
    value = PLANCK_H / momentum
    return PhysicsResult(
        answer=(
            rf"\lambda = \frac{{h}}{{mv}} = \frac{{{PLANCK_H:.5g}}}"
            rf"{{{p['m']:.4g} \cdot {p['v']:.4g}}} \approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"\lambda = \frac{h}{mv}",),
        substitutions=(rf"\lambda = \frac{{{PLANCK_H:.5g}}}{{{p['m']:.4g} \cdot {p['v']:.4g}}}",),
        quantities=(QuantityResult("", value, "m"),),
    )


def _half_life_remaining(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    halves = p.get("n_halves")
    if halves is None:
        if p["half_life"] <= 0:
            raise SolveServiceError("half-life must be positive")
        if p["elapsed"] < 0:
            raise SolveServiceError("elapsed time cannot be negative")
        halves = p["elapsed"] / p["half_life"]
    if halves < 0:
        raise SolveServiceError("the number of half lives cannot be negative")
    # Answer in the unit the question used. A sample given in grams should
    # not come back in kilograms; the arithmetic is a ratio either way.
    unit = (intent.physics_units or {}).get("m", "kg")
    given = (intent.physics_params or {}).get("m", p["m"])
    value = given / (2**halves)
    return PhysicsResult(
        answer=(
            rf"N = \frac{{N_0}}{{2^n}} = \frac{{{given:g}}}{{2^{{{halves:g}}}}} "
            rf"\approx {value:.4g} \text{{ {unit}}}"
        ),
        formulas=(r"N = \frac{N_0}{2^n}",),
        substitutions=(rf"N = \frac{{{given:g}}}{{2^{{{halves:g}}}}}",),
        quantities=(QuantityResult("", value, unit),),
    )


def _mass_energy(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["m"] * SPEED_OF_LIGHT**2
    return PhysicsResult(
        answer=(
            rf"E = mc^2 = {p['m']:g} \cdot ({SPEED_OF_LIGHT:.0f})^2 "
            rf"\approx {value:.4g} \text{{ J}}"
        ),
        formulas=(r"E = mc^2",),
        substitutions=(rf"E = {p['m']:g} \cdot ({SPEED_OF_LIGHT:.0f})^2",),
        quantities=(QuantityResult("", value, "J"),),
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "lorentz_factor": _relativity,
    "time_dilation": _relativity,
    "length_contraction": _relativity,
    "photoelectric_kinetic_energy": _photoelectric_kinetic_energy,
    "uncertainty_momentum": _uncertainty_momentum,
    "particle_box_energy": _particle_box_energy,
    "hydrogen_energy_level": _hydrogen_energy_level,
    "compton_shift": _compton_shift,
    "wien_peak": _wien_peak,
    "stefan_boltzmann_power": _stefan_boltzmann_power,
    "photon_energy": _photon_energy,
    "de_broglie_wavelength": _de_broglie_wavelength,
    "half_life_remaining": _half_life_remaining,
    "mass_energy": _mass_energy,
}
