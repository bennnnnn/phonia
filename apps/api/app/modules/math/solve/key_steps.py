"""Verified inverse-operation traces for linear, pure-power, and quadratic equations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sympy import (
    Abs,
    Eq,
    Poly,
    Symbol,
    expand,
    factor,
    latex,
    nsimplify,
    prod,
    simplify,
    solve,
    sqrt,
)

from app.modules.math.solve.declines import declines, sympy_decline
from app.modules.math.solve.display import without_unit_factors
from app.modules.math.solve.root_latex import expr_equal


@dataclass(frozen=True)
class KeyStep:
    """One justified transformation. Formula is LaTeX without ``$`` wrappers."""

    label: str
    formula: str
    reason: str | None = None
    conditions: str | None = None
    branch: str | None = None


_PLAIN_LABEL_TEX = re.compile(r"^[\w .,-]*$")
_ROOT_LABEL = "Take the square root of both sides"


def label_tex(value: Any) -> str:
    """A value inside a step label: ``3`` stays plain, ``\\frac{3}{2}`` gets ``$``.

    Labels render as bold text, so LaTeX markup needs math delimiters to show
    as math; plain numbers and terms read the same either way.
    """
    tex = str(latex(value))
    # A number stays plain ("by 2"); a term is math ("$2 x$"), so it is set in
    # the same italic as the line it acts on.
    if _PLAIN_LABEL_TEX.match(tex) and not re.search(r"[A-Za-z]", tex):
        return tex
    return f"${tex}$"


_UNIT_FACTOR = re.compile(r"(?<![\d.}])1 \\cdot ")


def written_side(text: str, variables: list[str]) -> tuple[Any, str] | None:
    """A side as the student typed it: ``3(x-2)+4``, not SymPy's ``3x - 2``.

    Parsed unevaluated and printed in the typed order, so Given shows the problem the
    student wrote: a change of base in its written base, ``1/x`` with no factor 1."""
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline() as declined:
        expr = parse_expression(text, variables, real=True, evaluate=False)
        tex = str(latex(without_unit_factors(expr), order="none"))
    if declined:
        return None
    return expr, _UNIT_FACTOR.sub("", tex)


def rewrite_label(written: Any, evaluated: Any) -> str | None:
    """The move from the typed side to the solver's: expand, collect, or none."""
    from sympy import Add, Mul, preorder_traversal

    def has_bracket(expr: Any) -> bool:
        return any(
            isinstance(node, Mul) and any(isinstance(arg, Add) for arg in node.args)
            for node in preorder_traversal(expr)
        )

    if has_bracket(written) and not has_bracket(evaluated):
        return "Expand"
    if len(Add.make_args(written)) != len(Add.make_args(evaluated)):
        return "Collect like terms"
    return None


def stringify_key_steps(steps: list[KeyStep]) -> list[str]:
    return [f"{step.label}: {step.formula}" for step in steps]


def equation_key_steps(
    lhs: Any,
    rhs: Any,
    variable: str,
    *,
    force_quadratic_formula: bool = False,
) -> list[KeyStep]:
    """Structured working from the original sides. Empty when the shape is unsupported."""
    symbols = getattr(lhs, "free_symbols", set()) | getattr(rhs, "free_symbols", set())
    var = next((symbol for symbol in symbols if str(symbol) == variable), Symbol(variable))
    from app.modules.math.solve.key_steps_special import (
        absolute_value_key_steps,
        exponential_key_steps,
        fractional_power_key_steps,
        logarithm_key_steps,
        radical_equation_key_steps,
        rational_equation_key_steps,
    )

    logarithm_steps = logarithm_key_steps(lhs, rhs, var)
    if logarithm_steps is not None:
        return logarithm_steps
    exponential_steps = exponential_key_steps(lhs, rhs, var)
    if exponential_steps is not None:
        return exponential_steps
    absolute_steps = absolute_value_key_steps(lhs, rhs, var)
    if absolute_steps is not None:
        return absolute_steps
    radical_steps = radical_equation_key_steps(lhs, rhs, var)
    if radical_steps is not None:
        return radical_steps
    fractional_power_steps = fractional_power_key_steps(lhs, rhs, var)
    if fractional_power_steps is not None:
        return fractional_power_steps
    rational_steps = rational_equation_key_steps(lhs, rhs, var)
    if rational_steps is not None:
        return rational_steps
    with sympy_decline() as declined:
        poly = Poly(simplify(lhs - rhs), var)
        degree = poly.degree()
    if declined:
        return []
    if degree == 1:
        return _linear_key_steps(lhs, rhs, var, poly)
    if degree == 2:
        return _quadratic_key_steps(
            lhs,
            rhs,
            var,
            poly,
            force_formula=force_quadratic_formula,
        )
    return _higher_degree_key_steps(lhs, rhs, var)


