"""Inequalities solved over the reals, single and compound, and their solution sets written
as a student writes them (``-1 < x < 5``, ``x < -1 \\text{ or } x > 1``)."""

from __future__ import annotations

from typing import Any

from sympy import (
    FiniteSet,
    Ge,
    Gt,
    Interval,
    Le,
    Lt,
    S,
    Symbol,
    Union,
    latex,
    oo,
    simplify,
    solve_univariate_inequality,
    solveset,
)

from app.modules.math.schemas import MathSolveResult
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.parse import (
    SolveServiceError,
    _expr_needs_real_domain,
    parse_expression,
)


def compound_solution_set(
    low: str, low_op: str, mid: str, high_op: str, high: str, variable: str
) -> Any:
    """The real solution set of ``low OP mid OP high``: the answer card's and the number
    line's (``solve/graph.py``), solved once here (they were copies that could drift)."""
    sym = Symbol(variable, real=True)
    low_e = parse_expression(low, [variable], real=True)
    mid_e = parse_expression(mid, [variable], real=True)
    high_e = parse_expression(high, [variable], real=True)
    lower_rel, upper_rel = _compound_relations(
        low, low_op, mid, high_op, high, low_e, mid_e, high_e
    )
    try:
        # solveset rejects And(...); solve each side and intersect on Reals.
        return solveset(lower_rel, sym, domain=S.Reals).intersect(
            solveset(upper_rel, sym, domain=S.Reals)
        )
    except Exception as exc:
        raise SolveServiceError(
            f"Could not solve compound inequality: {low} {low_op} {mid} {high_op} {high}"
        ) from exc


def _compound_relations(
    low: str, low_op: str, mid: str, high_op: str, high: str, low_e: Any, mid_e: Any, high_e: Any
) -> tuple[Any, Any]:
    ascending = low_op in ("<", "<=") and high_op in ("<", "<=")
    descending = low_op in (">", ">=") and high_op in (">", ">=")
    if ascending:
        lower_rel = Gt(mid_e, low_e) if low_op == "<" else Ge(mid_e, low_e)
        upper_rel = Lt(mid_e, high_e) if high_op == "<" else Le(mid_e, high_e)
    elif descending:
        # ``5 > x > 1`` → x < 5 and x > 1
        lower_rel = Lt(mid_e, low_e) if low_op == ">" else Le(mid_e, low_e)
        upper_rel = Gt(mid_e, high_e) if high_op == ">" else Ge(mid_e, high_e)
    else:
        raise SolveServiceError(
            f"Unsupported compound inequality direction: {low} {low_op} {mid} {high_op} {high}"
        )
    return lower_rel, upper_rel


def solve_compound_inequality(
    low: str,
    low_op: str,
    mid: str,
    high_op: str,
    high: str,
    variable: str,
) -> MathSolveResult:
    """Solve ``low OP mid OP high`` (e.g. ``1 < x <= 3``) as an And of relations."""
    sym = Symbol(variable, real=True)
    sol = compound_solution_set(low, low_op, mid, high_op, high, variable)
    low_e = parse_expression(low, [variable], real=True)
    mid_e = parse_expression(mid, [variable], real=True)
    high_e = parse_expression(high, [variable], real=True)
    sol_latex = inequality_solution_latex(sol, sym)
    cmp_latex = {"<": "<", ">": ">", "<=": "\\leq", ">=": "\\geq"}
    return MathSolveResult(
        solutions_latex=[sol_latex],
        steps=[
            (
                f"Compound inequality: {latex(low_e)} {cmp_latex[low_op]} "
                f"{latex(mid_e)} {cmp_latex[high_op]} {latex(high_e)}"
            ),
            f"Solution: {sol_latex}",
        ],
        lhs_latex=latex(mid_e),
        rhs_latex=f"{latex(low_e)}, {latex(high_e)}",
    )


