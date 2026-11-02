"""Tests for math fence validation."""

import json

import pytest

from app.modules.math.fence import densify_sparse_graph, validate_math_fences
from app.modules.math.schemas import GraphBlockSpec


def _verified(canonical_fence):
    from app.modules.math.tools import VerifiedMathBlock

    return VerifiedMathBlock(text="unused", canonical_fence=canonical_fence)


@pytest.mark.parametrize(
    "content",
    [
        '```geometry\n{"type":"rectangle","width":8,"height":5}\n```',
        '```geometry\n{"type":"rectangle","width":8,"height":5,"area":99}\n```',
        '```geometry\n{"type":"square","side":5,"show_area":true}\n```',
        '```geometry\n{"type":"rect","width":8,"height":5}\n```',
        '```geometry\n{"type":"triangle","base":8,"height":5}\n```',
        ('```geometry\n{"type":"right_triangle","base":6,"height":4,"show_hypotenuse":true}\n```'),
        (
            '```geometry\n{"type":"circle","radius":4,"show_diameter":true,'
            '"show_area":true,"show_circumference":true}\n```'
        ),
    ],
)
def test_unverified_geometry_fence_is_stripped(content: str) -> None:
    """Schema-valid invented diagrams must not ship without a canonical fence."""
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```geometry" not in out


def test_replaces_invalid_geometry_fence() -> None:
    content = "```geometry\n{bad json\n```"
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "Invalid geometry block" not in out


def test_empty_points_graph_fence_without_canonical_is_stripped() -> None:
    """Do not resample an unmatched model expr into a verified-looking curve."""
    content = '```graph\n{"type":"function","expr":"3*x+4","points":[]}\n```'
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```graph" not in out


def test_invalid_graph_json_still_strips() -> None:
    content = "```graph\n{bad json\n```"
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "Invalid graph block" not in out


def test_unverified_vertical_line_graph_fence_is_stripped() -> None:
    content = '```graph\n{"type":"vertical","x":4,"y_min":-5,"y_max":5,"title":"x = 4"}\n```'
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```graph" not in out


def test_replaces_truncated_unclosed_graph_fence_with_canonical() -> None:
    """Regression: a weak model often stops copying the verified points array
    mid-way (EOS at ~30 of 96 points), leaving a ```graph fence with no closing
    ```. _GRAPH_FENCE requires a closing fence, so the truncated JSON reached
    the client and rendered as "Could not render function graph." When this
    turn has a verified canonical fence, swap the truncated tail for the
    complete fence."""
    from app.core.config import get_settings
    from app.modules.math.tools.prompt import build_math_augmentation

    settings = get_settings()
    import asyncio

    _block, verified = asyncio.run(build_math_augmentation("Graph x^2", settings, needs_math=True))
    assert verified is not None and verified.canonical_fence is not None
    canonical = verified.canonical_fence
    assert canonical["type"] == "function"
    full_points = canonical["points"]
    # Simulate the model truncating the fence mid-points-array (no closing ```).
    truncated_json = json.dumps(canonical)
    cut = truncated_json[: truncated_json.find(",[-3.") + 5]
    content = "Here's the graph for $x^2$:\n\n```graph\n" + cut
    out = validate_math_fences(content, verified=verified)
    i = out.find("```graph\n")
    assert i != -1, "graph fence missing from output"
    j = out.find("\n```", i)
    assert j != -1, "fence not closed"
    out_json = out[i + 8 : j]
    out_spec = json.loads(out_json)
    assert out_spec["type"] == "function"
    assert out_spec["expr"] == "x^2"
    assert len(out_spec["points"]) == len(full_points)
    assert "Could not render" not in out


def test_truncated_unclosed_graph_fence_without_canonical_strips_json() -> None:
    """With no verified canonical fence, a truncated unclosed ```graph fence is
    stripped to 'Could not render that diagram.' rather than leaking the raw
    half-pasted points array."""
    content = "```graph\n" + '{"type":"function","expr":"x**2","points":[[-10,100],[-9,81'
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "[-10,100" not in out


