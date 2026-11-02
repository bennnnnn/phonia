"""Answers that were verified and wrong before the number and ask checks.

Each one was reproduced on main: the verified block showed the number in the
comment, with full confidence, under Given/Find/Formula/Answer.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.block import _solve_requested_quantities
from app.modules.physics.givens import unit_dimension
from app.modules.physics.schemas import PhysicsIntent

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


@pytest.mark.parametrize(
    ("text", "was", "now"),
    [
        (
            "Two charges of 2 × 10^-6 C and 3 × 10^-6 C are 0.5 m apart. "
            "Find the electric force between them.",
            "1.294e+12 N",
            "0.216 N",
        ),
        (
            "Light travels at 2 × 10^8 m/s in a medium. Find the refractive index.",
            "3.75e+07",
            "1.5",
        ),
        (
            "Find the energy of a photon of frequency 5 × 10^14 Hz.",
            "9.276e-33 J (0 eV)",
            "3.31 × 10⁻¹⁹ J (2.07 eV)",
        ),
        (
            "Find the de Broglie wavelength of an electron moving at 3 × 10^6 m/s.",
            "0.0001212 m",
            "2.42 × 10⁻¹⁰ m",
        ),
    ],
)
def test_scientific_notation_is_one_number(text: str, was: str, now: str) -> None:
    assert _answer(text) == now != was


def test_a_free_fall_speed_question_gets_a_speed_not_a_time() -> None:
    # Was 4.04 s: the ask fell through to the time-to-ground default.
    assert _answer(
        "A ball is dropped from 80 m. What is its speed just before it hits the ground?"
    ) == ("39.6 m/s")


def test_a_block_refuses_a_result_of_another_dimension() -> None:
    velocity = unit_dimension("meter / second")[0]  # type: ignore[index]
    intent = PhysicsIntent(
        kind="kinematics",
        physics_op="time_to_ground",
        physics_params={"g": 9.81, "h0": 80, "v0": 0},
        physics_units={"g": "m/s^2", "h0": "m", "v0": "m/s"},
        asked=(velocity,),
    )
    assert build_verified_physics_block(intent, _SETTINGS) is None


def test_heat_uses_both_readings_and_the_stated_capacity() -> None:
    # Was 167440 J: J/kg°C was not read, so water's 4186 replaced the stated
    # 4200, and ΔT was the first reading, 20, instead of 80 - 20.
    text = (
        "How much energy is needed to heat 2 kg of water from 20 °C to 80 °C? "
        "The specific heat capacity is 4200 J/kg°C."
    )
    assert _answer(text) == "5.04 × 10⁵ J"
    intent = extract_physics_intent(text)
    assert intent is not None
    formulas = _solve_requested_quantities(intent).formulas
    assert formulas[0] == r"\Delta T = T_2 - T_1 = 80 - 20 = 60"


def test_cooling_releases_heat() -> None:
    assert _answer("How much heat is released when 3 kg of water cools from 90 °C to 40 °C?") == (
        "627900 J (released)"
    )


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Was declined: the unlabelled 500 K was read as both reservoirs.
        ("Find the efficiency of a Carnot engine operating between 500 K and 300 K.", "0.4 (40%)"),
        ("Find the efficiency of a Carnot engine operating between 300 K and 500 K.", "0.4 (40%)"),
        ("A Carnot engine works between 227 °C and 27 °C. Find its efficiency.", "0.4 (40%)"),
    ],
)
def test_carnot_reads_both_reservoirs(text: str, answer: str) -> None:
    assert _answer(text) == answer


def test_a_rebound_reverses_the_velocity() -> None:
    # Was -0.4 N·s: 10 m/s in and 8 m/s back were read as two forward speeds.
    assert _answer(
        "A 0.2 kg ball hits a wall at 10 m/s and rebounds at 8 m/s. Find the impulse."
    ) == ("3.6 N·s (opposite to the initial motion)")


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # A force has no "initial motion": the impulse keeps its sign.
        ("A force of -10 N acts on a cart for 2 s. Find the impulse.", "-20 N·s"),
        # Slowing from -2 to -5 m/s is along the motion, not opposite it.
        ("A 0.5 kg ball's velocity changes from -2 m/s to -5 m/s. Find the impulse.", "1.5 N·s"),
        ("A 0.5 kg ball's velocity changes from 2 m/s to 5 m/s. Find the impulse.", "1.5 N·s"),
        # From rest there is no initial motion either: the sign is the direction.
        ("A 0.5 kg ball's velocity changes from 0 m/s to -4 m/s. Find the impulse.", "-2 N·s"),
    ],
)
def test_an_impulse_direction_is_only_relative_to_a_real_initial_motion(
    text: str, answer: str
) -> None:
    assert _answer(text) == answer


def test_both_launch_angles_are_answers() -> None:
    assert _answer("At what angle must a projectile be launched at 20 m/s to land 30 m away?") == (
        "23.7° or 66.3°"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Find the kinetic energy of a 2 kg object moving at 3 m/s and at 4 m/s.",
        # 4 - 7 = -3 is a coincidence: the 3 m/s it "derives" is itself stated.
        "Find the kinetic energy of a 2 kg object moving at 3 m/s, 4 m/s, and 7 m/s.",
        "A 5 kg mass is nearby. A force of 20 N acts on a 3 kg cart. What is the acceleration?",
        # One number in two units is two speeds: 3 km/h does not account for 3 m/s.
        "Find the kinetic energy of a 2 kg object at 3 km/h and at 3 m/s.",
        # Was 1.4 m: the extractor bound "1 radian" as 1 degree.
        "A projectile is launched at 20 m/s at 1 radian. Find its range. Use g=10.",
    ],
)
def test_a_skipped_given_declines(text: str) -> None:
    assert _answer(text) is None


def test_a_value_derived_from_givens_still_accounts_for_them() -> None:
    # 2 A + 3 A is the 5 A it binds; no given states 5 A, so it is derived.
    assert (
        _answer("Currents of 2 A and 3 A enter a junction. Find the current leaving the junction.")
        == "5 A leaving"
    )


@pytest.mark.parametrize(
    "text",
    [
        "A ball is dropped from 20 m on Jupiter. How long does it take to hit the ground?",  # 2.02 s
        "A 5 kg box rests on the floor on Jupiter. Find its weight.",  # 49.1 N
    ],
)
def test_a_body_without_a_school_g_does_not_get_earths(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        # Was 4190 J: "J/g°C" was not read, so water's 4186 J/(kg·K) replaced the stated c.
        (
            "How much heat is needed to raise the temperature of 100 g of water by 10 °C? "
            "c = 4.18 J/g°C",
            "4180 J",
        ),
        ("How much heat is needed to raise 50 g of copper by 30 °C? c = 0.385 J/g°C", "577.5 J"),
    ],
)
def test_a_specific_heat_per_gram_is_read(text: str, answer: str) -> None:
    assert _answer(text) == answer
