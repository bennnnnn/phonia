"""MCP adapter tests."""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways.mcp.registry import get
from app.modules.math.tool import SympyAdapter
from app.modules.web_search import WebSearchAdapter
from app.services.mcp import setup_mcp_adapters
from app.tests.tool_context import tool_context


def test_sympy_adapter_shim_is_the_math_tool():
    import app.modules.math.tool as legacy
    import app.modules.math.tool as math_tool

    assert legacy is math_tool
    assert legacy.SympyAdapter is SympyAdapter


@pytest.mark.asyncio
async def test_web_search_adapter_missing_query():
    adapter = WebSearchAdapter(Settings())
    ctx = tool_context()
    result = await adapter.invoke({}, ctx)
    assert "Missing query" in result.content
    # A call that never searched does not use up the turn's one search.
    assert ctx.first_results == {}


@pytest.mark.asyncio
async def test_web_search_adapter_uses_cached_search_with_the_turn_context(fake_redis):
    """Model-initiated web_search must go through search_cache (Tavily quota)."""
    from app.gateways.web_search_gateway import WebSearchHit

    user = MagicMock()
    user.id = uuid4()
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    hit = WebSearchHit(title="T", url="https://example.com", snippet="s")
    ctx = tool_context(user=user, redis=fake_redis)

    with patch(
        "app.modules.web_search.tool.run_cached_search",
        AsyncMock(return_value=([hit], ["q"])),
    ) as cached:
        result = await adapter.invoke({"query": "latest news"}, ctx)

    cached.assert_awaited_once()
    assert cached.await_args.args[1] == ["latest news"]
    assert cached.await_args.kwargs["user"] is user
    assert cached.await_args.kwargs["redis"] is fake_redis
    # The turn's one Tavily budget, by reference.
    assert cached.await_args.kwargs["budget"] is ctx.tavily_budget
    assert "BEGIN UNTRUSTED CONTENT — web search" in result.content
    assert "- T: https://example.com" in result.content
    assert result.data is not None
    assert result.data["hits"] == [
        {"title": "T", "url": "https://example.com", "snippet": "s"},
    ]


@pytest.mark.asyncio
async def test_web_search_adapter_date_anchors_current_news(fake_redis):
    from app.gateways.web_search_gateway import WebSearchHit
    from app.modules.web_search.query_builders import _today_label

    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    today = _today_label("America/Los_Angeles")
    hit = WebSearchHit(title="T", url="https://example.com", snippet=f"Reported {today}.")
    cached = AsyncMock(return_value=([hit], ["q"]))
    ctx = tool_context(
        redis=fake_redis,
        user_query="What's happening in the U.S. today?",
        user_timezone="America/Los_Angeles",
    )

    with patch("app.modules.web_search.tool.run_cached_search", cached):
        result = await adapter.invoke({"query": "major U.S. news today"}, ctx)

    searched = cached.await_args.args[1][0]
    assert searched.startswith("major U.S. news today ")
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", searched)
    assert "Only 1 matching result(s) were verified" in result.content
    assert "do not invent extra items" in result.content


@pytest.mark.asyncio
async def test_web_search_adapter_rejects_old_results_for_ai_developments_today(fake_redis):
    from app.gateways.web_search_gateway import WebSearchHit

    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    stale = WebSearchHit(
        title="Meta releases Llama 3",
        url="https://example.com/old",
        snippet="Published April 18, 2024.",
    )
    cached = AsyncMock(return_value=([stale], ["q"]))
    ctx = tool_context(
        redis=fake_redis,
        user_query="What are the three most important AI developments today?",
        user_timezone="America/Los_Angeles",
    )

    with patch("app.modules.web_search.tool.run_cached_search", cached):
        result = await adapter.invoke({"query": "AI developments today"}, ctx)

    searched = cached.await_args.args[1][0]
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", searched)
    assert "Only 0 independently dated same-day result(s) were found" in result.content
    assert result.data is None


