"""Complete verified implicit curves can use the same immediate graph output."""

import json
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.modules.math.fence import validate_math_fences
from app.modules.math.schemas import GraphBlockSpec
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.prompt import build_math_augmentation
from app.services.solving import VerifiedMathBlock


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["Graph x^2+y^2=1", "Graph x^2/9+y^2/4=1"])
async def test_exact_closed_relation_returns_unchanged_complete_graph(query):
    _, verified = await build_math_augmentation(query, Settings(math_tools_enabled=True))
    assert verified is not None and verified.canonical_fence is not None
    fence = verified.canonical_fence
    assert len(fence["points"]) >= 16 and fence["points"][0] == fence["points"][-1]
    reply = maybe_direct_math_reply(verified, query)
    assert reply == f"```graph\n{json.dumps(fence, separators=(',', ':'))}\n```\n"
    finalized = validate_math_fences(reply, verified=verified)
    assert finalized.count("```graph") == 1 and "```answer" not in finalized
    assert json.loads(finalized.split("```graph\n", 1)[1].split("\n```", 1)[0]) == fence


def _circle_block(**changes) -> VerifiedMathBlock:
    graph = GraphBlockSpec(
        expr="x**2 + y**2 = 1",
        x_min=-2,
        x_max=2,
        y_min=-2,
        y_max=2,
        points=[[1, 0], [0, 1], [-1, 0], [0, -1], [1, 0]],
    ).model_dump()
    graph.update(changes)
    return VerifiedMathBlock(text="verified", canonical_fence=graph)


@pytest.mark.parametrize(
    "query",
    [
        "Graph x^2+y^2=1 and explain the circle",
        "Graph x^2+y^2=1 with steps",
        "Graph x^2+y^2=1, hint only",
        "Graph x^2+y^2=1 and y=x",
        "Graph x^2+y^2=1 and find its area",
        "Graph x^2+y^2=1 from 0 to 1",
        "Graph x^2+y^2=1 on [0,1]",
        "Graph x^2+y^2=1 from 0 to 1 from -2 to 2",
        "Graph x^2+y^2=4",
        "Graph x^2+y^2<1",
        "Graph x^2+y^2=1!",
    ],
)
def test_relation_guard_preserves_extra_requests_and_ignored_ranges(query):
    assert maybe_direct_math_reply(_circle_block(), query) is None


@pytest.mark.parametrize("points", [[], [[1, 0]], [[1, 0], [0, 1]], [[1, 0], [0, 1], [-1, 0]]])
def test_incomplete_or_open_relation_cannot_skip_model(points):
    assert maybe_direct_math_reply(_circle_block(points=points), "Graph x^2+y^2=1") is None


def test_closed_relation_keeps_image_and_extra_canonical_result_guards():
    block = _circle_block()
    query = "Graph x^2+y^2=1"
    assert maybe_direct_math_reply(block, query, has_image_attachment=True) is None
    assert maybe_direct_math_reply(replace(block, canonical_answer="area = pi"), query) is None
    assert maybe_direct_math_reply(replace(block, allow_direct=False), query) is None
