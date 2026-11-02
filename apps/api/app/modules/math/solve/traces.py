"""Verified step traces beyond one equation: linear inequalities and 2x2 systems.

A trace is a list of ``KeyStep``: the rule applied, the line it produces, and
why the rule is allowed. Every produced line is checked with SymPy against the
original problem (the same solution set for an inequality, satisfied by the
unique solution for a system). A trace with a line that fails its check is
dropped whole, so a lesson never shows a step SymPy did not confirm.
"""

from __future__ import annotations

from typing import Any

from sympy import Eq, Expr, Poly, S, Symbol, expand, factor, ilcm, latex, simplify, solve, solveset
from sympy.core.relational import Ge, Gt, Le, Lt

from app.modules.math.solve.declines import declines, sympy_decline
from app.modules.math.solve.key_steps import KeyStep, equation_key_steps, equation_tex, label_tex

_RELATIONS = {"<": Lt, ">": Gt, "<=": Le, ">=": Ge}
_COMPARATOR_TEX = {"<": "<", ">": ">", "<=": r"\le", ">=": r"\ge"}
_FLIPPED = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}

_SAME_AMOUNT_REASON = "the same amount on both sides keeps the inequality true"
_NEGATIVE_DIVISOR_REASON = "dividing by a negative number reverses the inequality"


def _symbol(exprs: tuple[Any, ...], name: str) -> Any:
    """The expression's own symbol for ``name`` (it may carry assumptions)."""
    for expr in exprs:
        for symbol in getattr(expr, "free_symbols", set()):
            if str(symbol) == name:
                return symbol
    return Symbol(name)


def _split(expr: Any, var: Any) -> tuple[Any, Any]:
    """(constant part, variable part) of a sum."""
    if not hasattr(expr, "as_independent"):
        return expr, S.Zero
    return expr.as_independent(var, as_Add=True)


def _move_label(term: Any) -> str:
    if term.could_extract_minus_sign():
        return f"Add {label_tex(-term)} to both sides"
    return f"Subtract {label_tex(term)} from both sides"


def _move_all_label(term: Any) -> str:
    if term.could_extract_minus_sign():
        return f"Add {label_tex(-term)} to all three parts"
    return f"Subtract {label_tex(term)} from all three parts"


@declines(None)
def _solution_set(relations: list[Any], var: Any) -> Any | None:
    result = S.Reals
    for relation in relations:
        result = result.intersect(solveset(relation, var, domain=S.Reals))
    return result


def _inequality_tex(left: Any, op: str, right: Any) -> str:
    return f"{latex(left)} {_COMPARATOR_TEX[op]} {latex(right)}"


