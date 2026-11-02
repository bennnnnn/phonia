"""Multi-curve graph overlay — "graph y=x^2 and y=2x on the same graph"."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math import fence as math_fence
from app.modules.math import match as math_match
from app.modules.math.schemas import GraphBlockSpec
from app.tests.modules.math.prompt_support import augment_prompt_messages


class TestGraphExprPairSignal:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("graph y=x^2 and y=2x on the same graph", ("x^2", "2x")),
            ("compare y=x^2 and y=2x", ("x^2", "2x")),
            ("plot x^2 and 2x together", ("x^2", "2x")),
            ("graph y=x^2 and y=2x on the same graph.", ("x^2", "2x")),
            # π is part of an expression: "from 0 to 2π" once failed the whole pair.
            ("Graph y = sin(x) and y = cos(x) from 0 to 2π", ("sin(x)", "cos(x) from 0 to 2π")),
            ("plot sin(πx) and cos(πx)", ("sin(πx)", "cos(πx)")),
        ],
    )
    def test_matches_two_function_asks(self, text, expected):
        assert math_match.graph_expr_pair(text) == expected

    def test_does_not_swallow_trailing_prose_as_a_second_function(self):
        """Regression: "plot sin(x) and explain it" used to be read as a
        second function literally named "explain it"."""
        assert math_match.graph_expr_pair("plot sin(x) and explain it") is None

    def test_single_function_ask_does_not_match(self):
        assert math_match.graph_expr_pair("plot x^2") is None


class TestAugmentPromptMessagesForGraphPair:
    @pytest.mark.asyncio
    async def test_produces_two_curve_canonical_fence(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "graph y=x^2 and y=2x on the same graph"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        fence = verified.canonical_fence
        assert fence is not None
        assert fence["expr2"] is not None
        assert fence["points2"]
        assert len(fence["points2"]) > 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text, x_max",
        [
            ("Graph y = sin(x) and y = cos(x) from 0 to 2π", 6.2832),
            ("plot sin(πx) and cos(πx) from 0 to 2", 2.0),
        ],
    )
    async def test_pi_in_a_pair_still_draws_both_curves(self, text, x_max):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        fence = verified.canonical_fence
        assert fence is not None and fence["points"] and fence["points2"]
        assert fence["x_min"] == 0
        assert fence["x_max"] == pytest.approx(x_max, abs=1e-3)

    @pytest.mark.asyncio
    async def test_single_function_ask_is_unaffected(self):
        settings = Settings(web_search_enabled=False, math_tools_enabled=True)
        text = "plot sin(x) and explain it"
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": text}]
        _, verified = await augment_prompt_messages(messages, text, settings)
        assert verified is not None
        assert verified.canonical_fence["expr2"] is None


class TestDensifyPreservesSecondCurve:
    def test_densify_sparse_first_curve_also_densifies_second_curve(self):
        sparse = GraphBlockSpec(
            expr="x**2",
            variable="x",
            x_min=-10,
            x_max=10,
            points=[[-2, 4], [0, 0], [2, 4]],  # sparse — under _MIN_CURVE_POINTS
            expr2="2*x",
            variable2="x",
            points2=[[-10, -20], [10, 20]],
            label="y = x^2",
            label2="y = 2x",
        )
        densified = math_fence.densify_sparse_graph(sparse)
        assert len(densified.points) > len(sparse.points)
        assert densified.expr2 == "2*x"
        assert densified.points2 is not None
        assert len(densified.points2) > len(sparse.points2 or [])
        assert densified.label2 == "y = 2x"

    def test_densify_sparse_second_curve_when_first_already_dense(self):
        dense_pts = [[float(i), float(i * i)] for i in range(-24, 24)]  # 48 pts
        sparse = GraphBlockSpec(
            expr="x**2",
            variable="x",
            x_min=-10,
            x_max=10,
            points=dense_pts,
            expr2="2*x",
            variable2="x",
            points2=[[-10, -20], [10, 20]],
            label="y = x^2",
            label2="y = 2x",
        )
        densified = math_fence.densify_sparse_graph(sparse)
        assert densified.points == dense_pts  # curve 1 unchanged
        assert densified.points2 is not None
        assert len(densified.points2) > 2
