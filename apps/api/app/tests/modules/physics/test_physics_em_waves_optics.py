"""Circuits, fields, waves and optics read from the catalog, worked by hand."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.bodies import named_particle_charge
from app.modules.physics.constants import ELEMENTARY_CHARGE
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.solvers.si import to_si

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
            "A charge of 30 C flows through a wire in 10 s. Find the current.",
            "current_from_charge",
            "3 A",
        ),
        (
            "A copper wire is 10 m long with cross-sectional area 1 mm^2. The resistivity of "
            "copper is 1.7 × 10^-8 ohm m. Find its resistance.",
            "resistivity_resistance",
            "0.17 Ω",  # 1.7e-8 · 10 / 1e-6
        ),
        (
            "A 200 µF capacitor is connected to a 6 V battery. Find the charge stored on the capacitor.",
            "capacitor_charge",
            "0.0012 C",
        ),
        (
            "A capacitor of 50 µF stores a charge of 1 mC. Find the potential difference across it.",
            "capacitor_voltage",
            "20 V",
        ),
        (
            "Find the time constant of a circuit with a 10 kΩ resistor and a 1 µF capacitor.",
            "rc_time_constant",
            "0.01 s",
        ),
        # Like givens in µF answer in µF: 4·6/(4+6) and 4+6.
        (
            "Find the total capacitance of a 4 µF and a 6 µF capacitor in series.",
            "capacitors_series",
            "2.4 µF",
        ),
        (
            "Find the total capacitance of a 4 µF and a 6 µF capacitor in parallel.",
            "capacitors_parallel",
            "10 µF",
        ),
        (
            "A 100 µF capacitor is charging through a 10 kΩ resistor from a 12 V supply. "
            "Find the voltage after 1 s.",
            "capacitor_charging_voltage",
            "7.59 V",  # 12(1 - e⁻¹)
        ),
        (
            "A 100 µF capacitor is discharged through a 10 kΩ resistor after being charged to "
            "12 V. Find the voltage after 1 s.",
            "capacitor_discharge_voltage",
            "4.41 V",  # 12e⁻¹; "charged" in the story is not a charging circuit
        ),
        (
            "A transformer has 100 turns on the primary and 500 turns on the secondary. "
            "The primary voltage is 230 V. Find the secondary voltage.",
            "transformer_voltage",
            "1150 V",  # the role words follow the counts
        ),
        (
            "Two parallel plates 2 cm apart have a potential difference of 100 V. "
            "Find the electric field between them.",
            "plate_field",
            "5000 V/m",
        ),
        (
            "A charge of 2 × 10^-6 C is in an electric field of 5000 N/C. Find the force on the charge.",
            "field_force_on_charge",
            "0.01 N",
        ),
        (
            "An electron is accelerated through a potential difference of 100 V. Find the energy gained.",
            "charge_energy",
            "1.6 × 10⁻¹⁷ J",  # e · 100
        ),
        (
            "An electron is accelerated through a potential difference of 100 V. "
            "Find the energy gained in eV.",
            "charge_energy",
            "100 eV",
        ),
        (
            "A proton is in an electric field of 2000 N/C. Find the force on it.",
            "field_force_on_charge",
            "3.2 × 10⁻¹⁶ N",
        ),
        (
            # 500 turns are a count: μ₀·500·2/0.25, not 500 revolutions of 2π rad.
            "A solenoid of length 0.25 m has 500 turns and carries a current of 2 A. "
            "Find the magnetic field inside it.",
            "solenoid_field",
            "0.00503 T",
        ),
        (
            "A string fixed at both ends is 0.5 m long and waves travel along it at 150 m/s. "
            "Find the fundamental frequency.",
            "resonance_frequency",
            "150 Hz",  # v/2L
        ),
        (
            "Light travels from air into glass of refractive index 1.5 at an angle of incidence "
            "of 40 degrees. Find the angle of refraction.",
            "snell_refraction_angle",
            "25.4°",
        ),
        ("Find the power of a lens of focal length 25 cm.", "lens_power", "4 D"),
        (
            "Light of wavelength 600 nm passes through a diffraction grating with 300 lines per mm. "
            "Find the angle of the first order maximum.",
            "grating_angle",
            "10.4°",  # asin(600e-9 · 3e5)
        ),
        (
            "A diffraction grating has a line density of 5.00e5 /m. Light of wavelength 600 nm "
            "is seen in the first order. Find the angle.",
            "grating_angle",
            "17.5°",  # asin(600e-9 · 5e5)
        ),
        (
            "A concave mirror has a radius of curvature of 40 cm. Find its focal length.",
            "mirror_focal_length",
            "20 cm",
        ),
        (
            "An object is placed 30 cm from a lens and the image forms 60 cm from the lens. "
            "Find the magnification.",
            "magnification_distances",
            "-2",  # -v/u: a real image is inverted
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
        # Series or parallel is not said.
        "Find the total capacitance of a 4 µF and a 6 µF capacitor.",
        # A virtual image's distance carries the other sign.
        "An object is 30 cm from a lens and forms a virtual image 60 cm from the lens. "
        "Find the magnification.",
        # Which medium the light leaves is not said.
        "Light passes between materials of refractive index 1.5 and 1.0 at 30 degrees. "
        "Find the angle of refraction.",
        # Neither charging nor discharging.
        "A 100 µF capacitor in a circuit with a 10 kΩ resistor and a 12 V supply. "
        "Find the voltage after 1 s.",
        # No separation, so no field.
        "Two parallel plates have a potential difference of 100 V. Find the electric field.",
        # Two particles, two charges.
        "An electron and a proton are accelerated through a potential difference of 100 V. "
        "Find the energy gained.",
        # A price is not an energy.
        "A 2 kW heater runs for 3 hours. Electricity costs 15p per kWh. Find the cost.",
        "A 2 kW heater runs for 3 hours at 15p per kWh. How much does it cost to run?",
        "A 2 kW heater runs for 3 hours. What is the electricity bill at 15p per kWh?",
        # "Respectively": the role words before the list name both counts (was 46 V).
        "A transformer has primary and secondary coils with 100 and 500 turns respectively. "
        "The primary voltage is 230 V. Find the secondary voltage.",
        # A convex mirror's focal length is negative, by a convention not stated.
        "A convex mirror has a radius of curvature of 40 cm. Find its focal length.",
    ],
)
def test_a_question_the_catalog_cannot_read_exactly_declines(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        (
            "A siren of 500 Hz approaches a stationary observer at 20 m/s. "
            "The speed of sound is 340 m/s. Find the frequency heard.",
            "531 Hz (approaching, sound at 340 m/s)",  # 500·340/320
        ),
        (
            "A siren of 500 Hz moves away from a stationary observer at 20 m/s. "
            "The speed of sound is 340 m/s. Find the frequency heard.",
            "472 Hz (receding, sound at 340 m/s)",  # 500·340/360
        ),
        (
            "The speed of sound is 340 m/s. An ambulance siren of 700 Hz approaches a "
            "stationary listener at 30 m/s. What frequency does the listener hear?",
            "768 Hz (approaching, sound at 340 m/s)",
        ),
        (
            # The observer moves; the source is still: 500·350/340.
            "An observer moves at 10 m/s toward a stationary siren of 500 Hz. "
            "The speed of sound is 340 m/s. Find the frequency heard.",
            "515 Hz (approaching, sound at 340 m/s)",
        ),
        (
            "An observer moves at 10 m/s away from a stationary siren of 500 Hz. "
            "The speed of sound is 340 m/s. Find the frequency heard.",
            "485 Hz (receding, sound at 340 m/s)",  # 500·330/340
        ),
        (
            # Was 506 Hz: 72 km/h was read as 72 m/s. It is 20 m/s: 400·343/323.
            "A train whistle of 400 Hz approaches at 72 km/h. Find the observed frequency.",
            "425 Hz (approaching, sound at 343 m/s)",
        ),
    ],
)
def test_doppler_reads_who_moves_and_the_stated_speed_of_sound(text: str, answer: str) -> None:
    assert _answer(text) == answer


def test_a_cyclist_toward_a_still_siren_is_a_moving_observer() -> None:
    intent = extract_physics_intent(
        "A cyclist rides at 50 m/s toward a stationary siren of 500 Hz. Find the frequency heard."
    )
    assert intent is not None
    assert intent.physics_params == {"freq": 500.0, "v_src": 0.0, "v_sound": 343.0, "v_obs": 50.0}


@pytest.mark.parametrize(
    "text",
    [
        # No direction: toward and away give different answers.
        "A siren of 500 Hz moves at 20 m/s. The speed of sound is 340 m/s. Find the frequency heard.",
        # Both move, one speed: whose is it?
        "A source of 500 Hz and an observer both move at 20 m/s toward each other. "
        "The speed of sound is 340 m/s. Find the frequency heard.",
    ],
)
def test_doppler_without_a_role_or_direction_declines(text: str) -> None:
    assert _answer(text) is None


def test_a_stated_charge_beats_the_named_particle() -> None:
    intent = extract_physics_intent(
        "An electron with charge 1.6 × 10^-19 C is accelerated through a potential "
        "difference of 100 V. Find the kinetic energy gained."
    )
    assert intent is not None and intent.physics_params is not None
    assert intent.physics_params["Q"] == pytest.approx(1.6e-19)


@pytest.mark.parametrize(
    ("text", "charge"),
    [
        ("an electron is fired", ELEMENTARY_CHARGE),
        ("a proton moves", ELEMENTARY_CHARGE),
        ("an alpha particle", 2 * ELEMENTARY_CHARGE),
        ("an electron hits a proton", None),
        ("an electronic circuit", None),
    ],
)
def test_named_particle_charge(text: str, charge: float | None) -> None:
    assert named_particle_charge(text) == charge


@pytest.mark.parametrize(
    ("value", "unit", "key", "si"),
    [
        (500.0, "turns", "turns", 500.0),  # a count, not 500 revolutions
        (300.0, "lines per mm", "line_density", 3.0e5),  # read from the givens table
        (2.0, "cm", "d", 0.02),
    ],
)
def test_to_si_reads_counts_and_spelled_units(value: float, unit: str, key: str, si: float) -> None:
    assert to_si(value, unit, expected_key=key) == pytest.approx(si)


def test_givens_in_different_units_answer_in_si() -> None:
    # 4 µF + 6 nF: no one unit to answer in, so farads.
    assert (
        _answer("Find the total capacitance of a 4 µF and a 6 nF capacitor in parallel.")
        == "4.01 × 10⁻⁶ F"
    )


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # One free end is a quarter-wave resonator: v/4L, not v/2L (was 150 Hz).
        (
            "A string fixed at one end and free at the other is 0.5 m long. "
            "Waves travel along it at 150 m/s. Find the fundamental frequency.",
            "75 Hz",
        ),
        (
            "A pipe open at one end is 0.5 m long. Sound travels at 340 m/s. "
            "Find the fundamental frequency.",
            "170 Hz",
        ),
        # An interchangeable list read "respectively" keeps its order.
        (
            "Find the total capacitance of a 4 µF and a 6 µF capacitor respectively in series.",
            "2.4 µF",
        ),
        # "Bill" is a name here, not a price.
        ("Bill has a mass of 70 kg. What is Bill's weight?", "686.7 N"),
    ],
)
def test_review_cases_answer_the_question_asked(text: str, answer: str) -> None:
    assert _answer(text) == answer


def test_bragg_uses_the_stated_order_and_angle() -> None:
    wavelength = (
        "In Bragg reflection, crystal planes are 0.200 nm apart and the first-order "
        "angle is 30 degrees. Find the wavelength."
    )
    spacing = (
        "X-rays of wavelength 0.154 nm strike a crystal at a Bragg angle of 30 degrees "
        "in the first order. Find the plane spacing."
    )
    assert _answer(wavelength) == "0.2 nm"
    assert _answer(spacing) == "0.154 nm"


@pytest.mark.parametrize(
    "text",
    [
        "Bragg reflection from planes 0.200 nm apart at 30 degrees. Find the wavelength.",
        "First-order Bragg reflection from planes 0.200 nm apart. Find the wavelength.",
    ],
)
def test_bragg_declines_when_the_order_or_the_angle_is_missing(text: str) -> None:
    assert _answer(text) is None
