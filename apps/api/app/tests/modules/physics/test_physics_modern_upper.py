"""Photons, atoms, decay, relativity and orbits read from the catalog, worked by hand."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.givens import scan_givens

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    ("text", "operation", "answer"),
    [
        (
            "Light of frequency 1.2 × 10^15 Hz shines on a metal with work function 2.3 eV. "
            "Find the maximum kinetic energy of the photoelectrons.",
            "photoelectric_kinetic_energy",
            "4.27 × 10⁻¹⁹ J (2.66 eV)",
        ),
        (
            "Light of frequency 1.2 × 10^15 Hz falls on a metal with work function 2.3 eV. "
            "Find the stopping potential.",
            "stopping_potential",
            "2.66 V",
        ),
        (
            # 1e15 Hz is a frequency the kinetic-energy reader can see. The ask is volts.
            "The photoelectric work function is 2.00 eV and the frequency is 1.00e15 Hz. "
            "Find the stopping potential.",
            "stopping_potential",
            "2.14 V",
        ),
        (
            "A metal has a work function of 2.3 eV. Find the threshold frequency.",
            "threshold_frequency",
            "5.56 × 10¹⁴ Hz",
        ),
        (
            "A metal has a work function of 2.3 eV. Find the threshold wavelength.",
            "threshold_wavelength",
            "5.39 × 10⁻⁷ m",
        ),
        # The photon-energy extractor no longer claims a momentum question.
        (
            "Find the momentum of a photon of wavelength 500 nm.",
            "photon_momentum",
            "1.33 × 10⁻²⁷ kg·m/s",
        ),
        (
            "A radioactive sample has a half-life of 5 days. What fraction remains after 20 days?",
            "half_life_fraction",
            "0.0625",
        ),
        (
            "A 10 g sample has a half-life of 5 days. What mass remains after 20 days?",
            "half_life_remaining",
            "0.625 g",
        ),
        (
            "A radioactive isotope has a half-life of 5 days. Find the decay constant.",
            "decay_constant",
            # ln 2 / 5 days, per the day the half-life was given in (1.6e-6 1/s).
            "0.139 1/day",
        ),
        (
            "A sample contains 2 × 10^20 nuclei with a half-life of 5 days. Find its activity.",
            "activity_from_half_life",
            "3.21 × 10¹⁴ Bq",
        ),
        (
            "A radioactive isotope has a half-life of 5 days. Find the mean lifetime.",
            "mean_lifetime",
            "7.21 days",
        ),
        (
            "An electron in hydrogen falls from n = 3 to n = 2. "
            "Find the wavelength of the emitted photon.",
            "hydrogen_transition_wavelength",
            "6.56 × 10⁻⁷ m",  # 1/(R∞·(1/4 - 1/9))
        ),
        (
            # Was -1.51 eV: the level formula took n = 3 and ignored n = 2.
            "An electron in hydrogen falls from n = 3 to n = 2. "
            "Find the energy of the emitted photon in eV.",
            "hydrogen_transition_energy",
            "1.89 eV",
        ),
        (
            "Find the radius of the n = 2 orbit in the Bohr model of hydrogen.",
            "bohr_orbit_radius",
            "2.12 × 10⁻¹⁰ m",
        ),
        (
            "A quantum harmonic oscillator has angular frequency 1 × 10^14 rad/s. "
            "Find the energy of its ground state.",
            "quantum_oscillator_energy",
            "5.27 × 10⁻²¹ J",  # ħω/2
        ),
        (
            "A proton moves at 0.8c. Find its relativistic momentum.",
            "relativistic_momentum",
            "6.69 × 10⁻¹⁹ kg·m/s",  # gamma = 5/3
        ),
        (
            "An electron moves at 0.6c. Find its kinetic energy.",
            "relativistic_kinetic_energy",
            "2.05 × 10⁻¹⁴ J",  # (1.25 - 1)·mc²
        ),
        (
            # A space before c is still a fraction of the speed of light.
            "A proton moves at 0.8 c. Find its relativistic momentum.",
            "relativistic_momentum",
            "6.69 × 10⁻¹⁹ kg·m/s",
        ),
        (
            "An electron moves at 0.6 c. Find its total energy.",
            "relativistic_total_energy",
            "1.02 × 10⁻¹³ J",  # 1.25·mc²
        ),
        (
            "A spaceship moving at 0.6c fires a probe forward at 0.5c relative to the ship. "
            "Find the speed of the probe relative to Earth.",
            "relativistic_velocity_addition",
            "0.846 c",  # 1.1 / 1.3
        ),
        ("Find the Schwarzschild radius of the Sun.", "schwarzschild_radius", "2953 m"),
        (
            "Two energy levels are separated by 0.1 eV. "
            "Find the Boltzmann population ratio at 300 K.",
            "boltzmann_population_ratio",
            "0.0209",
        ),
        (
            "A system has 1 × 10^23 microstates. Find its entropy.",
            "boltzmann_entropy",
            "7.31 × 10⁻²² J/K",
        ),
        (
            "An excited state has a lifetime of 1 × 10^-8 s. "
            "Find the minimum uncertainty in its energy.",
            "energy_time_uncertainty",
            "5.27 × 10⁻²⁷ J",
        ),
        (
            # r = R_Earth + 400 km = 6771 km.
            "Find the period of a satellite orbiting 400 km above Earth.",
            "kepler_period_altitude",
            "5545 s",
        ),
    ],
)
def test_a_stated_law_is_read_and_verified(text: str, operation: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None and intent.physics_op == operation
    assert _answer(text) == answer
    block = build_verified_physics_block(intent, _SETTINGS)
    assert block is not None and maybe_direct_physics_reply(block, text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Below the threshold no electron leaves.
        "Light of frequency 3 × 10^14 Hz falls on a metal with work function 2.3 eV. "
        "Find the stopping potential.",
        # A probe fired backward subtracts.
        "A spaceship moving at 0.6c fires a probe backward at 0.5c relative to the ship. "
        "Find the speed of the probe relative to Earth.",
        # Two times and no word saying which is the half-life.
        "A sample decays for 20 days and 5 days. What fraction remains?",
        # A mass is not a count of nuclei.
        "A 2 g sample has a half-life of 5 days. Find its activity.",
        # No body named, so no radius to add the height to.
        "A satellite orbits at a height of 400 km. Find its orbital period.",
    ],
)
def test_a_question_the_catalog_cannot_read_exactly_declines(text: str) -> None:
    assert _answer(text) is None


def test_a_slow_car_is_not_answered_with_relativity() -> None:
    intent = extract_physics_intent("A 1000 kg car moves at 20 m/s. Find its momentum.")
    assert intent is not None and intent.physics_op == "momentum"


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("moves at 0.8c", "c"),  # written onto the number: the speed of light
        ("moves at 0.8 c.", "c"),  # a decimal below 1, then c: still a speed
        ("question 2 c) a car", ""),  # a part label, not a speed
        ("part 2 c. A car", ""),  # a whole number before a spaced c is a label
        ("mu is 0.3 c) Find", ""),  # "c)" labels a part even after a fraction
        ("12e-6 /°C", "/°C"),
        ("2e20 nuclei", "nuclei"),
        ("3.7e10 Bq", "Bq"),
    ],
)
def test_the_givens_scanner_reads_the_new_units(text: str, unit: str) -> None:
    assert scan_givens(text)[0].unit == unit
