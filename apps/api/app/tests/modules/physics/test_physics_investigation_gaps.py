"""Laws and readers the September investigation found left to the model.

Each table holds questions the solver now verifies, with the answer worked by
hand (g = 9.81 m/s²), and the near misses it must still decline: a reading
that is not complete is never verified.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.ask import asked_unit
from app.modules.physics.binding import crosswise
from app.modules.physics.binding_values import light_enters_from_air
from app.modules.physics.extract import needs_physics
from app.modules.physics.givens import scan_givens
from app.modules.physics.numbers import normalize_physics_numbers, normalize_physics_units
from app.services.law_binding.units import unit_dimension
from app.services.subjects.dispatch import detect_subject
from app.tests.modules.physics.support import answer_number

_SETTINGS = Settings(math_tools_enabled=True)


def _answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _SETTINGS)
    return None if block is None else block.canonical_answer


def _operation(text: str) -> str | None:
    intent = extract_physics_intent(text)
    return None if intent is None else intent.physics_op


def _assert_answer(text: str, operation: str, value: float, unit: str) -> None:
    assert _operation(text) == operation, text
    answer = _answer(text)
    assert answer is not None, text
    assert answer_number(answer) == pytest.approx(value, rel=5e-3), answer
    assert unit in answer, answer


# --- optics -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        # The angle to the surface is 90° less than the angle of incidence.
        (
            "Light strikes a glass block (n = 1.5) making an angle of 50 degrees with the "
            "surface. Find the angle of refraction.",
            25.37,
        ),
        (
            "a ray of light hits the surface of water (n=1.33) at 30° to the surface. "
            "what's the angle of refraction?",
            40.63,
        ),
        ("Light enters glass (n = 1.5) at 30°. what is the angle of refraction?", 19.47),
    ],
)
def test_snell_refraction_angle_reads_light_from_air(text: str, value: float) -> None:
    _assert_answer(text, "snell_refraction_angle", value, "°")


@pytest.mark.parametrize(
    "text",
    [
        # Light inside the glass, or coming from it, is not from air.
        "Light inside a glass block (n = 1.5) hits the surface at 30°. "
        "What is the angle of refraction?",
        "A ray leaves water (n = 1.33) at 30°. What is the angle of refraction?",
        "Light travelling in diamond hits glass (n = 1.5) at 30°. Find the angle of refraction.",
    ],
)
def test_snell_refraction_angle_declines_light_that_starts_in_a_medium(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("lower", "from_air"),
    [
        ("light strikes a glass block (n = 1.5)", True),
        ("a ray of light hits the surface of water (n=1.33)", True),
        ("light inside a glass block hits the surface", False),
        ("light from the glass enters water", False),
        ("a ray of light hits the surface from the air", True),
        ("light passes between two blocks", False),
    ],
)
def test_light_enters_from_air_reads_where_the_ray_starts(lower: str, from_air: bool) -> None:
    assert light_enters_from_air(lower) is from_air


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "what is the critical angle for light going from glass n=1.5 into water n=1.33",
            "critical_angle_between",
            62.46,
            "°",
        ),
        (
            "What is the critical angle for light going from glass (n = 1.5) into water "
            "(n = 1.33)?",
            "critical_angle_between",
            62.46,
            "°",
        ),
        (
            "What is the wavelength of 650 nm red light inside glass of refractive index 1.5?",
            "wavelength_in_medium",
            433.3,
            "nm",
        ),
        (
            "Light of wavelength 650 nm enters glass with refractive index 1.5. What is its "
            "wavelength in the glass?",
            "wavelength_in_medium",
            433.3,
            "nm",
        ),
        (
            "In a double slit experiment the slits are 0.2 mm apart and the screen is 1.5 m "
            "away. With 600 nm light, what's the fringe spacing?",
            "double_slit_fringe_spacing",
            0.0045,
            "m",
        ),
        (
            "A diffraction grating has 500 lines per mm. Light of 550 nm. At what angle is the "
            "first-order maximum?",
            "grating_angle",
            15.96,
            "°",
        ),
        (
            "a magnifying glass has focal length 5 cm. what's its power in diopters?",
            "lens_power",
            20.0,
            "D",
        ),
        (
            "A 4 cm tall object is 15 cm in front of a converging lens of focal length 10 cm. "
            "how tall is the image?",
            "image_height",
            8.0,
            "cm (inverted)",
        ),
        (
            "a concave mirror has a radius of curvature of 40 cm. an object is placed 30 cm "
            "away. where is the image?",
            "mirror_image_from_radius",
            60.0,
            "cm",
        ),
        (
            "an object is 8 cm from a converging lens with focal length 12 cm. find the image "
            "distance",
            "image_distance",
            24.0,
            "cm (virtual, on the object's side of the lens)",
        ),
        (
            "what is the image distance for a lens of focal length 20 cm and object at 10 cm",
            "image_distance",
            20.0,
            "virtual",
        ),
    ],
)
def test_optics_laws_answer_the_investigation_questions(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # Into the denser medium there is no total internal reflection.
        "what is the critical angle for light going from water n=1.33 into glass n=1.5",
        # Inside F a mirror's image is virtual, behind it.
        "a concave mirror has a radius of curvature of 40 cm. an object is placed 10 cm "
        "away. where is the image?",
        # Inside F the image is virtual and upright: its height's sign is a convention.
        "A 4 cm tall object is 5 cm in front of a converging lens of focal length 10 cm. "
        "how tall is the image?",
        # A diverging lens is outside these laws.
        "A 4 cm tall object is 15 cm in front of a diverging lens of focal length 10 cm. "
        "how tall is the image?",
        # A convex mirror diverges too: it was certified 30 cm (the image is 6 cm behind).
        "An object is placed at a distance of 10 cm from a convex mirror of focal length "
        "15 cm. Find the position and nature of the image.",
        "A 2 m tall person stands in front of a convex mirror of focal length 1 m, 3 m away. "
        "Where is the image?",
        # A far point is not a focal length: it was certified +1.25 D (the lens is concave).
        "The far point of a myopic person is 80 cm in front of the eye. What is the nature "
        "and power of the lens required to correct the problem?",
        "The near point of a hypermetropic eye is 1 m. What is the power of the lens "
        "required to correct this defect?",
        # A concave lens's power is negative.
        "Find the power of a concave lens of focal length 2 m.",
        # A diverging element however worded (review of the first fix).
        "An object is placed 10 cm from a convex spherical mirror of focal length 15 cm. "
        "Find the image distance.",
        "An object is 10 cm from a convex rear-view mirror of focal length 15 cm. Where is "
        "the image?",
        "A spherical mirror is convex. Its focal length is 15 cm and an object is placed "
        "10 cm in front of it. Find the image distance.",
        "An object 30 cm from a concave thin lens of focal length 15 cm. Find the image distance.",
        "The lens is concave. An object is placed 30 cm from it and its focal length is "
        "15 cm. Find the image distance.",
        # A short-sighted eye's lens diverges.
        "A myopic person uses a lens of focal length 80 cm. Find the power.",
        "A short-sighted person wears spectacles with lenses of focal length 50 cm. What is "
        "their power?",
        # -v/u is an inverted image's: a diverging element's or an erect image is +.
        "An object is 15 cm from a convex mirror; the image is 6 cm behind the mirror. Find "
        "the magnification.",
        "A concave lens forms an image 10 cm from the lens of an object 20 cm away. Find "
        "the magnification.",
        "A concave mirror forms an erect image 30 cm behind the mirror of an object 10 cm "
        "away. Find the magnification.",
        "A convex lens forms an upright image 30 cm from the lens of an object 10 cm away. "
        "Find the magnification.",
        # Heights are no distances: a Grade 10 book's 5 cm object and 25 cm image (-5).
        "The height of an object is 5 cm and the height of its image in a concave mirror is "
        "25 cm high. What is the magnification of the image?",
        # Second review: "biconcave", power to focal length, and lenses in contact.
        "An object is 30 cm from a biconcave lens of focal length 15 cm. Find the image distance.",
        "A concave lens has power 2.5 D. Find its focal length.",
        "A convex lens of power 4 D and a concave lens of power 2.5 D are in contact. Find "
        "the total power.",
    ],
)
def test_optics_laws_decline_what_they_cannot_read_whole(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "An object is placed 30 cm in front of a convex lens of focal length 10 cm. "
            "Find the image distance.",
            "image_distance",
            15.0,
            "cm",
        ),
        (
            "An object is placed 30 cm from a concave mirror of focal length 10 cm. Where "
            "is the image?",
            "image_distance",
            15.0,
            "cm",
        ),
        (
            "A convex lens forms a real image 30 cm from the lens of an object 15 cm away. "
            "Find the magnification.",
            "magnification_distances",
            -2.0,
            "",
        ),
        (
            "A hypermetropic person uses a lens of focal length 50 cm. Find the power.",
            "lens_power",
            2.0,
            "D",
        ),
    ],
)
def test_a_converging_element_keeps_its_card(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("What is the power of a lens with a focal length of 25 cm?", 4.0),
        ("A convex lens has f = 50 cm. What is its power?", 2.0),
    ],
)
def test_lens_power_reads_a_length_called_the_focal_length(text: str, value: float) -> None:
    _assert_answer(text, "lens_power", value, "D")


# --- forces and motion ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        (
            "A 25 kg crate is pulled across a floor by a rope at 30° above the horizontal "
            "with a 150 N force. μk = 0.2. find the accelaration",
            3.834,
        ),
        # Pushed down at the angle: the floor presses back harder.
        (
            "A 25 kg crate is pushed across a floor with a 150 N force at 30° below the "
            "horizontal. μk = 0.2. find the acceleration",
            2.634,
        ),
    ],
)
def test_angled_pull_friction_acceleration_resolves_the_force(text: str, value: float) -> None:
    _assert_answer(text, "angled_pull_friction_acceleration", value, "m/s²")


@pytest.mark.parametrize(
    "text",
    [
        # Steep enough to lift the crate: no floor to press on.
        "A 2 kg crate is pulled by a rope at 60° above the horizontal with a 150 N force. "
        "μk = 0.2. find the acceleration",
        # A slope's angle is not the rope's.
        "A 25 kg crate is pulled up a 30° incline by a rope at 20° above the horizontal "
        "with a 150 N force. μk = 0.2. find the acceleration",
    ],
)
def test_angled_pull_friction_acceleration_declines_outside_its_shape(text: str) -> None:
    assert _operation(text) != "angled_pull_friction_acceleration" or _answer(text) is None


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("accelaration?", "acceleration?"),
        ("it acclerates at 2 m/s^2", "it accelerates at 2 m/s^2"),
        ("whats the total distance?", "what's the total distance?"),
        ("Whats the tension", "What's the tension"),
        ("final velocty", "final velocity"),
    ],
)
def test_normalize_physics_units_reads_a_misspelt_ask(written: str, read: str) -> None:
    assert normalize_physics_units(written) == read


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "a train starts from rest and acclerates at 0.8 m/s^2 for 25 s, then travels at "
            "constant speed for 1 min. whats the total distance?",
            "two_stage_distance",
            1450.0,
            "m",
        ),
        (
            "a sprinter reaches her top speed of 11 m/s in 2.2 s starting from rest and "
            "holds it to the finish. how long does she take to run 100 m?",
            "two_stage_time",
            10.19,
            "s",
        ),
        (
            "A car accelerates from rest at 2 m/s^2 for 10 s, then brakes at 4 m/s^2 to a "
            "stop. total distance?",
            "two_stage_distance",
            150.0,
            "m",
        ),
        (
            "A bus starts from rest and accelerates to 12 m/s in 6 s, then brakes to a stop "
            "in 4 s. what is the total distance?",
            "two_stage_distance",
            60.0,
            "m",
        ),
        (
            "A car accelerates from rest at 2 m/s^2 for 10 s, then brakes at 4 m/s^2 to a "
            "stop. what is the total time?",
            "two_stage_time",
            15.0,
            "s",
        ),
    ],
)
def test_two_stage_motion_answers_the_whole_trip(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # One stage asked: not the whole trip.
        "A car accelerates from rest at 2 m/s^2 for 10 s, then brakes at 4 m/s^2 to a stop. "
        "how far does it travel while braking?",
        # A start speed: not from rest.
        "A car moving at 5 m/s accelerates at 2 m/s^2 for 10 s, then brakes at 4 m/s^2 to a "
        "stop. total distance?",
        # The 10 m ends before the top speed is reached.
        "a sprinter reaches her top speed of 11 m/s in 2.2 s starting from rest and holds it "
        "to the finish. how long does she take to run 10 m?",
        # A held speed with no time or distance has no end.
        "A train starts from rest, accelerates at 1 m/s^2 for 20 s, then travels at constant "
        "speed. total distance?",
        # A second stage this reading does not know.
        "A lift starts from rest and accelerates at 1 m/s^2 for 3 s, then goes up a 2 m shaft. "
        "total distance?",
    ],
)
def test_two_stage_motion_declines_a_partial_reading(text: str) -> None:
    assert _answer(text) is None


def test_stopping_distance_reads_a_braking_rate() -> None:
    _assert_answer(
        "Driver going 108 km/h sees a hazard, reaction time 0.8 s, then brakes at 6 m/s^2. "
        "total stopping distance?",
        "stopping_distance",
        99.0,
        "m",
    )


@pytest.mark.parametrize(
    ("text", "value", "unit"),
    [
        (
            "a boat heads straight across a river at 4 m/s while the current flows at 3 m/s. "
            "what is the boat's resultant speed relative to the bank?",
            5.0,
            "m/s",
        ),
        (
            "a plane flies due north at 250 km/h and a 50 km/h wind blows from west to east. "
            "what's its ground speed?",
            255.0,
            "km/h",
        ),
    ],
)
def test_perpendicular_velocity_sum_adds_at_right_angles(
    text: str, value: float, unit: str
) -> None:
    _assert_answer(text, "perpendicular_velocity_sum", value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # Aimed upstream to land opposite: the other triangle.
        "a boat wants to go straight across a river at 4 m/s while the current flows at "
        "3 m/s. what is the boat's resultant speed relative to the bank?",
        "a boat aims upstream so it crosses straight across a river at 4 m/s in a 3 m/s "
        "current. what is its resultant speed?",
        # A wind along the heading is not a right angle.
        "a plane flies due north at 250 km/h into a 50 km/h wind from the north. what's its "
        "ground speed?",
        # Between the axes.
        "a plane flies north-east at 250 km/h and a 50 km/h wind blows from west to east. "
        "what's its ground speed?",
    ],
)
def test_perpendicular_velocity_sum_declines_other_geometry(text: str) -> None:
    assert _operation(text) != "perpendicular_velocity_sum"


@pytest.mark.parametrize(
    ("lower", "crossing"),
    [
        ("flies due north and a wind blows from west to east", True),
        ("i walk 3 km east then 4 km north", True),
        ("flies north into a wind from the north", False),
        ("flies north-east with a wind from the west", False),
        ("heads north at a bearing of 30 degrees east", False),
    ],
)
def test_crosswise_reads_one_direction_on_each_axis(lower: str, crossing: bool) -> None:
    assert crosswise(lower) is crossing


def test_meeting_time_reads_when_do_they_meet() -> None:
    _assert_answer(
        "Two cars 300 m apart drive toward each other at 20 m/s and 10 m/s. when do they meet?",
        "meeting_time",
        10.0,
        "s",
    )


# --- momentum -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        # The asked body's mass names it; it is not a third mass.
        (
            "a 2 kg ball moving at 6 m/s hits a stationary 4 kg ball head-on in a perfectly "
            "elastic collision. what is the velocity of the 4 kg ball after?",
            "final_velocity",
            -2.0,
            "m/s and 4 m/s",
        ),
        (
            "A 1500 kg car going 20 m/s rear-ends a 1000 kg car going 10 m/s in the same "
            "direction and they lock bumpers. what's their speed just after?",
            "final_velocity",
            16.0,
            "m/s",
        ),
        (
            "a 10 g bullet traveling 400 m/s embeds in a 2 kg wooden block at rest on ice. "
            "how fast does the block move after?",
            "final_velocity",
            1.99,
            "m/s",
        ),
        # Directions: east is positive, so the west-moving puck's speed is negative.
        (
            "A 0.5 kg puck moving east at 4 m/s collides with a 0.3 kg puck moving west at "
            "2 m/s. they stick together. final velocity?",
            "final_velocity",
            1.75,
            "m/s",
        ),
        (
            "A 3 kg cart moving at 4 m/s collides and sticks to a 1 kg cart at rest. how much "
            "kinetic energy is lost?",
            "collision_energy_lost",
            6.0,
            "J",
        ),
        (
            "A 6 kg shell at rest explodes into two pieces, 2 kg and 4 kg. The 2 kg piece "
            "flies off at 30 m/s. how fast does the 4 kg piece move?",
            "explosion_speed",
            15.0,
            "m/s",
        ),
        (
            "A 6 kg bomb at rest explodes into a 2 kg piece and a 4 kg piece. If the 2 kg "
            "piece moves at 30 m/s, how fast does the 4 kg piece move?",
            "explosion_speed",
            15.0,
            "m/s",
        ),
        (
            "A tennis racket exerts an average force of 240 N on a 58 g ball for 5 ms. "
            "what's the change in the ball's speed?",
            "speed_change_from_force",
            20.69,
            "m/s",
        ),
        (
            "A 0.2 kg ball hits a wall at 15 m/s and bounces back at 10 m/s. contact time "
            "0.05 s. average force on the ball?",
            "rebound_average_force",
            100.0,
            "N",
        ),
        (
            "an astronaut of mass 90 kg throws a 3 kg wrench at 6 m/s. what's his recoil speed",
            "recoil_speed",
            0.2,
            "m/s",
        ),
    ],
)
def test_momentum_laws_answer_the_investigation_questions(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # One body's direction and the other's unsaid.
        "A 0.5 kg puck moving east at 4 m/s collides with a 0.3 kg puck moving at 2 m/s. "
        "they stick together. final velocity?",
        # East and north: two dimensions.
        "A 0.5 kg puck moving east at 4 m/s collides with a 0.3 kg puck moving north at "
        "2 m/s. they stick together. final velocity?",
        # An elastic collision loses no kinetic energy to ask about.
        "A 3 kg cart moving at 4 m/s collides elastically with a 1 kg cart at rest. how much "
        "kinetic energy is lost?",
        # Speeds listed apart from their masses: which is whose is not read.
        "Two carts of 2 kg and 3 kg move toward each other at 3 m/s and 2 m/s and stick "
        "together. what is their final velocity?",
        # The asked mass is no body's.
        "a 2 kg ball moving at 6 m/s hits a stationary 4 kg ball in a perfectly elastic "
        "collision. what is the velocity of the 3 kg ball after?",
        # The pieces do not make up the shell.
        "A 6 kg shell at rest explodes into two pieces, 2 kg and 3 kg. The 2 kg piece flies "
        "off at 30 m/s. how fast does the 3 kg piece move?",
        # Which piece moves is not said.
        "A 6 kg shell at rest explodes into two pieces, 2 kg and 4 kg. One piece flies off "
        "at 30 m/s. how fast does the other move?",
    ],
)
def test_momentum_laws_decline_a_partial_reading(text: str) -> None:
    assert _answer(text) is None


# --- fluids ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "What's the absolute pressure 50 m deep in seawater (density 1025 kg/m^3)? "
            "include atmospheric pressure",
            "absolute_pressure_at_depth",
            6.04e5,
            "Pa",
        ),
        (
            "Water flows at 2 m/s in a pipe of diameter 4 cm, which narrows to 2 cm "
            "diameter. what's the speed in the narrow part?",
            "continuity_velocity",
            8.0,
            "m/s",
        ),
        (
            "Water flows at 8 m/s in a 2 cm diameter pipe that widens to 4 cm. what is the "
            "speed in the wider section?",
            "continuity_velocity",
            2.0,
            "m/s",
        ),
        (
            "water in a horizontal pipe speeds up from 2 m/s to 8 m/s. what's the pressure drop?",
            "bernoulli_pressure_drop",
            30000.0,
            "Pa",
        ),
        (
            "Water leaks out of a small hole 3 m below the water surface in a big tank. how "
            "fast does it come out?",
            "torricelli_speed",
            7.672,
            "m/s",
        ),
        (
            "A 3 kg object weighs only 18 N when fully submerged in water. what is its volume?",
            "volume_from_apparent_weight",
            0.001165,
            "m³",
        ),
        (
            "In a hydraulic press the small piston has a diameter of 2 cm and the big one "
            "20 cm. If you push with 50 N on the small piston, what force is produced on the "
            "large piston?",
            "hydraulic_force",
            5000.0,
            "N",
        ),
    ],
)
def test_fluid_laws_answer_the_investigation_questions(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # The speed is the narrow part's: not the first section's.
        "A pipe of diameter 4 cm narrows to 2 cm. In the narrow part the water moves at "
        "8 m/s. Find the speed in the wide part.",
        "A pipe of diameter 4 cm narrows to 2 cm. In the narrow part the water moves at "
        "8 m/s. Find the speed in the narrow part.",
        # Slowing down raises the pressure.
        "water in a horizontal pipe slows from 8 m/s to 2 m/s. what's the pressure drop?",
        # A height change adds a term the horizontal form leaves out.
        "water in a pipe speeds up from 2 m/s to 8 m/s as it rises 3 m. what's the pressure drop?",
        # Heavier under water than in air is no upthrust.
        "A 3 kg object weighs 40 N when fully submerged in water. what is its volume?",
    ],
)
def test_fluid_laws_decline_a_partial_reading(text: str) -> None:
    assert _answer(text) is None


# --- oscillations, waves, modern -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "A 250 g mass hangs on a spring with k = 40 N/m. What is the period of oscillation?",
            "shm_period",
            0.4967,
            "s",
        ),
        ("frequency of a 1.2 m long simple pendulum?", "pendulum_frequency", 0.4551, "Hz"),
        (
            "What is the frequency of a simple pendulum of length 1.2 m?",
            "pendulum_frequency",
            0.4551,
            "Hz",
        ),
        (
            "A mass on a spring oscillates with a period of 0.8 s. if k = 50 N/m, what is the "
            "mass?",
            "spring_mass_from_period",
            0.8106,
            "kg",
        ),
        (
            "What is the sound intensity level of a sound with intensity 3.2 x 10^-5 W/m^2?",
            "sound_level",
            75.05,
            "dB",
        ),
        (
            "What is the sound level in dB for an intensity of 3.2 × 10^-5 W/m²?",
            "sound_level",
            75.05,
            "dB",
        ),
        (
            "how long until only 1/16 of a carbon-14 sample remains? half life 5730 years",
            "decay_time_from_fraction",
            22920.0,
            "years",
        ),
        (
            "Carbon-14 has a half-life of 5730 years. How long until 1/16 of a sample remains?",
            "decay_time_from_fraction",
            22920.0,
            "years",
        ),
        (
            "a radioactive source has an activity of 800 Bq. after 12 hours it's 200 Bq. "
            "what's the half-life?",
            "half_life_from_activities",
            6.0,
            "h",
        ),
        (
            "what percentage of a radioactive sample remains after 3 half-lives?",
            "percent_after_half_lives",
            12.5,
            "%",
        ),
        (
            "A muon travels at 0.98c. if its lifetime at rest is 2.2 µs, what's its lifetime "
            "measured in the lab?",
            "time_dilation",
            1.106e-5,
            "s",
        ),
    ],
)
def test_oscillation_wave_and_modern_laws_answer(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # A third is no exact decimal: the fraction stays unread.
        "how long until only 1/3 of a carbon-14 sample remains? half life 5730 years",
        # Activity that rises is no decay.
        "a radioactive source has an activity of 200 Bq. after 12 hours it's 800 Bq. "
        "what's the half-life?",
    ],
)
def test_decay_laws_decline_what_is_not_a_decay(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "read"),
    [
        ("only 1/16 of a sample", "only 0.0625 of a sample"),
        ("until 3/4 of the way", "until 0.75 of the way"),
        # Not "of" something, or not an exact decimal: left as written.
        ("only 1/3 of a sample", None),
        ("on 1/16 at noon", None),
    ],
)
def test_normalize_physics_numbers_reads_an_exact_fraction_of(text: str, read: str | None) -> None:
    assert normalize_physics_numbers(text) == read


# --- routing ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "a sprinter reaches her top speed of 11 m/s in 2.2 s starting from rest and holds it "
        "to the finish. how long does she take to run 100 m?",
        "A 25 kg crate is pulled across a floor by a rope at 30° above the horizontal with a "
        "150 N force. μk = 0.2. find the accelaration",
        "Light strikes a glass block (n = 1.5) making an angle of 50 degrees with the surface. "
        "Find the angle of refraction.",
        "a boat heads straight across a river at 4 m/s while the current flows at 3 m/s. what "
        "is the boat's resultant speed relative to the bank?",
    ],
)
def test_detect_subject_gives_the_investigation_gaps_to_physics(text: str) -> None:
    assert needs_physics(text)
    assert detect_subject(text) == "physics"


@pytest.mark.parametrize(
    "text",
    [
        "how fast is my wifi",
        "I'm recovering from rest days then going back to the gym",
        "the road narrows to one lane after the bridge, how long is the delay?",
        "my boat heads straight across the bay tomorrow, what should I pack?",
        "whats the time in Tokyo",
        "the river current is strong today, is it safe to swim?",
    ],
)
def test_needs_physics_leaves_everyday_lookalikes(text: str) -> None:
    assert not needs_physics(text)


# --- second pass: the investigation's other unsolved questions ------------------


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "a 70 kg man stands on bathroom scales in a lift accelerating downward at "
            "1.2 m/s^2. what do the scales read in N?",
            "lift_normal_force",
            602.7,
            "N",
        ),
        (
            "what horizontal force do you need to push a 40 kg box at constant velocity if μk "
            "is 0.35",
            "constant_velocity_push",
            137.3,
            "N",
        ),
        (
            "A 2000 kg truck tows an 800 kg car with a rope and they accelerate at 1.5 m/s^2. "
            "Ignoring friction, what's the tension in the tow rope?",
            "tow_tension",
            1200.0,
            "N",
        ),
        (
            "what is the mass of an object whose weight on the moon is 162 N? "
            "(g moon = 1.62 m/s^2)",
            "mass_from_weight",
            100.0,
            "kg",
        ),
        (
            "A cyclist going 36 km/h brakes uniformly and stops in 25 m. find the deceleration",
            "suvat_acceleration",
            -2.0,
            "m/s²",
        ),
        (
            "a train travels at 120 kph for 2.5 hours. how far does it go?",
            "rate_distance",
            300.0,
            "km",
        ),
    ],
)
def test_force_and_motion_laws_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "a 65 kg skier starts from rest at the top of a slope with a 40 m vertical drop. "
            "no friction. how fast at the bottom in km/h",
            "drop_speed",
            100.9,
            "km/h",
        ),
        (
            "A car engine delivers 90 kW when the car travels at a steady 25 m/s. What is the "
            "driving force?",
            "force_from_power",
            3600.0,
            "N",
        ),
        (
            "How much work must the brakes do to stop a 1200 kg car moving at 72 km/h?",
            "work_energy",
            -2.4e5,
            "J",
        ),
        (
            "A 750 W motor is 80% efficient. how long does it take to lift a 200 kg load "
            "through 6 m?",
            "lift_time_with_efficiency",
            19.62,
            "s",
        ),
        (
            "A spring with k = 800 N/m is compressed by 15 cm and launches a 200 g ball. "
            "what's the launch speed?",
            "spring_launch_speed",
            9.487,
            "m/s",
        ),
        (
            "A 0.5 kg ball is dropped from 2 m and bounces back up to 1.5 m. how much energy "
            "is lost in the bounce?",
            "bounce_energy_lost",
            2.4525,
            "J",
        ),
        (
            "a pump lifts 500 litres of water into a tank 12 m up in 2 minutes. what power "
            "does it need?",
            "pump_power",
            490.5,
            "W",
        ),
        (
            "A force of 25 N pushes a 4 kg box 6 m along a frictionless floor from rest. how "
            "fast is it going at the end?",
            "work_energy_speed",
            8.660,
            "m/s",
        ),
        (
            "A roller coaster car is moving at 5 m/s at the top of a 30 m high hill. ignoring "
            "friction, how fast is it at the bottom?",
            "energy_speed_from_moving_start",
            24.77,
            "m/s",
        ),
        (
            "A 2 m long pendulum is pulled back to 30° from the vertical and released. how fast "
            "is the bob at the lowest point?",
            "pendulum_bottom_speed",
            2.293,
            "m/s",
        ),
    ],
)
def test_energy_laws_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # Friction takes some of the drop's energy.
        "Using conservation of energy, a rough 2 kg block slides from rest down a 5 m high "
        "slope. Find its speed at the bottom.",
        # Bouncing higher than the drop is no loss.
        "A 0.5 kg ball is dropped from 1.5 m and bounces back up to 2 m. how much energy is "
        "lost in the bounce?",
        # Accelerating, the driving force is not P/v alone.
        "A car engine delivers 90 kW while the car accelerates at 2 m/s^2 through 25 m/s. "
        "What is the driving force?",
    ],
)
def test_energy_laws_decline_outside_their_shape(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "what's the orbital speed of a satellite 2000 km above the earths surface",
            "orbital_velocity",
            6900.0,
            "m/s",
        ),
        ("whats g at an altitude of 300 km above earth?", "gravity_at_height", 8.957, "m/s²"),
        (
            "A satellite has an orbital period of exactly 24 hours around Earth. what is the "
            "radius of its orbit?",
            "orbit_radius_from_period",
            4.224e7,
            "m",
        ),
        (
            "how much does a 70 kg astronaut weigh 400 km above the earth?",
            "weight_at_height",
            608.6,
            "N",
        ),
        (
            "A flywheel with I = 0.8 kg m^2 spins at 1200 rpm. What's its rotational KE?",
            "rotational_kinetic_energy",
            6317.0,
            "J",
        ),
        (
            "An ice skater spins at 2 rev/s with arms out (I = 4 kg·m²). She pulls her arms in "
            "so I = 1.6 kg·m². what's her new spin rate?",
            "angular_momentum_conservation",
            31.42,
            "rad/s",
        ),
    ],
)
def test_gravitation_and_rotation_laws_answer(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "You drive at 25 m/s toward a stationary siren of 800 Hz. what frequency do u hear? "
            "(v sound = 343 m/s)",
            "doppler_frequency",
            858.3,
            "Hz",
        ),
        (
            "A string 1.2 m long fixed at both ends has a wave speed of 240 m/s. What's the "
            "frequency of the 3rd harmonic?",
            "resonance_frequency",
            300.0,
            "Hz",
        ),
        (
            "a speaker radiates 2 W of sound equally in all directions. whats the intensity 5 m "
            "away",
            "point_source_intensity",
            0.006366,
            "W/m²",
        ),
        ("speed of sound in air at 30 °C?", "speed_of_sound_air", 349.0, "m/s"),
        (
            "A wave on a rope has frequency 4 Hz and wavelength 75 cm. how long does it take to "
            "travel 9 m?",
            "wave_travel_time",
            3.0,
            "s",
        ),
    ],
)
def test_wave_laws_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        ("A 4.7 kΩ resistor carries 2 mA. what is the voltage across it?", "voltage", 9.4, "V"),
        (
            "an LED draws 20 mA from a 3 V supply. what power does it use?",
            "electrical_power",
            0.06,
            "W",
        ),
        (
            "A 60 W bulb runs on 120 V. What is its resistance?",
            "resistance_from_power",
            240.0,
            "Ω",
        ),
        (
            "A 12 V battery with internal resistance 0.5 ohm is connected to a 5.5 ohm "
            "resistor. what current flows?",
            "current_with_internal_resistance",
            2.0,
            "A",
        ),
        (
            "how many kWh does a 60 W bulb use if it's left on for a whole week?",
            "energy_from_power_time",
            10.08,
            "kWh",
        ),
        (
            "A 1000 µF capacitor charged to 12 V discharges through a 500 Ω resistor. how long "
            "until the voltage drops to 3 V?",
            "capacitor_discharge_time",
            0.6931,
            "s",
        ),
        (
            "a proton travels at 3e6 m/s perpendicular to a 0.5 T field. radius of its circular "
            "path?",
            "charged_particle_radius",
            0.06264,
            "m",
        ),
        (
            "a coil of 200 turns, area 0.01 m^2, is in a field that drops from 0.5 T to 0 in "
            "0.1 s. average induced emf?",
            "faraday_emf",
            10.0,
            "V",
        ),
    ],
)
def test_electricity_and_magnetism_laws_answer(
    text: str, operation: str, value: float, unit: str
) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "a heat engine takes in 2000 J of heat and does 600 J of work per cycle. efficiency?",
            "efficiency_percent",
            30.0,
            "%",
        ),
        (
            "300 g of water at 90°C is mixed with 200 g of water at 20°C. what's the final temp?",
            "water_mixture_temperature",
            62.0,
            "°C",
        ),
        (
            "how much energy does it take to heat 1.5 kg of water from 68°F to 212°F",
            "heat_energy",
            5.023e5,
            "J",
        ),
        (
            "An aluminium rod 1.5 m long is heated from 20 °C to 120 °C. how much does it "
            "lengthen? α = 23×10^-6 /K",
            "linear_expansion_temperatures",
            0.00345,
            "m",
        ),
        (
            "a refrigerator removes 300 J of heat from inside while using 100 J of work. "
            "coefficient of performance?",
            "refrigerator_cop_from_heat",
            3.0,
            "",
        ),
        (
            "A 2 kW kettle heats 1.5 kg of water from 20 °C to 100 °C. assuming no heat loss, "
            "how long does it take?",
            "heating_time",
            251.2,
            "s",
        ),
    ],
)
def test_thermal_laws_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # A capacitor's voltage does not rise while it discharges.
        "A 1000 µF capacitor charged to 3 V discharges through a 500 Ω resistor. how long "
        "until the voltage drops to 12 V?",
        # A battery's internal resistance beside a parallel network is not one loop.
        "A 12 V battery with internal resistance 0.5 ohm drives a 5.5 ohm resistor and a "
        "4 ohm resistor in parallel. what current flows?",
    ],
)
def test_circuit_laws_decline_what_does_not_hold(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("left on for a whole week", "left on for 1 week"),
        ("for an hour", "for 1 hour"),
        ("a train travels at 120 kph", "a train travels at 120 km/h"),
        ("(v sound = 343 m/s)", "(speed of sound = 343 m/s)"),
        ("above the earths surface", "above the earth's surface"),
    ],
)
def test_normalize_physics_units_reads_everyday_spellings(written: str, read: str) -> None:
    assert normalize_physics_units(written) == read


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("how many kWh does a 60 W bulb use?", "kWh"),
        ("how many km does it travel?", "km"),
        # The SI unit, or a count, asks for no conversion.
        ("How many moles of ideal gas are in the tank?", None),
        ("how many turns does the coil need?", None),
    ],
)
def test_asked_unit_reads_how_many_units(text: str, unit: str | None) -> None:
    assert asked_unit(text) == unit


@pytest.mark.parametrize(
    ("expression", "written", "kelvin"),
    [("degC", 20.0, 293.15), ("degF", 68.0, 293.15), ("degF", 212.0, 373.15)],
)
def test_unit_dimension_reads_offset_temperature_scales(
    expression: str, written: float, kelvin: float
) -> None:
    reading = unit_dimension(expression)
    assert reading is not None
    _dimension, scale, offset = reading
    assert written * scale + offset == pytest.approx(kelvin)


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        (
            "A car at 30 m/s is chasing a truck doing 20 m/s that is 100 m ahead. how long to "
            "catch up?",
            "catch_up_time",
            10.0,
            "s",
        ),
        (
            "I walk 3 km east then 4 km north. what's my displacement?",
            "displacement_two_legs",
            5.0,
            "km (53.1° north of east)",
        ),
        (
            "A hiker walks 6 km south and then 8 km west. How far is she from her starting point?",
            "displacement_two_legs",
            10.0,
            "km (53.1° west of south)",
        ),
    ],
)
def test_relative_motion_readers_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    "text",
    [
        # A slower chaser never catches up.
        "A car at 20 m/s is chasing a truck doing 30 m/s that is 100 m ahead. how long to "
        "catch up?",
        # Which body chases is not written before the verb.
        "A truck doing 20 m/s is 100 m ahead of a car at 30 m/s that is chasing it. how long "
        "to catch up?",
        # Back along one axis: no right angle.
        "I walk 3 km east then 4 km west. what's my displacement?",
        # Between the axes.
        "I walk 3 km north-east then 4 km north. what's my displacement?",
        # The path walked, not the straight line.
        "I walk 3 km east then 4 km north. how far did I walk in total?",
    ],
)
def test_relative_motion_readers_decline_other_shapes(text: str) -> None:
    assert _operation(text) not in {"catch_up_time", "displacement_two_legs"}


# --- projectiles ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        # v0 = d * sqrt(g / 2h) = 1.2 * sqrt(9.81 / 1.8)
        (
            "A marble rolls off a 90 cm high bench and lands 1.2 m from the bench. "
            "how fast was it rolling?",
            2.80,
        ),
        (
            "A ball rolls off a 1.25 m high table and lands 2 m from its base. "
            "what was its launch speed?",
            3.96,
        ),
    ],
)
def test_level_launch_speed_reads_the_fall_and_the_landing(text: str, value: float) -> None:
    _assert_answer(text, "level_launch_speed", value, "m/s")


@pytest.mark.parametrize(
    "text",
    [
        # The speed at impact adds the fall's vertical speed: not the launch speed.
        "A marble rolls off a 90 cm high bench and lands 1.2 m from the bench. "
        "how fast was it going when it hit the floor?",
    ],
)
def test_level_launch_speed_declines_the_impact_speed(text: str) -> None:
    assert _operation(text) != "level_launch_speed"


@pytest.mark.parametrize(
    ("text", "values"),
    [
        (
            "A ball is kicked at 25 m/s at 40 degrees. (a) what is the max height (b) the range",
            ("13.2", "62.7"),
        ),
        (
            "A ball is kicked at 25 m/s at 40 degrees. (a) what is the time of flight "
            "(b) the range",
            ("3.28", "62.7"),
        ),
    ],
)
def test_projectile_parts_answer_every_labelled_part(text: str, values: tuple[str, ...]) -> None:
    answer = _answer(text)
    assert answer is not None, text
    for value in values:
        assert value in answer, answer


@pytest.mark.parametrize(
    "text",
    [
        # Part (c) is not a projectile quantity: two answers out of three is not the answer.
        "A ball is kicked at 25 m/s at 40 degrees. (a) what is the max height (b) the range "
        "(c) its kinetic energy",
        # Parts out of order are not one list.
        "A ball is kicked at 25 m/s at 40 degrees. (b) what is the max height (a) the range",
    ],
)
def test_projectile_parts_decline_a_dropped_part(text: str) -> None:
    assert _answer(text) is None


# --- modern -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "operation", "value", "unit"),
    [
        # hc/λ - φ = 4.959 eV - 4.2 eV
        (
            "Light of wavelength 250 nm shines on a metal with a work function of 4.2 eV. "
            "what is the max KE of the ejected electrons in eV?",
            "photoelectric_kinetic_energy_wavelength",
            0.759,
            "eV",
        ),
        # h / sqrt(2 m e V)
        (
            "What is the de Broglie wavelength of an electron accelerated through 150 V?",
            "de_broglie_from_voltage",
            1.0014e-10,
            "m",
        ),
        (
            "a proton is accelerated through a potential difference of 200 V. find its de "
            "Broglie wavelength",
            "de_broglie_from_voltage",
            2.024e-12,
            "m",
        ),
        # 0.003 u x 931.494 MeV/u
        (
            "In a nuclear reaction 0.003 u of mass is lost. how much energy is released in MeV?",
            "mass_energy_equivalence",
            2.794,
            "MeV",
        ),
        (
            "what's the energy of a 1.2 µm infrared photon in eV",
            "photon_energy",
            1.033,
            "eV",
        ),
    ],
)
def test_modern_laws_answer(text: str, operation: str, value: float, unit: str) -> None:
    _assert_answer(text, operation, value, unit)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        # P * lambda / (h c): one photon's energy was answered before, the power dropped.
        (
            "A 5 mW laser emits light of wavelength 630 nm. how many photons per second does "
            "it emit?",
            1.586e16,
        ),
        # P / (h f): a count per second, not the hertz of the given frequency.
        ("a 60 W bulb emits light at 5e14 Hz. how many photons does it emit per second?", 1.811e20),
    ],
)
def test_photon_emission_rate_counts_photons_not_one_energy(text: str, value: float) -> None:
    _assert_answer(text, "photon_emission_rate", value, "photons/s")


@pytest.mark.parametrize(
    "text",
    [
        # 50 kV is a tenth of an electron's rest energy: the classical momentum is off.
        "An electron is accelerated through 50 kV. what is its de broglie wavelength?",
        # A count over a stated time needs that time as an input: not the rate.
        "A 5 mW laser emits light of wavelength 630 nm. how many photons does it emit in 10 s?",
    ],
)
def test_modern_laws_decline_outside_their_reach(text: str) -> None:
    assert _answer(text) is None


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("0.003 u of mass is lost", "u"),
        ("the mass defect is 0.0304 u.", "u"),
        ("a mass of 4 amu", "amu"),
        # Written onto the number, or inside an equation, u is a velocity.
        ("show that v = 2u when t = 4", ""),
        ("v = 3 u + 2 when a = 0", ""),
    ],
)
def test_scan_givens_reads_an_atomic_mass_unit_only_where_written_as_one(
    text: str, unit: str
) -> None:
    givens = scan_givens(text)
    assert givens, text
    assert givens[0].unit == unit, givens
