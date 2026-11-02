"""Verified traces for radical, fractional-power, logarithm, rational and |x| equations.

Each tracer returns None when the equation is not its family, so
``key_steps.equation_key_steps`` can try them in order before the polynomial path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sympy import (
    Abs,
    E,
    Eq,
    Integer,
    Mul,
    Poly,
    S,
    exp,
    expand,
    im,
    latex,
    log,
    prod,
    simplify,
    solve,
)

from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.key_steps import (
    KeyStep,
    _canonical_root_formula,
    equation_key_steps,
    equation_tex,
    label_tex,
)
from app.modules.math.solve.root_latex import expr_equal


def _nonnegative_conditions(*sides: Any, var: Any, joiner: str) -> str:
    """``x + 3 \\ge 0``: each side that holds the unknown must not be negative."""
    return joiner.join(rf"{latex(side)} \ge 0" for side in sides if var in side.free_symbols)


def radical_equation_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    """Trace one or two square roots, including the extraneous-root check."""
    two_radicals = _two_radical_equation_key_steps(lhs, rhs, var)
    if two_radicals is not None:
        return two_radicals
    radical, other = lhs, rhs
    if not (getattr(radical, "is_Pow", False) and radical.exp == S.Half):
        if getattr(rhs, "is_Pow", False) and rhs.exp == S.Half:
            radical, other = rhs, lhs
        else:
            return None
    radicand = radical.base
    if var not in getattr(radicand, "free_symbols", set()):
        return None
    with sympy_decline() as declined:
        squared = Eq(radicand, expand(other**2))
        candidates = solve(squared, var)
        valid = [
            value
            for value in candidates
            if expr_equal(radical.subs(var, value), other.subs(var, value))
        ]
    if declined:
        return []
    if not candidates or not valid:
        return []
    # ``4 \ge 0`` is always true; only a side with the unknown restricts it.
    domain = _nonnegative_conditions(radicand, other, var=var, joiner=r" \quad\text{and}\quad ")
    return [
        KeyStep(label="Domain restrictions", formula=domain),
        KeyStep(label="Square both sides", formula=equation_tex(radicand, expand(other**2))),
        *_worked(
            radicand,
            expand(other**2),
            var,
            "Solve the squared equation",
            _canonical_root_formula(var, candidates),
        ),
        KeyStep(
            label="Check and reject extraneous roots",
            formula=_canonical_root_formula(var, valid),
        ),
    ]


def _two_radical_equation_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    """Verified repeated-squaring trace for ``sqrt(a)+sqrt(b)=constant``."""
    radical_side, target = lhs, rhs
    terms = radical_side.args if getattr(radical_side, "is_Add", False) else ()
    radicals = [term for term in terms if getattr(term, "is_Pow", False) and term.exp == S.Half]
    if len(terms) != 2 or len(radicals) != 2:
        radical_side, target = rhs, lhs
        terms = radical_side.args if getattr(radical_side, "is_Add", False) else ()
        radicals = [term for term in terms if getattr(term, "is_Pow", False) and term.exp == S.Half]
    if len(terms) != 2 or len(radicals) != 2:
        return None
    if var in getattr(target, "free_symbols", set()) or simplify(target) == 0:
        return None
    first, second = radicals
    first_base, second_base = first.base, second.base
    with sympy_decline() as declined:
        isolated = simplify((target**2 + second_base - first_base) / (2 * target))
        candidates = solve(Eq(second_base, isolated**2), var)
        valid = [
            value
            for value in candidates
            if expr_equal(radical_side.subs(var, value), target.subs(var, value))
        ]
    if declined:
        return []
    if not candidates or not valid:
        return []
    domain = _nonnegative_conditions(first_base, second_base, target, var=var, joiner=r",\quad ")
    return [
        KeyStep(label="Domain restrictions", formula=domain),
        KeyStep(
            label="Isolate one radical",
            formula=equation_tex(first, target - second),
        ),
        KeyStep(
            label="Square and isolate the remaining radical",
            formula=equation_tex(2 * target * second, target**2 + second_base - first_base),
        ),
        KeyStep(
            label="Square again",
            formula=equation_tex(second_base, isolated**2),
        ),
        KeyStep(
            label="Check in the original equation",
            formula=_canonical_root_formula(var, valid),
        ),
    ]


def fractional_power_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    power, target = lhs, rhs
    if not (getattr(power, "is_Pow", False) and power.base == var):
        if getattr(rhs, "is_Pow", False) and rhs.base == var:
            power, target = rhs, lhs
        else:
            return None
    exponent = power.exp
    if not (getattr(exponent, "is_Rational", False) and exponent.q != 1 and exponent.q % 2 == 1):
        return None
    from app.modules.math.solve.equations import _real_fractional_power_solutions

    solutions = _real_fractional_power_solutions(power, target, var)
    if not solutions:
        return []
    equivalent = Eq(var ** int(exponent.p), simplify(target ** int(exponent.q)))
    return [
        KeyStep(
            label="Use the real odd-root interpretation",
            formula=(
                rf"{latex(power)} = \left(\sqrt[{exponent.q}]{{{latex(var)}}}\right)"
                rf"^{{{exponent.p}}}"
            ),
        ),
        KeyStep(
            label=f"Raise both sides to the {exponent.q}rd power"
            if exponent.q == 3
            else f"Raise both sides to the {exponent.q}th power",
            formula=latex(equivalent),
        ),
        KeyStep(label="Solve over the reals", formula=_canonical_root_formula(var, solutions)),
    ]


def logarithm_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    """Verified trace for a sum of same-base logarithms."""
    if var in getattr(rhs, "free_symbols", set()):
        return None
    terms = lhs.args if getattr(lhs, "is_Add", False) else (lhs,)
    arguments: list[Any] = []
    base: Any | None = None
    for term in terms:
        numerator, denominator = term.as_numer_denom()
        if getattr(numerator, "func", None) is not log:
            return None
        if denominator == 1:
            candidate_base = E  # ``ln``
        elif getattr(denominator, "func", None) is log and len(denominator.args) == 1:
            candidate_base = denominator.args[0]
        else:
            return None
        if base is not None and not expr_equal(base, candidate_base):
            return None
        base = candidate_base
        arguments.append(numerator.args[0])
    if base is None or not arguments:
        return None
    with sympy_decline() as declined:
        combined = prod(arguments)
        target = simplify(base**rhs)
        candidates = solve(Eq(combined, target), var)
        valid = [
            value
            for value in candidates
            if all(bool(simplify(argument.subs(var, value)) > 0) for argument in arguments)
        ]
    if declined:
        return []
    if not candidates or not valid:
        return []
    domain = r" \text{ and } ".join(rf"{latex(argument)} > 0" for argument in arguments)
    candidate_formula = _canonical_root_formula(var, candidates)
    answer = _canonical_root_formula(var, valid)
    log_tex = r"\ln" if base == E else rf"\log_{{{latex(base)}}}"
    combine: list[KeyStep] = []
    if len(arguments) > 1:  # one logarithm has nothing to combine
        combine.append(
            KeyStep(
                label="Combine logarithms",
                formula=rf"{log_tex}\left({latex(combined)}\right) = {latex(rhs)}",
            )
        )
    return [
        KeyStep(label="Domain restriction", formula=domain),
        *combine,
        KeyStep(
            label="Convert to exponential form",
            formula=rf"{latex(combined)} = {latex(target)}",
        ),
        *_worked(combined, target, var, "Solve the resulting equation", candidate_formula),
        KeyStep(label="Reject values outside the domain", formula=answer),
    ]


def exponential_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    """``2^{x+1} = 32``: equal bases, or a logarithm of both sides."""
    if var in getattr(rhs, "free_symbols", set()) or not getattr(rhs, "is_number", False):
        return None
    if getattr(lhs, "func", None) is exp:
        base, exponent = E, lhs.args[0]
    elif getattr(lhs, "is_Pow", False) and getattr(lhs.base, "is_number", False):
        base, exponent = lhs.base, lhs.exp
    else:
        return None
    if var not in exponent.free_symbols or not (base.is_positive and base != 1):
        return None
    if not rhs.is_positive:
        return []
    with sympy_decline() as declined:
        candidates = solve(Eq(lhs, rhs), var)
        real = [value for value in candidates if value.is_real]
    if declined:
        return []
    if len(real) != 1:
        return []
    power = simplify(log(rhs) / log(base))
    steps: list[KeyStep] = []
    if base != E and power.is_Integer and isinstance(base, Integer):
        steps.append(
            KeyStep(
                label=f"Write ${latex(rhs)}$ as a power of ${latex(base)}$",
                formula=f"{latex(lhs)} = {latex(base)}^{{{latex(power)}}}",
            )
        )
        steps.append(
            KeyStep(
                label="Equal bases, so equal exponents",
                formula=f"{latex(exponent)} = {latex(power)}",
            )
        )
    else:
        name = r"\ln" if base == E else rf"\log_{{{latex(base)}}}"
        taken = "ln" if base == E else rf"$\log_{{{latex(base)}}}$"
        steps.append(
            KeyStep(
                label=f"Take {taken} of both sides",
                formula=rf"{latex(exponent)} = {name} {latex(rhs)}",
            )
        )
    if exponent != var:
        steps.append(
            KeyStep(label="Solve for the unknown", formula=f"{latex(var)} = {latex(real[0])}")
        )
    return steps


def rational_equation_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    left_num, left_den = getattr(lhs, "as_numer_denom", lambda: (lhs, 1))()
    right_num, right_den = getattr(rhs, "as_numer_denom", lambda: (rhs, 1))()
    left_has_variable_denominator = var in getattr(left_den, "free_symbols", set())
    right_has_variable_denominator = var in getattr(right_den, "free_symbols", set())
    if not left_has_variable_denominator and not right_has_variable_denominator:
        return None
    with sympy_decline() as declined:
        denominator = simplify(left_den * right_den)
        cleared_lhs = simplify(lhs * denominator)
        cleared_rhs = simplify(rhs * denominator)
        display_lhs = left_num if right_den == 1 else Mul(left_num, right_den, evaluate=False)
        display_rhs = right_num if left_den == 1 else Mul(right_num, left_den, evaluate=False)
        multiplied = equation_tex(display_lhs, display_rhs)
        poly = Poly(simplify(cleared_lhs - cleared_rhs), var)
        if poly.degree() < 1:
            return []
        den_poly = denominator.as_poly(var) if hasattr(denominator, "as_poly") else None
        den_degree = den_poly.degree() if den_poly is not None else None
        from app.core.config import get_settings

        degree_cap = get_settings().math_max_poly_degree
        high_denominator = den_degree is None or int(den_degree) > degree_cap
        candidates = solve(Eq(cleared_lhs, cleared_rhs), var)
        if high_denominator:
            # Do not ask SymPy for every root of a huge denominator.
            # A plain int has no .subs; the variable-denominator path is an expression.
            if isinstance(denominator, int):
                return []
            excluded = []
            solutions = [
                solution
                for solution in candidates
                if simplify(denominator.subs(var, solution)) != 0
            ]
        else:
            excluded = solve(Eq(denominator, 0), var)
            solutions = [
                solution
                for solution in candidates
                if all(not expr_equal(solution, value) for value in excluded)
            ]
    if declined:
        return []
    condition = r"\text{denominator} \ne 0"
    if high_denominator:
        exclusions_tex = condition
    elif excluded:
        exclusions_tex = r",\; ".join(rf"{latex(var)} \ne {latex(value)}" for value in excluded)
    else:
        exclusions_tex = condition
    steps = [
        KeyStep(label="Domain restrictions", formula=exclusions_tex),
        KeyStep(
            label=f"Multiply both sides by {label_tex(denominator)}",
            formula=multiplied,
        ),
    ]
    if candidates:
        steps.extend(
            _worked(
                cleared_lhs,
                cleared_rhs,
                var,
                "Solve the resulting equation",
                _canonical_root_formula(var, candidates),
            )
        )
    if solutions:
        final = _canonical_root_formula(var, solutions)
        if len(solutions) != len(candidates):
            steps.append(KeyStep(label="Reject excluded values", formula=final))
    else:
        steps.append(
            KeyStep(
                label="Reject the excluded candidate",
                formula=r"\text{no solution}",
            )
        )
    return steps


def absolute_value_key_steps(lhs: Any, rhs: Any, var: Any) -> list[KeyStep] | None:
    if getattr(rhs, "func", None) is Abs and getattr(lhs, "func", None) is not Abs:
        lhs, rhs = rhs, lhs
    if getattr(lhs, "func", None) is not Abs:
        return None
    if var in getattr(rhs, "free_symbols", set()) or not getattr(rhs, "is_number", False):
        return []
    with sympy_decline() as declined:
        if rhs < 0 or Poly(lhs.args[0], var).degree() != 1:
            return []
        solutions = solve(Eq(lhs, rhs), var)
    if declined:
        return []
    if not solutions:
        return []
    inside = lhs.args[0]
    # |u|=c splits into u=±c only when u is real. |x+I|=5 is a modulus, not that split.
    with sympy_decline() as declined:
        real = simplify(im(inside)) == 0
    if declined or not real:
        return []
    split = equation_tex(inside, rhs)
    if rhs != 0:
        split += rf" \quad\text{{or}}\quad {equation_tex(inside, -rhs)}"
    from app.modules.math.solve.root_latex import compact_root_answer_lines

    lines = compact_root_answer_lines(str(var), solutions)
    final = lines[0] if len(lines) == 1 else r" \text{ or } ".join(lines)
    # Each branch ends at its own root; the combined roots only close the whole trace.
    first = _worked(inside, rhs, var, "Solve both linear equations", final, which="first")
    second = (
        _worked(inside, -rhs, var, "Solve both linear equations", final, which="second")
        if rhs != 0
        else []
    )
    for branch, target in ((first, rhs), (second, -rhs)):
        with sympy_decline() as declined:
            roots = solve(Eq(inside, target), var)
        if branch and len(branch) > 1 and not declined and roots:
            branch[-1] = KeyStep(label="Simplify", formula=_canonical_root_formula(var, roots))
    if len(first) == 1 or (rhs != 0 and len(second) == 1):
        return [
            KeyStep(label="Split the absolute-value equation", formula=split),
            KeyStep(label="Solve both linear equations", formula=final),
        ]
    # Both roots close the trace as their own step, so it ends at the answer
    # card without reading as one branch's result.
    closing = [KeyStep(label="Both solutions", formula=final)] if second else []
    return [
        KeyStep(label="Split the absolute-value equation", formula=split),
        *first,
        *second,
        *closing,
    ]


def _worked(
    lhs: Any,
    rhs: Any,
    var: Any,
    label: str,
    formula: str,
    *,
    which: str | None = None,
) -> list[KeyStep]:
    """Every inverse move on the equation a special trace reaches, ending at its roots.

    ``log(2x) = 1`` becomes ``2x = 10``; that is "Divide both sides by 2", not a
    jump to ``x = 5``. With no supported trace it stays one ``label`` step.
    """
    steps = equation_key_steps(lhs, rhs, str(var))
    if not steps:
        return [KeyStep(label=label, formula=formula)]
    if which is not None:
        steps = [
            step
            if step.label == "Simplify"
            else replace(step, label=f"{step.label} ({which} equation)")
            for step in steps
        ]
    # The roots close the move, so the rejection step that follows starts from them.
    return [*steps, KeyStep(label="Simplify", formula=formula)]