@pytest.mark.asyncio
async def test_web_search_adapter_does_not_expand_one_today_source_into_three_items(fake_redis):
    from app.gateways.web_search_gateway import WebSearchHit
    from app.modules.web_search.query_builders import _today_label

    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    today = _today_label("America/Los_Angeles")
    one_hit = WebSearchHit(
        title="AI roundup",
        url="https://example.com/today",
        snippet=f"Updated {today}.",
    )
    cached = AsyncMock(return_value=([one_hit], ["q"]))
    ctx = tool_context(
        redis=fake_redis,
        user_query="What are the three most important AI developments today?",
        user_timezone="America/Los_Angeles",
    )

    with patch("app.modules.web_search.tool.run_cached_search", cached):
        result = await adapter.invoke({"query": "AI developments today"}, ctx)

    assert "Only 1 independently dated same-day result(s) were found" in result.content
    assert "split one source into multiple developments" in result.content
    assert result.data is None


@pytest.mark.asyncio
async def test_web_search_adapter_does_not_call_gateway_directly():
    """Regression: adapter must not bypass quota via web_search_gateway.search_web."""
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    with (
        patch(
            "app.modules.web_search.tool.run_cached_search",
            AsyncMock(return_value=([], ["q"])),
        ),
        patch("app.gateways.web_search_gateway.search_web", AsyncMock()) as direct,
    ):
        result = await adapter.invoke({"query": "anything"}, tool_context())
    direct.assert_not_awaited()
    assert result.content.startswith("No results:")


@pytest.mark.asyncio
async def test_web_search_adapter_second_invoke_reuses_first_result(fake_redis):
    from app.gateways.web_search_gateway import WebSearchHit

    user = MagicMock()
    user.id = uuid4()
    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    hit = WebSearchHit(title="T", url="https://example.com", snippet="s")
    cached = AsyncMock(return_value=([hit], ["q"]))
    ctx = tool_context(user=user, redis=fake_redis)

    with patch("app.modules.web_search.tool.run_cached_search", cached):
        first = await adapter.invoke({"query": "latest news"}, ctx)
        second = await adapter.invoke({"query": "something else"}, ctx)

    cached.assert_awaited_once()
    assert second.content == first.content
    assert second.data == first.data


@pytest.mark.asyncio
async def test_web_search_adapter_searches_once_per_turn_not_per_process(fake_redis):
    """The once-per-turn result lives on the turn's context, so the next turn searches."""
    from app.gateways.web_search_gateway import WebSearchHit

    adapter = WebSearchAdapter(Settings(web_search_enabled=True, mock_llm_enabled=True))
    cached = AsyncMock(
        return_value=([WebSearchHit(title="T", url="https://e.com", snippet="")], [])
    )

    with patch("app.modules.web_search.tool.run_cached_search", cached):
        await adapter.invoke({"query": "latest news"}, tool_context(redis=fake_redis))
        await adapter.invoke({"query": "latest news"}, tool_context(redis=fake_redis))

    assert cached.await_count == 2


def test_mcp_registry_setup():
    from app.gateways.mcp.registry import clear

    clear()
    setup_mcp_adapters(Settings())
    assert get("web_search") is not None
    # Recall has no calendar integration, so the model is never offered one.
    assert get("calendar") is None
    clear()


def test_mcp_registry_registers_image_search_when_enabled():
    from app.gateways.mcp.registry import clear

    clear()
    setup_mcp_adapters(Settings(image_search_enabled=True))
    assert get("search_image") is not None
    clear()

    setup_mcp_adapters(Settings(image_search_enabled=False))
    assert get("search_image") is None
    clear()


def test_mcp_registry_sympy_absent_when_math_tools_disabled():
    """PR 5: math_tools_enabled=False must unregister the model-callable
    "sympy" MCP tool — without this gate, the model could still reach SymPy
    via the tool even when the operator disabled math_tools_enabled (which
    otherwise gates only the pre-stream build_math_augmentation path)."""
    from app.gateways.mcp.registry import clear

    clear()
    setup_mcp_adapters(Settings(math_tools_enabled=False))
    assert get("sympy") is None

    clear()
    setup_mcp_adapters(Settings(math_tools_enabled=True))
    assert get("sympy") is not None


def test_sympy_adapter_describe_does_not_advertise_physics() -> None:
    description = SympyAdapter(Settings()).describe().lower()
    assert "kinematics" not in description
    assert "projectile" not in description
    assert "f=ma" not in description
    assert "scalar-energy" not in description