def test_replace_unclosed_graph_fence_safe_substitutes_canonical_without_sympy() -> None:
    """Timeout-fallback path: substitute a verified canonical fence SymPy-free
    (no densify) so a truncated graph fence doesn't leak raw JSON to the client
    when validate_math_fences was killed by the solve timeout."""
    from app.modules.math.fence import replace_unclosed_graph_fence_safe

    canonical_points: list[list[float]] = [[-10.0, 100.0], [0.0, 0.0], [10.0, 100.0]]
    canonical: dict[str, object] = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -10.0,
        "x_max": 10.0,
        "points": canonical_points,
    }
    truncated = "```graph\n" + json.dumps(canonical)[: json.dumps(canonical).find(",[0.0") + 5]
    out = replace_unclosed_graph_fence_safe(truncated, canonical)
    assert "Could not render" not in out
    i = out.find("```graph\n")
    assert i != -1
    j = out.find("\n```", i)
    assert j != -1, "safe fallback must close the fence"
    spec = json.loads(out[i + 8 : j])
    assert spec["type"] == "function"
    assert spec["expr"] == "x**2"
    # Canonical fence substituted as-is (no densify re-sample).
    out_points: list = spec["points"]
    assert len(out_points) == len(canonical_points)


def test_replace_unclosed_graph_fence_safe_strips_when_no_canonical() -> None:
    """No verified canonical fence → strip the truncated tail to the error note."""
    from app.modules.math.fence import replace_unclosed_graph_fence_safe

    content = "```graph\n" + '{"type":"function","expr":"x**2","points":[[-10,100],[-9,81'
    out = replace_unclosed_graph_fence_safe(content, None)
    assert "Could not render that diagram" in out
    assert "[-10,100" not in out


def test_replace_unclosed_graph_fence_safe_noop_when_no_unclosed_fence() -> None:
    """No diagram fence → return content unchanged (no SymPy, no rewrite)."""
    from app.modules.math.fence import replace_unclosed_graph_fence_safe

    content = "Just prose, no graph fence at all."
    assert replace_unclosed_graph_fence_safe(content, None) == content


def test_replace_unclosed_graph_fence_safe_degrades_closed_unmatched() -> None:
    """Timeout path must fail-closed on complete invented geometry/graph JSON."""
    from app.modules.math.fence import replace_unclosed_graph_fence_safe

    geo = '```geometry\n{"type":"rectangle","width":99,"height":1}\n```'
    geo_out = replace_unclosed_graph_fence_safe(geo, None)
    assert "Could not render that diagram" in geo_out
    assert "```geometry" not in geo_out
    assert "99" not in geo_out

    graph = '```graph\n{"type":"function","expr":"x**2","points":[[0.0,0.0],[1.0,1.0]]}\n```'
    graph_out = replace_unclosed_graph_fence_safe(graph, None)
    assert "Could not render that diagram" in graph_out
    assert "```graph" not in graph_out
    assert "x**2" not in graph_out


def test_rewrites_unverified_inequality_step_to_number_line() -> None:
    content = (
        '```graph\n{"type":"function","expr":"x > 3","title":"x > 3 (number line)",'
        '"points":[[-10,0],[3,0],[3,1],[10,1]]}\n```'
    )
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```graph" not in out


def test_unverified_single_point_graph_fence_is_stripped() -> None:
    content = (
        '```graph\n{"type":"function","expr":"(2, 3)","title":"Point (2, 3)","points":[[2,3]]}\n```'
    )
    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```graph" not in out


def test_rewrites_inequality_function_fence_to_canonical_number_line() -> None:
    canonical = {
        "type": "number_line",
        "title": "x > 3",
        "intervals": [
            {
                "start": 3.0,
                "end": None,
                "start_inclusive": False,
                "end_inclusive": False,
            }
        ],
    }
    content = (
        '```graph\n{"type":"function","expr":"x > 3","title":"x > 3 (number line)",'
        '"points":[[-10,0],[3,0],[3,1],[10,1]]}\n```'
    )
    out = validate_math_fences(content, verified=_verified(canonical))
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["type"] == "number_line"
    assert data["intervals"][0]["start"] == 3.0


def test_rewrites_function_graph_to_canonical_trajectory() -> None:
    points = [[0.0, 20.0], [1.0, 15.095], [2.02, 0.0]]
    canonical = {
        "type": "trajectory",
        "expr": "h(t) = 20 - 0.5*9.81*t^2",
        "variable": "t",
        "x_min": 0.0,
        "x_max": 2.02,
        "points": points,
        "title": "Height vs. Time",
        "trajectory_type": "position_vs_time",
    }
    content = (
        '```graph\n{"type":"function","expr":"h = h_0 + v_0 t - 0.5 g t^2","title":"height"}\n```'
    )
    out = validate_math_fences(content, verified=_verified(canonical))
    assert "Could not render" not in out
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["type"] == "trajectory"
    assert data["points"] == points


