"""P14: the `simulation` fence — a scene, not a plot of one.

P3 animated the trajectory *graph*, which shows the shape of a path. Seven of
the eleven verified kinds draw nothing at all, and for several the picture is
the explanation: circular motion is the most natural animation in the subject
and had no visual whatsoever.

`GraphBlockSpec` cannot express a scene. It is an x-y plot with axes and one
curve; a scene needs bodies with sizes, a ground, and force vectors pointing
somewhere in the world rather than along an axis.

This is the first slice the ticket asked for — the spec plus projectile and
orbit. Collisions are the next one, and the spec already carries what they
need (several bodies on one clock), which is asserted here so the shape cannot
drift before they land.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.physics.reply_policy import PHYSICS_SHORT_HINT
from app.modules.physics.schemas import (
    PhysicsIntent,
    SimulationBlockSpec,
    SimulationBody,
    SimulationVector,
)
from app.modules.physics.solver import solve_physics
from app.tests.modules.physics.support import (
    _spec_fence_kind,
    build_verified_physics_block,
    extract_physics_intent,
    validate_physics_fences,
)

PROJECTILE_Q = "a ball is thrown at 20 m/s at 30 degrees, what is the range"
CIRCULAR_Q = (
    "what is the centripetal acceleration of a car going 10 m/s around a 20 m radius corner"
)


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _scene(text: str) -> SimulationBlockSpec:
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)
    specs = solve_physics(intent).simulation_specs
    assert len(specs) == 1
    return specs[0]


def _fence_body(text: str, reply: str = "Here you go.") -> dict | None:
    """The scene as it actually reaches the client, through the real pipeline."""
    intent = extract_physics_intent(text)
    assert intent is not None
    out = validate_physics_fences(reply, verified=build_verified_physics_block(intent, _settings()))
    if "```simulation" not in out:
        return None
    return json.loads(out.split("```simulation")[1].split("```")[0].strip())


# --- what each kind now draws -----------------------------------------------


def test_a_projectile_answer_carries_one_labelled_scene() -> None:
    """One picture, not two of the same throw.

    The scene carries what the graph used to: the range and the height as
    measure lines and the launch angle as an arc.
    """
    intent = extract_physics_intent(PROJECTILE_Q)
    assert isinstance(intent, PhysicsIntent)
    result = solve_physics(intent)

    assert result.graph_specs == []
    (scene,) = result.simulation_specs
    labels = [vector.label for vector in scene.vectors]
    assert labels == ["R = 35.3 m", "H = 5.1 m"]
    assert [angle.label for angle in scene.angles] == ["30°"]
    assert scene.title_key == "projectile" and scene.alt


def test_the_scene_is_the_solved_path() -> None:
    """So the ball can never be somewhere the answer is not.

    It lands exactly at the range the answer gives, lifted by the ball's
    radius so it rests on the ground instead of half sunk in it.
    """
    intent = extract_physics_intent(PROJECTILE_Q)
    assert isinstance(intent, PhysicsIntent)
    result = solve_physics(intent)
    body = result.simulation_specs[0].bodies[0]

    assert body.path[0] == [0.0, body.radius]
    assert body.path[-1][0] == pytest.approx(result.quantities[0].value)
    assert body.path[-1][1] == pytest.approx(body.radius)


def test_circular_motion_finally_draws_something() -> None:
    """The kind the round-2 review found most conspicuously blank."""
    scene = _scene(CIRCULAR_Q)

    assert scene.type == "orbit"
    assert scene.centre == [0.0, 0.0]
    assert "centripetal" in scene.arrows


def test_the_orbit_is_actually_circular() -> None:
    """Every sample the same distance from the centre, at a constant angular
    step — which is what uniform circular motion is, and what makes the index
    the clock here as everywhere else."""
    import math

    scene = _scene(CIRCULAR_Q)
    path = scene.bodies[0].path
    radii = [math.hypot(x, y) for x, y in path]

    assert all(r == pytest.approx(radii[0], rel=1e-3) for r in radii)
    assert radii[0] == pytest.approx(20.0, rel=1e-3)
    # First and last sample coincide: one closed lap.
    assert path[0] == pytest.approx(path[-1], abs=1e-3)


@pytest.mark.parametrize(
    "text,expected",
    [
        (PROJECTILE_Q, "projectile_motion"),
        ("a ball is kicked at 20 m/s at 30 degrees, how high does it go", "projectile_motion"),
        (CIRCULAR_Q, "orbit"),
        ("what is the centripetal force on a 2 kg mass at 5 m/s on a 4 m radius", "orbit"),
        ("what is the period of a car going 10 m/s around a 20 m radius track", "orbit"),
    ],
)
def test_every_projectile_and_circular_op_gets_a_scene(text: str, expected: str) -> None:
    assert _scene(text).type == expected


# --- the scene is honest about what it draws --------------------------------


def test_a_projectile_scene_has_ground_under_it() -> None:
    """A projectile landing on nothing reads as a dot drifting in a box."""
    scene = _scene(PROJECTILE_Q)

    assert scene.ground is True
    assert scene.type == "projectile_motion"


def test_the_projectile_arrows_are_the_two_that_mean_something() -> None:
    """Velocity because it changes, gravity because it does not.

    A centripetal arrow on a parabola would be nonsense, and the scene does not
    carry one.
    """
    assert set(_scene(PROJECTILE_Q).arrows) == {"velocity", "gravity"}


def test_the_scene_leaves_headroom_above_the_apex() -> None:
    """The gravity arrow hangs off the body, so a box that stops at the peak
    clips it exactly where the picture is most interesting."""
    scene = _scene(PROJECTILE_Q)
    peak = max(y for _, y in scene.bodies[0].path)

    assert scene.y_max > peak


def test_the_path_stays_inside_the_scene() -> None:
    """A body leaving the box is drawn outside the SVG and simply vanishes."""
    for text in (PROJECTILE_Q, CIRCULAR_Q):
        scene = _scene(text)
        for x, y in scene.bodies[0].path:
            assert scene.x_min <= x <= scene.x_max
            assert scene.y_min <= y <= scene.y_max


# --- the fence, end to end --------------------------------------------------


def test_the_scene_reaches_the_reply_as_a_simulation_fence() -> None:
    body = _fence_body(PROJECTILE_Q)

    assert body is not None
    assert body["type"] == "projectile_motion"
    assert len(body["bodies"][0]["path"]) == 100


def test_canvas_labels_drop_redundant_decimal_zeros() -> None:
    body = _fence_body(FMA_Q)

    assert body is not None
    labels = [vector["label"] for vector in body["vectors"]]
    assert labels == ["F = 10 N", "a = 2 m/s²"]


def test_a_circular_answer_gets_a_scene_and_no_graph() -> None:
    """Circular motion has no curve to plot — its picture is the scene."""
    intent = extract_physics_intent(CIRCULAR_Q)
    assert intent is not None
    out = validate_physics_fences(
        "Here you go.", verified=build_verified_physics_block(intent, _settings())
    )

    assert "```simulation" in out
    assert "```graph" not in out


def test_a_clarifying_reply_gets_no_scene_either() -> None:
    """P12 covers every extra, and a scene is one.

    Worth pinning separately: P12 was written when there were two kinds of
    extra, and a third that slipped past the guard would put an animation under
    a question the model just said it could not answer.
    """
    assert _fence_body(PROJECTILE_Q, "Which angle do you mean — launch or elevation?") is None


def test_an_invented_scene_is_never_passed_through() -> None:
    """Server-owned, like geometry and graph. A model that writes its own
    physics animation gets it replaced by the verified one."""
    intent = extract_physics_intent(PROJECTILE_Q)
    assert intent is not None
    invented = '```simulation\n{"type":"orbit","bodies":[{"path":[[0,0],[1,1]]}]}\n```'
    out = validate_physics_fences(
        f"Here you go.\n\n{invented}",
        verified=build_verified_physics_block(intent, _settings()),
    )

    assert '"orbit"' not in out
    assert out.count("```simulation") <= 2  # one opener, one closer


def test_an_invented_scene_with_no_verified_block_is_struck_out() -> None:
    out = validate_physics_fences('```simulation\n{"type":"orbit","bodies":[]}\n```')

    assert PHYSICS_SHORT_HINT not in out
    assert "Could not render that diagram" in out


# --- the spec's own rules ---------------------------------------------------


def _body(**kwargs: object) -> SimulationBody:
    return SimulationBody(**{"path": [[0.0, 0.0], [1.0, 1.0]], **kwargs})  # type: ignore[arg-type]


def test_a_scene_accepts_several_bodies_on_one_clock() -> None:
    """The shape collisions need, asserted before they land so it cannot drift."""
    scene = SimulationBlockSpec(
        type="projectile_motion",
        bodies=[_body(), _body(role="secondary")],
    )

    assert len(scene.bodies) == 2
    assert scene.bodies[1].role == "secondary"


def test_bodies_sampled_at_different_rates_are_refused() -> None:
    """One clock walks them all, so unequal lengths drift apart on screen — a
    collision shown at the wrong moment, which is worse than no picture."""
    with pytest.raises(ValidationError):
        SimulationBlockSpec(
            type="projectile_motion",
            bodies=[_body(), _body(path=[[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])],
        )


def test_a_centripetal_arrow_requires_a_centre() -> None:
    """ "Toward the centre" is meaningless without one, and would be drawn
    toward the origin of the scene box instead."""
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="orbit", bodies=[_body()], arrows=["centripetal"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x_min": 10.0, "x_max": 0.0},
        {"y_min": 10.0, "y_max": 0.0},
    ],
)
def test_inverted_bounds_are_refused(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="orbit", bodies=[_body()], **kwargs)


def test_a_one_sample_path_is_not_motion() -> None:
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="orbit", bodies=[_body(path=[[0.0, 0.0]])])


def test_a_non_finite_sample_is_refused() -> None:
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="orbit", bodies=[_body(path=[[0.0, 0.0], [float("inf"), 1.0]])])


def test_the_title_defaults_rather_than_rendering_blank() -> None:
    assert SimulationBlockSpec(type="orbit", bodies=[_body()]).title == "Orbit"
    assert SimulationBlockSpec(type="projectile_motion", bodies=[_body()]).title == "Projectile"


# --- second slice: collisions and inclines ----------------------------------
#
# The two scenes the ticket named after the orbit. A collision is the case a
# number genuinely cannot carry — "1 m/s and 4 m/s" is the right answer
# and says nothing about which ball ends up ahead, whether either turns round,
# or that the pair keeps moving together when they stick. An incline is mostly
# a *diagram*: for two of the three friction ops the block never moves, and the
# free-body picture is what the question wanted.

ELASTIC_Q = (
    "in an elastic collision a 2 kg ball at 3 m/s hits a 1 kg ball at rest, "
    "find the final velocities"
)
INELASTIC_Q = (
    "a 2 kg ball at 3 m/s hits a 1 kg ball at rest and they stick together, find the final velocity"
)
SLIDING_Q = (
    "a block is released from rest on a 30 degree incline with a coefficient of friction of 0.2, "
    "what is the acceleration"
)
NORMAL_Q = "what is the normal force on a 5 kg block on a 30 degree incline"
HELD_Q = (
    "a block on a 10 degree incline with a coefficient of friction of 0.5, what is the acceleration"
)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# Path samples ship rounded to 4 dp to keep the fence small, so one step
# carries up to 1e-4 of error and a ratio of two of them amplifies it well past
# anything worth asserting. Measuring across a long span leaves the same
# absolute error on a displacement twenty times larger.
_SPAN = 20


def _speeds(path: list[list[float]]) -> tuple[float, float]:
    """Displacement per sample well before and well after contact.

    The clock is uniform, so this *is* a speed up to one constant factor —
    which is all these comparisons need.
    """
    return (
        (path[_SPAN][0] - path[0][0]) / _SPAN,
        (path[-1][0] - path[-1 - _SPAN][0]) / _SPAN,
    )


def test_a_collision_answer_carries_two_bodies() -> None:
    scene = _scene(ELASTIC_Q)

    assert scene.type == "collision"
    assert len(scene.bodies) == 2
    assert [b.role for b in scene.bodies] == ["primary", "secondary"]


def test_the_heavier_ball_is_drawn_larger() -> None:
    """Radius from mass by cube root, since a ball's size goes with its volume.

    Two identical circles would make the scene unreadable: which one is the
    2 kg ball is the first thing a viewer needs.
    """
    scene = _scene(ELASTIC_Q)
    heavy, light = scene.bodies

    assert heavy.radius > light.radius
    assert heavy.radius / light.radius == pytest.approx(2 ** (1 / 3), rel=1e-9)


def test_the_bodies_touch_exactly_at_contact() -> None:
    """Their surfaces meet at the midpoint of the clock — neither overlapping
    (which reads as passing through each other) nor short of it."""
    scene = _scene(ELASTIC_Q)
    b1, b2 = scene.bodies
    mid = len(b1.path) // 2

    gap = b2.path[mid][0] - b1.path[mid][0]
    # Tolerance set by the 4 dp the path ships at, not by the geometry.
    assert gap == pytest.approx(b1.radius + b2.radius, abs=1e-3)


def test_the_scene_shows_the_verified_speeds() -> None:
    """2 kg at 3 m/s into 1 kg at rest gives 1 m/s and 4 m/s.

    The scene has to move at those speeds, not at some display-friendly
    approximation, or it contradicts the pill printed above it.
    """
    scene = _scene(ELASTIC_Q)
    before1, after1 = _speeds(scene.bodies[0].path)
    before2, after2 = _speeds(scene.bodies[1].path)

    assert after1 / before1 == pytest.approx(1 / 3, rel=1e-3)  # 3 m/s -> 1 m/s
    assert before2 == pytest.approx(0.0, abs=1e-9)  # at rest
    assert after2 / after1 == pytest.approx(4.0, rel=1e-3)  # 4 m/s vs 1 m/s


def test_an_elastic_collision_separates_as_fast_as_it_approached() -> None:
    """The property that *defines* elastic, visible in the scene itself.

    Relative speed is preserved, so the gap at the start and the gap at the end
    are equal — which is a stronger check than either speed alone and would
    catch the two final velocities being swapped.
    """
    scene = _scene(ELASTIC_Q)
    b1, b2 = scene.bodies

    start_gap = b2.path[0][0] - b1.path[0][0]
    end_gap = b2.path[-1][0] - b1.path[-1][0]

    assert end_gap == pytest.approx(start_gap, abs=1e-3)


def test_an_inelastic_collision_leaves_them_stuck() -> None:
    """The counterpart, and the thing the single number cannot say at all."""
    scene = _scene(INELASTIC_Q)
    b1, b2 = scene.bodies

    start_gap = b2.path[0][0] - b1.path[0][0]
    end_gap = b2.path[-1][0] - b1.path[-1][0]

    assert start_gap > end_gap
    assert end_gap == pytest.approx(b1.radius + b2.radius, abs=1e-3)
    # Moving together means identical steps.
    assert _speeds(b1.path)[1] == pytest.approx(_speeds(b2.path)[1], abs=1e-4)


def test_a_collision_shows_velocity_and_nothing_it_cannot_justify() -> None:
    """Gravity is not acting along the track and there is no centre to orbit."""
    assert _scene(ELASTIC_Q).arrows == ["velocity"]


# --- inclines ---------------------------------------------------------------


@pytest.mark.parametrize("text", [SLIDING_Q, NORMAL_Q, HELD_Q])
def test_every_incline_op_gets_a_scene(text: str) -> None:
    assert _scene(text).type == "incline"


def test_the_incline_carries_its_angle() -> None:
    """The renderer reads normal and friction off the slope, not off the
    motion, so the angle has to travel with the scene."""
    scene = _scene(SLIDING_Q)

    assert scene.incline_deg == pytest.approx(30.0)


def test_the_block_sits_on_the_slope_it_is_given() -> None:
    """Every sample lies on the stated line, so the drawn surface and the drawn
    block cannot disagree about where the slope is."""
    import math

    scene = _scene(SLIDING_Q)
    theta = math.radians(scene.incline_deg or 0.0)
    x0, y0 = scene.bodies[0].path[0]

    for x, y in scene.bodies[0].path:
        assert y == pytest.approx(y0 - (x - x0) * math.tan(theta), abs=1e-3)


def test_a_sliding_block_speeds_up() -> None:
    """s = ½at² sampled uniformly in time, so the acceleration is the thing you
    see — a block moving at a constant rate down a slope would be a lie about
    the very quantity the answer reports."""
    path = _scene(SLIDING_Q).bodies[0].path
    first = path[1][0] - path[0][0]
    last = path[-1][0] - path[-2][0]

    assert last > first * 2


def test_a_block_friction_holds_does_not_move() -> None:
    """tan(10°) < 0.5, so a = 0 — and the scene says so by standing still.

    Showing it slide would contradict the answer directly.
    """
    assert _verified_answer(HELD_Q) == "0 m/s²"
    path = _scene(HELD_Q).bodies[0].path

    assert all(point == path[0] for point in path)


def test_an_incline_shows_weight_normal_and_friction() -> None:
    """The three forces the ticket named."""
    assert set(_scene(SLIDING_Q).arrows) == {"gravity", "normal", "friction"}


def test_a_frictionless_slope_draws_no_friction_arrow() -> None:
    """An arrow for a force that is not acting is worse than a missing one."""
    scene = _scene("a block slides down a frictionless 30 degree incline, what is the acceleration")

    assert "friction" not in scene.arrows
    assert {"gravity", "normal"} <= set(scene.arrows)


def test_a_flat_surface_gets_a_floor_diagram_not_an_incline() -> None:
    """A box on a floor: its weight and the normal force, the asked one the
    highlighted result. No slope, so no friction direction is invented."""
    intent = extract_physics_intent("what is the normal force on a 5 kg block")
    assert isinstance(intent, PhysicsIntent)

    (scene,) = solve_physics(intent).simulation_specs
    assert scene.type == "free_body" and scene.ground
    assert scene.bodies[0].shape == "box"
    weight, normal = scene.vectors
    assert weight.dy < 0 and normal.dy > 0
    assert normal.role == "result" and normal.label == "N = 49.1 N"


def test_a_floor_friction_question_draws_friction_against_the_push() -> None:
    intent = extract_physics_intent(
        "What minimum force is needed to start moving a 50 kg desk "
        "if the coefficient of static friction is 0.4?"
    )
    assert isinstance(intent, PhysicsIntent)

    (scene,) = solve_physics(intent).simulation_specs
    friction, push = scene.vectors[2:]
    assert friction.dx < 0 < push.dx
    assert push.role == "result" and push.label == "F = 196.2 N"


def test_the_angle_ships_without_floating_point_noise() -> None:
    """It arrives here through radians, so 30 comes back as 29.999999999999996
    and would ship in the fence JSON that way."""
    body = _fence_body(SLIDING_Q)

    assert body is not None
    assert body["incline_deg"] == 30.0


# --- the spec's rules for the new fields ------------------------------------


def test_normal_and_friction_arrows_require_a_slope() -> None:
    """Both are read off the slope, and a normal force pointing the wrong way
    is a more confident lie than no arrow at all."""
    for arrow in ("normal", "friction"):
        with pytest.raises(ValidationError):
            SimulationBlockSpec(type="incline", bodies=[_body()], arrows=[arrow])


def test_a_spring_scene_needs_its_wall() -> None:
    """The coil is drawn from the anchor. A missing wall is not a scene."""
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="spring", bodies=[_body()])


def test_a_scene_without_a_wall_does_not_grow_an_anchor_key() -> None:
    """Stored replies were written before springs. A null anchor would change them."""
    dumped = SimulationBlockSpec(type="projectile_motion", bodies=[_body()]).model_dump()
    assert "anchor" not in dumped
    spring = SimulationBlockSpec(type="spring", bodies=[_body()], anchor=[-1.0, 0.0]).model_dump()
    assert spring["anchor"] == [-1.0, 0.0]


def test_a_vertical_slope_is_refused() -> None:
    """At 90 degrees it is not an incline, it is a drop."""
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="incline", bodies=[_body()], incline_deg=90.0)


def test_each_scene_kind_has_its_own_default_title() -> None:
    for kind, title in [
        ("projectile_motion", "Projectile"),
        ("orbit", "Orbit"),
        ("collision", "Collision"),
        ("incline", "Inclined Plane"),
    ]:
        assert SimulationBlockSpec(type=kind, bodies=[_body()]).title == title  # type: ignore[arg-type]
    assert (
        SimulationBlockSpec(type="spring", bodies=[_body()], anchor=[-1.0, 0.0]).title == "Spring"
    )


def test_the_fence_layer_knows_every_scene_kind() -> None:
    """The one table both the fence layer and the direct guard read.

    A fifth scene type added to the schema and not to this set would be
    classified as a graph — it carries `x_min` too — and rendered as an empty
    pair of axes.
    """
    import typing

    from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES, SimulationType

    assert SIMULATION_SPEC_TYPES == set(typing.get_args(SimulationType))
    for kind in SIMULATION_SPEC_TYPES:
        assert _spec_fence_kind({"type": kind}) == "simulation"


# --- third slice: the still figures -----------------------------------------
#
# Four scene types have something moving; these three do not, and that is the
# point. A see-saw, a free-body diagram and a sum of force vectors are pictures
# of *forces*, which is what the four remaining number-only kinds were short
# of. Their arrows cannot be derived from a path — the direction of a resultant
# is the answer, not a consequence of it — so the solver states them, with the
# magnitude it already computed in the label.

TORQUE_Q = "torque of a 5 N force at 2 m from the pivot"
BALANCE_Q = "a 5 N force is 2 m from the pivot, how far must a 10 N force be to balance it"
FMA_Q = "a 5 kg mass accelerates at 2 m/s^2, what is the net force"
TENSION_Q = "what is the tension in a rope lifting a 5 kg mass at 2 m/s^2"
ATWOOD_Q = "an atwood machine with masses 3 kg and 5 kg, what is the acceleration"
RESULTANT_Q = "a 3 N force east and a 4 N force north, what is the resultant"
RESOLVE_Q = "resolve a 10 N force at 30 degrees into components"


@pytest.mark.parametrize(
    "text,expected",
    [
        (TORQUE_Q, "lever"),
        (BALANCE_Q, "lever"),
        (FMA_Q, "free_body"),
        (TENSION_Q, "free_body"),
        (ATWOOD_Q, "free_body"),
        (RESULTANT_Q, "vector_sum"),
        (RESOLVE_Q, "vector_sum"),
    ],
)
def test_the_last_two_number_only_kinds_now_draw(text: str, expected: str) -> None:
    """`torque` and `force` were two of the four kinds with no picture at all."""
    assert _scene(text).type == expected


def test_a_see_saw_shows_both_arms_where_they_actually_are() -> None:
    """The picture that makes P9's pairing bug impossible to miss.

    "the distance for a 10 N force to balance a 5 N force at 2 m" was once
    answered 4 m because the 2 m was read onto the force written first. Drawing
    each load at the arm it actually has puts that mistake on screen instead of
    leaving it in a number.
    """
    scene = _scene(BALANCE_Q)
    known, answer = scene.vectors

    assert known.anchor[0] == pytest.approx(-2.0)
    assert answer.anchor[0] == pytest.approx(1.0)
    assert answer.role == "result"
    # The label reads like the answer: "1 m", not "1.00 m".
    assert answer.label == "10 N at 1 m"
    # Each arrow carries its load, so the 10 N one out-reaches the 5 N one.
    assert abs(answer.dy) == pytest.approx(2 * abs(known.dy))


def test_the_two_moments_the_see_saw_draws_actually_balance() -> None:
    """F d on one side equals F d on the other, read off the drawn arms."""
    scene = _scene(BALANCE_Q)
    left, right = scene.vectors

    assert 5.0 * abs(left.anchor[0]) == pytest.approx(10.0 * abs(right.anchor[0]), rel=1e-3)


def test_a_lever_has_its_beam_and_its_pivot() -> None:
    scene = _scene(TORQUE_Q)

    assert scene.beam is not None
    assert scene.pivot == [0.0, 0.0]
    # Both arms are inside the drawn beam, or a load would hang off the end.
    assert scene.beam is not None
    for vector in scene.vectors:
        assert scene.beam[0] <= vector.anchor[0] <= scene.beam[2]


def test_an_angled_torque_is_drawn_at_the_angle_it_was_given() -> None:
    """tau = F d sin(theta) — the sin is the thing on screen rather than a
    factor to take on trust, so the arrow leans by exactly that angle."""
    import math

    square_on = _scene(TORQUE_Q).vectors[0]
    angled = _scene("torque of a 5 N force applied 2 m from the pivot at 30 degrees").vectors[0]

    assert square_on.dx == 0.0 and square_on.dy < 0
    assert math.atan2(-angled.dy, angled.dx) == pytest.approx(math.radians(30))
    # The force is given, not asked: the torque is the answer.
    assert angled.role == "force"


def test_tension_is_drawn_against_the_weight_it_carries() -> None:
    """Two arrows and a mass is the whole of this problem, and seeing them is
    what makes T = m(g + a) rather than m*a obvious."""
    scene = _scene(TENSION_Q)
    rope, weight = scene.vectors

    assert rope.dy > 0 and weight.dy < 0
    assert rope.role == "result"
    assert "59.1 N" in (rope.label or "")
    assert "49.1 N" in (weight.label or "")


def test_the_labels_carry_the_numbers_the_answer_carries() -> None:
    """Otherwise the picture and the pill could drift apart."""
    answer = _verified_answer(TENSION_Q)
    body = _fence_body(TENSION_Q)
    assert body is not None
    labels = " ".join(vector.get("label") or "" for vector in body["vectors"])

    assert answer is not None
    assert answer.split()[0] in labels


def test_an_atwood_pair_moves_in_opposite_directions_at_one_rate() -> None:
    """The whole idea of the apparatus, and the thing "2.45 m/s^2 and 36.79 N"
    gives no hint of."""
    scene = _scene(ATWOOD_Q)
    heavy, light = scene.bodies

    assert heavy.path[-1][1] < heavy.path[0][1]  # descends
    assert light.path[-1][1] > light.path[0][1]  # rises
    assert abs(heavy.path[-1][1] - heavy.path[0][1]) == pytest.approx(
        abs(light.path[-1][1] - light.path[0][1]), rel=1e-6
    )


def test_moving_pairs_keep_their_mass_labels() -> None:
    """The renderer cannot identify two moving bodies if their labels vanish."""
    atwood = _scene(ATWOOD_Q)
    collision = _scene(ELASTIC_Q)

    assert [body.label for body in atwood.bodies] == ["5 kg", "3 kg"]
    assert [body.label for body in collision.bodies] == ["2 kg", "1 kg"]


def test_a_resultant_out_reaches_the_components_it_came_from() -> None:
    """Here the arrow *lengths* carry meaning, unlike every other scene.

    A resultant drawn no longer than its parts would be the one picture that
    contradicts its own answer.
    """
    import math

    scene = _scene(RESULTANT_Q)
    result = next(v for v in scene.vectors if v.role == "result")
    parts = [v for v in scene.vectors if v.role == "force"]

    length = math.hypot(result.dx, result.dy)
    assert length == pytest.approx(5.0, rel=1e-6)
    for part in parts:
        assert length > math.hypot(part.dx, part.dy)


def test_the_resolved_components_form_a_right_triangle_with_their_force() -> None:
    """Tip of the horizontal component is where the vertical one starts, so the
    three arrows close — which is what resolving *means*."""
    scene = _scene(RESOLVE_Q)
    horizontal, vertical, original = scene.vectors

    assert vertical.anchor[0] == pytest.approx(horizontal.dx)
    assert vertical.anchor[1] == pytest.approx(0.0)
    assert original.dx == pytest.approx(horizontal.dx)
    assert original.dy == pytest.approx(vertical.dy)


def test_a_still_figure_needs_no_bodies() -> None:
    """A see-saw's picture is its beam and its loads; there is nothing to walk
    a clock through."""
    assert _scene(BALANCE_Q).bodies == []


def test_a_scene_with_neither_bodies_nor_vectors_is_refused() -> None:
    with pytest.raises(ValidationError):
        SimulationBlockSpec(type="lever")


def test_a_vector_needs_a_direction() -> None:
    """Zero length is not an arrow pointing nowhere, it is a missing answer."""
    with pytest.raises(ValidationError):
        SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=0.0)


def test_a_pivot_requires_a_beam() -> None:
    """On its own it is a dot in space."""
    with pytest.raises(ValidationError):
        SimulationBlockSpec(
            type="lever",
            vectors=[SimulationVector(anchor=[0.0, 0.0], dx=0.0, dy=-1.0)],
            pivot=[0.0, 0.0],
        )


def test_a_picture_does_not_grant_a_direct_reply() -> None:
    """Force and energy answers are unlabeled quantities, deliberately kept on
    the model path so the prompt can name the symbol.

    Attaching a scene routes through the diagram branch of the block builder,
    which is how that permission nearly flipped silently.
    """
    intent = extract_physics_intent(FMA_Q)
    assert intent is not None
    block = build_verified_physics_block(intent, _settings())

    assert block is not None
    assert block.allow_direct is False
    # The answer fence still leads, so the pill and the direct guard both work.
    assert block.canonical_fence is not None
    assert block.canonical_fence.get("type") == "answer"


# --- energy: only where there is something spatial --------------------------


def test_potential_energy_shows_the_height_it_multiplies() -> None:
    """The h in mgh is a quantity you can point at, so the picture points at it."""
    scene = _scene("what is the potential energy of a 2 kg object at a height of 5 m")
    weight, height = scene.vectors

    assert scene.ground is True
    assert weight.dy < 0 and "19.6 N" in (weight.label or "")
    assert height.role == "measure"
    assert height.dy == pytest.approx(5.0)
    assert "5 m" in (height.label or "")


def test_work_shows_the_distance_the_force_acted_over() -> None:
    scene = _scene("find the work done by a force of 10 N over a distance of 3 m")
    force, distance = scene.vectors

    assert force.dx > 0 and force.role == "result"
    assert distance.role == "measure"
    assert distance.dx == pytest.approx(3.0)


@pytest.mark.parametrize(
    "text",
    [
        "what is the kinetic energy of a 2 kg object moving at 3 m/s",
        "what is the power of a force of 10 N moving at 3 m/s",
    ],
)
def test_energy_without_a_spatial_quantity_draws_nothing(text: str) -> None:
    """A block with a "3 m/s" arrow beside it tells you nothing the sentence
    did not. A speed is not a thing you can point at, so these get no picture
    rather than a decorative one."""
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)

    assert solve_physics(intent).simulation_specs == []


def test_a_measure_is_not_drawn_as_a_force() -> None:
    """Its own role, so the client can draw it as a dimension line — a height
    that looked like a third force acting on the block would be a wrong
    free-body diagram, not just an ugly one."""
    scene = _scene("what is the potential energy of a 2 kg object at a height of 5 m")

    assert [v.role for v in scene.vectors] == ["force", "measure"]


def test_a_tension_arrow_out_reaches_the_weight_it_lifts() -> None:
    """The arrows carry their sizes, so T > W is visible when the mass speeds up."""
    rope, weight = _scene(TENSION_Q).vectors

    assert rope.dy == pytest.approx(5 * (9.81 + 2))
    assert weight.dy == pytest.approx(-5 * 9.81)


def test_an_acceleration_is_never_drawn_as_a_force() -> None:
    force, accel = _scene(FMA_Q).vectors

    assert force.role == "result"
    assert accel.role == "motion"


def test_a_given_force_is_not_the_highlighted_answer() -> None:
    force, accel = _scene("a 10 N force acts on a 2 kg mass, what is its acceleration").vectors

    assert force.role == "force"
    assert accel.role == "motion"


def test_the_atwood_scene_hangs_both_masses_from_a_pulley() -> None:
    """A wheel, a rope to each mass, the tension pulling each one up and its
    acceleration beside it: nothing pushes the pulley down."""
    scene = _scene(ATWOOD_Q)

    assert scene.pulley is not None
    assert sorted(tether.body for tether in scene.tethers) == [0, 1]
    tensions = [vector for vector in scene.vectors if vector.role == "result"]
    assert [vector.body for vector in tensions] == [0, 1]
    assert all(vector.dy > 0 for vector in tensions)
    heavy, light = (vector for vector in scene.vectors if vector.role == "motion")
    assert heavy.dy < 0 < light.dy


def test_upthrust_is_the_highlighted_answer_and_no_weight_is_invented() -> None:
    scene = _scene("what is the upthrust on a 0.002 m^3 object fully submerged in water")

    (upthrust,) = scene.vectors
    assert upthrust.role == "result" and upthrust.dy > 0
    assert upthrust.label == "F = 19.6 N"
    assert scene.bodies[0].label is None


def test_a_tiny_throw_fills_its_frame() -> None:
    """A 1 m floor left a 2 cm flick as a smear at the bottom of an empty box."""
    scene = _scene("a coin is flicked at 0.5 m/s at 30 degrees, what is the range")

    peak = max(y for _, y in scene.bodies[0].path)
    assert scene.y_max < 1.0
    assert peak > 0.3 * scene.y_max


def test_a_projectile_rests_on_the_ground_rather_than_in_it() -> None:
    scene = _scene(PROJECTILE_Q)
    body = scene.bodies[0]

    assert body.path[0][1] == pytest.approx(body.radius)
    assert body.path[-1][1] == pytest.approx(body.radius, abs=1e-6)


def test_a_pendulum_is_never_drawn_as_a_spring() -> None:
    """Even handed an amplitude, which is what the spring scene is drawn from."""
    intent = extract_physics_intent("what is the period of a pendulum of length 2 m")
    assert isinstance(intent, PhysicsIntent)
    swinging = intent.model_copy(
        update={
            "physics_params": {**(intent.physics_params or {}), "x": 0.1},
            "physics_units": {**(intent.physics_units or {}), "x": "m"},
        }
    )

    (scene,) = solve_physics(swinging).simulation_specs
    assert scene.type == "pendulum"
