"""Whole-request guards for direct graph, plotted-point and number-line replies.

A plot skips the model only when the entire request is the expression the
verified sampler drew; any extra clause keeps the language path.
"""

from __future__ import annotations

from app.modules.math.match.literal_plot import literal_number, literal_pair, plot_command_object
from app.modules.math.tools.direct_fences import MAX_DIRECT_ANSWER_CHARS, solver_fences
from app.services.solving import VerifiedMathBlock

_GRAPH_INTERACTION_WORDS = frozenset(
    {
        "a",
        "able",
        "an",
        "and",
        "around",
        "can",
        "controls",
        "down",
        "drag",
        "draggable",
        "explorable",
        "explore",
        "graph",
        "i",
        "in",
        "interactive",
        "interactively",
        "it",
        "left",
        "let",
        "make",
        "me",
        "move",
        "movable",
        "out",
        "pan",
        "pannable",
        "pinch",
        "pinchable",
        "plot",
        "right",
        "that",
        "the",
        "to",
        "up",
        "with",
        "zoom",
        "zoomable",
    }
)
_GRAPH_INTERACTION_ACTIONS = frozenset(
    {
        "drag",
        "draggable",
        "explorable",
        "explore",
        "interactive",
        "interactively",
        "move",
        "movable",
        "pan",
        "pannable",
        "pinch",
        "pinchable",
        "zoom",
        "zoomable",
    }
)
_GRAPH_INTERACTION_AFFORDANCES = frozenset(
    {
        "controls",
        "draggable",
        "explorable",
        "interactive",
        "interactively",
        "movable",
        "pannable",
        "pinch",
        "pinchable",
        "zoomable",
    }
)


def _requests_graph_interaction(words: list[str]) -> bool:
    word_set = set(words)
    has_action = bool(word_set & _GRAPH_INTERACTION_ACTIONS)
    has_user_agency = (
        {"let", "me"} <= word_set or {"can", "i"} <= word_set or {"able", "to"} <= word_set
    )
    return has_action and bool(word_set & _GRAPH_INTERACTION_AFFORDANCES or has_user_agency)


def _strip_graph_interaction_tail(request: str) -> str:
    """Remove a presentation-only graph-control clause.

    This is deliberately a small word grammar rather than one exact phrase:
    ``make it interactive``, ``let me explore it`` and ``with pinch and pan``
    are equivalent UI requests. Any number, operator, explanation word or
    second calculation keeps the normal model path.
    """
    clean = request.rstrip(".?").strip()
    lower = clean.lower()
    starts: list[int] = []
    for marker in (" and ", " with ", " as ", " so ", " that "):
        offset = 0
        while True:
            index = lower.find(marker, offset)
            if index < 0:
                break
            starts.append(index)
            offset = index + len(marker)
    for index in sorted(set(starts)):
        tail = lower[index + 1 :].replace("-", " ")
        if any(not (char.isascii() and (char.isalpha() or char.isspace())) for char in tail):
            continue
        words = tail.split()
        if words and set(words) <= _GRAPH_INTERACTION_WORDS and _requests_graph_interaction(words):
            return clean[:index].rstrip()
    return clean


def can_direct_point_or_vertical(verified: VerifiedMathBlock, user_text: str) -> bool:
    """Match a complete literal plot request, never a coordinate substring."""
    if len(user_text) > 1000:
        return False
    fences = solver_fences(verified)
    if len(fences) != 1:
        return False
    graph = fences[0]
    if graph.get("expr2") or graph.get("points2") or graph.get("variable", "x") != "x":
        return False
    if graph.get("type") == "vertical":
        return _literal_vertical(verified, graph, user_text)
    return graph.get("type") == "function" and _literal_point(verified, graph, user_text)


def _literal_point(verified: VerifiedMathBlock, graph: dict[str, object], user_text: str) -> bool:
    """The point extraction read from this very request, drawn and answered as is."""
    point, origin = verified.plot_point, verified.direct_request_text
    if point is None or origin is None or " ".join(origin.split()) != " ".join(user_text.split()):
        return False
    points = graph.get("points")
    if not isinstance(points, list) or len(points) != 1:
        return False
    drawn = points[0]
    if not isinstance(drawn, list) or len(drawn) != 2:
        return False
    # All three canonical representations must describe the requested point.
    return (
        (literal_number(drawn[0]), literal_number(drawn[1])) == point
        and literal_pair(str(graph.get("expr") or "")) == point
        and literal_pair(verified.canonical_answer or "") == point
    )


def _literal_vertical(
    verified: VerifiedMathBlock, graph: dict[str, object], user_text: str
) -> bool:
    """``plot x=4``: the request's x is the line's, and nothing else was asked."""
    request = plot_command_object(user_text)
    if request is None or verified.canonical_answer:
        return False
    for prefix in ("vertical line ", "line "):
        if request.lower().startswith(prefix):
            request = request[len(prefix) :]
            break
    lhs, separator, rhs = request.partition("=")
    x = literal_number(graph.get("x"))
    expr_lhs, expr_separator, expr_rhs = str(graph.get("expr") or "").partition("=")
    low, high = literal_number(graph.get("y_min")), literal_number(graph.get("y_max"))
    return bool(
        separator
        and lhs.strip().lower() == "x"
        and x is not None
        and literal_number(rhs.strip()) == x
        and expr_separator
        and expr_lhs.strip().lower() == "x"
        and literal_number(expr_rhs.strip()) == x
        and low is not None
        and high is not None
        and low < high
    )