def inequality_key_steps(lhs: Any, rhs: Any, variable: str, comparator: str) -> list[KeyStep]:
    """Linear inequality: variable terms left, constants right, then divide.

    Dividing by a negative coefficient reverses the comparator and says why.
    Empty for anything that is not linear in ``variable``.
    """
    if comparator not in _RELATIONS:
        return []
    var = _symbol((lhs, rhs), variable)
    with sympy_decline() as declined:
        degree = Poly(expand(lhs - rhs), var).degree()
    if declined:
        return []
    target = _solution_set([_RELATIONS[comparator](lhs, rhs)], var)
    if target is None:
        return []
    if degree == 2:
        return _quadratic_inequality_steps(lhs, rhs, var, comparator, target)
    if degree != 1:
        return []
    steps: list[KeyStep] = []
    state = {"left": lhs, "right": rhs, "op": comparator}

    def record(label: str, left: Any, right: Any, op: str, reason: str | None = None) -> bool:
        if _solution_set([_RELATIONS[op](left, right)], var) != target:
            return False
        state.update(left=left, right=right, op=op)
        steps.append(KeyStep(label=label, formula=_inequality_tex(left, op, right), reason=reason))
        return True

    left, right, op = state["left"], state["right"], str(state["op"])
    if var not in left.free_symbols and var in right.free_symbols:
        if not record(
            "Swap the sides",
            right,
            left,
            _FLIPPED[op],
            "reading it from the other side reverses the sign",
        ):
            return []
    left, right, op = state["left"], state["right"], str(state["op"])
    expanded_left, expanded_right = expand(left), expand(right)
    if expanded_left != left or expanded_right != right:
        if not record("Expand", expanded_left, expanded_right, op):
            return []
    left, right, op = state["left"], state["right"], str(state["op"])
    _, variable_terms = _split(right, var)
    if variable_terms != 0:
        if not record(
            _move_label(variable_terms),
            simplify(left - variable_terms),
            simplify(right - variable_terms),
            op,
            _SAME_AMOUNT_REASON,
        ):
            return []
    left, right, op = state["left"], state["right"], str(state["op"])
    constant, _ = _split(left, var)
    if constant != 0:
        if not record(
            _move_label(constant),
            simplify(left - constant),
            simplify(right - constant),
            op,
            _SAME_AMOUNT_REASON,
        ):
            return []
    left, right, op = state["left"], state["right"], str(state["op"])
    coefficient = simplify(left.coeff(var)) if hasattr(left, "coeff") else S.Zero
    if coefficient == 0 or not coefficient.is_number:
        return []
    if coefficient != 1:
        negative = bool(coefficient < 0)
        if not record(
            f"Divide both sides by {label_tex(coefficient)}",
            simplify(left / coefficient),
            simplify(right / coefficient),
            _FLIPPED[op] if negative else op,
            _NEGATIVE_DIVISOR_REASON if negative else None,
        ):
            return []
    return steps


def _quadratic_inequality_steps(
    lhs: Any, rhs: Any, var: Any, comparator: str, target: Any
) -> list[KeyStep]:
    """``x^2 - 4x - 5 < 0``: the roots, then the sign of the parabola between them."""
    from app.modules.math.solve.inequalities import inequality_solution_latex

    expr = expand(lhs - rhs)
    leading = Poly(expr, var).LC()
    roots = sorted(root for root in solve(Eq(expr, 0), var) if root.is_real)
    if len(roots) != 2 or not leading.is_number:
        return []
    steps: list[KeyStep] = []
    if simplify(rhs) != 0:
        steps.append(
            KeyStep(
                label="Move every term to one side",
                formula=_inequality_tex(expr, comparator, 0),
                reason=_SAME_AMOUNT_REASON,
            )
        )
    factored = factor(expr)
    if factored != expr:
        steps.append(
            KeyStep(label="Factor the left side", formula=_inequality_tex(factored, comparator, 0))
        )
    low, high = roots
    steps.append(
        KeyStep(
            label="Where the left side is zero",
            formula=rf"{latex(var)} = {latex(low)} \text{{ or }} {latex(var)} = {latex(high)}",
        )
    )
    below = comparator in {"<", "<="}
    opens_up = bool(leading > 0)
    side = "between" if below == opens_up else "outside"
    sign = "below" if below else "above"
    steps.append(
        KeyStep(
            label=(
                f"The parabola opens {'upward' if opens_up else 'downward'}, so it is "
                f"{sign} zero {side} the roots"
            ),
            formula=inequality_solution_latex(target, var),
        )
    )
    return steps


