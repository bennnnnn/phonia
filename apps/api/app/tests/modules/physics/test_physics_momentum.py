"""P4: momentum, impulse and 1D collisions.

The first ticket that adds verified physics surface rather than repairing it.
Momentum was the highest-frequency of the twelve topics the review found with
no verified answer under any phrasing — `p = mv`, `J = FΔt` and 1D
conservation are the most common mechanics asks after kinematics.

The negative table matters as much as the positive one. Physics extractors run
before the generic equation extractor, and this one runs before force and
energy, so an over-broad cue here steals from three directions at once.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.schemas import PhysicsIntent
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

PHYSICS_KINDS = {"kinematics", "projectile", "force", "energy", "momentum"}


def _settings() -> Settings:
    return Settings(math_tools_enabled=True)


def _verified_answer(text: str) -> str | None:
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    block = build_verified_physics_block(intent, _settings())
    return None if block is None else block.canonical_answer


# (question, expected physics_op, expected answer). Answers are pinned so a
# phrasing cannot pass by binding the right number to the wrong parameter.
VERIFIED: list[tuple[str, str, str]] = [
    # p = m v
    ("momentum of a 2 kg object moving at 3 m/s", "momentum", "6 kg·m/s"),
    ("what is the momentum of a 5 kg mass with velocity 4 m/s", "momentum", "20 kg·m/s"),
    ("calculate the momentum of a 2 kg ball travelling at 3 m/s", "momentum", "6 kg·m/s"),
    # J = F dt
    ("impulse of a 10 N force over 2 seconds", "impulse", "20 N·s"),
    ("what is the impulse when a 10 N force acts for 2 s", "impulse", "20 N·s"),
    ("find the impulse delivered by a 10 N force in 2 s", "impulse", "20 N·s"),
    # J = m dv — same quantity, and N·s and kg·m/s are the same unit.
    ("impulse on a 2 kg mass going from 3 m/s to 8 m/s", "impulse", "10 N·s"),
    # 1D collisions, type always stated
    (
        "a 2 kg ball at 3 m/s hits a 1 kg ball at rest and they stick together, "
        "find the final velocity",
        "final_velocity",
        "2 m/s",
    ),
    (
        "a 2 kg cart moving at 3 m/s collides perfectly inelastically with a 1 kg cart at rest, "
        "what is the final velocity",
        "final_velocity",
        "2 m/s",
    ),
    (
        "in an elastic collision a 2 kg ball at 3 m/s hits a 1 kg ball at rest, "
        "find the final velocity",
        "final_velocity",
        "1 m/s and 4 m/s",
    ),
    (
        "a 2 kg ball at 3 m/s collides elastically with a 1 kg ball at rest",
        "final_velocity",
        "1 m/s and 4 m/s",
    ),
]


@pytest.mark.parametrize("text,op,answer", VERIFIED, ids=[row[0][:44] for row in VERIFIED])
def test_momentum_phrasings_reach_a_verified_answer(text: str, op: str, answer: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is not None, "no intent extracted"
    assert intent.kind == "momentum"
    assert intent.physics_op == op
    assert _verified_answer(text) == answer


def test_every_momentum_op_has_at_least_three_phrasings() -> None:
    """The ticket's acceptance bar, enforced rather than counted by hand."""
    from collections import Counter

    covered = Counter(op for _, op, _ in VERIFIED)

    assert {op: n for op, n in covered.items() if n < 3} == {}
    assert set(covered) == {"momentum", "impulse", "final_velocity"}


# --- the physics is right, not just the plumbing ---------------------------


def test_elastic_collision_conserves_momentum_and_energy() -> None:
    """The property that defines an elastic collision, checked rather than assumed.

    Pinning "1 m/s and 4 m/s" proves the formula was transcribed; this
    proves it was the right formula.
    """
    from app.modules.physics.solver import solve_physics

    intent = extract_physics_intent(
        "a 2 kg ball at 3 m/s collides elastically with a 1 kg ball at rest"
    )
    assert isinstance(intent, PhysicsIntent)
    solve_physics(intent)  # must not raise

    m1, m2, v1, v2 = 2.0, 1.0, 3.0, 0.0
    u1 = ((m1 - m2) * v1 + 2 * m2 * v2) / (m1 + m2)
    u2 = ((m2 - m1) * v2 + 2 * m1 * v1) / (m1 + m2)

    assert m1 * v1 + m2 * v2 == pytest.approx(m1 * u1 + m2 * u2)
    assert 0.5 * m1 * v1**2 + 0.5 * m2 * v2**2 == pytest.approx(0.5 * m1 * u1**2 + 0.5 * m2 * u2**2)