def test_corrects_hallucinated_geometry_values_to_canonical() -> None:
    """The model claimed a wrong diagonal — the real computed value must win."""
    canonical = {
        "type": "rectangle",
        "width": 8,
        "height": 5,
        "diagonal": 9.434,
        "angle_deg": 32.0,
    }
    # Model's own fence: same kind, but wrong (hallucinated) diagonal.
    content = '```geometry\n{"type":"rectangle","width":8,"height":5,"diagonal":99}\n```'

    out = validate_math_fences(content, verified=_verified(canonical))

    assert '"diagonal":9.434' in out
    assert '"diagonal":99' not in out


def test_corrects_graph_fence_to_canonical_points() -> None:
    # Already-dense canonical — rewrite without densify churn.
    points = [[float(i) / 5, (float(i) / 5) ** 2] for i in range(-50, 51)]
    canonical = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -10.0,
        "x_max": 10.0,
        "points": points,
    }
    content = '```graph\n{"type":"function","expr":"x**2","points":[[0,0],[1,999]]}\n```'

    out = validate_math_fences(content, verified=_verified(canonical))

    assert "[1,999]" not in out
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["points"] == points


def test_corrects_trajectory_fence_to_canonical_points() -> None:
    points = [[i * 2.1 / 99, max(0.0, 20.0 - 4.905 * (i * 2.1 / 99) ** 2)] for i in range(100)]
    canonical = {
        "type": "trajectory",
        "expr": "h(t) = 20 - 0.5*9.81*t^2",
        "variable": "t",
        "x_min": 0.0,
        "x_max": 2.0,
        "points": points,
        "title": "Height vs. Time",
        "x_label": "Time (s)",
        "y_label": "Height (m)",
        "trajectory_type": "position_vs_time",
    }
    content = (
        '```graph\n{"type":"trajectory","expr":"h(t)=99","points":[[0,99],[1,99]],'
        '"title":"Wrong trajectory"}\n```'
    )

    out = validate_math_fences(content, verified=_verified(canonical))

    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["points"] == points
    assert data["title"] == "Height vs. Time"
    assert data["trajectory_type"] == "position_vs_time"


def test_densify_leaves_sparse_trajectory_points_unchanged() -> None:
    spec = GraphBlockSpec(
        type="trajectory",
        expr="h(t) = 20 - 0.5*9.81*t^2",
        variable="t",
        points=[[0.0, 20.0], [1.0, 15.095], [2.0, 0.38]],
        trajectory_type="position_vs_time",
    )

    assert densify_sparse_graph(spec) is spec


def test_corrects_points_less_function_fence_to_canonical() -> None:
    """The model often emits a ```graph fence with type=function but DROPS the
    points array (e.g. "Graph x=2y" → {"type":"function","expr":"x/2",...} with
    no points). validate_math_fences must substitute the verified canonical
    fence (with points) so the renderer has a curve to draw — and the rewritten
    text differs from the streamed draft, which is what lets the stream set
    final_content and the client re-render instead of showing
    "Could not render function graph."."""
    points = [[float(i) / 5, (float(i) / 5) / 2] for i in range(-50, 51)]
    canonical = {
        "type": "function",
        "expr": "x/2",
        "variable": "x",
        "x_min": -10.0,
        "x_max": 10.0,
        "points": points,
    }
    content = (
        '```graph\n{"type":"function","expr":"x/2","variable":"x",'
        '"x_min":-10.0,"x_max":10.0,"title":"x = 2y"}\n```'
    )

    out = validate_math_fences(content, verified=_verified(canonical))

    assert out != content  # rewritten → final_content would be set
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["points"] == points


def test_wrong_kind_model_fence_is_stripped_and_canonical_appended() -> None:
    """A canonical rectangle must not overwrite an unmatched square JSON —
    strip the invented square and append the verified rectangle."""
    canonical = {"type": "rectangle", "width": 8, "height": 5}
    content = '```geometry\n{"type":"square","side":5}\n```'

    out = validate_math_fences(content, verified=_verified(canonical))

    assert "Could not render that diagram" in out
    assert '"type":"square"' not in out.replace(" ", "")
    assert "```geometry" in out
    assert '"type":"rectangle"' in out.replace(" ", "")


def test_no_canonical_fence_strips_schema_valid_geometry() -> None:
    content = '```geometry\n{"type":"rectangle","width":8,"height":5}\n```'

    out = validate_math_fences(content, verified=_verified(None))

    assert "Could not render that diagram" in out
    assert "```geometry" not in out


