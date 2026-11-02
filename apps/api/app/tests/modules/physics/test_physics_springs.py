"""P7: springs, Hooke's law and simple harmonic motion.

Two hazards shaped this one.

"spring" is a season and a semester, so it is never a cue on its own — it only
counts beside a spring constant. And `k = 200` reads as an equation: before this
extractor existed, `what is the period of simple harmonic motion for a 0.5 kg
mass and k = 200 N/m` was answered as algebra, with `N = km/200`. The constant
is stripped before the equation check for exactly that reason.

The SHM period also emits a `position_vs_time` trajectory, which is what P3's
player animates — an oscillation is the one verified result where the motion is
the whole point.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {
    "kinematics",
    "projectile",
    "force",
    "energy",
    "momentum",
    "friction",
    "circular",
    "spring",
}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# k = 200 N/m, x = 0.1 m, m = 0.5 kg throughout:
# F = 20, U = 1, T = 2*pi*sqrt(0.5/200) = 0.314.
VERIFIED: list[tuple[str, str, str]] = [
    ("force of a spring with k = 200 N/m stretched 0.1 m", "spring_force", "20 N"),
    (
        "what is the spring force when the spring constant is 200 N/m and it is stretched 0.1 m",
        "spring_force",
        "20 N",
    ),
    (
        "find the restoring force for a 200 N/m spring compressed 0.1 m",
        "spring_force",
        "20 N",
    ),
    ("energy stored in a spring with k = 200 N/m stretched 0.1 m", "spring_energy", "1 J"),
    (
        "what is the elastic potential energy of a 200 N/m spring stretched 0.1 m",
        "spring_energy",
        "1 J",
    ),
    (
        "find the energy stored when a spring constant 200 N/m is compressed 0.1 m",
        "spring_energy",
        "1 J",
    ),
    ("period of a 0.5 kg mass on a spring with k = 200 N/m", "shm_period", "0.314 s"),
    (
        "what is the period of simple harmonic motion for a 0.5 kg mass and k = 200 N/m",
        "shm_period",
        "0.314 s",
    ),
    (
        "find the oscillation period of a 0.5 kg mass on a 200 N/m spring",
        "shm_period",
        "0.314 s",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_spring_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "spring"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_spring_op_has_at_least_three_phrasings() -> None:
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert {op: n for op, n in covered.items() if n < 3} == {}
    assert set(covered) == {"spring_force", "spring_energy", "shm_period"}


# --- the SHM trajectory, which P3 animates ---------------------------------


def test_an_shm_period_emits_an_animatable_trajectory() -> None:
    """The ticket's second acceptance clause.

    An oscillation is the one verified result where the motion *is* the answer,
    so it hands P3's player a curve rather than a bare number.
    """
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent(
        "period of a 0.5 kg mass on a spring with k = 200 N/m and amplitude 0.1 m"
    )
    assert isinstance(intent, PhysicsIntent)

    result = solve_physics(intent)
    assert result.answer_value == "0.314 s"
    assert len(result.graph_specs) == 1
    spec = result.graph_specs[0]
    assert spec.trajectory_type == "position_vs_time"
    assert spec.y_label == "Displacement (m)"

    ys = [point[1] for point in spec.points]
    # Starts at full displacement and swings symmetrically about zero.
    assert spec.points[0][1] == pytest.approx(0.1, abs=1e-3)
    assert max(ys) == pytest.approx(0.1, abs=1e-3)
    assert min(ys) == pytest.approx(-0.1, abs=1e-3)

    # The scene walks that same displacement. Its x is the graph's y.
    assert len(result.simulation_specs) == 1
    scene = result.simulation_specs[0]
    assert scene.type == "spring"
    assert scene.anchor is not None
    assert [point[0] for point in scene.bodies[0].path] == ys


def test_an_unstated_amplitude_is_normalised_not_invented() -> None:
    """Amplitude only scales the y-axis; the period is what was asked.

    So a question that omits it still gets a curve, with the axis saying plainly
    that the scale is normalised rather than quietly implying metres.
    """
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent("period of a 0.5 kg mass on a spring with k = 200 N/m")
    assert isinstance(intent, PhysicsIntent)

    result = solve_physics(intent)
    spec = result.graph_specs[0]
    assert spec.y_label == "Displacement (normalised)"
    assert max(point[1] for point in spec.points) == pytest.approx(1.0, abs=1e-3)
    # The spring is drawn at a display size, and no number is written on the
    # swing: neither the labels nor the description name an amplitude.
    (scene,) = result.simulation_specs
    assert scene.type == "spring"
    assert all(vector.label is None for vector in scene.vectors)
    assert scene.alt is not None and " m either side" not in scene.alt


# --- the physics ------------------------------------------------------------


def test_a_stiffer_spring_oscillates_faster() -> None:
    """T = 2*pi*sqrt(m/k) — the relationship, not a memorised number."""
    soft = _verified_answer("period of a 0.5 kg mass on a spring with k = 50 N/m")
    stiff = _verified_answer("period of a 0.5 kg mass on a spring with k = 800 N/m")

    assert soft is not None and stiff is not None
    assert float(soft.split()[0]) > float(stiff.split()[0])


def test_energy_is_half_the_force_times_the_displacement() -> None:
    """U = 1/2 k x^2 and F = k x come from one law; they must agree."""
    force = _verified_answer("force of a spring with k = 200 N/m stretched 0.1 m")
    energy = _verified_answer("energy stored in a spring with k = 200 N/m stretched 0.1 m")

    assert force is not None and energy is not None
    assert float(energy.split()[0]) == pytest.approx(0.5 * float(force.split()[0]) * 0.1, abs=0.01)


def test_compression_and_extension_give_the_same_force() -> None:
    """F = k|x| — the magnitude does not depend on which way the spring moved."""
    assert _verified_answer(
        "find the restoring force for a 200 N/m spring compressed 0.1 m"
    ) == _verified_answer("force of a spring with k = 200 N/m stretched 0.1 m")


# --- refusals and the vocabulary hazard -------------------------------------


UNDERSPECIFIED = [
    "force of a spring with k = 200 N/m",
    "energy stored in a spring stretched 0.1 m",
    "period of a mass on a spring with k = 200 N/m",
]


@pytest.mark.parametrize("text", UNDERSPECIFIED)
def test_springs_missing_a_given_are_refused(text: str) -> None:
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    "spring break starts in 3 weeks",
    "the spring semester has 14 weeks",
    "find the factors of 24",
    "what is the period of the function sin(2x)",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_spring_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_a_season_does_not_engage_the_math_path() -> None:
    """ "spring" only counts beside a spring constant.

    These cues feed the global pre-filter, so a bare mention would spend a tool
    round on a question nothing here can answer.
    """
    from app.tests.modules.physics.support import needs_physics

    assert not needs_physics("spring break starts in 3 weeks")
    assert needs_physics("force of a spring with k = 200 N/m stretched 0.1 m")


@pytest.mark.parametrize(
    "text,answer",
    [
        ("kinetic energy of a 2 kg object moving at 3 m/s", "9 J"),
        ("potential energy of a 2 kg mass at 5 m", "98.1 J"),
    ],
)
def test_ordinary_energy_questions_are_untouched(text: str, answer: str) -> None:
    """Spring runs before the energy extractor, so it must not swallow these.

    "elastic potential energy" *should* reach spring; plain potential energy
    must not.
    """
    intent = extract_physics_intent(text)

    assert intent is not None and intent.kind == "energy"
    assert _verified_answer(text) == answer


# --- P15: the pendulum ------------------------------------------------------
#
# One line of physics away from code that already shipped: T = 2π√(L/g) is
# structurally the same as this file's T = 2π√(m/k), and it emits the same
# displacement curve, so P3's player animates it for free. It lives on the
# `spring` kind for that reason — the same simple harmonic motion with a
# different period formula, not a new subject.
#
# `routing.py` already listed `pendulum` as a topic worth escalating to the
# smarter model, and P10 named it as explicitly unverified. The gap was
# acknowledged in two places and unfilled in both.

PENDULUM: list[tuple[str, str]] = [
    ("period of a 2 m pendulum", "2.84 s"),
    ("what is the time period of a simple pendulum of 2 m", "2.84 s"),
    ("how long does a 2 m pendulum take to swing back and forth", "2.84 s"),
    ("what is the period of a pendulum 2 m long", "2.84 s"),
    ("find the period of a 50 cm pendulum", "1.42 s"),
]


@pytest.mark.parametrize("text,answer", PENDULUM, ids=[t[:44] for t, _ in PENDULUM])
def test_pendulum_phrasings_reach_a_verified_answer(text: str, answer: str) -> None:
    intent = extract_physics_intent(text)

    assert intent is not None and intent.kind == "spring"
    assert intent.physics_op == "pendulum_period"
    assert _verified_answer(text) == answer


def test_the_period_does_not_depend_on_mass() -> None:
    """The fact that makes a pendulum worth asking about.

    A heavier bob does not swing slower. Nothing in the extractor reads a mass
    for this op, so stating one must change nothing — and if a later change
    starts binding mass here, this is what catches it.
    """
    without = _verified_answer("period of a 2 m pendulum")
    with_mass = _verified_answer("period of a 2 m pendulum with a 5 kg bob")

    assert without == with_mass == "2.84 s"


def test_quadrupling_the_length_doubles_the_period() -> None:
    """T ∝ √L, checked as a relationship rather than two pinned numbers.

    The tolerance is set by the answer strings, not by the physics: these are
    rounded to 2 dp before this test sees them, so doubling 2.01 gives 4.02
    where the exact ratio gives 4.01. Anything tighter tests the formatter.
    """
    short = _verified_answer("period of a 1 m pendulum")
    long = _verified_answer("period of a 4 m pendulum")

    assert short is not None and long is not None
    assert float(long.split()[0]) == pytest.approx(2 * float(short.split()[0]), abs=0.02)


def test_a_pendulum_on_the_moon_swings_slower() -> None:
    """`_detect_gravity` already knew about the Moon; this op just asks it.

    Weaker gravity means a longer period, which is the kind of claim a verified
    answer should be able to make.
    """
    earth = _verified_answer("period of a 2 m pendulum")
    moon = _verified_answer("a pendulum on the moon is 2 m long, what is its period")

    assert earth is not None and moon is not None
    assert float(moon.split()[0]) > float(earth.split()[0])


def test_the_pendulum_is_drawn_as_a_bob_on_its_string() -> None:
    """The bob swings on a tether of the stated length and comes back."""
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent("period of a 2 m pendulum")
    assert isinstance(intent, PhysicsIntent)

    result = solve_physics(intent)
    assert result.graph_specs == []
    (scene,) = result.simulation_specs
    assert scene.type == "pendulum"
    assert [tether.anchor for tether in scene.tethers] == [[0.0, 0.0]]
    path = scene.bodies[0].path
    assert path[0] == pytest.approx(path[-1])
    assert all(x * x + y * y == pytest.approx(4.0) for x, y in path)


def test_the_spring_period_is_untouched() -> None:
    """A pendulum has a length where a spring has a constant, so the two cannot
    collide — but the pendulum extractor runs first, so this says so."""
    intent = extract_physics_intent("the period of a 200 N/m spring with a 2 kg mass")

    assert isinstance(intent, PhysicsIntent) and intent.physics_op == "shm_period"
    assert _verified_answer("the period of a 200 N/m spring with a 2 kg mass") == "0.628 s"


@pytest.mark.parametrize(
    "text",
    [
        "the pendulum has swung back to the centre",
        "what is a pendulum",
        "public opinion is a pendulum",
        "the pendulum of fashion swings every 20 years",
    ],
)
def test_pendulum_needs_a_length_beside_it(text: str) -> None:
    """The idiom is real, and this cue feeds the global pre-filter.

    So "pendulum" counts only next to an actual length — the co-occurrence
    shape P5 used for friction and P7 for springs.
    """
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_a_pendulum_length_alone_is_not_a_question() -> None:
    """Describing one is not asking for its period."""
    assert _verified_answer("a pendulum is 2 m long") is None
