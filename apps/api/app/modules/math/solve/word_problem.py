"""Solve a translated word problem, or refuse it.

The translation (unknowns, equations, what is asked) comes from a model and is
only a candidate. It is accepted when the equations parse in the named
unknowns, SymPy finds exactly one solution that fits the stated domain (whole
numbers for counts, positive for ages and lengths), every equation holds at
that solution, and each asked-for quantity evaluates to a real number. The
steps are the verified equation or 2x2 system traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sympy import Add, Eq, Symbol, latex, simplify, solve

from app.modules.math.schemas.word_problem import WordProblemSetup
from app.modules.math.solve.declines import sympy_decline
from app.modules.math.solve.key_steps import KeyStep, equation_check_latex, equation_key_steps
from app.modules.math.solve.traces import system_check_latex, system_key_steps
from app.modules.math.solve.work_lines import exact, student_tex

_RESERVED = frozenset("ei")


@dataclass(frozen=True)
class WordSolution:
    equations: tuple[str, ...]  # LaTeX, in the problem's order
    values: tuple[tuple[str, Any], ...]  # (symbol, value) for every unknown
    answers: tuple[Any, ...]  # one value per target
    steps: tuple[KeyStep, ...]
    check: str | None


def _parse(text: str, names: list[str], *, evaluate: bool = True) -> Any | None:
    from app.modules.math.solve.parse import parse_expression

    with sympy_decline() as declined:
        parsed = parse_expression(text, names, evaluate=evaluate)
    if declined:
        return None
    # xreplace rebuilds (and so evaluates) the tree; an as-written parse keeps
    # its decimals until each term is rebuilt on its own.
    return exact(parsed) if evaluate else parsed


def _rebuilt(expr: Any) -> Any:
    if not getattr(expr, "args", ()):
        return expr
    return expr.func(*[_rebuilt(arg) for arg in expr.args])


def _written_terms(expr: Any) -> set[Any]:
    """The terms as written, brackets of sums opened: ``n + (n + 1)`` → n, n, 1."""
    if isinstance(expr, Add):
        return {term for arg in expr.args for term in _written_terms(arg)}
    return set(Add.make_args(exact(_rebuilt(expr))))


def _needs_simplify(text: str, value: Any, names: list[str]) -> bool:
    """True when SymPy combined or expanded what the translation wrote out."""
    written = _parse(text, names, evaluate=False)
    return written is not None and _written_terms(written) != set(Add.make_args(value))


def _fits(value: Any, setup: WordProblemSetup) -> bool:
    if not getattr(value, "is_number", False) or not value.is_real:
        return False
    if setup.whole_numbers and not value.is_integer:
        return False
    return not (setup.positive and not value.is_positive)


def solve_word_problem(setup: WordProblemSetup) -> WordSolution | None:
    names = [unknown.symbol for unknown in setup.unknowns]
    if (
        not setup.found
        or not names
        or not setup.targets
        or len(set(names)) != len(names)
        or _RESERVED & set(names)
        or len(setup.equations) < len(names)
    ):
        return None
    symbols = [Symbol(name) for name in names]
    pairs: list[tuple[Any, Any]] = []
    for item in setup.equations:
        if item.equation.count("=") != 1:
            return None
        left_text, right_text = item.equation.split("=")
        left, right = _parse(left_text, names), _parse(right_text, names)
        if left is None or right is None:
            return None
        used = (left - right).free_symbols
        if not used or not used <= set(symbols):
            return None
        pairs.append((left, right))
    with sympy_decline() as declined:
        found = solve([Eq(left, right) for left, right in pairs], symbols, dict=True)
    if declined:
        return None
    fitting: list[dict[Any, Any]] = []
    for solution in found:
        if all(symbol in solution and _fits(solution[symbol], setup) for symbol in symbols):
            if solution not in fitting:
                fitting.append(solution)
    if len(fitting) != 1:
        return None
    solution = fitting[0]
    for left, right in pairs:
        if simplify(left.subs(solution) - right.subs(solution)) != 0:
            return None
    answers: list[Any] = []
    for target in setup.targets:
        expr = _parse(target.expr, names)
        # A target that names no unknown ("48") would show a stated number as the answer.
        if expr is None or not expr.free_symbols or not expr.free_symbols <= set(symbols):
            return None
        value = simplify(expr.subs(solution))
        if not getattr(value, "is_number", False) or not value.is_real:
            return None
        answers.append(value)
    steps, check = _trace(pairs, names, solution)
    if len(names) == 1 and steps:
        left_text, right_text = setup.equations[0].equation.split("=")
        left, right = pairs[0]
        if _needs_simplify(left_text, left, names) or _needs_simplify(right_text, right, names):
            steps.insert(0, KeyStep(label="Simplify", formula=f"{latex(left)} = {latex(right)}"))
        # A teaching trace must visibly finish at the solved unknown instead
        # of relying on the separate answer chip to imply the last algebraic
        # line. Apply this to every one-unknown word problem, not one story.
        final = f"{latex(symbols[0])} = {latex(solution[symbols[0]])}"
        if not any(step.formula == final for step in steps):
            steps.append(KeyStep(label="Result", formula=final))
    return WordSolution(
        # As the translation wrote them, so the setup reads like the problem.
        equations=tuple(student_tex(item.equation) for item in setup.equations),
        values=tuple((name, solution[symbol]) for name, symbol in zip(names, symbols, strict=True)),
        answers=tuple(answers),
        steps=tuple(steps),
        check=check,
    )


def _trace(
    pairs: list[tuple[Any, Any]], names: list[str], solution: dict[Any, Any]
) -> tuple[list[KeyStep], str | None]:
    """The verified equation or 2x2 system trace; none for larger setups."""
    if len(names) == 1 and len(pairs) == 1:
        left, right = pairs[0]
        return equation_key_steps(left, right, names[0]), equation_check_latex(
            left, right, names[0]
        )
    if len(names) == 2 and len(pairs) == 2:
        steps = system_key_steps(pairs, names)
        if steps:
            return steps, system_check_latex(pairs, names, solution)
    return [], None