def test_rewrites_answer_fence_from_canonical() -> None:
    content = "Worked steps…\n```answer\nx = 99\n```"
    out = validate_math_fences(
        content,
        verified=_verified({"type": "answer", "content": "x = \\pm 2"}),
    )
    assert "```answer\nverified: true\nx = \\pm 2\n```" in out
    assert "x = 99" not in out


@pytest.mark.parametrize("lang", ["result", "final"])
def test_result_and_final_fences_rewrite_like_answer(lang: str) -> None:
    content = f"Worked steps…\n```{lang}\nx = 99\n```"
    out = validate_math_fences(
        content,
        verified=_verified({"type": "answer", "content": "x = \\pm 2"}),
    )
    assert "```answer\nverified: true\nx = \\pm 2\n```" in out
    assert "x = 99" not in out
    assert f"```{lang}" not in out


def test_unverified_answer_fence_demotes_to_prose_not_a_pill() -> None:
    content = (
        "The area is 12.\n"
        "```answer\n12\n```\n"
        '```geometry\n{"type":"rectangle","width":8,"height":5}\n```'
    )
    out = validate_math_fences(content, verified=None)
    assert "```answer" not in out
    assert "12" in out
    assert "Could not render that diagram" in out
    assert "```geometry" not in out


def test_unclosed_graph_does_not_swallow_following_python_fence() -> None:
    content = (
        'See the plot:\n\n```graph\n{"type":"function","expr":"x"\n'
        "then the code:\n\n```python\nprint(1)\n```"
    )
    out = validate_math_fences(content)
    assert "print(1)" in out
    assert "```python" in out
    assert "Could not render that diagram" in out


def test_leaves_answer_fence_when_canonical_is_geometry() -> None:
    """Wrong-kind canonical must not keep an unverified answer pill; geometry is appended."""
    content = "```answer\nx = 2\n```"
    out = validate_math_fences(
        content,
        verified=_verified({"type": "rectangle", "width": 8, "height": 5}),
    )
    assert "```answer" not in out
    assert "x = 2" in out
    assert "```geometry" in out
    assert '"type":"rectangle"' in out.replace(" ", "")


def test_rewrites_answer_fence_when_geometry_has_canonical_answer() -> None:
    from app.modules.math.tools import VerifiedMathBlock

    content = (
        '```geometry\n{"type":"rectangle","width":4,"height":5,"diagonal":99}\n```\n'
        "```answer\n99\n```"
    )
    verified = VerifiedMathBlock(
        text="unused",
        canonical_fence={
            "type": "rectangle",
            "width": 4,
            "height": 5,
            "area": 20,
            "diagonal": 6.403,
        },
        canonical_answer="20",
    )
    out = validate_math_fences(content, verified=verified)
    assert '"diagonal":6.403' in out
    assert '"diagonal":99' not in out
    assert "```answer\nverified: true\n20\n```" in out
    assert "```answer\n99\n```" not in out


def test_densifies_unverified_sparse_function_graph_fence() -> None:
    """Unmatched sparse sketches are not resampled into a verified-looking curve."""
    content = (
        '```graph\n{"type":"function","expr":"3*x**2 - 12","variable":"x",'
        '"x_min":-2,"x_max":2,"points":[[-2,0],[0,-12],[2,0]]}\n```'
    )

    out = validate_math_fences(content)
    assert "Could not render that diagram" in out
    assert "```graph" not in out


def test_densifies_sparse_canonical_graph_after_rewrite() -> None:
    """Verified sparse samples may still need densify — safe because expr
    came from SymPy, not the model's free-text fence."""
    canonical = {
        "type": "function",
        "expr": "x**4 - 4*x**2 - 12",
        "variable": "x",
        "x_min": -3.0,
        "x_max": 3.0,
        "points": [[-2.0, 0.0], [0.0, -12.0], [2.0, 0.0]],
    }
    # Model listed wrong y values — canonical wins, then densify.
    content = (
        '```graph\n{"type":"function","expr":"x**4 - 4*x**2 - 12","variable":"x",'
        '"x_min":-3,"x_max":3,"points":[[-2,0],[0,999],[2,0]]}\n```'
    )

    out = validate_math_fences(content, verified=_verified(canonical))
    assert "```graph" in out
    assert "[0,999]" not in out.replace(" ", "")
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert len(data["points"]) >= 48


def test_leaves_point_marker_graph_undensified() -> None:
    canonical = {
        "type": "function",
        "expr": "(2, 3)",
        "title": "Point (2, 3)",
        "points": [[2, 3]],
    }
    content = (
        '```graph\n{"type":"function","expr":"(2, 3)","title":"Point (2, 3)","points":[[2,3]]}\n```'
    )
    out = validate_math_fences(content, verified=_verified(canonical))
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["points"] == [[2, 3]]


