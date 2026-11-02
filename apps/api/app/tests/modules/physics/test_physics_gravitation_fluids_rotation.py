"""Round 3: gravitation, fluids and rotation.

Three things here were not formula work at all, and each was a wrong answer
waiting rather than a gap:

1. **Scientific notation did not parse.** "a planet of mass 6e24 kg" matched as
   *24 kg*, and the surface gravity came out 0 m/s^2. Astronomy is written
   this way and nothing else in the package reads it, so the fix is in the
   shared value scanners, not here.
2. **An altitude is not in the same unit as a radius.** "400 km above the
   earth" was added to 6.371e6 m as the number 400, giving the surface orbital
   speed to four significant figures — a plausible wrong answer. The two now
   travel as separate params and are added after the unit conversion.
3. **"two 1000 kg masses" states one number for two bodies**, which is the
   commonest wording of Newton's law of gravitation.

Rotation reverses nothing: P9's `_TORQUE_UNSUPPORTED` refusal stays exactly as
it was, because that is what stops *torque* claiming a moment of inertia. This
extractor runs after it and picks up the fall-through.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    needs_physics,
)

PHYSICS_KINDS = {
    "kinematics",
    "suvat",
    "projectile",
    "force",
    "energy",
    "momentum",
    "friction",
    "circular",
    "spring",
    "circuit",
    "torque",
    "waves",
    "optics",
    "thermal",
    "gravitation",
    "fluids",
    "rotation",
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


VERIFIED: list[tuple[str, str, str, str]] = [
    # --- gravitation ------------------------------------------------------
    (
        "what is the gravitational force between two 1000 kg masses 10 m apart",
        "gravitation",
        "gravitational_force",
        "6.67 × 10⁻⁷ N",
    ),
    (
        "what is the gravitational force between two 5000 kg spheres 2 m apart",
        "gravitation",
        "gravitational_force",
        "4.17 × 10⁻⁴ N",
    ),
    (
        "what is the orbital velocity at 400 km above the earth",
        "gravitation",
        "orbital_velocity",
        "7673 m/s",
    ),
    (
        "what is the orbital velocity of a satellite 300 km above the earth",
        "gravitation",
        "orbital_velocity",
        "7730 m/s",
    ),
    ("what is the escape velocity from earth", "gravitation", "escape_velocity", "11186 m/s"),
    ("what is the escape velocity from the moon", "gravitation", "escape_velocity", "2375 m/s"),
    (
        "what is g on a planet of mass 6e24 kg and radius 6.4e6 m",
        "gravitation",
        "surface_gravity",
        "9.78 m/s²",
    ),
    ("what is the surface gravity of mars", "gravitation", "surface_gravity", "3.73 m/s²"),
    # --- fluids -----------------------------------------------------------
    (
        "what is the pressure of a 200 N force over 0.01 m^2",
        "fluids",
        "pressure_from_force",
        "20000 Pa",
    ),
    (
        "what is the pressure at 3 m depth in water",
        "fluids",
        "pressure_at_depth",
        "29430 Pa (gauge)",
    ),
    (
        "what is the density of a 12 kg block of volume 0.004 m^3",
        "fluids",
        "density",
        "3000 kg/m³",
    ),
    (
        "what is the upthrust on a 0.002 m^3 object fully submerged in water",
        "fluids",
        "upthrust",
        "19.6 N",
    ),
    (
        "what is the velocity in a pipe narrowing from 0.04 m^2 to 0.01 m^2 at 2 m/s",
        "fluids",
        "continuity_velocity",
        "8 m/s",
    ),
    (
        "what is the flow rate through a 0.02 m^2 pipe at 3 m/s",
        "fluids",
        "flow_rate",
        "0.06 m³/s",
    ),
    # --- rotation ---------------------------------------------------------
    (
        "what is the angular velocity of a wheel turning 10 radians in 2 s",
        "rotation",
        "angular_displacement_rate",
        "5 rad/s",
    ),
    (
        "what is the moment of inertia of a 5 kg disc of radius 2 m",
        "rotation",
        "moment_of_inertia",
        "10 kg·m²",
    ),
    (
        "what is the moment of inertia of a 5 kg solid sphere of radius 2 m",
        "rotation",
        "moment_of_inertia",
        "8 kg·m²",
    ),
    (
        "what is the moment of inertia of a 3 kg hoop of radius 2 m",
        "rotation",
        "moment_of_inertia",
        "12 kg·m²",
    ),
    (
        "what is the angular momentum of a 4 kg m^2 disc at 3 rad/s",
        "rotation",
        "angular_momentum",
        "12 kg·m²/s",
    ),
    (
        "what is the rotational kinetic energy of a 4 kg m^2 disc at 3 rad/s",
        "rotation",
        "rotational_kinetic_energy",
        "18 J",
    ),
]


@pytest.mark.parametrize("text,kind,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_round_three_second_wave_phrasings(text: str, kind: str, op: str, answer: str) -> None:
    assert needs_physics(text), "dropped by the pre-filter before extraction"
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent), "no intent extracted"
    assert intent.kind == kind
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


# ---------------------------------------------------------------------------
# The three parsing defects, pinned by value.
# ---------------------------------------------------------------------------


def test_scientific_notation_is_read_as_written() -> None:
    """6e24 kg matched as 24 kg, and the answer was 0 m/s^2."""
    assert (
        _verified_answer("what is g on a planet of mass 6e24 kg and radius 6.4e6 m") == "9.78 m/s²"
    )


def test_an_altitude_is_converted_before_it_is_added_to_a_radius() -> None:
    """400 km was added to 6.371e6 m as the number 400.

    The result was the *surface* orbital speed to four significant figures — a
    wrong answer that looks entirely reasonable.
    """
    surface = _verified_answer("what is the orbital velocity at the surface of the earth")
    high = _verified_answer("what is the orbital velocity at 400 km above the earth")
    assert surface is not None and high is not None
    assert float(high.split()[0]) < float(surface.split()[0])
    assert high == "7673 m/s"


def test_a_question_with_no_digits_still_reaches_the_solver() -> None:
    """The numbers are the body's own, so the pre-filter's digit rule missed it."""
    assert needs_physics("what is the escape velocity from earth")
    assert _verified_answer("what is the escape velocity from earth") == "11186 m/s"


# ---------------------------------------------------------------------------
# Physical relationships.
# ---------------------------------------------------------------------------


def test_gravitational_force_obeys_the_inverse_square() -> None:
    near = _verified_answer("what is the gravitational force between two 1000 kg masses 1 m apart")
    far = _verified_answer("what is the gravitational force between two 1000 kg masses 2 m apart")
    assert near is not None and far is not None
    assert float(near.split()[0]) == pytest.approx(4 * float(far.split()[0]), rel=0.01)


def test_the_shape_decides_the_moment_of_inertia() -> None:
    """Same mass, same radius, three different answers."""
    hoop = _verified_answer("what is the moment of inertia of a 5 kg hoop of radius 2 m")
    disc = _verified_answer("what is the moment of inertia of a 5 kg disc of radius 2 m")
    sphere = _verified_answer("what is the moment of inertia of a 5 kg solid sphere of radius 2 m")
    assert hoop is not None and disc is not None and sphere is not None
    assert float(hoop.split()[0]) > float(disc.split()[0]) > float(sphere.split()[0])


def test_pressure_rises_with_depth() -> None:
    shallow = _verified_answer("what is the pressure at 3 m depth in water")
    deep = _verified_answer("what is the pressure at 6 m depth in water")
    assert shallow is not None and deep is not None
    assert float(deep.split()[0]) == pytest.approx(2 * float(shallow.split()[0]), rel=0.01)


# ---------------------------------------------------------------------------
# Refusals.
# ---------------------------------------------------------------------------

REFUSED = [
    # A planet described but not named, supplying only one of mass and radius.
    # Finishing it with Earth's other number is the projectile default again.
    "what is the escape velocity from a planet of mass 6e24 kg",
    "what is the surface gravity of a planet of radius 6.4e6 m",
    # The shape is the answer. A wheel is not a shape and an object is not one
    # either; answering with the disc constant would be confidently wrong.
    "what is the moment of inertia of a 5 kg wheel of radius 2 m",
    "what is the moment of inertia of a 5 kg object of radius 2 m",
    "what is the moment of inertia of a 5 kg flywheel of radius 2 m",
    # A floating body displaces its weight, a submerged one its volume.
    "what is the upthrust on a 0.002 m^3 object floating in water",
    # An unnamed liquid has no density to use.
    "what is the pressure at 3 m depth in a liquid",
]


@pytest.mark.parametrize("text", REFUSED)
def test_questions_outside_the_solved_shape_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


def test_torque_still_refuses_the_quantity_rotation_now_answers() -> None:
    """P9's refusal is kept, and is the reason this ordering works.

    It is what stops *torque* claiming a moment of inertia. Rotation runs after
    it and picks up the fall-through, so the two never compete.
    """
    from app.modules.physics.extractors.torque import _extract_torque_intent

    assert (
        _extract_torque_intent("what is the moment of inertia of a 5 kg disc of radius 2 m") is None
    )
    assert (
        _extract_torque_intent("what is the angular momentum of a 4 kg m^2 disc at 3 rad/s") is None
    )


NOT_PHYSICS = [
    "the gravity of the situation hit me 2 days later",
    "escape to a 3 day retreat",
    "the mass email went to 500 people",
    "there is a lot of pressure at work, 2 deadlines",
    "the flow of the essay is off in paragraph 2",
    "traffic density on the 5 lane road",
    "give me 3 tips to reduce blood pressure",
    "rotate the 3 images 90 degrees",
    "we rotate 4 people on support each week",
    "the momentum of the project picked up in week 2",
    "angular 17 released 3 new features",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_the_new_cues_do_not_steal_ordinary_english(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_displacing_states_the_submerged_volume() -> None:
    """ "displacing 2 m^3 of water" says it as plainly as "submerged" does."""
    assert (
        _verified_answer("what is the buoyant force on a body displacing 2 m^3 of water")
        == "19620 N"
    )


def test_during_and_discuss_do_not_change_a_solid_sphere() -> None:
    plain = "what is the moment of inertia of a 5 kg solid sphere of radius 2 m"
    noisy = f"{plain} during a discussion"
    assert _verified_answer(noisy) == _verified_answer(plain)
    intent = extract_physics_intent(noisy)
    assert intent is not None and intent.physics_params is not None
    assert intent.physics_params["shape_factor"] == 0.4


def test_angular_velocity_from_a_period_needs_no_radius() -> None:
    text = "what angular velocity gives a period of 2 s"
    intent = extract_physics_intent(text)
    assert intent is not None
    assert intent.physics_op == "angular_velocity"
    assert intent.physics_params is not None
    assert "r" not in intent.physics_params
    assert intent.physics_params["period"] == 2
    assert _verified_answer(text) == "3.14 rad/s"


def test_rad_per_second_is_not_an_angle_in_radians() -> None:
    """2 rad/s is already a speed. Reading the rad as an angle verified 0.667 rad/s."""
    for text in (
        "A wheel turns at 2.00 rad/s for 3.00 s. Find the angular speed.",
        "A wheel turns at 2.00 radians per second for 3.00 s. Find the angular speed.",
    ):
        intent = extract_physics_intent(text)
        assert intent is None or intent.physics_op != "angular_displacement_rate"
        assert _verified_answer(text) != "0.667 rad/s"


def test_a_narrowing_pipe_writes_its_unit_once() -> None:
    """ "from 0.04 to 0.01 m^2" puts the unit on the second area only.

    The same shape as the resistor networks, and it returned nothing for the
    same reason.
    """
    assert (
        _verified_answer("what is the velocity in a pipe narrowing from 0.04 to 0.01 m^2 at 2 m/s")
        == "8 m/s"
    )