def compound_inequality_key_steps(
    low: Any, low_op: str, middle: Any, high_op: str, high: Any, variable: str
) -> list[KeyStep]:
    """``low < ax + b < high``: undo ``b`` and ``a`` on all three parts."""
    if low_op not in ("<", "<=") or high_op not in ("<", "<="):
        return []
    var = _symbol((low, middle, high), variable)
    if var in getattr(low, "free_symbols", set()) or var in getattr(high, "free_symbols", set()):
        return []
    with sympy_decline() as declined:
        linear = Poly(expand(middle), var).degree() == 1
    if declined or not linear:
        return []

    def relations(lo: Any, op1: str, mid: Any, op2: str, hi: Any) -> list[Any]:
        return [_RELATIONS[op1](lo, mid), _RELATIONS[op2](mid, hi)]

    target = _solution_set(relations(low, low_op, middle, high_op, high), var)
    if target is None:
        return []
    steps: list[KeyStep] = []
    current = [low, low_op, expand(middle), high_op, high]

    def record(label: str, parts: list[Any], reason: str | None = None) -> bool:
        lo, op1, mid, op2, hi = parts
        if _solution_set(relations(lo, op1, mid, op2, hi), var) != target:
            return False
        current[:] = parts
        formula = (
            f"{latex(lo)} {_COMPARATOR_TEX[op1]} {latex(mid)} {_COMPARATOR_TEX[op2]} {latex(hi)}"
        )
        steps.append(KeyStep(label=label, formula=formula, reason=reason))
        return True

    lo, op1, mid, op2, hi = current
    constant, _ = _split(mid, var)
    if constant != 0:
        if not record(
            _move_all_label(constant),
            [simplify(lo - constant), op1, simplify(mid - constant), op2, simplify(hi - constant)],
            "the same amount on every part keeps both inequalities true",
        ):
            return []
    lo, op1, mid, op2, hi = current
    coefficient = simplify(mid.coeff(var)) if hasattr(mid, "coeff") else S.Zero
    if coefficient == 0 or not coefficient.is_number:
        return []
    if coefficient != 1:
        if coefficient < 0:
            parts = [
                simplify(hi / coefficient),
                op2,
                simplify(mid / coefficient),
                op1,
                simplify(lo / coefficient),
            ]
            reason = (
                "dividing by a negative number reverses both signs; "
                "it is written back from smallest to largest"
            )
        else:
            parts = [
                simplify(lo / coefficient),
                op1,
                simplify(mid / coefficient),
                op2,
                simplify(hi / coefficient),
            ]
            reason = None
        if not record(f"Divide all three parts by {label_tex(coefficient)}", parts, reason):
            return []
    return steps


def _substituted_tex(expr: Any, var: Any, value: Any) -> str:
    """``expr`` with ``var`` shown as ``(value)``, e.g. ``2 \\left(y + 1\\right) + 3 y``."""
    return _placeholder_tex(expr, {var: value})


def _placeholder_tex(expr: Any, values: dict[Any, Any]) -> str:
    """LaTeX of ``expr`` with each unknown shown as its parenthesized value."""
    replaced = expr
    shown: dict[str, Any] = {}
    for index, (var, value) in enumerate(values.items()):
        if var not in getattr(expr, "free_symbols", set()):
            continue
        name = f"QSUB{'ABCDEFGH'[index]}Q"
        replaced = replaced.subs(var, Symbol(name))
        shown[name] = value
    tex = str(latex(replaced))
    for name, value in shown.items():
        tex = tex.replace(name, rf"\left({latex(value)}\right)")
    return tex


def _linear_rows(pairs: list[tuple[Any, Any]], x: Any, y: Any) -> list[tuple[Any, Any, Any]] | None:
    """``a x + b y = c`` coefficients per equation; None if not linear with numbers."""
    rows: list[tuple[Any, Any, Any]] = []
    for lhs, rhs in pairs:
        with sympy_decline() as declined:
            poly = Poly(expand(lhs - rhs), x, y)
        if declined:
            return None
        if poly.total_degree() != 1:
            return None
        if any(sum(monomial) > 1 for monomial in poly.monoms()):
            return None
        a = poly.coeff_monomial(x)
        b = poly.coeff_monomial(y)
        k = poly.coeff_monomial(1)
        if not all(getattr(value, "is_number", False) for value in (a, b, k)):
            return None
        rows.append((a, b, -k))
    return rows


def _solved_for(lhs: Any, rhs: Any, candidates: tuple[Any, ...]) -> tuple[Any, Any] | None:
    """``y = 2x + 1`` → (y, 2x + 1) when one side is exactly one unknown."""
    for side, other in ((lhs, rhs), (rhs, lhs)):
        for var in candidates:
            if side == var and var not in other.free_symbols:
                return var, other
    return None