def test_sample_domain_unions_declared_window_and_key_points() -> None:
    """Default [-10,10] must expand when key points sit outside that window."""
    from app.modules.math.fence_graph import _sample_domain
    from app.modules.math.schemas import GraphBlockSpec

    spec = GraphBlockSpec(
        type="function",
        expr="x**2",
        variable="x",
        x_min=-10.0,
        x_max=10.0,
        points=[[-2.0, 4.0], [25.0, 625.0]],
    )
    x_min, x_max = _sample_domain(spec)
    assert x_min <= -10.0
    assert x_max >= 25.0


def test_leaves_already_dense_graph_formatting_alone() -> None:
    points = [[float(i) / 10, (float(i) / 10) ** 2] for i in range(-50, 51)]
    payload = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -5.0,
        "x_max": 5.0,
        "points": points,
    }
    content = f"```graph\n{json.dumps(payload)}\n```"
    out = validate_math_fences(content, verified=_verified(payload))
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["points"] == points


def test_validate_math_fences_caps_per_kind() -> None:
    from app.modules.math.fence import _MAX_GEOMETRY_FENCES, _MAX_GRAPH_FENCES

    bad_geo = "```geometry\n{bad json\n```"
    geo = "\n".join([bad_geo] * (_MAX_GEOMETRY_FENCES + 1))
    out_geo = validate_math_fences(geo)
    assert out_geo.count("Could not render that diagram") == _MAX_GEOMETRY_FENCES + 1
    assert "```geometry" not in out_geo

    bad_graph = "```graph\n{bad json\n```"
    graphs = "\n".join([bad_graph] * (_MAX_GRAPH_FENCES + 1))
    out_graph = validate_math_fences(graphs)
    assert out_graph.count("Could not render that diagram") == _MAX_GRAPH_FENCES + 1
    assert "```graph" not in out_graph


def test_beyond_cap_schema_valid_geometry_and_graph_are_stripped() -> None:
    from app.modules.math.fence import _MAX_GEOMETRY_FENCES, _MAX_GRAPH_FENCES

    geo = '```geometry\n{"type":"rectangle","width":8,"height":5,"area":99}\n```'
    out_geo = validate_math_fences("\n".join([geo] * (_MAX_GEOMETRY_FENCES + 1)))
    assert out_geo.count("Could not render that diagram") == _MAX_GEOMETRY_FENCES + 1
    assert "```geometry" not in out_geo
    assert '"area":99' not in out_geo

    graph = '```graph\n{"type":"function","expr":"x**2","points":[[0,0],[1,1]]}\n```'
    out_graph = validate_math_fences("\n".join([graph] * (_MAX_GRAPH_FENCES + 1)))
    assert out_graph.count("Could not render that diagram") == _MAX_GRAPH_FENCES + 1
    assert "```graph" not in out_graph
    assert '"expr":"x**2"' not in out_graph.replace(" ", "")


def test_converts_function_call_graph_text_to_fence() -> None:
    """A weak model emitted a tool call as TEXT. Strip it — do not sample
    the model's expr into a verified-looking curve."""
    content = (
        "Let me retry plotting x = 2y for you.\n\n"
        '!function_call:{"id": "call_DDKdZyJUmQWPSJVPyQNm7OyN", '
        '"call": "graph", "arguments": {"expr": "y=x/2", "variable": "x", '
        '"title": "Graph of x = 2y", "x_min": -10.0, "x_max": 10.0, '
        '"y_min": -5.0, "y_max": 5.0}}'
    )

    out = validate_math_fences(content)

    assert "!function_call" not in out
    assert "```graph" not in out


def test_function_call_graph_text_still_appends_canonical() -> None:
    points = [[float(i) / 5, (float(i) / 5) / 2] for i in range(-50, 51)]
    canonical = {
        "type": "function",
        "expr": "x/2",
        "variable": "x",
        "x_min": -10.0,
        "x_max": 10.0,
        "points": points,
    }
    content = (
        "Let me retry plotting x = 2y for you.\n\n"
        '!function_call:{"call": "graph", "arguments": {"expr": "y=x/2"}}'
    )
    out = validate_math_fences(content, verified=_verified(canonical))
    assert "!function_call" not in out
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["expr"] == "x/2"
    assert data["points"] == points


