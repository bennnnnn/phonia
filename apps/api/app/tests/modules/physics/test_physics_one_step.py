"""One-formula laws: the question states the inputs, and the catalog evaluates them."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


def _op(text: str) -> str | None:
    intent = extract_physics_intent(text)
    return None if intent is None else intent.physics_op


@pytest.mark.parametrize(
    ("text", "operation", "answer"),
    [
        (
            "A machine applies 30 N of input force and produces 120 N of output force. "
            "Find its mechanical advantage.",
            "machine_advantage_forces",
            "4",
        ),
        (
            "An ideal inclined plane is 4 m long and rises 1 m. Find its mechanical advantage.",
            "machine_advantage_inclined_plane",
            "4",
        ),
        (
            "A pulley supports a load with 4 supporting rope strands. Find its mechanical advantage.",
            "machine_advantage_pulley",
            "4",
        ),
        (
            "A wheel and axle has a wheel radius of 0.20 m and an axle radius of 0.04 m. "
            "Find its mechanical advantage.",
            "machine_advantage_wheel_axle",
            "5",
        ),
        (
            "A gear has 12 teeth on the input and 48 teeth on the output. "
            "Find the mechanical advantage.",
            "machine_advantage_gears",
            "4",
        ),
        (
            "A screw has a handle length of 0.25 m and a thread pitch of 0.005 m. "
            "Find its mechanical advantage.",
            "machine_advantage_screw",
            "314",
        ),
        (
            "A wedge is 0.10 m long and 0.02 m wide. Find its mechanical advantage.",
            "machine_advantage_wedge",
            "5",
        ),
        (
            "A physical pendulum has moment of inertia 0.50 kg m^2, mass 2.0 kg "
            "and pivot distance 0.40 m. Find its period.",
            "physical_pendulum_period",
            "1.59 s",
        ),
        (
            "A conical pendulum of length 1.20 m makes an angle of 30 degrees "
            "with the vertical. Find its period.",
            "conical_pendulum_period",
            "2.05 s",
        ),
        (
            "A toy car just completes a vertical loop of radius 0.50 m. Find its speed.",
            "loop_entry_speed",
            "4.95 m/s",
        ),
        (
            "A sound has intensity 1.00e-6 W/m^2 at the threshold of hearing. "
            "Find the sound level in decibels.",
            "sound_level",
            "60 dB",
        ),
        (
            "The shear stress is 8.00e6 Pa and the shear strain is 0.00200. "
            "Find the shear modulus.",
            "shear_modulus",
            "4 × 10⁹ Pa",
        ),
        (
            "The pressure increases by 2.00e5 Pa. The original volume is 0.00400 m^3 "
            "and the change in volume is 1.00e-5 m^3. Find the bulk modulus.",
            "bulk_modulus",
            "8 × 10⁷ Pa",
        ),
        (
            "The lateral strain is 0.00100 and the axial strain is 0.00400. Find Poisson's ratio.",
            "poisson_ratio",
            "0.25",
        ),
        (
            "A driving gear with 40 teeth spins at 10 rad/s. The driven gear has 20 teeth. "
            "Find the angular speed.",
            "gear_output_speed",
            "20 rad/s",
        ),
        (
            "A driving gear has 40 teeth and the driven gear has 20 teeth. Find the gear ratio.",
            "gear_ratio",
            "2",
        ),
        (
            "An object obeying Newton's law of cooling starts at 80 °C in a room at 20 °C. "
            "The time constant is 10 s. What is its temperature after 10 s?",
            "newton_cooling",
            "42.1 °C",
        ),
        (
            "A wave of intensity 1500 W/m^2 is absorbed. Find the radiation pressure.",
            "radiation_pressure_absorbed",
            "5 × 10⁻⁶ Pa",
        ),
        (
            "A wave of intensity 1500 W/m^2 is reflected. Find the radiation pressure.",
            "radiation_pressure_reflected",
            "1 × 10⁻⁵ Pa",
        ),
        (
            "An Otto engine has a compression ratio of 8 and gamma 1.40. Find the efficiency.",
            "otto_efficiency",
            "0.565",
        ),
    ],
)
def test_one_formula_question(text: str, operation: str, answer: str | None) -> None:
    assert _op(text) == operation
    got = _answer(text)
    assert got is not None
    if answer is not None:
        assert got == answer


def test_a_simple_pendulum_stays_the_length_formula() -> None:
    assert _op("A pendulum of length 1.20 m. Find its period.") == "pendulum_period"


def test_contact_at_the_top_is_not_the_loop_entry_speed() -> None:
    assert (
        _op("A car moves in a vertical circle of radius 0.50 m. Find its speed at the top.")
        == "contact_speed"
    )


def test_radiation_pressure_without_absorbed_or_reflected_declines() -> None:
    assert _op("A wave of intensity 1500 W/m^2. Find the radiation pressure.") is None