def _higher_degree_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep]:
    """``x^3 - 6x^2 + 11x - 6 = 0``: worked only when it splits into linear factors."""
    expr = expand(lhs - rhs)
    factored = factor(expr)
    pieces = [arg.as_base_exp()[0] for arg in factored.as_ordered_factors()]
    varying = [piece for piece in pieces if var in piece.free_symbols]
    if len(varying) < 2 or any(Poly(piece, var).degree() != 1 for piece in varying):
        return []
    return _factor_trace(lhs, rhs, var, expr, factored)


def equation_check_latex(lhs: Any, rhs: Any, variable: str) -> str | None:
    """Short substitution check when every root is rational."""
    with sympy_decline() as declined:
        var = Symbol(variable)
        solutions = solve(Eq(lhs, rhs), var)
    if declined or not solutions:
        return None
    with sympy_decline() as declined:
        rational = all(getattr(s, "is_number", False) and bool(s.is_rational) for s in solutions)
    if declined or not rational:
        return None
    if len(solutions) == 2 and expr_equal(solutions[0] + solutions[1], 0):
        pos = simplify(Abs(solutions[0]))
        dummy = Symbol("QQQ")
        left = latex(lhs.subs(var, dummy)).replace("QQQ", rf"(\pm {latex(pos)})")
        return f"{left} = {latex(rhs)}"
    parts = [_substituted_eq(lhs, rhs, var, sol) for sol in solutions]
    if not all(parts):
        return None
    return r" \text{ and } ".join(parts)


def _canonical_root_formula(var: Any, solutions: list[Any]) -> str:
    from app.modules.math.solve.root_latex import compact_root_answer_lines

    lines = compact_root_answer_lines(str(var), solutions)
    return lines[0] if len(lines) == 1 else r" \text{ or } ".join(lines)


def equation_tex(left: Any, right: Any) -> str:
    return f"{latex(left)} = {latex(right)}"


@declines(False)
def _is_negative_number(val: Any) -> bool:
    return bool(getattr(val, "is_number", False) and val.is_number and val < 0)


def _is_solved(lhs: Any, rhs: Any, var: Any) -> bool:
    return expr_equal(lhs, var) and var not in getattr(rhs, "free_symbols", set())


def _independent(expr: Any, var: Any) -> Any:
    if not hasattr(expr, "as_independent"):
        return 0
    indep, _dep = expr.as_independent(var, as_Add=True)
    return indep


def _dependent(expr: Any, var: Any) -> Any:
    if not hasattr(expr, "as_independent"):
        return 0
    _indep, dep = expr.as_independent(var, as_Add=True)
    return dep


def _reciprocal_if_proper_fraction(coeff: Any) -> Any | None:
    """``x/2`` → multiply by 2, not divide by ``1/2``."""
    rat = simplify(coeff)
    if not getattr(rat, "is_number", False) or not getattr(rat, "is_rational", False):
        return None
    numer, denom = rat.as_numer_denom()
    if not getattr(numer, "is_integer", False) or not getattr(denom, "is_integer", False):
        return None
    if denom in (0, 1, -1):
        return None
    if abs(int(numer)) >= abs(int(denom)):
        return None
    return simplify(1 / rat)


def _latex_coeff(val: Any) -> str:
    tex = str(latex(val))
    if val.is_number and val < 0:
        return f"({tex})"
    return tex


def _is_symbol_power_product(expr: Any) -> bool:
    """``x`` / ``x^{2}`` / ``x y`` — not a leftover integer like ``8/2 → 4``."""
    if getattr(expr, "is_Symbol", False):
        return True
    if getattr(expr, "is_Pow", False):
        return bool(getattr(expr.base, "is_Symbol", False))
    if getattr(expr, "is_Mul", False):
        return all(_is_symbol_power_product(arg) for arg in expr.args)
    return False


