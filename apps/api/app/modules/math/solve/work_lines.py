"""One line of a student's work: parsed, its solution set, and how it is shown.

A line is one relation in one unknown (``2x + 3 = 11``, ``-2x > 6``) or a
final list of values (``x = 2 or x = 3``). Sides are kept twice: evaluated
for the math, and as written for the diagnoses that need to see a bracket
before SymPy distributes it. Only polynomial sides of degree at most two are
accepted, which keeps ``solveset`` exact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sympy import (
    Eq,
    FiniteSet,
    Float,
    Interval,
    Poly,
    Rational,
    S,
    Union,
    expand,
    latex,
    oo,
    solveset,
)
from sympy.core.relational import Ge, Gt, Le, Lt

from app.modules.math.solve.declines import declines, sympy_decline

RELATIONS = {"=": Eq, "<": Lt, ">": Gt, "<=": Le, ">=": Ge}
INEQUALITIES = frozenset({"<", ">", "<=", ">="})
FLIPPED = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
OP_TEX = {"=": "=", "<": "<", ">": ">", "<=": r"\le", ">=": r"\ge"}
COMPARATOR = re.compile(r"<=|>=|<|>|=")
_MAX_DEGREE = 2


@dataclass(frozen=True)
class Line:
    tex: str
    op: str
    lhs: Any = None
    rhs: Any = None
    written_lhs: Any = None
    written_rhs: Any = None
    solutions: Any = None
    values: tuple[Any, ...] = ()

    def side(self, name: str) -> Any:
        return self.lhs if name == "lhs" else self.rhs

    def written(self, name: str) -> Any:
        return self.written_lhs if name == "lhs" else self.written_rhs


def parse_line(raw: str, var: Any) -> Line | None:
    if " or " in raw:
        return _parse_values(raw, var)
    comparators = COMPARATOR.findall(raw)
    if len(comparators) != 1:
        return None
    op = comparators[0]
    left_raw, right_raw = COMPARATOR.split(raw)
    parsed = [_parse_side(text, var) for text in (left_raw, right_raw)]
    if parsed[0] is None or parsed[1] is None:
        return None
    (lhs, written_lhs), (rhs, written_rhs) = parsed[0], parsed[1]
    if not all(_polynomial(side, var) for side in (lhs, rhs)):
        return None
    solutions = solution_set(lhs, op, rhs, var)
    if solutions is None:
        return None
    return Line(
        tex=student_tex(raw),
        op=op,
        lhs=lhs,
        rhs=rhs,
        written_lhs=written_lhs,
        written_rhs=written_rhs,
        solutions=solutions,
    )


def _parse_values(raw: str, var: Any) -> Line | None:
    values: list[Any] = []
    for part in raw.split(" or "):
        name, _, value = part.partition("=")
        if name.strip() != str(var):
            return None
        parsed = _parse_side(value, var)
        if parsed is None or var in parsed[0].free_symbols:
            return None
        values.append(parsed[0])
    shown = r" \text{ or } ".join(
        f"{latex(var)} = {student_tex(part.partition('=')[2].strip())}"
        for part in raw.split(" or ")
    )
    return Line(tex=shown, op="or", solutions=FiniteSet(*values), values=tuple(values))


def _parse_side(text: str, var: Any) -> tuple[Any, Any] | None:
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline() as declined:
        value = parse_expression(text, [str(var)])
        written = parse_expression(text, [str(var)], evaluate=False)
    if declined:
        return None
    value = exact(value)
    # No xreplace on ``written``: rebuilding a node evaluates it, which would
    # expand the very bracket a diagnosis needs to see.
    if not value.free_symbols <= {var} or not written.free_symbols <= {var}:
        return None
    return value, written


def exact(expr: Any) -> Any:
    """``3.5`` → ``7/2`` so a decimal answer compares equal to the exact one."""
    floats = expr.atoms(Float)
    if not floats:
        return expr
    return expr.xreplace({f: Rational(str(f)) for f in floats})


@declines(False)
def _polynomial(expr: Any, var: Any) -> bool:
    return bool(expr.is_polynomial(var)) and Poly(expr, var).degree() <= _MAX_DEGREE


def solution_set(lhs: Any, op: str, rhs: Any, var: Any) -> Any | None:
    with sympy_decline() as declined:
        result = solveset(RELATIONS[op](lhs, rhs), var, domain=S.Reals)
    if declined:
        return None
    if not isinstance(result, FiniteSet | Interval | Union) and result not in (S.EmptySet, S.Reals):
        return None
    return result


def gradeable(solutions: Any) -> bool:
    return solutions not in (S.EmptySet, S.Reals) and isinstance(
        solutions, FiniteSet | Interval | Union
    )


def student_tex(raw: str) -> str:
    """The line as the student wrote it, with comparators and powers in LaTeX."""
    text = raw.strip().replace("**", "^").replace("<=", r" \le ").replace(">=", r" \ge ")
    text = re.sub(r"\^\(([^()]*)\)", r"^{\1}", text)
    text = re.sub(r"\^(\d{2,})", r"^{\1}", text)
    text = text.replace("*", r" \cdot ")
    return re.sub(r"\s+", " ", text).strip()


def answer_tex(solutions: Any, var: Any) -> str | None:
    name = latex(var)
    if isinstance(solutions, FiniteSet):
        values = sorted(solutions, key=lambda value: float(value))
        return r" \text{ or } ".join(f"{name} = {latex(value)}" for value in values)
    pieces = list(solutions.args) if isinstance(solutions, Union) else [solutions]
    parts: list[str] = []
    for piece in pieces:
        if not isinstance(piece, Interval):
            return None
        part = _interval_tex(piece, name)
        if part is None:
            return None
        parts.append(part)
    return r" \text{ or } ".join(parts)


def _interval_tex(interval: Any, name: str) -> str | None:
    start, end = interval.start, interval.end
    below = "<" if interval.right_open else r"\le"
    above = ">" if interval.left_open else r"\ge"
    if start == -oo and end == oo:
        return None
    if start == -oo:
        return f"{name} {below} {latex(end)}"
    if end == oo:
        return f"{name} {above} {latex(start)}"
    lower = "<" if interval.left_open else r"\le"
    return f"{latex(start)} {lower} {name} {below} {latex(end)}"


def states_solution(line: Line, var: Any) -> bool:
    if line.op == "or":
        return True
    for unknown, value in ((line.lhs, line.rhs), (line.rhs, line.lhs)):
        if unknown == var and var not in value.free_symbols:
            return True
    return False


def fixed_line(lhs: Any, op: str, rhs: Any, var: Any) -> Line | None:
    lhs, rhs = expand(lhs), expand(rhs)
    solutions = solution_set(lhs, op, rhs, var)
    if solutions is None:
        return None
    tex = f"{latex(lhs)} {OP_TEX[op]} {latex(rhs)}"
    return Line(tex=tex, op=op, lhs=lhs, rhs=rhs, solutions=solutions)