@pytest.mark.asyncio
async def test_sympy_adapter_rejects_rce_payload_via_solve():
    """The model can call this tool directly — it must not be a second,
    unguarded path to the same eval() gadget the direct math_solve fix
    blocks (see test_math_service.py's parametrized RCE test)."""
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {
            "action": "solve",
            "lhs": "x.__class__.__bases__[0].__subclasses__()[400]('id')",
            "rhs": "0",
            "variables": ["x"],
        },
        tool_context(),
    )
    assert "Math error" in result.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action, expr, variable",
    [
        ("simplify", "x + x", "x"),
        ("diff", "x**2", "x"),
        ("integrate", "2*x", "x"),
        ("factor", "x**2 - 1", "x"),
        ("expand", "(x - 1)*(x + 1)", "x"),
    ],
)
async def test_sympy_adapter_dispatches_simplify_diff_integrate(action, expr, variable):
    """BUG FIX: schemas/tools.py declared "simplify"/"diff"/"integrate" as
    valid actions, but invoke() had no branch for them — a model call with
    one of these actions fell through to the free-text intent-extraction
    fallback instead of calling the already-implemented math_solve
    functions. factor/expand were advertised in describe() without handlers.

    Parity fix (math review #1): these now attach a canonical ```answer
    fence so validate_math_fences corrects the model's final answer to the
    verified SymPy value — same invariant _action_solve enforces for
    equation solves."""
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": action, "expr": expr, "variable": variable}, tool_context()
    )
    assert "Result:" in result.content
    assert "```answer\n" not in result.content
    assert result.data is not None
    assert result.data["canonical_fence"]["type"] == "answer"
    assert result.data["canonical_fence"]["content"].strip()


@pytest.mark.asyncio
async def test_sympy_adapter_expr_op_definite_integrate_attaches_answer():
    """A definite integral gets the same canonical ```answer fence as an
    indefinite one (parity with the heuristic _verified_block_calculus)."""
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "integrate", "expr": "x**2", "variable": "x", "lower": "0", "upper": "1"},
        tool_context(),
    )
    assert "Result:" in result.content
    assert "```answer\n" not in result.content
    assert result.data is not None
    assert result.data["canonical_fence"]["type"] == "answer"
    # ∫₀¹ x² dx = 1/3
    assert "frac{1}{3}" in result.data["canonical_fence"]["content"]


@pytest.mark.asyncio
async def test_sympy_adapter_expr_op_unclosed_integral_emits_honesty_note():
    """When SymPy can't find a closed form (hands back a literal Integral),
    the adapter must NOT attach a ```answer / canonical fence — the model
    must not be told to copy an unverified value as verified. Mirrors
    _verified_block_calculus's solved=False branch."""
    adapter = SympyAdapter(Settings())
    # x**x has no elementary antiderivative — SymPy leaves it as an unevaluated
    # Integral(...) rather than raising, so `solved` is False.
    result = await adapter.invoke(
        {"action": "integrate", "expr": "x**x", "variable": "x"}, tool_context()
    )
    assert "could not find a closed-form result" in result.content
    assert "Do NOT claim this as a verified answer" in result.content
    assert "```answer" not in result.content
    assert result.data is None


@pytest.mark.asyncio
async def test_sympy_adapter_dispatches_parity_actions():
    """BUG FIX (math audit): the MCP tool surface was smaller than the heuristic
    path — system/limit/series/newton had no structured action, so the model
    couldn't call them directly. They now route to the existing verified
    math_solve functions."""
    adapter = SympyAdapter(Settings())

    limit_res = await adapter.invoke(
        {"action": "limit", "expr": "sin(x)/x", "variable": "x", "point": "0"}, tool_context()
    )
    assert "Result:" in limit_res.content
    assert "```answer\n" not in limit_res.content
    assert limit_res.data is not None
    assert limit_res.data["canonical_fence"]["type"] == "answer"
    # lim_{x→0} sin(x)/x = 1
    assert limit_res.data["canonical_fence"]["content"].strip() == "1"

    series_res = await adapter.invoke(
        {"action": "series", "expr": "x", "variable": "x", "start": "1", "end": "10"},
        tool_context(),
    )
    assert "Result:" in series_res.content
    assert "```answer\n" not in series_res.content
    assert series_res.data is not None
    assert series_res.data["canonical_fence"]["type"] == "answer"
    # Σ_{1..10} x = 55
    assert series_res.data["canonical_fence"]["content"].strip() == "55"

    newton_res = await adapter.invoke(
        {"action": "newton", "expr": "x**2 - 2", "variable": "x", "guess": 1.0}, tool_context()
    )
    assert "converged=True" in newton_res.content
    assert "```answer\n" not in newton_res.content
    assert "1.41" in newton_res.content  # √2 ≈ 1.4142…
    assert newton_res.data is not None
    assert newton_res.data["canonical_fence"]["type"] == "answer"
    assert "1.41" in newton_res.data["canonical_fence"]["content"]

    system_res = await adapter.invoke(
        {
            "action": "system",
            "equations": [["x + y", "3"], ["x - y", "1"]],
            "variables": ["x", "y"],
        },
        tool_context(),
    )
    # x = 2, y = 1.
    assert "2" in system_res.content
    assert "1" in system_res.content