def _cancelled_side_tex(side: Any, divisor: Any) -> str:
    """Strike matching factors when dividing ``3x`` by ``3``, not when ``8/2``."""
    d_tex = str(latex(divisor))
    if divisor == 0:
        return str(latex(side))
    if expr_equal(side, divisor):
        return f"\\frac{{\\cancel{{{d_tex}}}}}{{\\cancel{{{d_tex}}}}}"
    with sympy_decline() as declined:
        # ``0.4x / 0.4`` is ``1.0 x`` until its float factor is read exactly.
        rest = nsimplify(simplify(side / divisor))
    if declined:
        return f"\\frac{{{latex(side)}}}{{{d_tex}}}"
    if expr_equal(rest, 1) and expr_equal(rest * divisor, side):
        return f"\\frac{{\\cancel{{{d_tex}}}}}{{\\cancel{{{d_tex}}}}}"
    if _is_symbol_power_product(rest) and expr_equal(rest * divisor, side):
        return f"\\frac{{\\cancel{{{d_tex}}} {latex(rest)}}}{{\\cancel{{{d_tex}}}}}"
    return f"\\frac{{{latex(side)}}}{{{d_tex}}}"


def _divide_both_sides_step(
    cur_l: Any,
    cur_r: Any,
    coeff: Any,
    *,
    label: str | None = None,
    branch: str | None = None,
) -> KeyStep:
    return KeyStep(
        label=label or f"Divide both sides by {label_tex(coeff)}",
        # Only the variable side cancels: ``3x = 3`` divided by 3 is ``x = 3/3``, not
        # a struck-through 3 on both sides.
        formula=(
            f"{_cancelled_side_tex(cur_l, coeff)} = \\frac{{{latex(cur_r)}}}{{{latex(coeff)}}}"
        ),
        reason=f"this undoes multiplication by {latex(coeff)}",
        branch=branch,
    )


def _is_negative_term(term: Any) -> bool:
    """``-3y`` or ``-3y - 5``: a subtracted term is added back, not subtracted twice."""
    return bool(
        (getattr(term, "is_Mul", False) or getattr(term, "is_Add", False))
        and term.could_extract_minus_sign()
    )


def _tidy(expr: Any) -> Any:
    """``4.0`` is ``4`` on a working line; other decimals stay as written."""
    from sympy import Float, Integer

    if not hasattr(expr, "atoms"):
        return expr
    whole = {value: Integer(int(value)) for value in expr.atoms(Float) if float(value).is_integer()}
    return expr.xreplace(whole) if whole else expr


def _grouped(term: Any) -> str:
    """``3y + 5`` subtracted is ``- (3y + 5)``; without the brackets the line is false."""
    tex = str(latex(term))
    if getattr(term, "is_Add", False):
        return rf"\left({tex}\right)"
    return tex


def _remove_term_step(
    cur_l: Any,
    cur_r: Any,
    term: Any,
    *,
    which: str | None = None,
    branch: str | None = None,
) -> KeyStep:
    if _is_negative_number(term) or _is_negative_term(term):
        addend = -term
        shown = _grouped(addend)
        label = f"Add {label_tex(addend)} to both sides"
        formula = f"{latex(cur_l)} + {shown} = {latex(cur_r)} + {shown}"
        reason = f"this cancels the subtracted {latex(addend)}"
    else:
        shown = _grouped(term)
        label = f"Subtract {label_tex(term)} from both sides"
        formula = f"{latex(cur_l)} - {shown} = {latex(cur_r)} - {shown}"
        reason = f"this removes the added {latex(term)}"
    if which is not None:
        label = f"{label} of the {which} equation"
    return KeyStep(label=label, formula=formula, reason=reason, branch=branch)