def inequality_solution_latex(solution: Any, sym: Any) -> str:
    """``-1 < x < 5`` and ``x < -1 \\text{ or } x > 1``, as a student writes them.

    SymPy hands back either a logical ``And``/``Or`` (printed with ``\\wedge``)
    or a set of intervals; both read as the same school notation here.
    """
    with sympy_decline() as declined:
        found = solution.as_set() if hasattr(solution, "as_set") else solution
    if declined:
        return str(latex(solution))
    name = latex(sym)
    if found == S.Reals:
        return rf"\text{{all real }} {name}"
    if found == S.EmptySet:
        return r"\text{no solution}"

    def piece(part: Any) -> str | None:
        if isinstance(part, FiniteSet):
            return r" \text{ or } ".join(f"{name} = {latex(value)}" for value in part)
        if not isinstance(part, Interval):
            return None
        low = "<" if part.left_open else r"\le"
        high = "<" if part.right_open else r"\le"
        if part.start == -oo:
            return f"{name} {high} {latex(part.end)}"
        if part.end == oo:
            return f"{name} {'>' if part.left_open else r'\ge'} {latex(part.start)}"
        return f"{latex(part.start)} {low} {name} {high} {latex(part.end)}"

    parts = list(found.args) if isinstance(found, Union) else [found]
    if (
        len(parts) == 2
        and all(isinstance(part, Interval) for part in parts)
        and parts[0].start == -oo
        and parts[1].end == oo
        and parts[0].end == parts[1].start
        and parts[0].right_open
        and parts[1].left_open
    ):
        return rf"{name} \ne {latex(parts[0].end)}"
    shown = [piece(part) for part in parts]
    if any(text is None for text in shown):
        return str(latex(solution))
    return r" \text{ or } ".join(text for text in shown if text)


def inequality_solution_set(lhs: str, rhs: str, comparator: str, variable: str) -> Any:
    """The solution set of ``lhs CMP rhs``, an Interval/Union: the answer card's and the
    number line's, solved once here (the number line used to solve it its own way)."""
    real = _expr_needs_real_domain(lhs, rhs)
    sym = Symbol(variable, real=True) if real else Symbol(variable)
    left = parse_expression(lhs, [variable], real=real)
    right = parse_expression(rhs, [variable], real=real)
    rel_cls = {"<": Lt, ">": Gt, "<=": Le, ">=": Ge}.get(comparator)
    if rel_cls is None:
        raise SolveServiceError(f"Unknown inequality comparator: {comparator}")
    try:
        if real:
            return solveset(rel_cls(left, right), sym, domain=S.Reals)
        return solve_univariate_inequality(
            rel_cls(simplify(left - right), 0), sym, relational=False
        )
    except Exception as exc:  # NotImplementedError / non-univariate / etc.
        raise SolveServiceError(f"Could not solve inequality: {lhs} {comparator} {rhs}") from exc


def solve_inequality(lhs: str, rhs: str, variable: str, comparator: str) -> MathSolveResult:
    """Solve a single-variable inequality, e.g. `x**2 - 1 > 0` → x < -1 or x > 1.

    `comparator` is the canonical form returned by try_extract_inequality_from_text
    ("<", ">", "<=", ">="). lhs/rhs go through the same allow-checked parser as
    every other expression; the relational is built from SymPy Lt/Gt/Le/Ge, so
    no user string is eval'd.
    """
    real = _expr_needs_real_domain(lhs, rhs)
    sym = Symbol(variable, real=True) if real else Symbol(variable)
    left = parse_expression(lhs, [variable], real=real)
    right = parse_expression(rhs, [variable], real=real)
    sol = inequality_solution_set(lhs, rhs, comparator, variable)
    sol_latex = inequality_solution_latex(sol, sym)
    cmp_latex = {"<": "<", ">": ">", "<=": "\\leq", ">=": "\\geq"}[comparator]
    return MathSolveResult(
        solutions_latex=[sol_latex],
        steps=[
            f"Inequality: {latex(left)} {cmp_latex} {latex(right)}",
            f"Solution: {sol_latex}",
        ],
        lhs_latex=latex(left),
        rhs_latex=latex(right),
    )