@pytest.mark.asyncio
async def test_sympy_adapter_dsolve_and_second_diff():
    adapter = SympyAdapter(Settings())
    ode = await adapter.invoke(
        {"action": "dsolve", "expr": "dy/dx = y", "variable": "x"}, tool_context()
    )
    assert ode.data is not None
    assert ode.data["canonical_fence"]["type"] == "answer"
    low = ode.data["canonical_fence"]["content"].lower()
    assert "e" in low or "exp" in low or "c" in low

    d2 = await adapter.invoke(
        {"action": "diff", "expr": "x**4 - 3*x**2", "variable": "x", "order": 2}, tool_context()
    )
    assert d2.data is not None
    content = d2.data["canonical_fence"]["content"]
    assert "x^{3}" not in content
    assert "2 x^{2}" in content or "12" in content


@pytest.mark.asyncio
async def test_sympy_adapter_simplify_times_out_instead_of_blocking(
    thread_sympy_executor: None,
):
    """Uses the in-process thread executor so the local ``_hang`` closure is
    callable (closures aren't picklable across a subprocess boundary). The
    production ProcessPoolSympyExecutor's hard-kill-on-timeout is exercised
    separately in test_sympy_executor.py."""
    settings = Settings(stem_solve_timeout_seconds=0.05)
    adapter = SympyAdapter(settings)

    def _hang(expr, variable):
        import time

        time.sleep(1)
        raise AssertionError("should have been cancelled by the timeout")

    with patch("app.modules.math.tool.math_solve.simplify_expression", side_effect=_hang):
        result = await asyncio.wait_for(
            adapter.invoke(
                {"action": "simplify", "expr": "x + x", "variable": "x"}, tool_context()
            ),
            timeout=5,
        )
    assert "timed out" in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_broken_pool_degrades_like_timeout(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
):
    from concurrent.futures.process import BrokenProcessPool

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise BrokenProcessPool("killed by sibling timeout")

    monkeypatch.setattr("app.core.sympy_executor.run_sympy", boom)
    adapter = SympyAdapter(Settings(stem_solve_timeout_seconds=5))
    result = await adapter.invoke(
        {"action": "simplify", "expr": "x + x", "variable": "x"}, tool_context()
    )
    assert "timed out" in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_reports_a_declined_value_as_its_reason(
    thread_sympy_executor: None,
):
    """A decline is not a timeout: the model is told the reason, not "timed out"."""
    from app.services.solving import SolveServiceError

    adapter = SympyAdapter(Settings(stem_solve_timeout_seconds=5))
    declined = SolveServiceError("could not verify: an odd root kept no real value")
    with patch("app.modules.math.tool.math_solve.simplify_expression", side_effect=declined):
        result = await adapter.invoke(
            {"action": "simplify", "expr": "x + x", "variable": "x"}, tool_context()
        )
    assert result.content == "Math error: could not verify: an odd root kept no real value"


@pytest.mark.asyncio
async def test_sympy_adapter_solve_times_out_instead_of_blocking(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
):
    """BUG FIX (was silent): this adapter used to call math_solve directly,
    synchronously, with no timeout — unlike every chat-path caller. A hung
    expression must now time out instead of blocking the worker forever.

    Uses the in-process thread executor so the local ``_hang`` closure is
    callable (closures aren't picklable across a subprocess boundary)."""
    settings = Settings(stem_solve_timeout_seconds=0.05)
    adapter = SympyAdapter(settings)

    def _hang(data):
        import time

        time.sleep(1)
        raise AssertionError("should have been cancelled by the timeout")

    with patch("app.modules.math.tool.math_solve.solve_equation", side_effect=_hang):
        result = await asyncio.wait_for(
            adapter.invoke(
                {"action": "solve", "lhs": "x", "rhs": "0", "variables": ["x"]}, tool_context()
            ),
            timeout=5,
        )
    assert "timed out" in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_rectangle_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "rectangle", "width": 8, "height": 5, "unit": "cm"}, tool_context()
    )
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "rectangle"
    assert fence["width"] == 8.0
    assert fence["height"] == 5.0
    assert "```geometry\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_integrate_definite():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "integrate", "expr": "x**2", "variable": "x", "lower": "0", "upper": "1"},
        tool_context(),
    )
    assert "Result:" in result.content
    assert "```answer\n" not in result.content
    assert result.data is not None
    assert result.data["canonical_fence"]["type"] == "answer"
    assert "frac{1}{3}" in result.data["canonical_fence"]["content"]


