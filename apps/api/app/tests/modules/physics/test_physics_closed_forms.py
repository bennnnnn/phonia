"""The one-expression laws added after the catalog close-out."""

from __future__ import annotations

import pytest

from app.modules.physics.extract import extract_physics_intent
from app.tests.modules.physics.support import answer_number
from app.tests.modules.physics.test_physics_binding import _answer

_CASES = [
    (
        "A wire carries 1.60 A through area 1.00e-4 m^2 with number density 1.00e28 /m^3. "
        "Find the drift speed.",
        "drift_speed",
        9.986e-6,
    ),
    (
        "A wire carries 2.00 A. The carrier number density is 8.00e28 per cubic meter "
        "and the cross-sectional area is 1.00e-6 m^2. Find the drift speed.",
        "drift_speed",
        1.5606e-4,
    ),
    (
        "Two parallel wires carry 2.00 A and 3.00 A and are 0.100 m apart. "
        "Find the force per unit length.",
        "wire_force_per_length",
        1.2e-5,
    ),
    (
        "An ideal gas has gamma 1.40, pressure 1.01e5 Pa, and density 1.20 kg/m^3. "
        "Find the speed of sound.",
        "ideal_gas_sound_speed",
        343.27,
    ),
    (
        "An ideal transformer has 100 primary turns, 500 secondary turns, "
        "and primary current 2.00 A. Find the secondary current.",
        "transformer_current",
        0.4,
    ),
    (
        "A parallel-plate capacitor has plate area 0.0200 m^2, separation 0.00100 m, "
        "and dielectric constant 5.00. Find the capacitance.",
        "dielectric_parallel_plate",
        8.854e-10,
    ),
    (
        "A blackbody with emissivity 1 and area 1 m^2 has body temperature 300 K "
        "and surroundings 290 K. Find the net radiated power.",
        "net_blackbody_power",
        58.246,
    ),
    (
        "An adiabatic process has gamma 1.40, initial temperature 300 K, "
        "initial volume 2.00 L, and final volume 1.00 L. Find the final temperature.",
        "adiabatic_temperature",
        395.85,
    ),
    (
        "Cv is 20.8 J/(mol·K). Use Mayer's relation to find the molar heat capacity "
        "at constant pressure.",
        "mayer_cp",
        29.114,
    ),
    (
        "Cp is 29.1 J/(mol·K). Use Mayer's relation to find the molar heat capacity "
        "at constant volume.",
        "mayer_cv",
        20.786,
    ),
    (
        "By Mayer's relation, the molar heat capacity at constant pressure is 29.1 J/mol/K. "
        "Find the molar heat capacity at constant volume.",
        "mayer_cv",
        20.786,
    ),
    (
        "A series circuit has inductive reactance 150 ohm, capacitive reactance 50 ohm, "
        "and resistance 100 ohm. Find the tangent of the phase angle.",
        "series_phase_tangent",
        1.0,
    ),
    (
        "An AC circuit has rms voltage 120 V, rms current 2.00 A, and a phase angle "
        "of 60 degrees. Find the average power.",
        "average_power_phase",
        120.0,
    ),
    (
        "A hydrogen-like ion has atomic number 2 and n = 1. Find its energy.",
        "hydrogenlike_energy",
        -8.716e-18,
    ),
    (
        "A mutual inductance of 0.200 H has its current change by 3.00 A during 0.500 s. "
        "Find the induced emf.",
        "mutual_inductance_emf",
        1.2,
    ),
    (
        "An electric dipole moment of 1.0e-9 C·m is observed at a distance of 0.0500 m "
        "on its axis. Find the electric field.",
        "dipole_field_axis",
        1.438e5,
    ),
    (
        "Masses of 1 kg at 0 m, 2 kg at 2 m, and 3 kg at 6 m. Find the center of mass.",
        "center_of_mass_three",
        3.6667,
    ),
    (
        "A thin film of refractive index 1.40 is viewed in constructive interference "
        "at wavelength 560 nm for order 1. Find the thickness.",
        "thin_film_constructive",
        300,
    ),
    (
        "A thin film of refractive index 1.40 is viewed in destructive interference "
        "at wavelength 560 nm for order 1. Find the thickness.",
        "thin_film_destructive",
        200,
    ),
    (
        "Use the vis-viva equation for the Sun at a distance of 1.47e11 m "
        "with semi-major axis 1.496e11 m. Find the speed.",
        "vis_viva",
        30307,
    ),
    (
        "An electron gas has number density 8.47e28 /m^3. Find the Fermi energy.",
        "fermi_energy",
        1.127e-18,
    ),
    (
        "Using Planck's law, a blackbody at temperature 5800 K emits at wavelength 500 nm. "
        "Find the spectral radiance.",
        "planck_spectral_radiance",
        2.688e13,
    ),
    (
        "A conductor of conductivity 5.80e7 S/m carries a wave of frequency 1.00 MHz. "
        "Find the skin depth.",
        "skin_depth",
        6.609e-5,
    ),
    (
        "A conductor of conductivity 5.80e7 S/m and relative permeability 200 "
        "carries a wave of frequency 1.00 MHz. Find the skin depth.",
        "skin_depth_permeability",
        4.673e-6,
    ),
    (
        "A nonmagnetic conductor has resistivity 1.72e-8 ohm m and a wave of frequency "
        "1.00 MHz. Find the skin depth.",
        "skin_depth_resistivity",
        6.601e-5,
    ),
    (
        "A coaxial cable 2.00 m long has an inner radius of 1.00 mm and an outer radius "
        "of 4.00 mm. Find the capacitance.",
        "coaxial_capacitance",
        8.026e-11,
    ),
    (
        "A spherical capacitor has an inner radius of 10.0 cm and an outer radius of 20.0 cm. "
        "Find the capacitance.",
        "spherical_capacitance",
        2.225e-11,
    ),
    (
        "A resonator has a resonant frequency of 1.00 MHz and a bandwidth of 10.0 kHz. "
        "Find the quality factor.",
        "quality_factor_bandwidth",
        100,
    ),
    (
        "A series circuit has resistance 10.0 ohm, inductance 50.0 mH, and capacitance "
        "2.00 uF. Find the quality factor.",
        "quality_factor_rlc",
        15.811,
    ),
    (
        "An electron of energy 5.00 eV hits a barrier of height 10.0 eV that is 0.100 nm wide. "
        "Find the tunneling probability.",
        "tunnel_probability",
        0.1012,
    ),
]


@pytest.mark.parametrize(("text", "operation", "value"), _CASES)
def test_a_closed_form_is_verified(text: str, operation: str, value: float) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    answer = _answer(text)
    assert answer is not None
    assert answer_number(answer) == pytest.approx(value, rel=0.02)


@pytest.mark.parametrize(
    "text",
    [
        "Two parallel wires carry 2.00 A and 3.00 A. Find the force per unit length.",
        "A hydrogen-like ion has n = 1. Find its energy.",
        "Masses of 1 kg at 0 m, 2 kg at 2 m, 3 kg at 6 m, and 4 kg at 8 m. "
        "Find the center of mass.",
        "A parallel-plate capacitor has plate area 0.02 m^2 and separation 1 mm "
        "and a dielectric. Find the capacitance.",
        "A thin film of refractive index 1.40 at wavelength 560 nm for order 1. "
        "Find the thickness.",
        "Use the vis-viva equation for the Sun at a distance of 1.47e11 m. Find the speed.",
        "An electron of energy 15.0 eV hits a barrier of height 10.0 eV that is 0.100 nm wide. "
        "Find the tunneling probability.",
    ],
)
def test_a_closed_form_with_a_missing_input_declines(text: str) -> None:
    assert _answer(text) is None
