"""Plot follow-ups: "graph it" draws the curve an earlier message named or was.

``resolve_graph_followup`` rewrites "plot it" from the prior user messages; the
public surface stays ``app.modules.math.tools.extract``.
"""

from __future__ import annotations

import re

from app.modules.math.solve.declines import sympy_decline

_GRAPH_FOLLOWUP_VERBS = ("graph", "plot", "sketch", "draw", "visualize", "visualise", "chart")
_GRAPH_FOLLOWUP_OBJECTS = frozenset(
    {
        "",
        "it",
        "this",
        "that",
        "the equation",
        "the function",
        "the curve",
        "the parabola",
        "the quadratic",
        "the polynomial",
        "this equation",
        "that equation",
        "this function",
        "that function",
    }
)
_POLITE_PREFIXES = ("please ", "can you ", "could you ")


def _strip_polite_wrappers(lower: str) -> str:
    s = lower
    changed = True
    while changed:
        changed = False
        if s.startswith("please "):
            s = s[7:].strip()
            changed = True
        if s.endswith(" please"):
            s = s[:-7].strip()
            changed = True
        for prefix in _POLITE_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix) :].strip()
                changed = True
                break
    return s


def is_graph_followup(text: str) -> bool:
    """True for ``graph it`` / ``plot this equation`` with no new formula."""
    from app.modules.math.match.scan import prepare

    cleaned = prepare(text)
    if not cleaned:
        return False
    lower = _strip_polite_wrappers(cleaned.lower().rstrip(".!?"))
    rest: str | None = None
    for verb in _GRAPH_FOLLOWUP_VERBS:
        if lower == verb:
            rest = ""
            break
        prefix = f"{verb} "
        if lower.startswith(prefix):
            rest = lower[len(prefix) :].strip()
            break
    if rest is None:
        return False
    return rest in _GRAPH_FOLLOWUP_OBJECTS


def _is_plottable_expr(expr: str) -> bool:
    compact = expr.replace(" ", "")
    if not compact:
        return False
    lower = compact.lower()
    if lower in {"it", "this", "that"}:
        return False
    from app.modules.math.match.letter_runs import has_unknown_english_run

    if has_unknown_english_run(compact):
        return False
    return any(ch.isdigit() for ch in compact) or "x" in lower


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Written maths, not data: "$x^{2}+y^{2}$", "y = 3".
_FORMULA_MARK = re.compile(r"[\^\\=]|\$[^$]*[a-z][^$]*\$", re.IGNORECASE)


def _holds_data(text: str) -> bool:
    """Two or more numbers in plain words ("math 85, physics 78"), not a formula or one
    number ("$2$", "I have 2 apples")."""
    return len(_NUMBER.findall(text)) >= 2 and _FORMULA_MARK.search(text) is None


# ``y = 3x + 2`` or ``f(x) = x^2`` inside a sentence, one per clause.
_CLAUSE_SPLIT = re.compile(r"\s+(?:and|or|vs\.?|versus)\s+|[,;?]", re.IGNORECASE)
_NAMED_FUNCTION = re.compile(r"\b(?:y|f\(x\))\s*=\s*(.+)$")
# ``x + y = 5`` is not ``y = 5``: a term before ``y`` makes it one side of an equation.
_TERM_END = frozenset("+-*/^=).0123456789")


def _function_of_x(expr: str) -> bool:
    from app.modules.math.solve.parse import parse_expression

    if not _is_plottable_expr(expr):
        return False
    with sympy_decline() as declined:
        parsed = parse_expression(expr.replace("^", "**"), ["x"])
    return not declined and {str(symbol) for symbol in parsed.free_symbols} <= {"x"}


def _named_functions(text: str) -> list[str]:
    """The curves a sentence names: ``slope of y = 3x + 2 and y = 2x + 3``."""
    found: list[str] = []
    for clause in _CLAUSE_SPLIT.split(text):
        match = _NAMED_FUNCTION.search(clause)
        if match is None:
            continue
        before = clause[: match.start()].rstrip()
        if before and before[-1] in _TERM_END:
            continue
        expr = match.group(1).strip().rstrip(".")
        if expr and _function_of_x(expr) and expr not in found:
            found.append(expr)
    return found


def _bare_function_of_x(text: str) -> str | None:
    """A message that is only an expression in x (``$x^{2}$``, ``sin(x)``): the curve to graph."""
    from app.modules.math.match.scan import prepare
    from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy

    cleaned = prepare(text)
    if not cleaned:
        return None
    expr = normalize_latex_to_sympy(cleaned).strip()
    return expr if "x" in expr.lower() and _function_of_x(expr) else None


def _plottable_graph_source(text: str) -> str | None:
    from app.modules.math.tools.extract import extract_math_intent

    intent = extract_math_intent(text)
    if intent is None:
        # "what is the slope of y = 3x + 2 and y = 2x + 3" is not solved (the
        # lines' crossing point is not their slope), but "graph it" still
        # draws the lines it names.
        named = _named_functions(text)
        if 1 <= len(named) <= 2:
            return " and ".join(named)
        # A bare `x^2` asks nothing, so "plot it" next is the question.
        return _bare_function_of_x(text)
    if intent.kind == "graph" and intent.expr and _is_plottable_expr(intent.expr):
        return intent.expr
    if intent.kind == "graph_pair" and intent.expr and intent.expr2:
        if _is_plottable_expr(intent.expr) and _is_plottable_expr(intent.expr2):
            return f"{intent.expr} and {intent.expr2}"
    if intent.kind == "vertical" and intent.point_x is not None:
        return f"x={intent.point_x:g}"
    if intent.kind == "equation" and intent.lhs and intent.rhs:
        if _is_plottable_expr(intent.lhs) or _is_plottable_expr(intent.rhs):
            return f"{intent.lhs}={intent.rhs}"
    if intent.kind not in {"calculus", "system"}:
        return None
    # A derivative or a slope question about named lines: graph those lines.
    named = _named_functions(text)
    if 1 <= len(named) <= 2:
        return " and ".join(named)
    equations = intent.system_equations or []
    if intent.kind == "system" and len(equations) == 2:
        from app.modules.math.tools.extractors.graph import _solve_for_y_as_function_of_x

        lines = [_solve_for_y_as_function_of_x(f"{lhs}={rhs}") for lhs, rhs in equations]
        if all(lines):
            return " and ".join(line for line in lines if line)
    if intent.kind == "calculus" and intent.expr and _function_of_x(intent.expr):
        return intent.expr
    return None


def resolve_graph_followup(text: str, prior_user_messages: list[str] | None) -> tuple[str, bool]:
    """Rewrite ``graph it`` from a prior equation.

    Returns ``(content, skip_math)``. ``skip_math`` is True only when this
    *is* a pronoun follow-up with no plottable prior — caller must not stamp
    *Couldn't verify* (``graph_expr("it")`` looks like math and used to).
    """
    if not is_graph_followup(text):
        return text, False
    for prior in reversed(prior_user_messages or []):
        src = _plottable_graph_source(prior)
        if src:
            return f"graph {src}", False
    # Data and no function ("Here are my exam marks: math 85, physics 78", then "graph it")
    # asks for a chart of it, which the chart contract draws; asking for a function to
    # graph was the reply (2026-10-24).
    if any(_holds_data(prior) for prior in prior_user_messages or []):
        return text, False
    return text, True
