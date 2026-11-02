"""Graph intent extractors: points, vertical lines, curves, pairs, polar and parametric."""

from __future__ import annotations

import re

from app.modules.math.match.letter_runs import MATH_MULTI_LETTER
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.tools.expr_rewrite import math_expr_or_none
from app.modules.math.tools.request_text import strip_trailing_filler


def _extract_point_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    point = mtm.bare_coord(cleaned) or mtm.plot_point(cleaned)
    if point is None:
        return None
    return MathIntent(
        kind="point",
        point_x=point[0],
        point_y=point[1],
        operation="graph",
    )


def _extract_vertical_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    vert_x = mtm.vertical_line_x(cleaned)
    if vert_x is None:
        return None
    return MathIntent(kind="vertical", point_x=vert_x, operation="graph")


def _rhs_after_letter_eq(text: str, letter: str) -> str | None:
    """RHS of a standalone ``letter = …``, stopping at ``,`` / `` and ``."""
    lower = text.lower()
    n = len(lower)
    i = 0
    while i < n:
        if lower[i] == letter and (i == 0 or not lower[i - 1].isalnum()):
            j = i + 1
            while j < n and lower[j].isspace():
                j += 1
            if j < n and lower[j] == "=":
                k = j + 1
                while k < n and lower[k].isspace():
                    k += 1
                end = k
                while end < n:
                    if lower.startswith(",", end) or lower.startswith(" and ", end):
                        break
                    end += 1
                rhs = text[k:end].strip().rstrip(" .?!")
                return rhs or None
        i += 1
    return None


def _is_bare_number(text: str) -> bool:
    try:
        float(text.strip())
    except ValueError:
        return False
    return True


def _extract_polar_or_parametric_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    compact = lower.replace(" ", "")
    has_plot = any(
        word in lower for word in ("graph", "plot", "sketch", "draw", "polar", "parametric")
    )
    if not has_plot:
        return None
    if "r=" in compact and ("polar" in lower or "theta" in lower or "θ" in cleaned):
        rhs = _rhs_after_letter_eq(cleaned, "r")
        if rhs is not None:
            rhs = rhs.replace("θ", "theta")
            guarded = math_expr_or_none(rhs.replace("^", "**"))
            if guarded is not None:
                var = "theta" if "theta" in guarded.lower() else "t"
                return MathIntent(
                    kind="graph",
                    school_op="polar",
                    expr=guarded.replace("^", "**"),
                    variable=var,
                    operation="graph",
                )
    x_rhs = _rhs_after_letter_eq(cleaned, "x")
    y_rhs = _rhs_after_letter_eq(cleaned, "y")
    if x_rhs is None or y_rhs is None:
        return None
    if _is_bare_number(x_rhs) and _is_bare_number(y_rhs):
        return None
    if "parametric" not in lower and "t" not in f"{x_rhs} {y_rhs}".lower():
        return None
    gx = math_expr_or_none(x_rhs.replace("^", "**"))
    gy = math_expr_or_none(y_rhs.replace("^", "**"))
    if gx is None or gy is None:
        return None
    return MathIntent(
        kind="graph",
        school_op="parametric",
        expr=gx.replace("^", "**"),
        expr2=gy.replace("^", "**"),
        variable="t",
        operation="graph",
    )


def _extract_graph_pair_intent(cleaned: str) -> MathIntent | None:
    """Checked BEFORE the single-expression graph extractor below — "graph
    y=x^2 and y=2x" must not fall into graph_expr's single-capture, which
    would grab "x^2 and y=2x" as one unparseable expr and silently produce
    no augmentation for a very ordinary "compare these two functions" ask."""
    from app.modules.math import match as mtm

    pair = mtm.graph_expr_pair(cleaned)
    if pair is None:
        return None
    first, second = pair
    # A trailing domain ("graph y=x^2 and y=2x from 0 to 100") lands on the
    # second expression after the " and " split. Peel it off and apply the
    # window to both curves so they share one x-range for comparison.
    domain = mtm.graph_domain(second)
    x_min: float | None = None
    x_max: float | None = None
    if domain is not None:
        x_min, x_max, second = domain
    expr1 = strip_trailing_filler(first).replace("^", "**")
    expr2 = strip_trailing_filler(second).replace("^", "**")
    if not expr1 or not expr2:
        return None
    return MathIntent(
        kind="graph_pair",
        expr=expr1,
        expr2=expr2,
        operation="graph",
        graph_x_min=x_min,
        graph_x_max=x_max,
    )


