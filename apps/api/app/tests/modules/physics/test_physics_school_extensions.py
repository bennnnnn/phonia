"""Closed school templates that used to be declined as advanced physics."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.display import plain_number
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    needs_physics,
)

_SETTINGS = Settings(math_tools_enabled=True)

VERIFIED: list[tuple[str, str, str]] = [
    (
        "Kirchhoff's junction rule: currents of 2 A and 3 A enter and 1 A leaves.",
        "kirchhoff_junction",
        "4 A leaving",
    ),
    (
        "Kirchhoff's loop rule for a single loop with a 12 V battery "
        "and resistors of 4 ohm and 2 ohm.",
        "kirchhoff_loop",
        "2 A",
    ),
    (
        "Use Gauss's law to find the field outside a sphere of charge 2e-6 C and radius 0.2 m.",
        "gauss_outside",
        "4.49 × 10⁵ N/C",
    ),
    (
        "Using Gauss's law, a point charge of 4.00 uC. Find the electric field outside "
        "at a distance of 0.200 m from the center.",
        "gauss_outside",
        "8.99 × 10⁵ N/C",
    ),
    (
        "Use Gauss's law for a point inside a hollow shell of charge 2e-6 C "
        "with shell radius 0.5 m and a distance of 0.2 m from the center.",
        "gauss_inside_shell",
        "0 N/C",
    ),
    (
        "Use Gauss's law inside a uniform sphere of charge 2e-6 C "
        "with radius 0.5 m and a distance of 0.2 m from the center.",
        "gauss_inside_sphere",
        "28760 N/C",
    ),
    (
        "Use Gauss's law for an infinite line charge of 2e-6 C/m at a distance of 0.05 m.",
        "gauss_line",
        "7.19 × 10⁵ N/C",
    ),
    (
        "Use Gauss's law for an infinite nonconducting sheet of charge density 2e-6 C/m^2.",
        "gauss_plane",
        "1.13 × 10⁵ N/C",
    ),
    (
        "Faraday's law for 100 turns when the flux changes by 0.02 Wb in 0.1 s.",
        "faraday_emf",
        "20 V",
    ),
    (
        "An inductor of 0.5 H has current change from 1 A to 3 A in 0.1 s. Find the induced emf.",
        "inductor_emf",
        "10 V",
    ),
    (
        "Find the energy stored in a 2 H inductor carrying 3 A.",
        "inductor_energy",
        "9 J",
    ),
    (
        "Find the time constant of an RL circuit with a 2 H inductor and a 4 ohm resistor.",
        "rl_time_constant",
        "0.5 s",
    ),
    (
        "An RL circuit with a 12 V battery, a 4 ohm resistor and a 2 H inductor "
        "is closed. Find the current after 0.5 s as it grows.",
        "rl_growth",
        "1.9 A",
    ),
    (
        "An RL circuit with a 4 ohm resistor and a 2 H inductor is opened. "
        "The current of 3 A decays. Find the current after 0.5 s.",
        "rl_decay",
        "1.1 A",
    ),
    ("What is the rms voltage for a peak of 10 V?", "rms_voltage", "7.07 V"),
    ("What is the rms current for a peak of 2 A?", "rms_current", "1.41 A"),
    ("What is the peak voltage for an rms of 10 V?", "rms_voltage", "14.1 V"),
    ("What is the peak current for an rms of 2 A?", "rms_current", "2.83 A"),
    (
        "Kirchhoff's loop rule for a single loop with a 12 V battery "
        "and resistors of 4 ohm, 2 ohm and 6 ohm.",
        "kirchhoff_loop",
        "1 A",
    ),
    (
        "Faraday's law for 100 turns of area 0.01 m^2 when the field changes "
        "from 0 T to 0.2 T in 0.1 s.",
        "faraday_emf",
        "2 V",
    ),
    (
        "Find the inductive reactance of a 0.2 H inductor at 50 Hz.",
        "inductive_reactance",
        "62.8 Ω",
    ),
    (
        "Find the capacitive reactance of a 1e-4 F capacitor at 50 Hz.",
        "capacitive_reactance",
        "31.8 Ω",
    ),
    (
        "Find the series impedance for a resistance of 30 ohm, "
        "inductive reactance of 40 ohm and capacitive reactance of 10 ohm.",
        "series_impedance",
        "42.4 Ω",
    ),
    (
        "Find the resonant frequency of an LC circuit with inductance 1 H and capacitance 1e-6 F.",
        "lc_resonance",
        "159 Hz",
    ),
    (
        "Find the average power of an AC current of 2 A through a resistance of 5 ohm.",
        "ac_average_power",
        "20 W",
    ),
    (
        "Use Poiseuille's law for a pipe of radius 0.001 m and length 0.1 m "
        "with pressure difference 1000 Pa and viscosity 0.001 Pa*s.",
        "poiseuille_flow",
        "3.93 × 10⁻⁶ m³/s",
    ),
    (
        "Using Poiseuille's law, a tube of radius 1.00 mm and length 0.200 m "
        "has a pressure difference of 2000 Pa. The viscosity is 0.00100 Pa*s. "
        "Find the volume flow rate.",
        "poiseuille_flow",
        "3.93 × 10⁻⁶ m³/s",
    ),
    (
        "Use Bernoulli for water flow with initial height of 5 m and final height of 1 m. "
        "P1 is 100000 Pa, density 1000 kg/m^3, v1 is 2 m/s and v2 is 2 m/s. Find P2.",
        "bernoulli_pressure",
        "139240 Pa",
    ),
    (
        "Find the gravitational potential of a 6e24 kg mass at a distance of 6e6 m.",
        "gravitational_potential",
        "-6.67 × 10⁷ J/kg",
    ),
    (
        "Find the gravitational potential energy of a 6e24 kg mass and a 1 kg mass "
        "separated by a distance of 6e6 m.",
        "gravitational_potential_energy",
        "-6.67 × 10⁷ J",
    ),
    (
        "Find the orbital energy of a 6e24 kg mass and a 1 kg mass at a distance of 6e6 m.",
        "orbital_energy",
        "-3.34 × 10⁷ J",
    ),
    (
        "Use Kepler's law for a 6e24 kg mass and an orbital radius of 6e6 m. Find the period.",
        "kepler_period",
        "4615 s",
    ),
    (
        "Find the internal energy of 2 mol of monatomic ideal gas at 300 K.",
        "monatomic_energy",
        "7483 J",
    ),
    (
        "An isobaric expansion at a pressure of 100000 Pa changes volume "
        "from 0.01 m^3 to 0.03 m^3. Find the work.",
        "isobaric_work",
        "2000 J",
    ),
    (
        "An adiabatic expansion with gamma of 1.4 starts at 200000 Pa and volume 0.01 m^3 "
        "and ends at volume 0.02 m^3. Find the final pressure.",
        "adiabatic_pressure",
        "75786 Pa",
    ),
    (
        "An adiabatic process with gamma of 1.4 starts at 200000 Pa and volume 0.01 m^3 "
        "and ends at 100000 Pa. Find the final volume.",
        "adiabatic_volume",
        "0.0164 m³",
    ),
    (
        "Find the coefficient of performance of a refrigerator with a hot reservoir "
        "at 300 K and a cold reservoir at 250 K.",
        "refrigerator_cop",
        "5",
    ),
    (
        "Find the coefficient of performance of a heat pump with a hot reservoir "
        "at 300 K and a cold reservoir at 250 K.",
        "heat_pump_cop",
        "6",
    ),
    (
        "What is the volume of 2 mol of ideal gas at 300 K and a pressure of 101325 Pa?",
        "ideal_gas_volume",
        "0.0492 m³",
    ),
    (
        "How many moles of ideal gas are in a volume of 0.05 m^3 at a pressure of 101325 Pa "
        "and a temperature of 300 K?",
        "ideal_gas_amount",
        "2.03 mol",
    ),
    (
        "What is the temperature of 2 mol of ideal gas in a volume of 0.05 m^3 "
        "at a pressure of 101325 Pa?",
        "ideal_gas_temperature",
        "305 K",
    ),
    (
        "what is the force on a charge of 2 C moving at 10 m/s "
        "in a 0.4 T magnetic field at 30 degrees",
        "magnetic_force_charge",
        "4 N",
    ),
    (
        "what is the force on a 2 m wire carrying 3 A in a 0.5 T magnetic field at 30 degrees",
        "magnetic_force_wire",
        "1.5 N",
    ),
    (
        "what is the magnetic flux through 0.2 m^2 in a 0.5 T field at 60 degrees",
        "magnetic_flux",
        "0.05 Wb",
    ),
    (
        "Doppler effect: the source approaches at 30 m/s and the observer approaches "
        "at 10 m/s. The frequency is 500 Hz.",
        "doppler_frequency",
        "564 Hz (approaching, sound at 343 m/s)",
    ),
]

REFUSED = [
    "Use Bernoulli for water flow. P1 is 100000 Pa, density 1000 kg/m^3, "
    "v1 is 2 m/s and v2 is 6 m/s. Find P2.",
    "Use Poiseuille's law for a pipe of radius 0.001 m and length 0.1 m "
    "with pressure difference 1000 Pa.",
    "Use Gauss's law for a charge of 2e-6 C.",
    "A gaussian of charge 2e-6 C and radius 0.2 m.",
    "Kirchhoff's junction rule with currents of 2 A, 3 A and 1 A.",
    "Kirchhoff's loop rule with batteries of 12 V and 6 V and resistors of 4 ohm and 2 ohm.",
    "An adiabatic expansion starts at 200000 Pa and volume 0.01 m^3 and ends at volume 0.02 m^3.",
    "what is the pressure of 2 moles of ideal gas at 300 degrees in 0.05 m^3",
    "what is the observed frequency of a 400 Hz siren moving at 30 m/s",
]


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(("text", "operation", "answer"), VERIFIED)
def test_school_extension_is_verified(text: str, operation: str, answer: str) -> None:
    assert needs_physics(text)
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == operation
    assert _answer(text) == answer


@pytest.mark.parametrize("text", REFUSED)
def test_incomplete_school_template_is_not_answered(text: str) -> None:
    assert _answer(text) is None


def test_series_impedance_from_henry_farad_and_hertz() -> None:
    import math

    text = (
        "Find the series impedance for a resistance of 3 ohm, "
        "an inductance of 1 H and a capacitance of 1e-6 F at 50 Hz."
    )
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "series_impedance"
    params = intent.physics_params
    assert params is not None
    assert params["R"] == 3
    assert params["inductance"] == 1
    assert params["capacitance"] == 1e-6
    assert params["freq"] == 50
    inductive = 2 * math.pi * params["freq"] * params["inductance"]
    capacitive = 1 / (2 * math.pi * params["freq"] * params["capacitance"])
    expected = math.sqrt(params["R"] ** 2 + (inductive - capacitive) ** 2)
    assert _answer(text) == f"{plain_number(expected)} Ω"


def test_conceptual_gauss_is_not_forced_into_physics() -> None:
    assert needs_physics("what is Gauss's law") is False


@pytest.mark.parametrize("body", ["Jupiter", "the Sun"])
def test_horizontal_bernoulli_on_a_body_without_school_g_still_answers(body: str) -> None:
    # The height variant declares g. This selection does not use it, so the body
    # must not decline the question.
    text = (
        f"Use Bernoulli for horizontal water flow on {body}: P1 is 100000 Pa, density "
        "1000 kg/m^3, v1 is 2 m/s and v2 is 6 m/s. Find P2."
    )
    assert _answer(text) == "84000 Pa"


def test_bernoulli_with_height_on_jupiter_declines() -> None:
    text = (
        "Use Bernoulli for water flow with initial height of 5 m and final height of 1 m "
        "on Jupiter. P1 is 100000 Pa, density 1000 kg/m^3, v1 is 2 m/s and v2 is 2 m/s. "
        "Find P2."
    )
    assert _answer(text) is None


def test_horizontal_bernoulli_on_the_moon_does_not_take_the_moon_g() -> None:
    text = (
        "Use Bernoulli for horizontal water flow on the Moon: P1 is 100000 Pa, density "
        "1000 kg/m^3, v1 is 2 m/s and v2 is 6 m/s. Find P2."
    )
    assert _answer(text) == "84000 Pa"


def test_schrodinger_stays_recognized_and_unverified() -> None:
    text = "Derive the time-dependent Schrodinger equation for this Hamiltonian."
    assert needs_physics(text) is True
    assert extract_physics_intent(text) is None
