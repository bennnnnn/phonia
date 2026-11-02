"""Unknown notation needs clarification even when math intent does not match."""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants.math import MATH_FENCE_SAFETY_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.math.match import needs_symbolic
from app.services.math_notation import MATH_NOTATION_CLARIFICATION_HINT


@pytest.mark.parametrize("compact", [False, True])
def test_unknown_notation_gets_clarification_without_math_intent(compact: bool) -> None:
    query = "What is frad{64}?"
    assert not needs_symbolic(query)
    hints = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
    )
    assert MATH_FENCE_SAFETY_HINT in hints
    assert "\n".join(hints).count(MATH_NOTATION_CLARIFICATION_HINT) == 1


@pytest.mark.parametrize("compact", [False, True])
def test_recognized_math_turn_keeps_clarification_guard_and_standard_aliases(
    compact: bool,
) -> None:
    hints = _style_format_hints(
        query_text="Solve x + 1 = 3",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
    )
    joined = "\n".join(hints)
    assert joined.count(MATH_NOTATION_CLARIFICATION_HINT) == 1
    assert MATH_NOTATION_CLARIFICATION_HINT in joined
    assert MATH_NOTATION_CLARIFICATION_HINT in joined
    assert MATH_NOTATION_CLARIFICATION_HINT in joined