def can_direct_graph(verified: VerifiedMathBlock, user_text: str) -> bool:
    """Match the whole plot request, not an expression extracted from one clause."""
    from app.modules.math.match import graph_domain, prepare
    from app.modules.math.match.graph import _GRAPH_PAIR_TRAILING_FILLER

    if len(user_text) > 1000 or verified.canonical_answer:
        return False
    fences = solver_fences(verified)
    if len(fences) != 1 or fences[0].get("type") not in {"function", "inequality"}:
        return False
    graph = fences[0]
    points, expr = graph.get("points"), graph.get("expr")
    expr2, points2 = graph.get("expr2"), graph.get("points2")
    paired = bool(expr2 or points2)
    if not isinstance(expr, str) or not expr.strip() or graph.get("variable", "x") != "x":
        return False
    if graph.get("type") == "function" and (not isinstance(points, list) or len(points) < 2):
        return False
    if paired and (
        graph.get("type") != "function"
        or not isinstance(expr2, str)
        or not expr2.strip()
        or not isinstance(points2, list)
        or len(points2) < 2
        or graph.get("variable2") != "x"
    ):
        return False
    request = prepare(user_text)
    if not request:
        return False
    from app.modules.math.tools.extract import is_graph_followup

    # Follow-ups ("Plot", "graph it") reuse the verified samples from a prior
    # message; the current line has no f(x) to string-match. A bare "Plot" has
    # no "plot " prefix, and fell to the model, which wrote out its reasoning.
    if is_graph_followup(user_text):
        return True
    if request.lower().startswith("please "):
        request = request[7:].lstrip()
    for prefix in ("graph ", "plot ", "draw ", "sketch ", "visualize ", "visualise "):
        if request.lower().startswith(prefix):
            # Keep !: it may be a factorial that extraction did not preserve.
            request = request[len(prefix) :].strip().rstrip(".?")
            break
    else:
        return False
    request = _strip_graph_interaction_tail(request)
    domain = graph_domain(request)
    if domain is not None:
        lo, hi, request = domain
        # A range ignored by extraction or narrowed by sampling needs language.
        if graph.get("x_min") != lo or graph.get("x_max") != hi:
            return False
    if paired:
        for suffix in _GRAPH_PAIR_TRAILING_FILLER:
            if request.lower().endswith(suffix):
                request = request[: -len(suffix)].rstrip()
                break
        split_at = request.lower().find(" and ")
        if split_at < 0:
            return False
        clauses = (request[:split_at].strip(), request[split_at + 5 :].strip())
        for clause, sampled_expr in zip(clauses, (expr, expr2), strict=True):
            if "=" in clause:
                lhs, _, clause = clause.partition("=")
                if lhs.strip().lower() != "y":
                    return False
            # Reuse the exact sampled expressions, preserving any extra
            # request, third curve, factorial, or ignored domain as a mismatch.
            if clause.replace(" ", "").replace("^", "**") != str(sampled_expr).replace(
                " ", ""
            ).replace("^", "**"):
                return False
        return True
    if (
        graph.get("type") == "function"
        and "=" in expr
        and request.replace(" ", "").replace("^", "**") == expr.replace(" ", "").replace("^", "**")
    ):
        # The verified circle/ellipse sampler preserves the whole relation
        # and closes its parametric loop; it is not a y=f(x) expression.
        return isinstance(points, list) and len(points) >= 3 and points[0] == points[-1]
    if graph.get("type") == "function" and "=" in request:
        original = request
        lhs, _, rhs = request.partition("=")
        if lhs.strip().lower() == "y":
            request = rhs
        elif "y" not in original.lower():
            rhs_c = rhs.replace(" ", "").replace("^", "**")
            lhs_c = lhs.replace(" ", "").replace("^", "**")
            if rhs_c in {"0", "0.0"}:
                request = lhs
            elif lhs_c in {"0", "0.0"}:
                request = rhs
            else:
                return False
        else:
            return False
    # The verified sampler preserves its input expr. Requiring the entire
    # remaining request to match it keeps "and solve/explain/tell me..." and
    # additional formulas on the model path, without another SymPy parse.
    return request.replace(" ", "").replace("^", "**") == expr.replace(" ", "").replace("^", "**")


def can_direct_number_line(
    verified: VerifiedMathBlock, user_text: str, *, require_solve: bool = True
) -> bool:
    """A whole inequality solve can display its answer and solution set directly.

    ``require_solve=False`` is for a lesson request whose teaching words were
    already stripped ("show steps for 2x+3<7" leaves the bare inequality).
    """
    from app.modules.math.match import prepare
    from app.modules.math.solve.latex_normalize import _rewrite_bare_abs_bars

    answer = (verified.canonical_answer or "").strip()
    fences = solver_fences(verified)
    if (
        len(user_text) > 1000
        or not answer
        or len(answer) > MAX_DIRECT_ANSWER_CHARS
        or len(fences) != 1
        or fences[0].get("type") != "number_line"
    ):
        return False
    expr = fences[0].get("expr")
    request = prepare(user_text)
    if not isinstance(expr, str) or not expr.strip() or not request:
        return False
    if request.lower().startswith("please "):
        request = request[7:].lstrip()
    if request.lower().startswith("solve "):
        request = request[6:].strip()
    elif require_solve:
        return False
    if request.lower().startswith("the inequality "):
        request = request[15:].lstrip()
    from app.modules.math.tools.extractors.algebra import _strip_number_line_presentation

    request = _strip_number_line_presentation(request)
    # Keep factorials and all remaining prose/domain clauses intact. Only
    # spelling-equivalent operators and whitespace can differ from the exact
    # inequality the solver used; no new symbolic parsing or prose whitelist.
    request = request.rstrip(".?")

    def compact(value: str) -> str:
        return (
            _rewrite_bare_abs_bars(value)
            .replace(" ", "")
            .replace("^", "**")
            .replace("≤", "<=")
            .replace("≥", ">=")
            .replace("\u2212", "-")
        )

    return compact(request) == compact(expr.rstrip(".?"))