def _linear_key_steps(lhs: Any, rhs: Any, var: Any, poly: Any) -> list[KeyStep]:
    c1 = poly.coeff_monomial(var)
    c0 = poly.coeff_monomial(1)
    if c1 == 0:
        return []
    if _is_solved(lhs, rhs, var):
        return []
    steps: list[KeyStep] = []
    cur_l, cur_r = lhs, rhs
    exp_l, exp_r = expand(cur_l), expand(cur_r)
    if not expr_equal(exp_l, cur_l) or not expr_equal(exp_r, cur_r):
        steps.append(KeyStep(label="Expand", formula=equation_tex(exp_l, exp_r)))
        cur_l, cur_r = exp_l, exp_r

    r_dep = _dependent(cur_r, var)
    if r_dep != 0:
        steps.append(_remove_term_step(cur_l, cur_r, r_dep))
        cur_l = _tidy(simplify(cur_l - r_dep))
        cur_r = _tidy(simplify(cur_r - r_dep))
        if not _is_solved(cur_l, cur_r, var):
            steps.append(KeyStep(label="Simplify", formula=equation_tex(cur_l, cur_r)))

    l_indep = _independent(cur_l, var)
    if l_indep != 0:
        steps.append(_remove_term_step(cur_l, cur_r, l_indep))
        cur_l = _tidy(simplify(cur_l - l_indep))
        cur_r = _tidy(simplify(cur_r - l_indep))
        if not _is_solved(cur_l, cur_r, var):
            steps.append(KeyStep(label="Simplify", formula=equation_tex(cur_l, cur_r)))

    coeff = cur_l.coeff(var) if hasattr(cur_l, "coeff") else c1
    if coeff == 0:
        return steps
    if coeff == -1:
        steps.append(
            KeyStep(
                label="Multiply both sides by -1",
                formula=equation_tex(-cur_l, -cur_r),
                reason="this changes the sign of both sides",
            )
        )
        return steps
    if coeff != 1:
        multiplier = _reciprocal_if_proper_fraction(coeff)
        if multiplier is not None:
            steps.append(
                KeyStep(
                    label=f"Multiply both sides by {label_tex(multiplier)}",
                    formula=(
                        f"{latex(multiplier)} \\cdot ({latex(cur_l)}) = "
                        f"{latex(multiplier)} \\cdot ({latex(cur_r)})"
                    ),
                    reason="this clears the coefficient",
                )
            )
        else:
            steps.append(_divide_both_sides_step(cur_l, cur_r, coeff))
        return steps
    if not steps:
        isolated = simplify(-c0 / c1)
        return [
            KeyStep(
                label="Isolate",
                formula=f"{latex(c1)} \\cdot {var} = {latex(-c0)}",
            ),
            KeyStep(label="Solve", formula=f"{var} = {latex(isolated)}"),
        ]
    return steps


def _quadratic_key_steps(
    lhs: Any,
    rhs: Any,
    var: Any,
    poly: Any,
    *,
    force_formula: bool = False,
) -> list[KeyStep]:
    c2 = poly.coeff_monomial(var**2)
    c1 = poly.coeff_monomial(var)
    c0 = poly.coeff_monomial(1)
    if c2 == 0:
        return []
    if c1 == 0:
        return _pure_power_key_steps(lhs, rhs, var, c2, c0)
    expr = simplify(lhs - rhs)
    factored = factor(expr)
    if not force_formula and factored != expr and (factored.is_Mul or factored.is_Pow):
        return _factor_trace(lhs, rhs, var, expr, factored)
    return _quadratic_formula_steps(var, c2, c1, c0)


