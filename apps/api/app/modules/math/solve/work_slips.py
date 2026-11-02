"""What went wrong between a student's last good line and the first wrong one.

Each diagnoser compares the two lines with one common slip in mind: a term
moved without changing sign, one side changed and not the other, multiplying
where dividing undoes, an inequality not reversed (or reversed for no reason),
a bracket half-expanded, like terms combined wrong, a root lost or added. The
first that fits names the slip in two voices: an explanation with the fix,
and a hint that keeps the fix back. A proposed corrected line must have the
same solutions as the last good line, or the diagnosis is dropped for the
next one; the fallback only says the line does not follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from sympy import (
    Add,
    Eq,
    FiniteSet,
    Mul,
    S,
    Symbol,
    expand,
    latex,
    preorder_traversal,
    simplify,
    solveset,
)

from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.root_latex import expr_equal
from app.modules.math.solve.work_lines import (
    FLIPPED,
    INEQUALITIES,
    OP_TEX,
    Line,
    exact,
    fixed_line,
    states_solution,
)

_NICE = 100
_MAX_SPLIT_TERMS = 4


@dataclass(frozen=True)
class Mistake:
    """The first wrong line (1-based) and what went wrong in the move to it.

    ``explanation`` names the slip and the fix; ``hint`` names the slip and
    keeps the fix back ("don't finish it for me").
    """

    line: int
    kind: str
    explanation: str
    hint: str
    fixed_label: str | None = None
    fixed_tex: str | None = None


def diagnose(prev: Line, cur: Line, var: Any, number: int) -> tuple[Mistake, Line | None]:
    """The slip from ``prev`` to ``cur`` and, when known, the verified fixed line."""
    if prev.op != "or" and cur.op == "or":
        diagnosers: tuple[Any, ...] = (_factor_root_sign, _solution_count)
    elif prev.op == "or":
        diagnosers = (_solution_count,)
    else:
        diagnosers = (
            _direction,
            _scaling,
            _brackets,
            _moved_term,
            _divide_every_term,
            _one_side_rewrite,
            _solution_count,
            _answer_does_not_check,
        )
    for diagnose in diagnosers:
        found = diagnose(prev, cur, var, number)
        if found is None:
            continue
        mistake, fixed = found
        if fixed is not None and fixed.solutions != prev.solutions:
            continue
        return mistake, fixed
    return _unexplained(prev, cur, var, number), None


def _nice(value: Any) -> bool:
    """A factor a student would divide by: a small integer or ``1/n``, not 1."""
    if not getattr(value, "is_Rational", False) or value in (0, 1):
        return False
    return (value.q == 1 and abs(value.p) <= _NICE) or (abs(value.p) == 1 and value.q <= _NICE)


def _ratio(numerator: Any, denominator: Any, var: Any) -> Any | None:
    if denominator == 0:
        return None
    with sympy_decline() as declined:
        ratio = simplify(numerator / denominator)
    if declined:
        return None
    if var in ratio.free_symbols or not _nice(ratio):
        return None
    return ratio


def _side_word(name: str) -> str:
    return "left" if name == "lhs" else "right"


def _other(name: str) -> str:
    return "rhs" if name == "lhs" else "lhs"


def _sign_word(op: str) -> str:
    return "equals sign" if op == "=" else "inequality sign"


def _paren(value: Any) -> str:
    tex = str(latex(value))
    return rf"\left({tex}\right)" if value.could_extract_minus_sign() or value.is_Add else tex


def _mistake(
    number: int,
    kind: str,
    explanation: str,
    hint: str,
    fixed: Line | None,
    label: str | None,
) -> tuple[Mistake, Line | None]:
    return (
        Mistake(
            line=number,
            kind=kind,
            explanation=explanation,
            hint=hint,
            fixed_label=label if fixed is not None else None,
            fixed_tex=fixed.tex if fixed is not None else None,
        ),
        fixed,
    )


def _direction(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """Right numbers, wrong way round: the inequality sign itself slipped."""
    if prev.op not in INEQUALITIES or cur.op not in INEQUALITIES:
        return None
    flipped = FLIPPED[cur.op]
    fixed = fixed_line(cur.lhs, flipped, cur.rhs, var)
    if fixed is None or fixed.solutions != prev.solutions:
        return None
    if expr_equal(cur.lhs, prev.rhs) and expr_equal(cur.rhs, prev.lhs):
        return _mistake(
            number,
            "swap_without_flip",
            "Swapping the two sides turns the inequality sign around too: "
            f"${prev.tex}$ says the same as ${fixed.tex}$.",
            "When you swap the two sides of an inequality, what has to happen to the sign?",
            fixed,
            "Swap the sides and turn the sign around",
        )
    factor = _variable_side_ratio(prev, cur, var)
    if factor is not None and factor < 0 and cur.op == prev.op:
        return _mistake(
            number,
            "no_flip",
            f"Multiplying or dividing by a negative number reverses the inequality, "
            f"so ${OP_TEX[prev.op]}$ becomes ${OP_TEX[flipped]}$ here.",
            "You divided (or multiplied) by a negative number. "
            "What does that do to the inequality sign?",
            fixed,
            f"{_scale_label(factor)} and reverse the sign",
        )
    if cur.op == FLIPPED[prev.op]:
        reason = (
            f"Here you {_scale_verb(factor)}, which is positive, so ${OP_TEX[prev.op]}$ stays."
            if factor is not None
            else f"Adding or subtracting never reverses it, so ${OP_TEX[prev.op]}$ stays."
        )
        return _mistake(
            number,
            "wrong_flip",
            f"The sign only reverses when you multiply or divide by a negative number. {reason}",
            "Did anything in this step reverse the inequality? "
            "Only multiplying or dividing by a negative number does.",
            fixed,
            "Keep the inequality sign",
        )
    return None


def _variable_side_ratio(prev: Line, cur: Line, var: Any) -> Any | None:
    for name in ("lhs", "rhs"):
        before, after = prev.side(name), cur.side(name)
        if var in before.free_symbols and var in after.free_symbols:
            return _ratio(before, after, var)
    return None


def _multiplies(factor: Any) -> bool:
    """Dividing by ``1/3`` is taught as multiplying by 3."""
    inverse = 1 / factor
    return bool(inverse.is_Integer) and not factor.is_Integer


def _scale_label(factor: Any) -> str:
    if _multiplies(factor):
        return f"Multiply both sides by ${latex(1 / factor)}$"
    return f"Divide both sides by ${latex(factor)}$"


def _scale_verb(factor: Any) -> str:
    if _multiplies(factor):
        return f"multiplied by ${latex(1 / factor)}$"
    return f"divided by ${latex(factor)}$"


def _scaled_tex(value: Any, factor: Any) -> str:
    """``\\frac{8}{2} = 4`` or ``4 \\cdot 3 = 12``: the arithmetic the fix needs."""
    result = latex(value / factor)
    if _multiplies(factor):
        return f"{_paren(value)} \\cdot {_paren(1 / factor)} = {result}"
    if factor.is_Integer:
        return rf"\frac{{{latex(value)}}}{{{latex(factor)}}} = {result}"
    return rf"{_paren(value)} \div {_paren(factor)} = {result}"


def _scaling(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """The unknown's side was scaled right; the other side was not."""
    for name in ("lhs", "rhs"):
        before, after = prev.side(name), cur.side(name)
        if var not in before.free_symbols or var not in after.free_symbols:
            continue
        factor = _ratio(before, after, var)
        if factor is None or _has_like_terms(prev.written(name)):
            continue
        other = _other(name)
        other_before, other_after = prev.side(other), cur.side(other)
        expected = other_before / factor
        if expr_equal(other_after, expected):
            continue
        op = FLIPPED[prev.op] if prev.op in INEQUALITIES and factor < 0 else prev.op
        pair = (after, expected) if name == "lhs" else (expected, after)
        fixed = fixed_line(pair[0], op, pair[1], var)
        label = _scale_label(factor)
        arithmetic = _scaled_tex(other_before, factor)
        undo = (
            f"dividing by ${latex(1 / factor)}$"
            if _multiplies(factor)
            else f"multiplying by ${latex(factor)}$"
        )
        flip_note = (
            " A negative factor also reverses the inequality sign."
            if op != prev.op and cur.op == prev.op
            else ""
        )
        if expr_equal(other_after, other_before * factor):
            return _mistake(
                number,
                "scaled_the_wrong_way",
                f"To undo {undo}, do the opposite on both sides: ${arithmetic}$. "
                f"This line did the same operation again instead.{flip_note}",
                f"What undoes {undo}?",
                fixed,
                label,
            )
        if expr_equal(other_after, other_before - factor) and after == var:
            return _mistake(
                number,
                "subtracted_coefficient",
                f"${latex(before)}$ means ${latex(factor)}$ times ${latex(var)}$, so subtracting "
                f"${latex(factor)}$ does not undo it. {label}: ${arithmetic}$.{flip_note}",
                f"${latex(before)}$ means ${latex(factor)}$ times ${latex(var)}$. "
                "What undoes multiplying?",
                fixed,
                label,
            )
        if expr_equal(other_after, other_before):
            return _mistake(
                number,
                "scaled_one_side",
                f"The {_side_word(name)} side was scaled but the {_side_word(other)} side was "
                f"not. {label}: ${arithmetic}$.{flip_note}",
                f"You changed the {_side_word(name)} side. "
                f"Did the {_side_word(other)} side get the same treatment?",
                fixed,
                label,
            )
        if var in other_before.free_symbols:
            continue
        if expr_equal(other_after, -expected):
            return _mistake(
                number,
                "scaled_sign",
                f"Watch the sign: ${arithmetic}$.{flip_note}",
                f"Recheck the sign on the {_side_word(other)} side.",
                fixed,
                label,
            )
        return _mistake(
            number,
            "scaled_arithmetic",
            f"${arithmetic}$, not ${latex(other_after)}$.{flip_note}",
            f"Recheck the arithmetic on the {_side_word(other)} side.",
            fixed,
            label,
        )
    return None


