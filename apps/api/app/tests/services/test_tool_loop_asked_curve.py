"""A curve the learner asked for draws, though its formula is only in an earlier reply.

Live (2026-10-24): "can you graph how the balloon's volume changes with temperature from
the problem earlier?" The sympy tool sampled the line, but no user line held its formula
(the assistant wrote the problem), so the user-match gate dropped the curve and the reply
said "here's the plot" over nothing. The gate guards the verified answer; a curve claims
none. Only a true follow-up keeps its curve: a message with a formula of its own is
matched against it, and a curve a matched call drew is never replaced.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gateways import litellm_gateway
from app.gateways.mcp import registry as mcp_registry
from app.modules.chat import tool_loop
from app.modules.math.text_plot import asks_for_an_earlier_curve
from app.modules.math.tool_check import tool_call_matches_user_text

from .tool_loop_support import settings

_ASK = (
    "ok back to studying. can you graph how the balloon's volume changes with "
    "temperature from the problem earlier?"
)
_BALLOON = {"action": "graph", "expr": "2.0*(t + 273.15)/298.15"}
_CURVE = {"type": "function", "expr": "0.006708*t + 1.8323", "x_range": [-273, 100]}


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


def _round(*args: dict[str, Any]) -> AsyncMock:
    tool_calls = [
        {
            "id": f"g{i}",
            "type": "function",
            "function": {"name": "sympy", "arguments": json.dumps(arg)},
        }
        for i, arg in enumerate(args)
    ]
    return AsyncMock(side_effect=[{"content": None, "tool_calls": tool_calls}])


async def _run(prompt: str, *results: tuple[dict[str, Any], dict[str, Any]]) -> Any:
    """Run one selection round whose calls (args, result data) are ``results``."""
    invoke = AsyncMock(
        side_effect=[MagicMock(content="Sampled 96 points", data=data) for _args, data in results]
    )
    with (
        patch.object(litellm_gateway, "complete_with_tools", _round(*(a for a, _ in results))),
        patch.object(mcp_registry, "invoke_validated", invoke),
        patch("app.core.sympy_executor.run_sympy", _inline),
    ):
        out, verified, _terminal, _hits = await tool_loop.run_tool_rounds(
            settings=settings(mcp_tool_loop_enabled=True, mcp_tool_loop_max_rounds=1),
            messages=[{"role": "user", "content": prompt}],
            usage={},
        )
    tool_messages = [m["content"] for m in out if m.get("role") == "tool"]
    return verified, tool_messages


async def test_an_asked_curve_draws_without_a_verified_answer(sympy_registered: None) -> None:
    verified, tool_messages = await _run(
        _ASK, (_BALLOON, {"canonical_fence": _CURVE, "canonical_answer": "V = 2"})
    )
    assert verified is not None
    assert verified.canonical_fence == _CURVE
    assert verified.canonical_answer is None
    assert "does not match" in tool_messages[0]


@pytest.mark.parametrize(
    ("prompt", "fence"),
    [
        # Not a graph turn: the model's own curve is not what the learner asked for.
        ("what's the volume of the balloon from earlier at 75 degrees?", _CURVE),
        # A graph turn, but the unmatched result is an answer, not a curve.
        (_ASK, {"type": "answer", "content": "V = 2.34 L"}),
        # The user's own formula, mistyped by the model: the wrong curve never draws.
        ("graph y = x^2 + 1", _CURVE),
    ],
)
async def test_other_unmatched_results_stay_dropped(
    sympy_registered: None, prompt: str, fence: dict[str, Any]
) -> None:
    verified, _messages = await _run(prompt, (_BALLOON, {"canonical_fence": fence}))
    assert verified is None


async def test_an_unmatched_curve_never_replaces_a_matched_one(sympy_registered: None) -> None:
    sine = {"type": "function", "expr": "sin(x)"}
    verified, _messages = await _run(
        "plot y = sin(x)",
        ({"action": "graph", "expr": "sin(x)"}, {"canonical_fence": sine}),
        ({"action": "graph", "expr": "cos(x)"}, {"canonical_fence": _CURVE}),
    )
    assert verified is not None
    assert verified.canonical_fences == [sine]


@pytest.mark.parametrize(
    ("text", "asks"),
    [
        (_ASK, True),
        ("can you graph it?", True),
        ("graph y = x^2 + 1", False),  # its own formula
        ("what's the volume at 75 degrees?", False),  # no graph asked
    ],
)
def test_an_earlier_curve_is_asked_for_by_words_alone(text: str, asks: bool) -> None:
    assert asks_for_an_earlier_curve(text) is asks


def test_a_contraction_is_not_the_follow_ups_formula() -> None:
    args = json.dumps({"action": "graph", "expr": "x**2"})
    assert tool_call_matches_user_text(args, ["let's graph it", "y = x^2"])
    assert tool_call_matches_user_text(args, ["it’s time to graph it", "y = x^2"])
    # The follow-up's own formula is still its reference.
    assert not tool_call_matches_user_text(args, ["let's graph y = x^3", "y = x^2"])


@pytest.mark.parametrize(
    ("args", "text"),
    [
        ({"action": "graph", "expr": "x**2"}, "plot 'x^2'"),
        ({"action": "integrate", "expr": "x**2"}, "integrate 'x^2'"),
        ({"action": "simplify", "expr": "x**2 + 2*x + 1"}, "simplify 'x^2 + 2x + 1'"),
    ],
)
def test_a_quoted_formula_keeps_its_letters(args: dict[str, Any], text: str) -> None:
    assert tool_call_matches_user_text(json.dumps(args), [text])
