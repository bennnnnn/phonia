# ruff: noqa: RUF003 -- each constant's comment writes its textbook symbol (σ, μ₀).
"""The physical constants physics solves and prints with, each read once from Pint.

One home for every solver, extractor and the expression notation, so no file types a
constant again. A test pins each CODATA magnitude, so a Pint upgrade cannot move an answer.
Values are in SI base units.
"""

from __future__ import annotations

import math

from app.services.units import constant

SPEED_OF_LIGHT = constant("speed_of_light")  # c, m/s
ELEMENTARY_CHARGE = constant("elementary_charge")  # e, C
ELECTRON_MASS = constant("electron_mass")  # mₑ, kg
PROTON_MASS = constant("proton_mass")  # kg
NEUTRON_MASS = constant("neutron_mass")  # kg
PLANCK_H = constant("planck_constant")  # h, J·s
HBAR = constant("hbar")  # ħ, J·s
BIG_G = constant("gravitational_constant")  # G, N·m²/kg²
GAS_CONSTANT = constant("molar_gas_constant")  # R, J/(mol·K)
BOLTZMANN = constant("boltzmann_constant")  # k_B, J/K
STEFAN_BOLTZMANN = constant("stefan_boltzmann_constant")  # σ, W/(m²·K⁴)
WIEN_B = constant("wien_wavelength_displacement_law_constant")  # b, m·K
RYDBERG = constant("rydberg_constant")  # R∞, 1/m
BOHR_RADIUS = constant("bohr_radius")  # a₀, m
EPSILON_0 = constant("vacuum_permittivity")  # ε₀, F/m
MU_0 = constant("vacuum_permeability")  # μ₀, H/m
COULOMB_K = 1.0 / (4.0 * math.pi * EPSILON_0)  # k_e, N·m²/C²
