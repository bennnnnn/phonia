"""A failed evaluation must not certify only the assignment that precedes it."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.function_def import has_assignment_evaluation_request
from app.modules.math.tools.prompt import build_math_augmentation


@pytest.mark.parametrize(
    "query",
    [
        "Let x=-5. Evaluate$x^$$x^2$",
        "Given y=3; compute(y+",
        "Set t=4. Calculate$frad(t)$",
        "Let x=5. What is frad(x)?",
        "Let x=5. Evaluate",
        "x=5. What's the value of frad(x)?",
        "Let x=2; y=3. Evaluate$broken(x,y)$",
    ],
)
@pytest.mark.asyncio
async def test_failed_evaluation_cannot_fall_back_to_binding_answer(query: str) -> None:
    assert has_assignment_evaluation_request(query)
    intent = extract_math_intent(query)
    assert intent is None
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None
    assert maybe_direct_math_reply(verified, query) is None


@pytest.mark.parametrize(
    "query,answer",
    [
        ("Let x=-5. Evaluate x^2", "25"),
        ("Let x=-5. Evaluate 2*x^2", "50"),
        ("Let x=5. Evaluate 2x", "10"),
        ("Let x=5. What is x+2?", "7"),
        ("Let x=-5. Evaluate $x^2$", "25"),
        ("Given y=3. Compute y+2", "5"),
    ],
)
def test_valid_substitution_still_returns_requested_value(query: str, answer: str) -> None:
    assert has_assignment_evaluation_request(query)
    intent = extract_math_intent(query)
    assert intent is not None and intent.kind == "arithmetic"
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.canonical_answer == answer


@pytest.mark.parametrize("query", ["Evaluate x+1=3", "Solve x+y=5; x-y=1", "Solve 2x=10"])
def test_equations_without_a_later_evaluation_are_preserved(query: str) -> None:
    assert not has_assignment_evaluation_request(query)
    intent = extract_math_intent(query)
    assert intent is not None and intent.kind in {"equation", "system"}


@pytest.mark.parametrize("query", ["Let x=-5", "Solve x=5"])
def test_a_value_already_stated_is_not_solved_again(query: str) -> None:
    # "x = 5" solved is "x = 5": a verified card for it certifies whatever was typed.
    assert not has_assignment_evaluation_request(query)
    assert extract_math_intent(query) is None


@pytest.mark.asyncio
async def test_a_parser_miss_is_answered_not_sent_back() -> None:
    # 2026-10-31: a clear Grade 11 question got "Could you rewrite it?".
    query = "Express z = 1 - i√3 in polar form and evaluate z^10."
    note, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None and note is not None
    assert "Answer the whole question yourself" in note
    assert "do not claim a verified result" in note
    assert "Ask the user to rewrite" not in note


def test_assignment_detector_is_bounded() -> None:
    assert not has_assignment_evaluation_request("x=5. " + " " * 1000 + "Evaluate x^2")
