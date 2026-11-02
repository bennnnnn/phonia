"""One-number laws a question can state in full."""

from __future__ import annotations

import pytest

from app.modules.physics.extract import extract_physics_intent
from app.tests.modules.physics.support import answer_number
from app.tests.modules.physics.test_physics_binding import _answer

_CASES = [
    (
        "An ideal gas has 1.00e24 molecules, temperature 300 K, and volume 0.0200 m^3. "
        "Find the pressure.",
        "molecule_gas_pressure",
        2.07e5,
    ),
    (
        "An ideal gas has 1.00e24 molecules, pressure 1.00e5 Pa, and temperature 300 K. "
        "Find the volume.",
        "molecule_gas_volume",
        0.0414,
    ),
    (
        "An ideal gas has pressure 1.00e5 Pa, volume 0.0200 m^3, and temperature 300 K. "
        "Find the number of molecules.",
        "molecule_gas_count",
        4.83e23,
    ),
    (
        "How many molecules are in an ideal gas at a pressure of 1.00e5 Pa, "
        "a volume of 0.0200 m^3, and a temperature of 300 K?",
        "molecule_gas_count",
        4.83e23,
    ),
    (
        "An ideal gas has 1.00e24 molecules, pressure 1.00e5 Pa, and volume 0.0200 m^3. "
        "Find the temperature.",
        "molecule_gas_temperature",
        145,
    ),
    (
        "An ideal gas at pressure 1.00e5 Pa and temperature 300 K has molar mass "
        "0.0320 kg/mol. Find the density.",
        "ideal_gas_density",
        1.28,
    ),
    (
        "A capacitor stores charge 2.00e-4 C and has capacitance 1.00e-6 F. "
        "Find the stored energy.",
        "capacitor_energy_charge",
        0.02,
    ),
    (
        "A capacitor has charge 2.00e-4 C and voltage 12.0 V. Find the stored energy.",
        "capacitor_energy_charge_voltage",
        0.0012,
    ),
    (
        "A plane wave carries 4.00 W across an area of 2.00e-4 m^2. Find the intensity.",
        "plane_wave_intensity",
        20000,
    ),
    (
        "An electromagnetic wave has magnetic field 2.00e-6 T. Find the electric field.",
        "em_wave_electric_field",
        600,
    ),
    (
        "An electromagnetic wave has electric field 3000 V/m. Find the magnetic field.",
        "em_wave_magnetic_field",
        1e-5,
    ),
    (
        "The electric field is 100 V/m and the magnetic field is 1.00e-6 T. "
        "Find the Poynting magnitude.",
        "poynting_magnitude",
        79.6,
    ),
    (
        "Young's modulus is 2.00e11 Pa and the density is 7800 kg/m^3. Find the wave speed.",
        "rod_wave_speed",
        5060,
    ),
    (
        "The shear modulus is 8.00e10 Pa and the density is 7800 kg/m^3. "
        "Find the shear-wave speed.",
        "shear_wave_speed",
        3200,
    ),
    (
        "A Lorentz transformation at 0.600c maps an event at coordinate 100 m and "
        "time 1.00e-6 s. Find the transformed coordinate.",
        "lorentz_coordinate",
        -99.8,
    ),
    (
        "A Lorentz transformation at 0.600c maps an event at coordinate 100 m and "
        "time 1.00e-6 s. Find the transformed time.",
        "lorentz_time",
        1e-6,
    ),
    (
        "In the Bohr model, n = 2. Find the angular momentum.",
        "bohr_angular_momentum",
        2.11e-34,
    ),
    (
        "The orbital quantum number is 2. Find the angular momentum squared.",
        "orbital_angular_momentum_squared",
        6.67e-68,
    ),
    (
        "The magnetic quantum number is 2. Find the z component of angular momentum.",
        "angular_momentum_z",
        2.11e-34,
    ),
    (
        "A hydrogen-like ion has atomic number Z = 2 and n = 3. Find the orbit radius.",
        "hydrogenlike_radius",
        2.38e-10,
    ),
    (
        "The magnetic quantum number is 1 and the field is 0.500 T. Find the Zeeman shift.",
        "zeeman_shift",
        4.64e-24,
    ),
    (
        "Find the pair-production threshold energy of an electron.",
        "pair_production_threshold",
        1.64e-13,
    ),
    (
        "The refractive index is 1.50 and the half-angle is 30 degrees. "
        "Find the numerical aperture.",
        "numerical_aperture",
        0.75,
    ),
    (
        "A diffraction grating has 600 lines and the order is 2. Find the resolving power.",
        "grating_resolving_power",
        1200,
    ),
    (
        "A diffraction grating has 800 lines and is used in second order. "
        "Find the resolving power.",
        "grating_resolving_power",
        1600,
    ),
    (
        "In the BCS approximation, the critical temperature is 10.0 K. Find the energy gap.",
        "bcs_gap",
        2.44e-22,
    ),
    (
        "Find the Hawking power of the Sun.",
        "hawking_power",
        9.01e-29,
    ),
    (
        "In the Friedmann equation, the density is 1.00e-26 kg/m^3, the curvature is 0, "
        "the scale factor is 1.00e26 m, and the cosmological constant is 1.00e-20 /m^2. "
        "Find the Hubble parameter.",
        "friedmann_hubble",
        0.0173,
    ),
    (
        "In the Friedmann equation, the density is 1.00e-26 kg/m^3, the curvature is 0, "
        "the scale factor is 1.00e26 m, and the cosmological constant is 1.00e-52 /m^2. "
        "Find the Hubble parameter.",
        "friedmann_hubble",
        2.930409372178323e-18,
    ),
    (
        "For the virial theorem, the potential energy is -2.00e11 J. Find the kinetic energy.",
        "virial_kinetic_energy",
        1e11,
    ),
    (
        "For the virial theorem, the kinetic energy is 1.00e11 J. Find the potential energy.",
        "virial_potential_energy",
        -2e11,
    ),
    (
        "The Higgs vacuum expectation value is 2.46e5 MeV and the self-coupling is 0.129. "
        "Find the Higgs mass.",
        "higgs_mass",
        2.23e-25,
    ),
    (
        "In QCD, the momentum scale is 2000 MeV, the Lambda scale is 200 MeV, and there "
        "are 5 flavors. Find the strong coupling.",
        "strong_coupling",
        0.356,
    ),
]


@pytest.mark.parametrize(("text", "operation", "value"), _CASES)
def test_a_stated_form_is_verified(text: str, operation: str, value: float) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    answer = _answer(text)
    assert answer is not None
    assert answer_number(answer) == pytest.approx(value, rel=0.02)


def test_resolving_power_without_an_order_declines() -> None:
    assert _answer("A diffraction grating has 800 lines. Find the resolving power.") is None


def test_a_hydrogenlike_radius_without_z_declines() -> None:
    assert _answer("A hydrogen-like ion has n = 3. Find the orbit radius.") is None


def test_a_friedmann_parameter_without_lambda_declines() -> None:
    assert (
        _answer(
            "In the Friedmann equation, the density is 1.00e-26 kg/m^3, the curvature is 0, "
            "and the scale factor is 1.00e26 m. Find the Hubble parameter."
        )
        is None
    )