def _has_non_math_word(side: str) -> bool:
    """True when a 3+ letter run is English, not a known SymPy name."""
    i = 0
    n = len(side)
    while i < n:
        if side[i].isalpha():
            j = i + 1
            while j < n and side[j].isalpha():
                j += 1
            run = side[i:j]
            if len(run) >= 3 and run.lower() not in MATH_MULTI_LETTER:
                return True
            i = j
        else:
            i += 1
    return False


def _solve_for_y_as_function_of_x(expr: str) -> str | None:
    """Turn an equation like ``x=2y`` into the function ``x/2`` (y = f(x)).

    Returns the RHS as a SymPy-text string in terms of x, or None when the
    equation can't be isolated to a single y = f(x) (e.g. no y, multiple
    solutions, or y is not the dependent variable). ``y=x^2`` stays a plain
    expression already; this only rewires equations that contain ``=``.
    """
    if "=" not in expr:
        return None
    from sympy import Eq, Symbol, solve
    from sympy.core.relational import Relational

    from app.core.sympy_notation import school_text
    from app.modules.math.solve.parse import parse_expression

    lhs_str, _, rhs_str = expr.partition("=")
    lhs_str, rhs_str = lhs_str.strip(), rhs_str.strip()
    if not lhs_str or not rhs_str:
        return None
    # Only attempt when y is present (the dependent variable we solve for).
    if "y" not in lhs_str and "y" not in rhs_str:
        return None
    # ``Graph y = x^2`` must not parse Graph as G*r*a*p*h and "solve" to
    # x**2/(G*a*h*p*r). English tokens on either side are not an equation
    # to isolate; the graph-expr peeler should have already dropped them.
    if _has_non_math_word(lhs_str) or _has_non_math_word(rhs_str):
        return None
    with sympy_decline() as declined:
        lhs = parse_expression(lhs_str, ["x", "y"], real=True)
        rhs = parse_expression(rhs_str, ["x", "y"], real=True)
    if declined:
        return None
    if isinstance(lhs, Relational) or isinstance(rhs, Relational):
        return None
    y = Symbol("y", real=True)
    with sympy_decline() as declined:
        sols = solve(Eq(lhs, rhs), y, dict=True)
    if declined:
        return None
    if not sols or len(sols) != 1:
        return None
    sol = sols[0]
    value = sol.get(y) if isinstance(sol, dict) else sol
    if value is None:
        return None
    # Must be a function of x only (no free y left).
    text = school_text(value).replace(" ", "")
    if "y" in text:
        return None
    return text or None


def _equation_as_function_of_x(expr: str) -> str | None:
    """Plot ``4x^2-5x-12=0`` as ``y = 4x^2-5x-12`` (lhs - rhs).

    ``sample_function`` rejects Equalities, so a graph cue on a one-variable
    equation used to stamp *Couldn't verify* instead of drawing the parabola.
    Relations that still contain ``y`` (circles, ``x=2y``) stay on the
    ellipse / solve-for-y paths — do not rewrite those as a residual in x.
    """
    if "=" not in expr:
        return None
    lhs_str, _, rhs_str = expr.partition("=")
    lhs_str, rhs_str = lhs_str.strip(), rhs_str.strip()
    if not lhs_str or not rhs_str:
        return None
    if "y" in lhs_str or "y" in rhs_str:
        return None
    if _has_non_math_word(lhs_str) or _has_non_math_word(rhs_str):
        return None
    from sympy.core.relational import Relational

    from app.core.sympy_notation import school_text
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline() as declined:
        lhs = parse_expression(lhs_str, ["x"], real=True)
        rhs = parse_expression(rhs_str, ["x"], real=True)
    if declined:
        return None
    if isinstance(lhs, Relational) or isinstance(rhs, Relational):
        return None
    diff = lhs - rhs
    extra = {str(s) for s in diff.free_symbols} - {"x"}
    if extra:
        return None
    if diff == 0:
        return None
    lhs_compact = lhs_str.replace(" ", "").replace("^", "**")
    rhs_compact = rhs_str.replace(" ", "").replace("^", "**")
    if rhs_compact in {"0", "0.0"}:
        return lhs_str.replace("^", "**").replace(" ", "")
    if lhs_compact in {"0", "0.0"}:
        return rhs_str.replace("^", "**").replace(" ", "")
    text = school_text(diff).replace(" ", "")
    return text or None