def test_strips_non_graph_function_call_text() -> None:
    """A non-graph !function_call blob must be stripped, not shown as raw text."""
    content = '!function_call:{"call": "web_search", "arguments": {"query": "weather"}}'
    out = validate_math_fences(content)
    assert "!function_call" not in out
    assert "web_search" not in out


def test_appends_canonical_answer_when_model_omits_fence() -> None:
    verified = _verified({"type": "answer", "content": "x = 2"})
    out = validate_math_fences("The solution follows from the steps above.", verified=verified)
    assert "```answer\nverified: true\nx = 2\n```" in out


def test_appends_answer_even_when_prose_already_has_math_result() -> None:
    verified = _verified({"type": "answer", "content": "x = 2"})
    out = validate_math_fences("The solution is $x = 2$.", verified=verified)
    assert out.count("```answer") == 1
    assert "**Answer**\n\n```answer\nverified: true\nx = 2\n```" in out


def test_appends_canonical_geometry_when_model_omits_fence() -> None:
    spec = {"type": "rectangle", "width": 8, "height": 5}
    out = validate_math_fences("Here is a rectangle.", verified=_verified(spec))
    assert "```geometry" in out
    assert '"type":"rectangle"' in out.replace(" ", "")
    assert "```geometry\n" not in "Here is a rectangle."


def test_appends_canonical_graph_when_model_omits_fence() -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    out = validate_math_fences("Here is the parabola.", verified=_verified(spec))
    assert "```graph" in out
    fence = out.split("```graph")[1].split("```")[0].strip()
    data = json.loads(fence)
    assert data["type"] == "function"
    assert data["expr"] == "x**2"


def test_strips_model_chart_when_verified_graph_exists() -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    content = (
        "Here is the parabola.\n"
        "```chart\n"
        '{"mark":"line","encoding":{"x":{"field":"x"},"y":{"field":"y"}}}\n'
        "```\n"
    )
    out = validate_math_fences(content, verified=_verified(spec))
    assert "```chart" not in out
    assert "```graph" in out
    assert json.loads(out.split("```graph")[1].split("```")[0].strip())["expr"] == "x**2"


@pytest.mark.parametrize("lang", ["vega", "vega-lite", "plot"])
def test_strips_chart_aliases_when_verified_graph_exists(lang: str) -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    content = f'Here is the parabola.\n```{lang}\n{{"mark":"line"}}\n```\n'
    out = validate_math_fences(content, verified=_verified(spec))
    assert f"```{lang}" not in out
    assert "```graph" in out


def test_strips_sample_point_table_when_verified_graph_exists() -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    content = (
        "Here's the parabola.\n\n"
        "### Sample Points\n"
        "| $x$ | $y = x^2$ |\n"
        "|-----|-----------|\n"
        "| -1  | 1         |\n"
        "| 1   | 1         |\n\n"
        "The vertex is the origin."
    )
    out = validate_math_fences(content, verified=_verified(spec))
    assert "| $x$" not in out
    assert "| 1" not in out
    assert "Sample Points" not in out
    assert "vertex is the origin" in out
    assert "```graph" in out


def test_strips_ascii_sketch_when_verified_graph_exists() -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    content = (
        "Parabola through the origin.\n\n"
        "### How to Sketch\n"
        "1. Plot the vertex.\n"
        "> ASCII approximation:\n"
        "> ```\n"
        ">   ^ y\n"
        "> ---+----> x\n"
        "> ```\n"
    )
    out = validate_math_fences(content, verified=_verified(spec))
    assert "How to Sketch" not in out
    assert "ASCII" not in out
    assert "Parabola through the origin." in out
    assert "```graph" in out


def test_strips_mermaid_when_verified_graph_exists() -> None:
    spec = {
        "type": "function",
        "expr": "x**2",
        "variable": "x",
        "x_min": -2,
        "x_max": 2,
        "points": [[-2, 4], [0, 0], [2, 4]],
    }
    content = (
        "Here's the parabola.\n\n"
        "### Mermaid Diagram (approximation):\n"
        "```mermaid\n"
        "graph LR\n"
        '    A["(-3,9)"] --> B["(0,0)"]\n'
        "```\n"
    )
    out = validate_math_fences(content, verified=_verified(spec))
    assert "```mermaid" not in out
    assert "Mermaid Diagram" not in out
    assert "```graph" in out


