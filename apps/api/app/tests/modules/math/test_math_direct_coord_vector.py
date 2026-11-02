"""Closed coordinate/vector replies must consume every literal operand."""

import pytest

from app.core.config import Settings
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.workout import as_formula_heading


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer",
    [
        ("Find the distance between (0,0) and (3,4)", "5"),
        ("Find the midpoint of (0,0) and (4,6)", "(2, 3)"),
        ("Find the slope of the line through (0,0) and (2,4)", "2"),
        ("Find the magnitude of <3,4>", "5"),
        ("Find the dot product of <1,2> and <3,4>", "11"),
        ("Find the cross product of <1,0,0> and <0,1,0>", "(0, 0, 1)"),
        ("Find the cross product of <1,2> and <3,4>", "(0, 0, -2)"),
        ("Please find the distance between (-3,0) and (0,4).", "5"),
        ("Calculate the magnitude of <0,0,0>", "0"),
    ],
)
async def test_closed_coordinate_vector_asks_return_one_verified_answer(query, answer):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_answer == answer
    reply = maybe_direct_math_reply(verified, query)
    assert reply is not None
    # One answer, last; distance, slope and midpoint also show their formula.
    assert reply.endswith(f"```answer\n{answer}\n```\n")
    assert reply.count("```answer") == 1
    if any(word in query for word in ("distance", "slope", "midpoint")):
        assert "**Formula**" in as_formula_heading(reply) and "**Substitution**" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Find the midpoint of (0,0) and (4,6) and (8,10)",
        "Find the distance between (0,0) and (3,4) and (6,8)",
        "Find the magnitude of <3,4> and <6,8>",
        "Find the distance between (0,0) and (3,4) on a sphere",
        "Find the geodesic distance between (0,0) and (3,4)",
        "Find the magnitude of <3,,4>",
        "Find the magnitude of <3,4,>",
        "Find the magnitude of <3,4",
        "Find the magnitude of <3,nan>",
        "Find the magnitude of <3,inf>",
        "Find the magnitude of <1,2,3,4>",
        "Find the midpoint of (0,0) and (4,,6)",
        "Find the midpoint of (0,0) and (4,6",
        "Find the dot product of <1,2> and <3,4> and <5,6>",
        "Find the dot product of <1,2> and <3,4,5>",
    ],
)
async def test_extra_malformed_nonfinite_or_wrong_dimension_operands_are_not_certified(query):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Find the distance between (0,0) and (3,4) and explain the formula",
        "Find the midpoint of (0,0) and (4,6), hint only",
        "Find the slope of the line through (0,0) and (2,4) with steps",
        "Find the magnitude of <3,4> and 2+2",
        "Find the dot product of <1,2> and <3,4> and explain orthogonality",
        "Find the cross product of <1,0,0> and <0,1,0> with proof",
    ],
)
async def test_complete_operands_with_teaching_or_extra_clauses_keep_the_model_path(query):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None
    reply = maybe_direct_math_reply(verified, query)
    if "hint only" in query:
        # Hint scope is enforced before the model sees the solver block, so a
        # deterministic next-move hint is safer than allowing an answer leak.
        assert reply is not None
        assert "Hint:" in reply
        assert "(2, 3)" not in reply
    else:
        assert reply is None