def _finish_single_variable(lhs: Any, rhs: Any, var: Any, value: Any, steps: list[KeyStep]) -> None:
    """Solve a one-unknown linear equation, ending on ``var = value``."""
    inner = equation_key_steps(lhs, rhs, str(var))
    steps.extend(inner)
    final = f"{latex(var)} = {latex(value)}"
    if not inner or inner[-1].formula != final:
        steps.append(KeyStep(label="Simplify", formula=final))


def system_key_steps(pairs: list[tuple[Any, Any]], variables: list[str]) -> list[KeyStep]:
    """Two linear equations in two unknowns: substitution or elimination.

    Substitution when one equation is already solved for an unknown or an
    unknown has coefficient ±1; otherwise elimination with integer multipliers.
    Every derived equation must hold at SymPy's unique solution.
    """
    if len(pairs) != 2 or len(variables) != 2:
        return []
    x = _symbol(tuple(side for pair in pairs for side in pair), variables[0])
    y = _symbol(tuple(side for pair in pairs for side in pair), variables[1])
    rows = _linear_rows(pairs, x, y)
    if rows is None:
        return []
    (a1, b1, _), (a2, b2, _) = rows
    if simplify(a1 * b2 - a2 * b1) == 0:
        return []
    with sympy_decline() as declined:
        solutions = solve([Eq(lhs, rhs) for lhs, rhs in pairs], [x, y], dict=True)
    if declined:
        return []
    if len(solutions) != 1 or x not in solutions[0] or y not in solutions[0]:
        return []
    solution = solutions[0]
    steps = _substitution_steps(pairs, rows, x, y, solution)
    if steps is None:
        steps = _elimination_steps(pairs, rows, x, y, solution)
    return steps or []


@declines(False)
def _holds(lhs: Any, rhs: Any, solution: dict[Any, Any]) -> bool:
    return bool(simplify(lhs.subs(solution) - rhs.subs(solution)) == 0)


def _substitution_steps(
    pairs: list[tuple[Any, Any]],
    rows: list[tuple[Any, Any, Any]],
    x: Any,
    y: Any,
    solution: dict[Any, Any],
) -> list[KeyStep] | None:
    isolated: tuple[int, Any, Any] | None = None
    steps: list[KeyStep] = []
    # An equation in one unknown ("4x = 8") gives that unknown's value first.
    for index, (a, b, _) in enumerate(rows):
        if (a == 0) != (b == 0):
            isolated = _isolate(pairs, index, y if a == 0 else x, steps)
            if isolated is None:
                return None
            break
    if isolated is None:
        for index, (lhs, rhs) in enumerate(pairs):
            found = _solved_for(lhs, rhs, (x, y))
            if found is not None:
                isolated = (index, found[0], found[1])
                break
    if isolated is None:
        for index, (a, b, _) in enumerate(rows):
            for var, coefficient in ((x, a), (y, b)):
                if coefficient in (1, -1):
                    isolated = _isolate(pairs, index, var, steps)
                    if isolated is None:
                        return None
                    break
            if isolated is not None:
                break
    if isolated is None:
        return None
    index, var, expression = isolated
    other = y if var == x else x
    lhs, rhs = pairs[1 - index]
    substituted_lhs = lhs.subs(var, expression)
    substituted_rhs = rhs.subs(var, expression)
    if not _holds(substituted_lhs, substituted_rhs, solution):
        return None
    steps.append(
        KeyStep(
            label=f"Substitute into equation ({2 - index})",
            formula=(
                f"{_substituted_tex(lhs, var, expression)} = "
                f"{_substituted_tex(rhs, var, expression)}"
            ),
            reason=f"both equations share the same {latex(var)}",
        )
    )
    _finish_single_variable(substituted_lhs, substituted_rhs, other, solution[other], steps)
    back = expression.subs(other, solution[other])
    if not _holds(var, back, solution):
        return None
    if other in expression.free_symbols:
        steps.append(
            KeyStep(
                label=f"Substitute {latex(other)} = {label_tex(solution[other])} back",
                formula=(
                    f"{latex(var)} = {_substituted_tex(expression, other, solution[other])}"
                    f" = {latex(simplify(back))}"
                ),
            )
        )
    return steps


