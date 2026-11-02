"""A physics turn must not be labeled or wrapped as math."""

from app.core.config import Settings
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_REPLY_POLICY, MATH_TUTORING_HINT
from app.modules.physics.reply_policy import PHYSICS_INTENT_HINT, PHYSICS_REPLY_POLICY
from app.services.solving import VERIFIED_MATH_BEGIN, strip_verified_solve_markers
from app.services.subjects.dispatch import detect_subject
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent

_DROP = "A ball is dropped from a height of 20 m. Find the time to ground. Use g=10."
_ALGEBRA = "Solve 2x + 3 = 7"


def test_physics_turn_is_not_labeled_as_math() -> None:
    assert detect_subject(_DROP) == "physics"
    assert detect_subject(_ALGEBRA) != "physics"


def test_physics_prompt_uses_physics_hints() -> None:
    hints = _style_format_hints(
        query_text=_DROP,
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert PHYSICS_INTENT_HINT in hints
    assert PHYSICS_REPLY_POLICY in hints
    assert MATH_INTENT_HINT not in hints
    assert MATH_TUTORING_HINT not in hints
    assert MATH_REPLY_POLICY not in hints
    joined = "\n".join(hints)
    assert "Math / algebra" not in joined
    assert MATH_TUTORING_HINT not in joined
    assert "[BEGIN VERIFIED PHYSICS]" in joined


def test_verified_physics_block_is_not_wrapped_as_math() -> None:
    intent = extract_physics_intent(_DROP)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    assert block.text.startswith("[BEGIN VERIFIED PHYSICS]")
    assert VERIFIED_MATH_BEGIN not in block.text
    stripped = strip_verified_solve_markers(block.text)
    assert "2\\,\\mathrm{s}" in stripped
    assert "[BEGIN VERIFIED PHYSICS]" not in stripped
    assert "Verified formula:" in stripped
    assert "Verified substitution:" in stripped
    assert "Verified result: $2\\,\\mathrm{s}$" in stripped
    assert "Verified answer:" not in stripped
