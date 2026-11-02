"""The model's instructions agree with each other and with what the server does.

Two pairs used to contradict:

- Maths: ``MATH_SOLVER_HINT`` said "be cautious and say when you are unsure" while
  the unverified note said "Never tell the user that a result is unverified, not
  verified, or could not be verified", and the server deletes "I couldn't verify
  this" from every reply. The check mark is the signal now, so no instruction
  asks for a verification disclaimer; uncertainty is stated as the assumption.
- Physics: ``PHYSICS_REPLY_POLICY`` said "do not repeat the result" and also "The
  Answer line must state the result", while the server appends the card anyway.
  Now: state the result once, on the Answer line; the server swaps a line that
  only restates the verified value for the card.
"""

from __future__ import annotations

from app.modules.math.fence import append_unverified_math_note
from app.modules.math.reply_policy import MATH_SOLVER_HINT
from app.modules.math.tools.prompt import _unverified_math_note
from app.modules.physics.prompt import _unverified_physics_note
from app.modules.physics.reply_policy import PHYSICS_REPLY_POLICY


def test_math_hint_does_not_ask_for_a_disclaimer_the_server_deletes() -> None:
    hint = MATH_SOLVER_HINT.lower()
    assert "say when you are unsure" not in hint
    assert "disclaimer" in hint
    note = _unverified_math_note("equation").lower()
    assert "never tell the user that a result is unverified" in note
    # The server enforces the same rule the prompts state.
    assert append_unverified_math_note("x = 3.\n\n*I couldn't verify this result.*") == "x = 3."


def test_physics_policy_asks_for_the_result_once_on_the_answer_line() -> None:
    policy = PHYSICS_REPLY_POLICY.lower()
    assert "do not repeat the result" not in policy
    assert "state the result once, on the answer line" in policy
    assert "never end on the heading" in policy
    assert "Compute the result and write it under Answer." in _unverified_physics_note()