def _pure_power_key_steps(lhs: Any, rhs: Any, var: Any, c2: Any, c0: Any) -> list[KeyStep]:
    steps: list[KeyStep] = []
    cur_l, cur_r = lhs, rhs
    if var in getattr(cur_r, "free_symbols", set()):
        return []
    l_indep = _independent(cur_l, var)
    if l_indep != 0:
        steps.append(_remove_term_step(cur_l, cur_r, l_indep))
        cur_l = simplify(cur_l - l_indep)
        cur_r = simplify(cur_r - l_indep)
        if not _is_solved(cur_l, cur_r, var):
            steps.append(KeyStep(label="Simplify", formula=equation_tex(cur_l, cur_r)))

    leading = cur_l.coeff(var**2) if hasattr(cur_l, "coeff") else c2
    if leading not in (0, 1, -1) and leading is not None:
        steps.append(_divide_both_sides_step(cur_l, cur_r, leading))
        cur_l = simplify(cur_l / leading)
        cur_r = simplify(cur_r / leading)
        steps.append(KeyStep(label="Simplify", formula=equation_tex(cur_l, cur_r)))
    elif leading == -1:
        steps.append(
            KeyStep(
                label="Multiply both sides by -1",
                formula=equation_tex(-cur_l, -cur_r),
            )
        )
        cur_l, cur_r = simplify(-cur_l), simplify(-cur_r)

    radicand = simplify(cur_r) if expr_equal(cur_l, var**2) else simplify(-c0 / c2)
    if not getattr(radicand, "is_number", False) or not radicand.is_number:
        return steps
    if radicand < 0:
        steps.append(
            KeyStep(
                label="Take square roots of both sides",
                formula=rf"{latex(var)} = \pm \sqrt{{{latex(radicand)}}}",
            )
        )
        # Raw sqrt() puts i in the numerator. The chip uses the canonical
        # conjugate form, so the last step has to come from that formatter.
        solutions = solve(Eq(var**2, radicand), var)
        from app.modules.math.solve.root_latex import compact_root_answer_lines

        lines = compact_root_answer_lines(str(var), solutions)
        if lines:
            formula = lines[0] if len(lines) == 1 else r" \text{ or } ".join(lines)
            steps.append(KeyStep(label="Simplify", formula=formula))
        return steps
    # The root operation, then any reduction as its own final step, so the last
    # line matches the answer chip without hiding the root that produced it.
    if radicand == 0:
        steps.append(KeyStep(label=_ROOT_LABEL, formula=rf"{latex(var)} = \pm \sqrt{{0}}"))
        steps.append(KeyStep(label="Simplify", formula=rf"{latex(var)} = 0"))
        return steps
    written = rf"\sqrt{{{latex(radicand)}}}"
    steps.append(KeyStep(label=_ROOT_LABEL, formula=rf"{latex(var)} = \pm {written}"))
    reduced = latex(simplify(sqrt(radicand)))
    if reduced != written:
        steps.append(KeyStep(label="Simplify", formula=rf"{latex(var)} = \pm {reduced}"))
    return steps


def _linear_factors(factored: Any, var: Any) -> list[Any]:
    pieces: list[Any] = []
    if factored.is_Pow:
        base, _exp = factored.as_base_exp()
        pieces.append(base)
    elif factored.is_Mul:
        for arg in factored.args:
            if arg.is_Pow:
                pieces.append(arg.as_base_exp()[0])
            elif var in getattr(arg, "free_symbols", set()):
                pieces.append(arg)
    else:
        pieces.append(factored)
    linear: list[Any] = []
    for piece in pieces:
        poly = piece.as_poly(var) if hasattr(piece, "as_poly") else None
        if poly is not None and poly.degree() == 1:
            linear.append(piece)
    # The order the factored line prints them, so the next line reads the same way.
    return sorted(linear, key=lambda piece: _factor_order(piece, var))


def _factor_order(piece: Any, var: Any) -> tuple[bool, float]:
    """A bare ``x`` leads (``x(x + 2)(x - 2)``); the rest go in root order, ``x - a`` as 0."""
    root = 0.0
    with sympy_decline():
        roots = solve(piece, var)  # a dict, not a list, for ``P - I V`` with a real P
        if isinstance(roots, list) and roots and roots[0].is_number:
            root = float(roots[0])
    return (not piece.is_Symbol, root)


def _ordered_factored_tex(factored: Any, var: Any) -> str:
    """``(x + 2)(2x - 1)`` with the factors in root order, as the next line lists them."""
    coefficient, rest = factored.as_coeff_Mul()
    factors = [arg for arg in (rest.args if rest.is_Mul else (rest,)) if var in arg.free_symbols]
    constant = [
        arg for arg in (rest.args if rest.is_Mul else (rest,)) if var not in arg.free_symbols
    ]

    shown: list[str] = []
    for arg in sorted(factors, key=lambda item: _factor_order(item.as_base_exp()[0], var)):
        base, power = arg.as_base_exp()
        body = latex(base) if base.is_Symbol else rf"\left({latex(base)}\right)"
        shown.append(body if power == 1 else f"{body}^{{{latex(power)}}}")
    lead = coefficient * prod(constant) if constant else coefficient
    prefix = "" if lead == 1 else "-" if lead == -1 else f"{latex(lead)} "
    return prefix + " ".join(shown)