def test_appends_answer_and_graph_for_physics() -> None:
    from app.modules.math.tools import VerifiedMathBlock

    spec = {
        "type": "trajectory",
        "expr": "h(t)",
        "points": [[0, 20], [1, 15]],
    }
    verified = VerifiedMathBlock(
        text="unused",
        canonical_fence=spec,
        canonical_answer="2.02 s",
    )
    out = validate_math_fences("The ball lands at $t = 2.02$ s.", verified=verified)
    assert "```answer\nverified: true\n2.02 s\n```" in out
    assert out.index("```answer") < out.index("```graph")
    assert json.loads(out.split("```graph")[1].split("```")[0].strip())["type"] == "trajectory"


def test_appends_answer_when_prose_omits_verified_value() -> None:
    verified = _verified({"type": "answer", "content": "x = 12"})
    out = validate_math_fences("Worked steps follow.", verified=verified)
    assert "```answer\nverified: true\nx = 12\n```" in out


def test_a_different_x_equals_in_prose_keeps_the_pill_and_is_flagged() -> None:
    """The prose's ``x = 2`` against a verified ``x = 0`` used to hide the pill.

    That guard dated from a solver misread (``2x+3=3`` for ``2x+3=7``); it also
    let every wrong model value stand unchallenged. The verified pill now always
    shows, with one correction line, and misreads are fixed in the extractor.
    """
    verified = _verified({"type": "answer", "content": "x = 0"})
    out = validate_math_fences(
        "The correct equation is $2x + 3 = 7$.\n\n**Solution:** $x = 2$",
        verified=verified,
    )
    assert "x = 2" in out
    assert (
        "The verified answer is $x = 0$.\n\n**Answer**\n\n```answer\nverified: true\nx = 0\n```"
        in out
    )


def test_intermediate_2x_equals_does_not_count_as_conflicting_x() -> None:
    verified = _verified({"type": "answer", "content": "x = 2"})
    out = validate_math_fences("First $2x = 4$. Then divide.", verified=verified)
    assert "```answer\nverified: true\nx = 2\n```" in out


def test_draw_geometry_without_canonical_answer_does_not_append_pill() -> None:
    from app.modules.math.tools import VerifiedMathBlock

    verified = VerifiedMathBlock(
        text="unused",
        canonical_fence={
            "type": "right_triangle",
            "base": 3,
            "height": 4,
            "show_hypotenuse": True,
        },
        canonical_answer=None,
    )
    out = validate_math_fences("Here's the right triangle.", verified=verified)
    assert "```answer" not in out
    assert "```geometry" in out


def test_short_integer_in_exponent_does_not_suppress_answer_pill() -> None:
    verified = _verified({"type": "answer", "content": "2"})
    out = validate_math_fences("Consider $x^2$ for this problem.", verified=verified)
    assert "```answer\nverified: true\n2\n```" in out


def test_one_line_arithmetic_gets_one_card() -> None:
    verified = _verified({"type": "answer", "content": "3"})
    out = validate_math_fences("$3 + 0 = 3$", verified=verified)
    assert out.count("```answer") == 1


def test_symbolic_mismatch_still_appends_canonical_chip() -> None:
    """The model's prose answer is wrong — the verified chip must win."""
    verified = _verified({"type": "answer", "content": "x = \\frac{7}{2}"})
    out = validate_math_fences("The steps give $x = 4$.", verified=verified)
    assert "```answer\nverified: true\nx = \\frac{7}{2}\n```" in out


def test_symbolic_audit_failure_falls_back_to_append() -> None:
    """Unparseable canonical (multi-branch answer) → today's behavior unchanged."""
    verified = _verified(
        {
            "type": "answer",
            "content": "x = 2 \\pi k + \\frac{\\pi}{6} \\text{ or } x = 2 \\pi k + \\frac{5 \\pi}{6}",
        }
    )
    out = validate_math_fences("The solutions are periodic.", verified=verified)
    assert "```answer" in out


def test_does_not_duplicate_existing_answer_fence() -> None:
    verified = _verified({"type": "answer", "content": "x = 2"})
    content = "Worked steps…\n```answer\nx = 99\n```"
    out = validate_math_fences(content, verified=verified)
    assert out.count("```answer") == 1
    assert "```answer\nverified: true\nx = 2\n```" in out
    assert "x = 99" not in out


def test_needs_math_fence_validate_skips_plain_replies() -> None:
    from app.modules.math.fence import needs_math_fence_validate

    assert needs_math_fence_validate("hi there", None) is False
    assert needs_math_fence_validate("```answer\nx = 1\n```", None) is True
    from app.services.solving import VerifiedMathBlock

    verified = VerifiedMathBlock(text="x = 1", canonical_answer="1")
    assert needs_math_fence_validate("plain", verified) is True