def _isolate(
    pairs: list[tuple[Any, Any]], index: int, var: Any, steps: list[KeyStep]
) -> tuple[int, Any, Any] | None:
    """Solve equation ``index`` for ``var``; no step when it already reads ``var = …``."""
    found = _solved_for(*pairs[index], (var,))
    if found is not None:
        return index, var, found[1]
    expression = solve(Eq(*pairs[index]), var)
    if len(expression) != 1:
        return None
    steps.append(
        KeyStep(
            label=f"Solve equation ({index + 1}) for {latex(var)}",
            formula=equation_tex(var, expression[0]),
        )
    )
    return index, var, expression[0]


def _elimination_steps(
    pairs: list[tuple[Any, Any]],
    rows: list[tuple[Any, Any, Any]],
    x: Any,
    y: Any,
    solution: dict[Any, Any],
) -> list[KeyStep] | None:
    (a1, b1, c1), (a2, b2, c2) = rows
    if not all(getattr(value, "is_integer", False) for value in (a1, b1, c1, a2, b2, c2)):
        return None
    steps: list[KeyStep] = []
    standard = [(a * x + b * y, c) for a, b, c in rows]
    if any(
        expand(lhs) != expand(s_lhs) or rhs != s_rhs
        for (lhs, rhs), (s_lhs, s_rhs) in zip(pairs, standard, strict=True)
    ):
        steps.append(
            KeyStep(
                label="Write both equations as ax + by = c",
                formula=(f"{equation_tex(*standard[0])}, \\quad {equation_tex(*standard[1])}"),
            )
        )
    # Eliminate the unknown whose coefficients need the smaller common multiple;
    # a column with a zero has nothing to cancel.
    x_column = a1 != 0 and a2 != 0
    y_column = b1 != 0 and b2 != 0
    if not (x_column or y_column):
        return None
    eliminate_y = y_column and (
        not x_column or ilcm(int(abs(b1)), int(abs(b2))) <= ilcm(int(abs(a1)), int(abs(a2)))
    )
    first, second = (b1, b2) if eliminate_y else (a1, a2)
    common = ilcm(int(abs(first)), int(abs(second)))
    multipliers = (common // int(abs(first)), common // int(abs(second)))
    scaled: list[tuple[Any, Any, Any]] = []
    for index, ((a, b, c), multiplier) in enumerate(zip(rows, multipliers, strict=True)):
        scaled.append((a * multiplier, b * multiplier, c * multiplier))
        if multiplier != 1:
            steps.append(
                KeyStep(
                    label=f"Multiply equation ({index + 1}) by {multiplier}",
                    formula=equation_tex(a * multiplier * x + b * multiplier * y, c * multiplier),
                    reason=f"so the {latex(y if eliminate_y else x)} terms cancel",
                )
            )
    (sa1, sb1, sc1), (sa2, sb2, sc2) = scaled
    add = (sb1 if eliminate_y else sa1) == -(sb2 if eliminate_y else sa2)
    sign = 1 if add else -1
    kept = x if eliminate_y else y
    kept_coefficient = (sa1 + sign * sa2) if eliminate_y else (sb1 + sign * sb2)
    kept_constant = sc1 + sign * sc2
    if kept_coefficient == 0:
        return None
    combined = (kept_coefficient * kept, kept_constant)
    if not _holds(*combined, solution):
        return None
    steps.append(
        KeyStep(
            label="Add the equations" if add else "Subtract equation (2) from equation (1)",
            formula=equation_tex(*combined),
            reason=f"the {latex(y if eliminate_y else x)} terms cancel",
        )
    )
    value = solution[kept]
    if kept_coefficient != 1:
        steps.append(
            KeyStep(
                label=f"Divide both sides by {label_tex(kept_coefficient)}",
                formula=f"{latex(kept)} = {latex(value)}",
            )
        )
    other = y if eliminate_y else x
    lhs, rhs = pairs[0]
    substituted_lhs = lhs.subs(kept, value)
    substituted_rhs = rhs.subs(kept, value)
    if not _holds(substituted_lhs, substituted_rhs, solution):
        return None
    steps.append(
        KeyStep(
            label=f"Substitute {latex(kept)} = {label_tex(value)} into equation (1)",
            formula=(
                f"{_substituted_tex(lhs, kept, value)} = {_substituted_tex(rhs, kept, value)}"
            ),
        )
    )
    _finish_single_variable(substituted_lhs, substituted_rhs, other, solution[other], steps)
    return steps


def system_check_latex(
    pairs: list[tuple[Any, Any]], variables: list[str], solution: dict[Any, Any]
) -> str | None:
    """``2(3) + 3(2) = 12 and (3) - (2) = 1``: each original equation at the solution."""
    shown: list[str] = []
    for lhs, rhs in pairs:
        values: dict[Any, Any] = {}
        for name in variables:
            var = _symbol((lhs, rhs), name)
            if var in lhs.free_symbols or var in rhs.free_symbols:
                if var not in solution:
                    return None
                values[var] = solution[var]
        if not _holds(lhs, rhs, solution):
            return None
        shown.append(f"{_placeholder_tex(lhs, values)} = {_placeholder_tex(rhs, values)}")
    return r" \text{ and } ".join(shown)


def _parse_sides(sides: list[str], variables: list[str]) -> list[Any] | None:
    """Each side as an expression; a bare SymPy name parses to its object (``limit``, ``CC``)."""
    from app.modules.math.solve.parse import _expr_needs_real_domain, parse_expression

    real = _expr_needs_real_domain(*sides)
    with sympy_decline() as declined:
        parsed = [parse_expression(side, variables, real=real) for side in sides]
    if declined or not all(isinstance(side, Expr) for side in parsed):
        return None
    return parsed


def inequality_trace(
    lhs: str, rhs: str, variable: str, comparator: str
) -> tuple[list[KeyStep], str | None]:
    """Parse, then trace. Returns (steps, given LaTeX); ([], None) when unsupported."""
    parsed = _parse_sides([lhs, rhs], [variable])
    if parsed is None or comparator not in _RELATIONS:
        return [], None
    left, right = parsed
    steps = inequality_key_steps(left, right, variable, comparator)
    if not steps:
        return [], None
    return steps, _inequality_tex(left, comparator, right)


def compound_inequality_trace(
    low: str, low_op: str, middle: str, high_op: str, high: str, variable: str
) -> tuple[list[KeyStep], str | None]:
    parsed = _parse_sides([low, middle, high], [variable])
    if parsed is None or low_op not in _RELATIONS or high_op not in _RELATIONS:
        return [], None
    lo, mid, hi = parsed
    steps = compound_inequality_key_steps(lo, low_op, mid, high_op, hi, variable)
    if not steps:
        return [], None
    given = (
        f"{latex(lo)} {_COMPARATOR_TEX[low_op]} {latex(mid)} {_COMPARATOR_TEX[high_op]} {latex(hi)}"
    )
    return steps, given


def system_trace(
    equations: list[tuple[str, str]], variables: list[str]
) -> tuple[list[KeyStep], str | None, str | None]:
    """Parse, then trace a 2x2 linear system: (steps, given LaTeX, check LaTeX)."""
    if len(equations) != 2 or len(variables) != 2:
        return [], None, None
    parsed = _parse_sides([side for pair in equations for side in pair], variables)
    if parsed is None:
        return [], None, None
    pairs = [(parsed[0], parsed[1]), (parsed[2], parsed[3])]
    steps = system_key_steps(pairs, variables)
    if not steps:
        return [], None, None
    everything = tuple(side for pair in pairs for side in pair)
    symbols = [_symbol(everything, name) for name in variables]
    with sympy_decline() as declined:
        solution = solve([Eq(lhs, rhs) for lhs, rhs in pairs], symbols, dict=True)[0]
    if declined:
        return [], None, None
    given = r", \quad ".join(equation_tex(lhs, rhs) for lhs, rhs in pairs)
    return steps, given, system_check_latex(pairs, variables, solution)