def _strip_math_delims_and_fix_superscripts(raw: str) -> str:
    """Normalize a graph expression the composer/math keyboard may wrap in
    inline-math delimiters or malformed superscripts.

    The math keyboard wraps the typed expression in ``$...$``; ``graph_expr``
    returns it verbatim, so without stripping, SymPy's safe-char gate rejects
    ``$``/``{``/``}`` and the turn ships without a verified fence. The
    keyboard also emits a base-less superscript chain for "x²" — ``^{x}^{2}``
    — which we fold into ``x^{2}`` (first superscript's content becomes the
    base of the second).

        "$x^2$"          → "x^2"
        "$^{x}^{2}$"      → "^{x}^{2}" → "x^{2}"
    """
    s = raw.strip()
    # Strip one pair of inline-math delimiters ($...$) wrapping the expr.
    if len(s) >= 2 and s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    # Fold a base-less superscript chain: ^{a}^{b} → a^{b}.
    s = re.sub(r"\^{([^{}]+)}\^{([^{}]+)}", r"\1^{\2}", s)
    # Strip braces from any remaining single superscript: x^{2} → x^2.
    # (The graph path converts ^ to ** next; leaving {2} would make SymPy's
    # safe-char gate reject the expression.)
    s = re.sub(r"\^{([^{}]+)}", r"^\1", s)
    return s


def _extract_graph_intent(cleaned: str) -> MathIntent | None:
    from app.modules.math import match as mtm

    if mtm.calc_op(cleaned) in {"derivative", "differentiate"}:
        return None
    g_expr = mtm.graph_expr(cleaned)
    if g_expr is None:
        return None
    g_expr = _strip_math_delims_and_fix_superscripts(g_expr)
    # strip_trailing_filler(g_expr) used to run twice (once for the x= vertical
    # check, once for the returned graph expr). Compute it once and derive
    # both forms from it.
    stripped = strip_trailing_filler(g_expr)
    # A user-named domain ("from 0 to 100") must be peeled off the expression
    # before SymPy sees it, and applied to the sample window. Without this,
    # "graph y=x^2 from 0 to 100" sampled on the [-10, 10] default and the
    # model often emitted its own (wrong) spec for the requested range.
    domain = mtm.graph_domain(stripped)
    x_min: float | None = None
    x_max: float | None = None
    if domain is not None:
        x_min, x_max, stripped = domain
    expr_no_space = stripped.replace("^", "**").replace(" ", "")
    # Prefer vertical for "graph x=4": the ENTIRE RHS after "x=" must be a
    # pure number — "x=2y" / "x=2*y" are functions (y = x/2), not vertical
    # lines, so they must fall through to the solve-for-y path below.
    if expr_no_space.lower().startswith("x="):
        try:
            num = float(expr_no_space[2:])
        except ValueError:
            num = None
        if num is not None:
            return MathIntent(kind="vertical", point_x=num, operation="graph")
    # graph_expr already matched, so this turn is a plot ask. English leftovers
    # ("Graph y", "the reason") must not reach solve-for-y (implicit
    # multiplication → x**2/(G*a*h*p*r)) or fall through to the equation
    # solver. Empty expr skips the verified fence; the honesty note still
    # fires because needs_symbolic saw the graph cue.
    guarded = math_expr_or_none(stripped)
    if guarded is None:
        return MathIntent(
            kind="graph", expr="", operation="graph", graph_x_min=x_min, graph_x_max=x_max
        )
    expr = guarded.replace("^", "**")
    # An equation like "x=2y" is not a function expression — solve for y as
    # y = f(x) (e.g. "x/2") so sample_function can plot it. Without this,
    # sample_function gets an Equality and rejects it, so no verified graph
    # is emitted and the model emits its own (often wrong) spec.
    # A one-variable equation ("graph 4x^2-5x-12=0") has no y to isolate;
    # plot lhs - rhs so the parabola's roots sit on the x-axis.
    if "=" in expr:
        solved = _solve_for_y_as_function_of_x(expr)
        if solved is not None:
            expr = solved
        else:
            as_fx = _equation_as_function_of_x(expr)
            if as_fx is not None:
                expr = as_fx
    return MathIntent(
        kind="graph", expr=expr, operation="graph", graph_x_min=x_min, graph_x_max=x_max
    )
