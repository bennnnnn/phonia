# ruff: noqa: RUF002 -- textbook formulas use a proper minus sign.
"""Physical constants, reference tables and the weak-equilibrium root the solvers share.

One home, so a solver never imports a sibling solver for a number and two files never carry two
different values of the same constant.
"""

from __future__ import annotations

import math
from itertools import pairwise

from app.services.solving import SolveServiceError
from app.services.units import CELSIUS_OFFSET_K, constant

# CODATA values from the shared unit registry, in the units chemistry works in. A test pins
# each, so a Pint upgrade cannot move an answer.
GAS_R = constant("molar_gas_constant", "L * atm / (mol * K)")
GAS_R_J = constant("molar_gas_constant", "J / (mol * K)")
BOLTZMANN = constant("boltzmann_constant", "J / K")
PLANCK = constant("planck_constant", "J * s")
FARADAY = constant("faraday_constant", "C / mol")
AVOGADRO = constant("avogadro_constant", "1 / mol")
PROTON_U = constant("proton_mass", "u")
NEUTRON_U = constant("neutron_mass", "u")
# The energy equivalent of 1 u.
MEV_PER_U = constant("atomic_mass_constant * speed_of_light ** 2", "MeV")
# 25 °C, the temperature standard values (E°, ΔG°, Kw) are tabulated at.
STANDARD_TEMPERATURE_K = CELSIUS_OFFSET_K + 25
# Water's ion product at 25 °C is a tabulated value, not a constant of nature.
KW = 1.0e-14
PKW = 14  # -log10(KW), so pH + pOH

# Standard reduction potential and electrons for the common aqueous ion.
STANDARD_REDUCTION: dict[str, tuple[float, int]] = {
    "Li": (-3.04, 1),
    "K": (-2.93, 1),
    "Ba": (-2.91, 2),
    "Ca": (-2.87, 2),
    "Na": (-2.71, 1),
    "Mg": (-2.37, 2),
    "Al": (-1.66, 3),
    "Mn": (-1.18, 2),
    "Zn": (-0.76, 2),
    "Cr": (-0.74, 3),
    "Fe": (-0.44, 2),
    "Cd": (-0.40, 2),
    "Co": (-0.28, 2),
    "Ni": (-0.25, 2),
    "Sn": (-0.14, 2),
    "Pb": (-0.13, 2),
    "H": (0.0, 2),
    "Cu": (0.34, 2),
    "Ag": (0.80, 1),
    "Hg": (0.85, 2),
    "Au": (1.50, 3),
}

# Below this an ion concentration is comparable to the 1e-7 M that water supplies itself.
_DILUTE_ION = 1.0e-6
# mmHg vapor pressure of water. Values between points are linearly interpolated.
WATER_VAPOR_MMHG: tuple[tuple[float, float], ...] = (
    (0, 4.58),
    (5, 6.54),
    (10, 9.21),
    (15, 12.79),
    (20, 17.54),
    (25, 23.76),
    (30, 31.82),
    (35, 42.18),
    (40, 55.32),
    (45, 71.88),
    (50, 92.51),
    (60, 149.4),
    (70, 233.7),
    (80, 355.1),
    (90, 525.8),
    (100, 760.0),
)


def weak_dissociation(constant: float, concentration: float) -> float:
    """Positive root of x² + Kx − KC = 0."""
    if constant <= 0 or concentration <= 0:
        raise SolveServiceError("weak equilibrium inputs must be positive")
    discriminant = constant * constant + 4 * constant * concentration
    amount = (-constant + math.sqrt(discriminant)) / 2
    if amount < _DILUTE_ION:
        # Water's own 1e-7 M is no longer negligible, so the quadratic is not the answer.
        raise SolveServiceError("water's contribution is required for this very weak electrolyte")
    return amount


def water_vapor_mmhg(temperature_c: float) -> float | None:
    """Vapor pressure of water. Exact at the table points, log-linear in 1/T between them.

    ln P is close to linear in 1/T (Clausius–Clapeyron), so this is accurate between
    points where a straight line in P would overshoot by 1–2 % (22 °C: 19.83 mmHg).
    """
    points = WATER_VAPOR_MMHG
    if temperature_c < points[0][0] or temperature_c > points[-1][0]:
        return None
    for (left_t, left_p), (right_t, right_p) in pairwise(points):
        if left_t <= temperature_c <= right_t:
            left_inv = 1 / (left_t + CELSIUS_OFFSET_K)
            right_inv = 1 / (right_t + CELSIUS_OFFSET_K)
            span = (1 / (temperature_c + CELSIUS_OFFSET_K) - left_inv) / (right_inv - left_inv)
            return math.exp(math.log(left_p) + span * (math.log(right_p) - math.log(left_p)))
    return None