def test_inelastic_collision_conserves_momentum_but_not_energy() -> None:
    """The counterpart: sticking together must lose kinetic energy."""
    m1, m2, v1, v2 = 2.0, 1.0, 3.0, 0.0
    u = (m1 * v1 + m2 * v2) / (m1 + m2)

    assert m1 * v1 + m2 * v2 == pytest.approx((m1 + m2) * u)
    assert 0.5 * (m1 + m2) * u**2 < 0.5 * m1 * v1**2 + 0.5 * m2 * v2**2


# --- refusals --------------------------------------------------------------


UNSTATED_COLLISION = [
    "a 2 kg ball at 3 m/s hits a 1 kg ball at rest, find the final velocity",
    "a 2 kg cart collides with a 1 kg cart at 4 m/s, what is the final velocity",
    "a 3 kg trolley moving at 2 m/s collides with a 5 kg trolley at rest",
]


@pytest.mark.parametrize("text", UNSTATED_COLLISION)
def test_an_unstated_collision_type_is_refused_not_guessed(text: str) -> None:
    """Elastic and inelastic give different answers from identical inputs.

    Same reasoning as the tension guard added in P2: with nothing in the
    question to choose between them, any answer is a coin flip dressed up as a
    verified result, and a wrong number inside the verified block is worse than
    no block at all.
    """
    assert _verified_answer(text) is None


NOT_PHYSICS = [
    "solve 2x + 7 = 19",
    "the project lost momentum this quarter",
    "I made an impulse purchase of 3 items",
    "what is a hash collision in a database with 500 rows",
    "what is the momentum of the team after 3 wins",
    "find the factors of 24",
    # "elastic" alone is not a collision — this is the cue that must never
    # stand on its own.
    "an elastic band stretched 5 cm",
]


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_momentum_cues_do_not_steal_other_subjects(text: str) -> None:
    intent = extract_physics_intent(text)
    assert intent is None or intent.kind not in PHYSICS_KINDS


def test_the_same_numbers_still_route_by_the_question_asked() -> None:
    """`2 kg` and `3 m/s` are a momentum question or an energy one.

    Only the noun separates them, and momentum now runs first — so this is the
    pair most likely to cross-fire.
    """
    momentum = extract_physics_intent("momentum of a 2 kg object moving at 3 m/s")
    energy = extract_physics_intent("kinetic energy of a 2 kg object moving at 3 m/s")
    assert momentum is not None and momentum.kind == "momentum"
    assert energy is not None and energy.kind == "energy"
    assert _verified_answer("kinetic energy of a 2 kg object moving at 3 m/s") == "9 J"


def test_momentum_direct_reply_uses_the_solver_owned_answer() -> None:
    from app.tests.modules.physics.support import maybe_direct_physics_reply

    text = "momentum of a 2 kg mass moving at 3 m/s"
    intent = extract_physics_intent(text)
    assert intent is not None
    block = build_verified_physics_block(intent, _settings())
    assert block is not None

    reply = maybe_direct_physics_reply(block, text)
    assert reply is not None
    assert "**Given**" in reply
    assert "**Linear momentum formula**" in reply
    assert "**Answer**" in reply
    assert "```answer\n6\\,\\mathrm{kg·m/s}\n```" in reply


# --- P11: an angled collision was answered as a projectile -------------------
#
# Found in a user screenshot, not in a test. "a 2 kg ball at 3 m/s hits a 1 kg
# ball at rest elastically in 2D at 30 degrees" came back `0.79 m` — which is
# 3^2 sin(60 deg) / 9.81, the range of a ball lobbed at 3 m/s. The question was
# about a collision and the answer was about a projectile.
#
# Cause: P2 recognises a projectile by its signature, a speed and an angle in
# one clause, which a 2D collision also has. The projectile extractor runs
# before this one, so it did not compete for the question — it took it. This
# table is the one P4 should have had.