@pytest.mark.asyncio
async def test_sympy_adapter_square_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke({"action": "square", "side": 5, "unit": "cm"}, tool_context())
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "square"
    assert fence["side"] == 5.0
    assert "```geometry\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_circle_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke({"action": "circle", "radius": 3, "unit": "cm"}, tool_context())
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "circle"
    assert fence["radius"] == 3.0
    assert "```geometry\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_graph_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "graph", "expr": "x**2", "x_min": -2, "x_max": 2}, tool_context()
    )
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "function"
    # SymPy's reading, in the grammar the phone resamples (graph_expr_text).
    assert fence["expr"] == "x^2"
    assert len(fence["points"]) >= 2
    assert "```graph\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_graph_without_an_expression_does_not_sample_a_parabola():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke({"action": "graph"}, tool_context())
    assert result.data is None
    assert "x**2" not in result.content
    assert "expression" in result.content.lower()


@pytest.mark.asyncio
async def test_sympy_adapter_solve_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "solve", "lhs": "x**2 - 1", "rhs": "0", "variables": ["x"]}, tool_context()
    )
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "answer"
    assert fence["content"]
    assert "```answer\n" not in result.content
    assert "x" in fence["content"] or "1" in fence["content"]


@pytest.mark.asyncio
async def test_sympy_adapter_system_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {
            "action": "system",
            "equations": [["x + y", "3"], ["x - y", "1"]],
            "variables": ["x", "y"],
        },
        tool_context(),
    )
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "answer"
    assert "x" in fence["content"] and "y" in fence["content"]
    assert "```answer\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_inequality_includes_canonical_fence():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {
            "action": "inequality",
            "lhs": "x**2 - 1",
            "rhs": "0",
            "comparator": ">",
            "variables": ["x"],
        },
        tool_context(),
    )
    assert result.data is not None
    # BUG FIX: the MCP inequality path used to attach only an ```answer
    # canonical fence and no graph, so the solution set was never rendered
    # as an SVG. Now a one-variable inequality attaches the verified
    # number_line graph fence as canonical (the answer still ships in the
    # content text).
    fence = result.data["canonical_fence"]
    assert fence["type"] == "number_line"
    assert result.data.get("canonical_answer")
    assert "```answer\n" not in result.content
    assert "```graph\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_inequality_rejects_bad_comparator():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {"action": "inequality", "lhs": "x", "rhs": "0", "comparator": "!="}, tool_context()
    )
    assert "comparator" in result.content.lower()
    assert result.data is None


@pytest.mark.asyncio
async def test_sympy_adapter_graph_pair_via_expr2():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke(
        {
            "action": "graph",
            "expr": "x**2",
            "expr2": "2*x",
            "x_min": -2,
            "x_max": 2,
        },
        tool_context(),
    )
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["expr"] == "x^2"
    assert fence["expr2"] == "2x"
    assert fence["points2"] is not None
    assert len(fence["points2"]) >= 2
    assert fence["label2"]
    assert "```graph\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_graph_ellipse_relation():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke({"action": "graph", "expr": "x**2 + y**2 = 1"}, tool_context())
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["points"][0] == fence["points"][-1]
    assert len(fence["points"]) >= 16
    assert "```graph\n" not in result.content


@pytest.mark.asyncio
async def test_sympy_adapter_graph_number_line_runs_off_loop():
    adapter = SympyAdapter(Settings())
    result = await adapter.invoke({"action": "graph", "expr": "x > 3"}, tool_context())
    assert result.data is not None
    fence = result.data["canonical_fence"]
    assert fence["type"] == "number_line"
    assert "```graph\n" not in result.content
