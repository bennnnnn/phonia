"""A question line no longer drops the verified physics card or its scene.

``validate_physics_fences`` used to look for the exact display string and, when
it was missing and any line ended with "?", returned the prose alone: "Want the
max height too?" cost the reply its card and simulation, and a wrong range in
the prose stood unchallenged.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.modules.physics.fence import validate_physics_fences
from app.modules.physics.reply_policy import PHYSICS_SHORT_HINT
from app.services.answer_fence import VERIFIED_ANSWER_MARKER
from app.services.solving import VerifiedPhysicsBlock

_RANGE = "A ball is thrown at 20 m/s at 30 degrees. Find the range. Ignore air resistance."


@pytest.fixture(scope="module")
def projectile() -> VerifiedPhysicsBlock:
    intent = extract_physics_intent(_RANGE)
    assert intent is not None
    verified = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.display_answer == "35.3\\,\\mathrm{m}"
    return verified


def _card(verified: VerifiedPhysicsBlock) -> str:
    return f"```answer\n{VERIFIED_ANSWER_MARKER}\n{verified.display_answer}\n```"


def test_a_follow_up_offer_keeps_the_card_and_the_scene(
    projectile: VerifiedPhysicsBlock,
) -> None:
    prose = (
        "$R = \\frac{20^2 \\sin 60^\\circ}{9.81}$  \n$R = 35.3\\ \\text{m}$\n\n"
        "Want me to find the maximum height too?"
    )
    out = validate_physics_fences(prose, verified=projectile)
    assert _card(projectile) in out
    assert "```simulation" in out
    assert "Want me to find the maximum height too?" in out
    assert "The verified answer is" not in out


def test_a_wrong_value_before_a_question_is_corrected(projectile: VerifiedPhysicsBlock) -> None:
    prose = (
        "$R = \\frac{20^2 \\sin 30^\\circ}{9.81} = 20.4\\ \\text{m}$\n\n"
        "Want me to find the maximum height too?"
    )
    out = validate_physics_fences(prose, verified=projectile)
    correction = "The verified answer is $35.3\\,\\mathrm{m}$."
    assert correction in out
    assert out.index(correction) < out.index(_card(projectile))
    assert "```simulation" in out


def test_a_wrong_answer_line_is_corrected_above_the_card(projectile: VerifiedPhysicsBlock) -> None:
    prose = (
        "**Given**  \n$v_0 = 20\\ \\text{m/s}$\n\n**Formula**  \n"
        "$R = \\frac{v_0^2 \\sin 2\\theta}{g}$\n\n**Answer**  \n$R = 20.4\\ \\text{m}$"
    )
    out = validate_physics_fences(prose, verified=projectile)
    # The verified card takes the wrong line's place under the heading.
    assert "$R = 20.4\\ \\text{m}$" not in out
    assert (
        "The verified answer is $35.3\\,\\mathrm{m}$.\n\n**Answer**\n\n" + _card(projectile)
    ) in out


def test_a_restated_answer_line_gives_way_to_the_card(projectile: VerifiedPhysicsBlock) -> None:
    prose = "**Formula**  \n$R = \\frac{v_0^2 \\sin 2\\theta}{g}$\n\n**Answer**  \n$R = 35.3\\ \\text{m}$"
    out = validate_physics_fences(prose, verified=projectile)
    assert "$R = 35.3\\ \\text{m}$" not in out
    assert "**Answer**\n\n" + _card(projectile) in out
    assert "The verified answer is" not in out


def test_steps_under_the_answer_heading_move_above_the_card(
    projectile: VerifiedPhysicsBlock,
) -> None:
    """The card used to follow the model's Answer lines, so its box held the working."""
    prose = (
        "**Formula**  \n$R = \\frac{v_0^2 \\sin 2\\theta}{g}$\n\n**Answer**  \n"
        "$R = \\frac{20^2 \\sin 60^\\circ}{9.81}$  \n$R = \\frac{346.4}{9.81}$  \n"
        "$R \\approx 35.3\\ \\text{m}$\n\nThe ball lands about 35 m away."
    )
    out = validate_physics_fences(prose, verified=projectile)
    heading = out.index("**Answer**\n\n" + _card(projectile))
    assert out.index("$R = \\frac{20^2 \\sin 60^\\circ}{9.81}$") < heading
    assert out.index("$R = \\frac{346.4}{9.81}$") < heading
    assert "$R \\approx 35.3\\ \\text{m}$" not in out
    assert out.count("**Answer**") == 1
    assert out.index("The ball lands about 35 m away.") > heading
    assert "```simulation" in out


def test_a_clarifying_question_with_no_result_still_gets_no_card(
    projectile: VerifiedPhysicsBlock,
) -> None:
    prose = "Is the ball launched from the ground or from a cliff?"
    out = validate_physics_fences(prose, verified=projectile)
    assert "```answer" not in out
    assert PHYSICS_SHORT_HINT not in out


def test_the_card_carries_the_server_marker(projectile: VerifiedPhysicsBlock) -> None:
    out = validate_physics_fences(
        "The range follows from the projectile formula.", verified=projectile
    )
    assert out.count(_card(projectile)) == 1


def test_finalizing_twice_changes_nothing(projectile: VerifiedPhysicsBlock) -> None:
    once = validate_physics_fences("The range is $35.3\\ \\text{m}$.", verified=projectile)
    assert validate_physics_fences(once, verified=projectile) == once
