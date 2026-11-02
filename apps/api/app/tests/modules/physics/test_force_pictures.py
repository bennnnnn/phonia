"""Draw the forces on a body: its free-body diagram even with no number to solve."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.modules.physics.extract import needs_physics
from app.modules.physics.fence import validate_physics_fences
from app.modules.physics.force_pictures import force_picture, force_picture_block
from app.modules.physics.prompt import solve_physics_request
from app.tests.behavior.harness import is_picture_only


def _labels(text: str) -> set[str]:
    picture = force_picture(text)
    assert picture is not None, text
    spec = picture.spec
    return {*(spec.arrow_labels or {}).values(), *(v.label for v in spec.vectors if v.label)}


@pytest.mark.parametrize(
    "text, kind, labels",
    [
        (
            "Draw the forces on a box sliding down a 30 degree incline with friction",
            "incline",
            {"mg", "N", "f"},
        ),
        ("Draw a free-body diagram of a block on a frictionless ramp", "incline", {"mg", "N"}),
        ("Draw a free-body diagram of a block at rest on an incline", "incline", {"mg", "N", "f"}),
        ("show the forces acting on a hanging mass", "free_body", {"T", "mg"}),
        ("draw the forces on a lamp suspended from the ceiling", "free_body", {"T", "mg"}),
        ("What forces act on a book resting on a table?", "free_body", {"mg", "N"}),
        (
            # A real table rubs: friction is drawn unless it is smooth.
            "draw the forces on a block on a table pulled by a rope at 30 degrees",
            "free_body",
            {"mg", "N", "T", "f"},
        ),
        (
            "draw a free-body diagram of a crate pushed across a rough floor",
            "free_body",
            {"mg", "N", "F", "f"},
        ),
        ("sketch the forces on a ball falling with air resistance", "free_body", {"mg", "drag"}),
        ("FBD of a stone thrown up in the air", "free_body", {"mg"}),
    ],
)
def test_force_picture_draws_the_situation_with_symbol_labels(
    text: str, kind: str, labels: set[str]
) -> None:
    picture = force_picture(text)
    assert picture is not None
    assert picture.spec.type == kind
    assert _labels(text) == labels
    # Symbols only: no number is invented for a force.
    assert not any(char.isdigit() for label in labels for char in label)


def test_force_picture_keeps_a_given_angle_and_names_a_missing_one() -> None:
    given = force_picture("draw the forces on a box on a 30° incline")
    missing = force_picture("draw the forces on a box on an incline")
    assert given is not None and missing is not None
    assert [angle.label for angle in given.spec.angles] == ["30°"]
    assert [angle.label for angle in missing.spec.angles] == ["θ"]
    assert "θ slope" in missing.shows


@pytest.mark.parametrize(
    "text",
    [
        "draw the forces of the market",
        "the forces of nature are amazing",
        "show me the incline at Lalibela",
        "what forces shaped the French revolution?",
        "draw a box",
        "what is the slope of y = 2x + 3?",
        # Rigs this draws no picture of: a loop of track, a pulley on a slope, one mass
        # on a pulley rope, a curve on ice.
        "draw the forces on a roller coaster cart at the top of a loop",
        "draw the forces on a block on an incline connected over a pulley to a hanging mass",
        "draw the forces on a mass hanging from a pulley",
        "draw the forces on a car on an icy curve",
        "draw the forces of the learning curve",
        "what forces shape the curve of supply and demand?",
        "how do I fix a squeaky pulley on my garage door?",
    ],
)
def test_force_picture_leaves_other_requests_alone(text: str) -> None:
    assert force_picture(text) is None


def test_a_digit_free_free_body_request_is_physics() -> None:
    assert needs_physics("show the forces acting on a hanging mass")
    assert not needs_physics("draw the forces of the market")


def test_a_force_picture_turn_carries_the_scene_and_no_result() -> None:
    text = "Draw the forces on a box sliding down a 30 degree incline with friction"
    outcome, block = solve_physics_request(text, get_settings(), None)
    assert outcome == "picture"
    assert block is not None and is_picture_only(block)
    assert block.canonical_fence is not None and block.canonical_fence["type"] == "incline"
    assert not block.allow_direct
    # The prompt says what the picture shows, so the prose can name each force.
    picture = force_picture(text)
    assert picture is not None and picture.shows in block.text


def test_a_solved_turn_is_not_picture_only() -> None:
    text = "A 5 kg box slides down a 30° incline with μ = 0.2. Find its acceleration."
    outcome, block = solve_physics_request(text, get_settings(), None)
    assert outcome == "verified"
    assert not is_picture_only(block)


def test_the_picture_replaces_a_sketch_in_characters() -> None:
    block = force_picture_block("show the forces acting on a hanging mass")
    assert block is not None
    reply = (
        "Two forces act on the mass.\n\n"
        "```text\n   ↑ T\n   │\n ┌───┐\n │ m │\n └───┘\n   │\n   ▼ mg\n```\n\n"
        "The tension $T$ balances the weight $mg$.\n\n"
        "```python\nT = m * g\n```"
    )
    out = validate_physics_fences(reply, verified=block)
    assert "┌───┐" not in out
    assert "```python" in out
    assert "```answer" not in out
    assert out.count("```simulation") == 1
    assert out.index("The tension") < out.index("```simulation")


@pytest.mark.parametrize(
    "text, kind, labels",
    [
        (
            "Draw the forces on a box pushed up a 25 degree incline with friction",
            "incline",
            {"mg", "N", "F", "f"},
        ),
        ("draw the forces on a box pulled up a ramp by a rope", "incline", {"mg", "N", "T", "f"}),
        (
            "draw a free body diagram of a block pushed horizontally up a frictionless 30° ramp",
            "incline",
            {"mg", "N", "F"},
        ),
        # Held still by the rope: friction's way is not drawn, only named.
        (
            "draw the forces on a block held at rest on a rough incline by a rope",
            "incline",
            {"mg", "N", "T"},
        ),
        ("show the forces on a crate pulled down a rough slope", "incline", {"mg", "N", "T", "f"}),
        (
            "draw the forces on a block sliding up an incline with friction",
            "incline",
            {"mg", "N", "f"},
        ),
        (
            "Draw a free-body diagram for two blocks connected by a string over a pulley",
            "free_body",
            {"T", "m₁g", "m₂g"},
        ),
        (
            "show the forces on a block on a rough table connected over a pulley to a hanging mass",
            "free_body",
            {"m₁g", "N", "T", "f", "m₂g"},
        ),
        ("draw the forces on a car going around a curve", "free_body", {"mg", "N", "f", "a"}),
        ("free body diagram of a car on a banked curve", "incline", {"mg", "N", "a"}),
        (
            "draw the forces on a ball on a string swung in a vertical circle",
            "free_body",
            {"T", "mg"},
        ),
    ],
)
def test_force_picture_draws_pulleys_curves_and_driven_slopes(
    text: str, kind: str, labels: set[str]
) -> None:
    picture = force_picture(text)
    assert picture is not None
    assert picture.spec.type == kind
    assert _labels(text) == labels
    # Symbols only: m₁g names a body, and no force gets a number.
    assert not any(char in "0123456789" for label in labels for char in label)


def test_friction_opposes_the_motion_on_a_driven_slope() -> None:
    up = force_picture("draw the forces on a box pushed up a 25 degree incline with friction")
    assert up is not None
    push = next(v for v in up.spec.vectors if v.label == "F")
    friction = next(v for v in up.spec.vectors if v.label == "f")
    # Pushed up the slope (up and to the left), friction down it (down and to the right).
    assert push.dx < 0 < push.dy and friction.dy < 0 < friction.dx
    assert "friction" not in up.spec.arrows
    down = force_picture("show the forces on a crate pulled down a rough slope")
    assert down is not None and "friction" in down.spec.arrows


def test_a_vertical_circle_draws_where_it_was_asked() -> None:
    both = force_picture("draw the forces on a ball on a string swung in a vertical circle")
    top = force_picture("draw the forces on a ball on a string at the top of a vertical circle")
    assert both is not None and top is not None
    assert len(both.spec.bodies) == 2 and len(top.spec.bodies) == 1
    # At the top both forces point down, to the centre.
    assert all(vector.dy < 0 for vector in top.spec.vectors)


def test_a_banked_curve_keeps_its_angle() -> None:
    picture = force_picture("draw the forces on a car on a road banked at 15 degrees")
    assert picture is not None
    assert [angle.label for angle in picture.spec.angles] == ["15°"]
    assert picture.spec.title_key == "circular_motion"


# A Class 8 book (2026-10-30): a body pushed, pulled or sliding on a real surface rubs
# against it, so friction is drawn unless the surface is smooth; a vehicle stands on a road.
@pytest.mark.parametrize(
    "text, labels",
    [
        (
            "A book is placed on the surface of a table. The book is pushed in one "
            "direction. Draw the forces acting on the book and explain.",
            {"mg", "N", "F", "f"},
        ),
        (
            "Draw a free body diagram (FBD) to show various forces acting on a body which "
            "is sliding on an inclined plane.",
            {"mg", "N", "f"},
        ),
        (
            "Draw and explain a free body diagram (FBD) to show all the forces acting on a car.",
            {"mg", "N", "F", "f"},
        ),
        ("Draw the forces on a parked car.", {"mg", "N"}),
        ("Draw the forces on a box pushed across a smooth floor.", {"mg", "N", "F"}),
        ("Draw the free-body diagram of a block resting on a table.", {"mg", "N"}),
        ("Draw the forces on a crate dragged along a frictionless floor.", {"mg", "N", "T"}),
    ],
)
def test_friction_is_drawn_where_a_body_rubs_on_a_surface(text: str, labels: set[str]) -> None:
    assert _labels(text) == labels


def test_the_reply_never_says_where_the_picture_is_drawn() -> None:
    text = "Draw the forces on a parked car."
    block = force_picture_block(text)
    assert block is not None
    reply = "The diagram is drawn under this reply. Its weight $mg$ acts down."
    out = validate_physics_fences(reply, verified=block, user_text=text)
    assert out.startswith("The diagram is shown below. Its weight")


# Review (2026-10-30): no friction on a body at rest with nothing driving it, and no
# level-road car for a car part, a rider, a braking car's engine force or a hill.
@pytest.mark.parametrize(
    "text, labels",
    [
        ("A box lies on the floor, not moving. Draw the forces on it.", {"mg", "N"}),
        ("A box rests on the floor and does not slide. What forces act on it?", {"mg", "N"}),
        ("Draw the forces acting on a box resting on the floor of a moving elevator.", {"mg", "N"}),
        (
            "A book lies on a table near the edge, facing towards the window. Draw the forces "
            "on the book.",
            {"mg", "N"},
        ),
        ("A box slides across the floor. Draw the forces on it.", {"mg", "N", "f"}),
        (
            "A car moves along a level road at constant speed. Draw the forces on it.",
            {"mg", "N", "F", "f"},
        ),
        ("Draw the forces on a car that is braking to a stop.", {"mg", "N", "f"}),
        ("A car coasts with its engine off. Draw the forces on it.", {"mg", "N", "f"}),
    ],
)
def test_friction_and_drive_follow_what_the_body_does(text: str, labels: set[str]) -> None:
    assert _labels(text) == labels


@pytest.mark.parametrize(
    "text",
    [
        "What forces act on a car engine piston?",
        "What forces act on a bicycle chain?",
        "Show the forces acting on a car tyre.",
        "Draw the forces on a person standing in a moving bus.",
        "A car drives up a hill. What forces act on it?",
    ],
)
def test_a_vehicle_part_rider_or_hill_is_no_level_road_car(text: str) -> None:
    picture = force_picture(text)
    assert picture is None or "vehicle" not in picture.shows


def test_a_man_is_named_as_himself() -> None:
    picture = force_picture("A man stands still on a level floor. Draw the forces on him.")
    assert picture is not None and picture.shows.startswith("a man on a level surface")


def test_the_picture_note_keeps_is_and_are() -> None:
    text = "Draw the forces on a parked car."
    block = force_picture_block(text)
    assert block is not None
    reply = "The forces are drawn below this answer. Its weight $mg$ acts down."
    out = validate_physics_fences(reply, verified=block, user_text=text)
    assert out.startswith("The forces are shown below.")


# Second review (2026-10-30): the vehicle is drawn only when its own forces are asked.
@pytest.mark.parametrize(
    "text, shows",
    [
        ("A lamp hangs from the ceiling of a bus. Draw the forces on the lamp.", "a hanging mass"),
        (
            "A pendulum bob hangs from the ceiling of an accelerating car. Draw the forces on "
            "the bob.",
            "a hanging mass",
        ),
        ("A ball is thrown from a moving car. Draw the forces on the ball.", "a body in the air"),
        ("Draw the forces on a box moving at constant velocity on a table.", "a box on a level"),
        ("An apple lies on a desk. Draw the forces on it.", "an apple on a level"),
    ],
)
def test_the_body_asked_about_is_the_one_drawn(text: str, shows: str) -> None:
    picture = force_picture(text)
    assert picture is not None and picture.shows.startswith(shows)


@pytest.mark.parametrize(
    "text",
    [
        "A car is towed by a truck. Draw the forces on the car.",
        "A truck pulls a trailer. Draw the forces on the trailer.",
    ],
)
def test_a_towed_vehicle_gets_no_engine_force(text: str) -> None:
    picture = force_picture(text)
    assert picture is None or "driving force" not in picture.shows


def test_a_box_at_constant_velocity_has_no_lone_friction() -> None:
    assert _labels("Draw the forces on a box moving at constant velocity on a table.") == {
        "mg",
        "N",
    }