# --- P12: a verified answer attached to a clarifying question ----------------
#
# From the same screenshot as P11. Asked a 2D collision, the model did the right
# thing and asked which ball deflects — and the pipeline pinned a verified
# `0.79 m` and a full trajectory chart with a Play button underneath the
# question. Nothing here could tell "the model forgot the fence" apart from "the
# model has no answer to fence", so it assumed the first.
#
# P11 fixes the collision that produced this one. P12 is the general case: the
# next under-specified physics question would otherwise do exactly the same.

_TRAJECTORY = {
    "type": "trajectory",
    "expr": "h(t)",
    "points": [[0, 0], [1, 15], [2, 20]],
}


def _projectile_block():
    from app.modules.math.tools import VerifiedMathBlock

    return VerifiedMathBlock(
        text="unused",
        canonical_fence=_TRAJECTORY,
        canonical_answer="35.31 m",
    )


# The reply from the incident, verbatim. A paraphrase would have hidden the
# point: its question is the *opening* line and its closing line is a plain
# statement, so "the reply ends with a question" — the obvious rule, and the one
# first written down for this — misses the very case it was written for.
_INCIDENT_REPLY = (
    "Which ball's final path is at **30°** — the **2 kg ball** or the **1 kg ball**?"
    "\n\nFor a 2D elastic collision, that angle is needed to determine the final velocities."
)


def test_a_clarifying_question_gets_no_answer_pill_or_chart() -> None:
    out = validate_math_fences(_INCIDENT_REPLY, verified=_projectile_block())

    assert "```answer" not in out
    assert "```graph" not in out
    assert out.strip() == _INCIDENT_REPLY.strip()


def test_a_question_on_the_last_line_is_caught_too() -> None:
    """The other shape of the same reply, since position decides nothing."""
    out = validate_math_fences(
        "I need one more detail before I can work this out.\n\n"
        "Is the collision elastic or inelastic?",
        verified=_projectile_block(),
    )

    assert "```answer" not in out
    assert "```graph" not in out


def test_answered_then_asked_keeps_its_chart() -> None:
    """The case that makes a bare question-mark test wrong.

    Offering a follow-up is normal and good. This reply ends in a question and
    has answered, so it keeps everything a plain answer would get.
    """
    out = validate_math_fences(
        "The range is about 35.31 m. Would you like the maximum height too?",
        verified=_projectile_block(),
    )

    assert "```graph" in out
    assert "```answer" in out


def test_a_reply_that_states_no_answer_and_asks_nothing_still_gets_both() -> None:
    """The guard must not swallow the case it sits in front of.

    "Worked steps follow" with no result is exactly what appending fences is
    for, and it stays that way.
    """
    out = validate_math_fences(
        "Let me set that up using the range equation.", verified=_projectile_block()
    )

    assert "```answer\nverified: true\n35.31 m\n```" in out
    assert "```graph" in out


def test_a_clarifying_question_gets_no_diagram_either() -> None:
    """All three extras, not just the pill — a diagram is as wrong as a chart."""
    from app.modules.math.tools import VerifiedMathBlock

    verified = VerifiedMathBlock(
        text="unused",
        canonical_fence={"type": "right_triangle", "base": 3, "height": 4},
        canonical_answer="5 cm",
    )
    out = validate_math_fences("Which side is the hypotenuse here?", verified=verified)

    assert "```answer" not in out
    assert "```geometry" not in out


def test_a_solver_with_no_answer_still_illustrates_its_question() -> None:
    """The case that nearly made this guard a regression.

    Angles alone fix a triangle's shape but not its size, so the solver returns
    a diagram and no number, and the reply asks for a side length. A first draft
    read that as "asks and states no answer" and took the diagram away — which
    the existing underdetermined-triangle tests caught. A verified answer has to
    exist before withholding one means anything.
    """
    from app.modules.math.tools import VerifiedMathBlock

    verified = VerifiedMathBlock(
        text="unused",
        canonical_fence={"type": "triangle", "base": 3, "height": 4},
        canonical_answer=None,
    )
    out = validate_math_fences(
        "The area cannot be determined from angles alone. What is one side length?",
        verified=verified,
    )

    assert "```geometry" in out


def test_question_marks_inside_emphasis_still_count() -> None:
    """Models bold the ask: `**Which ball deflects?**` ends in `*`, not `?`."""
    out = validate_math_fences(
        "**Which ball's final path is at 30°?**", verified=_projectile_block()
    )

    assert "```answer" not in out
    assert "```graph" not in out