def _factor_trace(lhs: Any, rhs: Any, var: Any, expr: Any, factored: Any) -> list[KeyStep]:
    steps: list[KeyStep] = []
    if not expr_equal(rhs, 0):
        steps.append(
            KeyStep(
                label="Rearrange",
                formula=equation_tex(expr, 0),
                reason="factoring needs one side equal to zero",
            )
        )
    factors = _linear_factors(factored, var)
    steps.append(
        KeyStep(
            label="Factor the left side",
            formula=f"{_ordered_factored_tex(factored, var)} = 0"
            if factors
            else equation_tex(factored, 0),
        )
    )
    if len(factors) < 1:
        return steps
    or_parts = [equation_tex(piece, 0) for piece in factors]
    steps.append(
        KeyStep(
            label="Set each factor equal to zero",
            formula=r" \quad\text{or}\quad ".join(or_parts),
            reason="a product is zero when at least one factor is zero",
        )
    )
    ordinals = ("first", "second", "third")
    for index, piece in enumerate(factors):
        which = ordinals[index] if index < len(ordinals) else None
        branch = str(piece)
        indep = _independent(piece, var)
        cur_l, cur_r = piece, 0
        if indep != 0:
            steps.append(_remove_term_step(cur_l, cur_r, indep, which=which, branch=branch))
        coeff = piece.coeff(var) if hasattr(piece, "coeff") else 1
        if coeff not in (0, 1, -1):
            steps.append(
                _divide_both_sides_step(
                    simplify(piece - indep),
                    -indep,
                    coeff,
                    label=(
                        f"Divide both sides of the {which} equation by {label_tex(coeff)}"
                        if which
                        else f"Divide both sides by {label_tex(coeff)}"
                    ),
                    branch=branch,
                )
            )
    solutions = solve(Eq(expr, 0), var)
    if len(solutions) == 2 and expr_equal(solutions[0] + solutions[1], 0):
        positive = simplify(Abs(solutions[0]))
        final = rf"{latex(var)} = \pm {latex(positive)}"
    else:
        final = r" \text{ or } ".join(f"{latex(var)} = {latex(solution)}" for solution in solutions)
    if final:
        steps.append(KeyStep(label="Simplify", formula=final))
    return steps


def _quadratic_formula_steps(var: Any, c2: Any, c1: Any, c0: Any) -> list[KeyStep]:
    discriminant = simplify(c1**2 - 4 * c2 * c0)
    if c2 == 1:
        denom = "2"
    elif c2 == -1:
        denom = "-2"
    else:
        denom = f"2({latex(c2)})"
    steps = [
        KeyStep(
            label="Discriminant",
            formula=(
                f"\\Delta = {_latex_coeff(c1)}^{{2}} - 4({latex(c2)})({latex(c0)}) "
                f"= {latex(discriminant)}"
            ),
        ),
        KeyStep(
            label="Quadratic formula",
            formula=(
                f"{var} = \\frac{{-{_latex_coeff(c1)} \\pm "
                f"\\sqrt{{{latex(discriminant)}}}}}{{{denom}}}"
            ),
        ),
    ]
    solutions = solve(Eq(c2 * var**2 + c1 * var + c0, 0), var)
    final = _canonical_root_formula(var, solutions)
    if final:
        steps.append(KeyStep(label="Simplify", formula=final))
    return steps


def _substituted_eq(lhs: Any, rhs: Any, var: Any, val: Any) -> str:
    dummy = Symbol("QQQ")
    value = str(latex(val))
    wrapped = f"({value})"

    def substitute(side: Any) -> str:
        tex = str(latex(side.subs(var, dummy)))
        # Already bracketed or braced (``\log(QQQ)``, ``2^{QQQ}``): no second pair.
        tex = tex.replace(r"\left(QQQ\right)", rf"\left({value}\right)")
        tex = tex.replace("{QQQ}", f"{{{value}}}")
        return tex.replace("QQQ", wrapped)

    left = substitute(lhs)
    right = substitute(rhs) if var in getattr(rhs, "free_symbols", set()) else latex(rhs)
    return f"{left} = {right}"


def used_factor_trace(steps: list[KeyStep]) -> bool:
    return any(step.label.startswith("Factor") for step in steps)
