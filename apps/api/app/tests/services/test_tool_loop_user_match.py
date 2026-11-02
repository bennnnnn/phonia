"""A sympy tool result is verified only for the problem the user wrote.

The model once typed rhs 19 for "2x + 5 = 17"; the tool solved its typo and the
reply showed a green-checked x = 7. A tool call's equation or expression must
match the user's own text (compared with SymPy) before its result becomes the
turn's verified block, and it never replaces a block the server already built.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.modules.chat import tool_loop
from app.modules.math.tool_check import tool_call_matches_user_text
from app.services.solving import VerifiedMathBlock, VerifiedPhysicsBlock
from app.tests.modules.chat.chat_test_support import turn_deps

from .tool_loop_support import settings


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


@pytest.mark.parametrize(
    ("args", "user", "matches"),
    [
        ({"action": "solve", "lhs": "2*x + 5", "rhs": "17"}, "solve 2x + 5 = 17", True),
        ({"action": "solve", "lhs": "2*x + 5", "rhs": "19"}, "solve 2x + 5 = 17", False),
        ({"action": "solve", "lhs": "2*x - 12", "rhs": "0"}, "solve 2x + 5 = 17", True),
        (
            {"action": "solve", "lhs": "2*x + 5", "rhs": "19"},
            "graph y = 2x + 5 and solve 2x + 5 = 17",
            False,
        ),
        ({"action": "solve", "lhs": "x**2 - 5*x + 6", "rhs": "0"}, "solve x^2 - 5x + 6 = 0", True),
        (
            {"action": "diff", "expr": "x**2", "variable": "x"},
            "I think the derivative of x^3 is 3x",
            False,
        ),
        (
            {"action": "diff", "expr": "x**3", "variable": "x"},
            "I think the derivative of x^3 is 3x",
            True,
        ),
        ({"action": "integrate", "expr": "x**2"}, "integrate x^2 dx", True),
        (
            {"action": "integrate", "expr": "x**2", "lower": "0", "upper": "3"},
            "integrate x^2 from 0 to 2",
            False,
        ),
        (
            {"action": "integrate", "expr": "x**2", "lower": "0", "upper": "2"},
            "integrate x^2 from 0 to 2",
            True,
        ),
        (
            {"action": "limit", "expr": "(x**2-4)/(x-2)", "point": "2"},
            "limit as x approaches 2 of (x^2-4)/(x-2)",
            True,
        ),
        (
            {"action": "limit", "expr": "(x**2-4)/(x-2)", "point": "3"},
            "limit as x approaches 2 of (x^2-4)/(x-2)",
            False,
        ),
        ({"action": "graph", "expr": "2*x + 5"}, "graph y = 2x + 5", True),
        ({"action": "graph", "expr": "x**2"}, "graph y=x^2", True),
        ({"action": "graph", "expr": "x**3"}, "graph y=x^2", False),
        ({"action": "circle", "radius": 3}, "area of a circle with radius 3 cm", True),
        ({"action": "circle", "radius": 4}, "area of a circle with radius 3 cm", False),
        (
            {"action": "system", "equations": [["x + y", "5"], ["x - y", "1"]]},
            "solve x + y = 5, x - y = 1",
            True,
        ),
        (
            {"action": "system", "equations": [["x + y", "6"], ["x - y", "1"]]},
            "solve x + y = 5, x - y = 1",
            False,
        ),
        (
            {"action": "inequality", "lhs": "2*x + 1", "rhs": "7", "comparator": ">"},
            "solve 2x + 1 > 7",
            True,
        ),
        (
            {"action": "inequality", "lhs": "2*x + 1", "rhs": "7", "comparator": "<"},
            "solve 2x + 1 > 7",
            False,
        ),
        ({"action": "simplify", "expr": "x*y"}, "tell me a joke", False),
    ],
)
def test_tool_call_matches_only_the_users_problem(
    args: dict[str, Any], user: str, matches: bool
) -> None:
    assert tool_call_matches_user_text(json.dumps(args), [user]) is matches


def test_a_follow_up_with_no_math_of_its_own_reads_the_previous_question() -> None:
    args = json.dumps({"action": "graph", "expr": "2*x + 5"})
    assert tool_call_matches_user_text(args, ["now graph it", "solve 2x + 5 = 17"])
    assert not tool_call_matches_user_text(args, ["now graph it", "solve 3x + 5 = 17"])


def _sympy_round(args: dict[str, Any]) -> AsyncMock:
    return AsyncMock(
        side_effect=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "s1",
                        "type": "function",
                        "function": {"name": "sympy", "arguments": json.dumps(args)},
                    }
                ],
            }
        ]
    )


def _solve_result(answer: str) -> MagicMock:
    return MagicMock(
        content=f"Verified result: {answer}",
        data={"canonical_fence": {"type": "answer", "content": answer}, "canonical_answer": answer},
    )


async def _run(prompt: str, args: dict[str, Any], answer: str) -> tuple[list[dict[str, Any]], Any]:
    with (
        patch(
            "app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools",
            _sympy_round(args),
        ),
        patch(
            "app.modules.chat.tool_loop.calls.mcp_registry.invoke_validated",
            AsyncMock(return_value=_solve_result(answer)),
        ),
        patch("app.core.sympy_executor.run_sympy", _inline),
    ):
        out, verified, _terminal, _hits = await tool_loop.run_tool_rounds(
            settings=settings(mcp_tool_loop_enabled=True, mcp_tool_loop_max_rounds=1),
            messages=[{"role": "user", "content": prompt}],
            usage={},
        )
    return out, verified


async def test_a_mistyped_tool_call_is_not_the_verified_answer(sympy_registered: None) -> None:
    out, verified = await _run(
        "graph y = 2x + 5 and solve 2x + 5 = 17",
        {"action": "solve", "lhs": "2*x + 5", "rhs": "19", "variables": ["x"]},
        "x = 7",
    )
    assert verified is None
    tool_message = next(m for m in out if m.get("role") == "tool")
    assert "does not match" in tool_message["content"]


async def test_a_faithful_tool_call_is_the_verified_answer(sympy_registered: None) -> None:
    _out, verified = await _run(
        "graph y = 2x + 5 and solve 2x + 5 = 17",
        {"action": "solve", "lhs": "2*x + 5", "rhs": "17", "variables": ["x"]},
        "x = 6",
    )
    assert verified is not None
    assert verified.canonical_answer == "x = 6"


async def _tool_loop_path(ctx_verified: Any, tool_verified: Any) -> Any:
    from app.modules.chat.stream_paths import run_tool_loop_path

    ctx = MagicMock()
    ctx.user_message_content = "solve 2x + 5 = 17 and also graph y = 2x + 5"
    ctx.search_sources = []
    ctx.lightweight_turn = False
    ctx.instant_reply = None
    ctx.verified_subject = ctx_verified
    ctx.prompt_messages = [{"role": "user", "content": ctx.user_message_content}]
    ctx.web_search_classified = None
    deps = turn_deps(quota={"global_spend_exceeded": AsyncMock(return_value=False)})
    with (
        patch("app.modules.chat.tool_loop.turn_needs_tool_loop", return_value=True),
        patch(
            "app.modules.chat.tool_loop.run_tool_rounds",
            AsyncMock(return_value=(ctx.prompt_messages, tool_verified, None, [])),
        ),
    ):
        await run_tool_loop_path(
            deps, AsyncMock(), Settings(), ctx, usage={}, on_status=None, should_cancel=None
        )
    return ctx.verified_subject


async def test_a_tool_result_never_replaces_the_servers_own_block() -> None:
    server = VerifiedMathBlock(
        text="unused",
        canonical_fence={"type": "answer", "content": "x = 6"},
        canonical_answer="x = 6",
    )
    graph = {"type": "function", "expr": "2*x + 5", "points": [[0, 5], [1, 7]]}
    tool = VerifiedMathBlock(
        text="",
        canonical_fence={"type": "answer", "content": "x = 7"},
        canonical_fences=[{"type": "answer", "content": "x = 7"}, graph],
        canonical_answer="x = 7",
    )
    kept = await _tool_loop_path(server, tool)
    assert kept.canonical_answer == "x = 6"
    assert kept.canonical_fence == {"type": "answer", "content": "x = 6"}
    # A diagram the server did not have may join it.
    assert graph in kept.canonical_fences


async def test_a_physics_block_is_kept_whole() -> None:
    physics = VerifiedPhysicsBlock(text="verified", canonical_answer="35.3 m")
    tool = VerifiedMathBlock(text="", canonical_answer="x = 7")
    assert await _tool_loop_path(physics, tool) is physics


async def test_with_no_server_block_the_tool_block_is_used() -> None:
    tool = VerifiedMathBlock(text="", canonical_answer="x = 6")
    assert await _tool_loop_path(None, tool) is tool