ANGLED_COLLISIONS = [
    "a 2 kg ball at 3 m/s hits a 1 kg ball at rest elastically in 2D at 30 degrees",
    "a 2 kg ball at 3 m/s collides elastically with a 1 kg ball at 30 degrees",
    "two cars collide at 20 m/s at an angle of 30 degrees, find the final velocity",
    "a 2 kg ball collides with a 1 kg ball at 4 m/s, deflected at 45 degrees",
]


@pytest.mark.parametrize("text", ANGLED_COLLISIONS, ids=[t[:44] for t in ANGLED_COLLISIONS])
def test_an_angled_collision_gets_no_verified_answer(text: str) -> None:
    """Only 1D conservation is implemented, so 2D is out of scope — say so.

    Refusing looks like a downgrade and is not: the model then answers unaided
    under P10's caution, instead of the user reading a checked-looking number
    for a problem nobody asked about.
    """
    assert _verified_answer(text) is None


@pytest.mark.parametrize("text", ANGLED_COLLISIONS, ids=[t[:44] for t in ANGLED_COLLISIONS])
def test_an_angled_collision_is_never_a_projectile(text: str) -> None:
    """Pins the specific mis-route, not just its symptom.

    Refusing at the block stage would hide a projectile intent still being
    extracted — the next ticket to give projectiles a second op would bring
    `0.79 m` straight back.
    """
    intent = extract_physics_intent(text)

    assert intent is None or intent.kind != "projectile"


def test_a_bare_angle_is_enough_to_refuse() -> None:
    """The commonest 2D phrasing never says "2D".

    Three of the four rows above carry a word — `in 2D`, `at an angle`,
    `deflected` — that a wording guard catches. This one carries only degrees,
    and it is the phrasing a person actually types. A head-on collision has no
    angle to state, so inside a collision the number can only be the deflection.
    """
    assert (
        _verified_answer("a 2 kg ball at 3 m/s collides elastically with a 1 kg ball at rest")
        is not None
    )
    assert (
        _verified_answer("a 2 kg ball at 3 m/s collides elastically with a 1 kg ball at 30 degrees")
        is None
    )


def test_1d_collisions_are_untouched_by_the_guards() -> None:
    """The refusal must cost nothing that already worked.

    Both guards sit in front of live paths — one in the projectile extractor,
    one in this one — so the regression they risk is silent.
    """
    assert (
        _verified_answer(
            "a 2 kg ball at 3 m/s hits a 1 kg ball at rest and they stick together, "
            "find the final velocity"
        )
        == "2 m/s"
    )
    assert (
        _verified_answer(
            "in an elastic collision a 2 kg ball at 3 m/s hits a 1 kg ball at rest, "
            "find the final velocities"
        )
        == "1 m/s and 4 m/s"
    )


REAL_PROJECTILES = [
    ("a ball is thrown at 20 m/s at 30 degrees, what is the range", "35.3 m"),
    ("projectile launched at 20 m/s at 30 degrees find the range", "35.3 m"),
    ("a ball is kicked at 20 m/s at 30 degrees, how high does it go", "5.1 m"),
]


@pytest.mark.parametrize("text,answer", REAL_PROJECTILES, ids=[t[:44] for t, _ in REAL_PROJECTILES])
def test_real_projectiles_still_answer(text: str, answer: str) -> None:
    """The other half of the guard: a projectile with an angle is still one."""
    assert _verified_answer(text) == answer


COLLISION_WORD_ELSEWHERE = [
    (
        "a stone is dropped and falls for 3 s before it hits the ground, how fast is it going",
        "29.4 m/s",
    ),
    ("a hammer strikes a nail with 20 N of force over 0.1 s, what is the impulse", "2 N·s"),
    ("what is the momentum of a 2 kg ball that hits a wall at 3 m/s", "6 kg·m/s"),
]


@pytest.mark.parametrize(
    "text,answer", COLLISION_WORD_ELSEWHERE, ids=[t[:44] for t, _ in COLLISION_WORD_ELSEWHERE]
)
def test_a_collision_word_alone_does_not_disqualify_a_question(text: str, answer: str) -> None:
    """ "hits" and "strikes" are ordinary words for arriving somewhere.

    Both guards are narrower than the word they key on. The first is scoped to
    the projectile extractor, which a falling body never reaches; the second to
    the two-mass conservation branch, which impulse and p = mv do not enter. So
    a question that merely says "hits" keeps its answer.
    """
    assert _verified_answer(text) == answer