def _has_like_terms(written: Any) -> bool:
    """``3x + 2x`` as written: combining is the move, not scaling."""
    if written is None:
        return False
    return len(Add.make_args(written)) > len(Add.make_args(_evaluated(written)))


def _evaluated(expr: Any) -> Any:
    if not getattr(expr, "args", ()):
        return expr
    return expr.func(*[_evaluated(arg) for arg in expr.args])


def _bracket(written: Any, var: Any) -> tuple[Any, list[Any]] | None:
    """(multiplier, terms inside) of the first ``c(a + b)`` as written."""
    if written is None:
        return None
    for node in preorder_traversal(written):
        if not isinstance(node, Mul):
            continue
        sums = [arg for arg in node.args if isinstance(arg, Add) and var in arg.free_symbols]
        rest = [arg for arg in node.args if not (isinstance(arg, Add) and var in arg.free_symbols)]
        if len(sums) != 1 or any(var in arg.free_symbols for arg in rest):
            continue
        multiplier = exact(_evaluated(Mul(*rest))) if rest else S.One
        if multiplier == 1:
            continue
        return multiplier, list(Add.make_args(exact(_evaluated(sums[0]))))
    return None


def _brackets(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """``4(x - 2)`` expanded wrong while the other side stayed put."""
    for name in ("lhs", "rhs"):
        other = _other(name)
        if not expr_equal(cur.side(other), prev.side(other)):
            continue
        found = _bracket(prev.written(name), var)
        if found is None:
            continue
        multiplier, terms = found
        before, after = prev.side(name), cur.side(name)
        expanded = expand(before)
        if expr_equal(after, expanded):
            continue
        inside = Add(*terms)
        outside = expand(before - multiplier * inside)
        lead = "-" if multiplier == -1 else latex(multiplier)
        shown = rf"{lead}\left({latex(inside)}\right)"
        pair = (expanded, cur.rhs) if name == "lhs" else (cur.lhs, expanded)
        fixed = fixed_line(pair[0], prev.op, pair[1], var)
        product = expand(multiplier * inside)
        for term in terms:
            if expr_equal(after, outside + product - multiplier * term + term):
                return _mistake(
                    number,
                    "partial_distribution",
                    f"The ${latex(multiplier)}$ multiplies every term inside the brackets: "
                    f"${shown} = {latex(product)}$. The ${latex(term)}$ was not multiplied.",
                    f"When you expand ${shown}$, does ${latex(multiplier)}$ multiply every term "
                    "inside the brackets?",
                    fixed,
                    "Expand the brackets",
                )
            if expr_equal(after, outside + product - 2 * multiplier * term):
                return _mistake(
                    number,
                    "distribution_sign",
                    f"Watch the signs: ${_paren(multiplier)} \\cdot {_paren(term)} = "
                    f"{latex(multiplier * term)}$, so ${shown} = {latex(product)}$.",
                    f"Check the sign of ${_paren(multiplier)} \\cdot {_paren(term)}$.",
                    fixed,
                    "Expand the brackets",
                )
        return _mistake(
            number,
            "distribution",
            f"Expanding gives ${shown} = {latex(product)}$.",
            f"Recheck how you expanded ${shown}$.",
            fixed,
            "Expand the brackets",
        )
    return None


def _move_tex(value: Any, moved: Any) -> str:
    """``11 - 3 = 8`` / ``2 + 5 = 7``: the other side after the move."""
    result = latex(expand(value - moved))
    if moved.could_extract_minus_sign():
        return f"{latex(value)} + {latex(-moved)} = {result}"
    return f"{latex(value)} - {_paren(moved)} = {result}"


def _move_label(moved: Any) -> str:
    if moved.could_extract_minus_sign():
        return f"Add ${latex(-moved)}$ to both sides"
    return f"Subtract ${latex(moved)}$ from both sides"


def _moved_term(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """A term left one side; the other side did not get the opposite."""
    for name in ("lhs", "rhs"):
        before, after = prev.side(name), cur.side(name)
        moved = expand(before - after)
        if moved == 0 or not any(expr_equal(moved, term) for term in Add.make_args(expand(before))):
            continue
        other = _other(name)
        other_before, other_after = prev.side(other), cur.side(other)
        expected = expand(other_before - moved)
        if expr_equal(other_after, expected):
            continue
        pair = (after, expected) if name == "lhs" else (expected, after)
        fixed = fixed_line(pair[0], prev.op, pair[1], var)
        label = _move_label(moved)
        arithmetic = _move_tex(other_before, moved)
        term = latex(moved) if moved.could_extract_minus_sign() else f"+{latex(moved)}"
        if expr_equal(other_after, other_before + moved):
            return _mistake(
                number,
                "moved_without_sign_change",
                f"A term changes sign when it crosses the {_sign_word(prev.op)}. "
                f"{label}: ${arithmetic}$.",
                f"When ${term}$ crosses to the other side, what happens to its sign?",
                fixed,
                label,
            )
        if expr_equal(other_after, other_before):
            return _mistake(
                number,
                "moved_one_side",
                f"${term}$ came off the {_side_word(name)} side only. Whatever you do to one "
                f"side, do to the other: ${arithmetic}$.",
                f"You took ${term}$ off the {_side_word(name)} side. "
                f"What has to happen on the {_side_word(other)} side?",
                fixed,
                label,
            )
        if var in expected.free_symbols or var in other_after.free_symbols:
            continue
        return _mistake(
            number,
            "move_arithmetic",
            f"${arithmetic}$, not ${latex(other_after)}$.",
            f"Recheck the arithmetic on the {_side_word(other)} side.",
            fixed,
            label,
        )
    return None


def _divide_every_term(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """The number side was divided; only some terms of the unknown's side were."""
    for name in ("lhs", "rhs"):
        other = _other(name)
        other_before, other_after = prev.side(other), cur.side(other)
        if var in other_before.free_symbols or var in other_after.free_symbols:
            continue
        factor = _ratio(other_before, other_after, var)
        if factor is None:
            continue
        before, after = prev.side(name), cur.side(name)
        expected = expand(before / factor)
        if expr_equal(after, expected):
            continue
        terms = list(Add.make_args(expand(before)))
        if len(terms) < 2 or len(terms) > _MAX_SPLIT_TERMS:
            continue
        partial = any(
            expr_equal(after, Add(*[t / factor if t in chosen else t for t in terms]))
            for size in range(1, len(terms))
            for chosen in combinations(terms, size)
        )
        if not partial:
            continue
        op = FLIPPED[prev.op] if prev.op in INEQUALITIES and factor < 0 else prev.op
        pair = (expected, other_after) if name == "lhs" else (other_after, expected)
        fixed = fixed_line(pair[0], op, pair[1], var)
        shown = rf"\frac{{{latex(before)}}}{{{latex(factor)}}}"
        return _mistake(
            number,
            "divided_some_terms",
            f"Dividing a side by ${latex(factor)}$ divides every term on it: "
            f"${shown} = {latex(expected)}$.",
            f"When you divide by ${latex(factor)}$, does every term on the "
            f"{_side_word(name)} side get divided?",
            fixed,
            f"Divide every term by ${latex(factor)}$",
        )
    return None


def _one_side_rewrite(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """One side rewritten to something it does not equal; the other side untouched."""
    for name in ("lhs", "rhs"):
        other = _other(name)
        if not expr_equal(cur.side(other), prev.side(other)):
            continue
        before, after = prev.side(name), cur.side(name)
        if expr_equal(before, after):
            continue
        simplified = expand(before)
        pair = (simplified, cur.rhs) if name == "lhs" else (cur.lhs, simplified)
        fixed = fixed_line(pair[0], prev.op, pair[1], var)
        return _mistake(
            number,
            "simplified_wrong",
            f"The {_side_word(name)} side simplifies to ${latex(simplified)}$, "
            f"not ${latex(after)}$.",
            f"Recheck how you combined the terms on the {_side_word(name)} side.",
            fixed,
            f"Simplify the {_side_word(name)} side",
        )
    return None


def _values_tex(var: Any, values: Any) -> str:
    ordered = sorted(values, key=lambda value: float(value))
    return r" \text{ or } ".join(f"{latex(var)} = {latex(value)}" for value in ordered)


def _factor_root_sign(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """``(x - 3) = 0`` read as ``x = -3``."""
    if prev.rhs != 0 or not isinstance(prev.written_lhs, Mul):
        return None
    factors = [
        _evaluated(arg) for arg in prev.written_lhs.args if var in getattr(arg, "free_symbols", ())
    ]
    for factor in factors:
        roots = solveset(Eq(factor, 0), var, domain=S.Reals)
        if not isinstance(roots, FiniteSet) or len(roots) != 1:
            continue
        (root,) = tuple(roots)
        if root in cur.solutions or -root not in cur.solutions:
            continue
        fixed = Line(
            tex=_values_tex(var, prev.solutions),
            op="or",
            solutions=prev.solutions,
            values=tuple(prev.solutions),
        )
        return _mistake(
            number,
            "factor_root_sign",
            f"Setting ${latex(factor)} = 0$ gives ${latex(var)} = {latex(root)}$, "
            f"not ${latex(-root)}$.",
            f"Solve ${latex(factor)} = 0$ again: which value of ${latex(var)}$ makes it zero?",
            fixed,
            "Set each factor equal to zero",
        )
    return None


def _solution_count(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """A solution lost (a square root without the minus) or one added."""
    before, after = prev.solutions, cur.solutions
    if not isinstance(before, FiniteSet) or not isinstance(after, FiniteSet):
        return None
    lost, extra = before - after, after - before
    if lost and not extra:
        missing = _values_tex(var, lost)
        square = (
            prev.op == "="
            and prev.lhs.is_Pow
            and prev.lhs.exp == 2
            and var not in prev.rhs.free_symbols
        )
        if square:
            return _mistake(
                number,
                "lost_negative_root",
                f"A square root has two answers, positive and negative: "
                f"${_values_tex(var, before)}$.",
                f"Is there only one number whose square is ${latex(prev.rhs)}$?",
                None,
                None,
            )
        return _mistake(
            number,
            "lost_solution",
            f"This line loses ${missing}$, which also solves line {number - 1}.",
            f"Is that the only value that works in line {number - 1}?",
            None,
            None,
        )
    if extra and not lost:
        added = _values_tex(var, extra)
        return _mistake(
            number,
            "extra_solution",
            f"${added}$ does not solve line {number - 1}.",
            f"Does every value in line {number} work in line {number - 1}?",
            None,
            None,
        )
    return None


def _substituted(expr: Any, var: Any, value: Any) -> str:
    placeholder = Symbol("QUQ")
    return str(latex(expr.subs(var, placeholder))).replace("QUQ", rf"\left({latex(value)}\right)")


def _answer_does_not_check(prev: Line, cur: Line, var: Any, number: int) -> Any:
    """``x = 7`` for ``2x + 3 = 11``: show the substitution failing."""
    if prev.op != "=" or cur.op != "=" or not states_solution(cur, var):
        return None
    value = cur.rhs if cur.lhs == var else cur.lhs
    left, right = prev.lhs.subs(var, value), prev.rhs.subs(var, value)
    if var in prev.rhs.free_symbols:
        shown = (
            f"${_substituted(prev.lhs, var, value)} = {latex(left)}$ but "
            f"${_substituted(prev.rhs, var, value)} = {latex(right)}$"
        )
    else:
        shown = f"${_substituted(prev.lhs, var, value)} = {latex(left)}$, not ${latex(right)}$"
    return _mistake(
        number,
        "answer_does_not_check",
        f"${latex(var)} = {latex(value)}$ does not satisfy line {number - 1}: {shown}.",
        f"Substitute ${latex(var)} = {latex(value)}$ back into line {number - 1}. Does it work?",
        None,
        None,
    )


def _unexplained(prev: Line, cur: Line, var: Any, number: int) -> Mistake:
    witness = ""
    before, after = prev.solutions, cur.solutions
    value = next(iter(before)) if isinstance(before, FiniteSet) and len(before) == 1 else None
    if value is not None and not after.contains(value):
        witness = (
            f" For example, ${latex(var)} = {latex(value)}$ solves line {number - 1} "
            f"but not line {number}."
        )
    return Mistake(
        line=number,
        kind="does_not_follow",
        explanation=f"Line {number} does not follow from line {number - 1}.{witness}",
        hint=f"Line {number} does not follow from line {number - 1}. Redo that one step.",
    )
