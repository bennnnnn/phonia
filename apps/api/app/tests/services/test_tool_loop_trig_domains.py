"""MCP retries cannot certify a trig answer for the wrong user domain."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.mcp.base import ToolResult
from app.modules.chat.tool_loop import rounds
from app.modules.math.reply_policy import MATH_REPLY_POLICY
from app.services.subjects.registry import subject_adapter
from app.tests.tool_context import tool_context


def _call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


async def _run(query: str, calls: list[dict], invoke: AsyncMock):
    with (
        patch(
            "app.modules.chat.tool_loop.rounds.litellm_gateway.complete_with_tools",
            AsyncMock(return_value={"tool_calls": calls}),
        ),
        patch("app.modules.chat.tool_loop.calls.mcp_registry.invoke_validated", invoke),
    ):
        return await rounds._run_rounds(
            settings=Settings(mcp_tool_loop_max_calls_per_round=4),
            messages=[{"role": "user", "content": query}],
            usage={},
            tools=[
                {"type": "function", "function": {"name": "sympy"}},
                {"type": "function", "function": {"name": "web_search"}},
            ],
            ctx=tool_context(),
            on_status=None,
            should_cancel=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,rhs",
    [
        ("Solve sin(x)=1/2 for 0<=x<=2*pi", "1/2"),
        ("Solve sin(x)=2 over the complex numbers", "2"),
        ("Solve sin(x)=1/2 from -pi to pi", "1/2"),
    ],
)
async def test_unrestricted_trig_retry_cannot_attach_canonical_answer(query: str, rhs: str):
    invoke = AsyncMock(
        return_value=ToolResult(
            name="sympy",
            content="Verified all-real solution",
            data={"canonical_answer": "wrong-domain answer"},
        )
    )
    messages, verified, terminal, hits = await _run(
        query, [_call("trig", "sympy", {"action": "solve", "lhs": "sin(x)", "rhs": rhs})], invoke
    )
    invoke.assert_not_awaited()
    assert verified is None and terminal is None and not hits
    assert messages[-2]["role"] == "tool" and messages[-2]["tool_call_id"] == "trig"
    assert "No solution was certified" in messages[-2]["content"]  # safety phrase
    assert messages[-1] == {"role": "system", "content": MATH_REPLY_POLICY}
    assert rounds.first_unanswered_tool_turn(messages) is None


@pytest.mark.asyncio
async def test_restricted_trig_request_preserves_other_computations_and_tools():
    invoke = AsyncMock(
        side_effect=[
            ToolResult(name="sympy", content="x=2", data={"canonical_answer": "x = 2"}),
            ToolResult(name="web_search", content="Reference result"),
        ]
    )
    _, verified, _, _ = await _run(
        "Solve sin(x)=1/2 on [0,pi], solve x+1=3, and find a reference.",
        [
            _call("trig", "sympy", {"action": "solve", "lhs": "sin(x)", "rhs": "1/2"}),
            _call("algebra", "sympy", {"action": "solve", "lhs": "x+1", "rhs": "3"}),
            _call("search", "web_search", {"query": "trigonometry reference"}),
        ],
        invoke,
    )
    assert invoke.await_count == 2
    assert [call.args[0] for call in invoke.await_args_list] == ["sympy", "web_search"]
    assert verified is not None and verified.canonical_answer == "x = 2"


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["", " from scratch", " within a few steps"])
async def test_all_real_or_teaching_trig_request_keeps_tool_result(suffix: str):
    invoke = AsyncMock(
        return_value=ToolResult(
            name="sympy",
            content="Periodic solution",
            data={"canonical_answer": "periodic branches"},
        )
    )
    _, verified, _, _ = await _run(
        f"Solve sin(x)=1/2{suffix}",
        [_call("trig", "sympy", {"action": "solve", "lhs": "sin(x)", "rhs": "1/2"})],
        invoke,
    )
    invoke.assert_awaited_once()
    assert verified is not None and verified.canonical_answer == "periodic branches"


@pytest.mark.parametrize(
    "name,args",
    [
        ("sympy", {"action": "simplify", "expr": "sin(pi/6)"}),
        ("sympy", "not JSON"),
        ("sympy", "[]"),
        ("web_search", {"query": "sin(x) complex solutions"}),
    ],
)
def test_guard_leaves_other_actions_and_argument_validation_to_registry(name: str, args):
    tool = subject_adapter("math").tool
    assert tool is not None
    assert not tool.refuses(name, args, "Solve sin(x)=2 over the complex numbers")
