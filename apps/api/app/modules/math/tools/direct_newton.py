"""Newton requests: the guess and lead-in extraction reads, and closed requests that show
the recorded iteration without solving again.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.modules.math import solve as math_solve
from app.modules.math.tools.direct_calculus import _compact, _expression
from app.services.number_text import DECIMAL_LITERAL, bounded_decimal
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout, text_line

_NUMBER = bounded_decimal(12)
_START = re.compile(
    rf"(.+) (?:starting at|with initial guess(?: of)?) "
    rf"(?:([A-Za-z])(?:_?0)?\s*=\s*)?({_NUMBER})",
    re.IGNORECASE,
)
_PREFIXES = (
    "use newton method to solve ",
    "use newton's method to solve ",
    "use newton's method to find the root of ",
    "use newton method to find the root of ",
    "use newton's method for ",
    "use newton's method on ",
    "newton's method for ",
    "newton's method on ",
)


def has_newton_request(text: str) -> bool:
    return re.search(r"\bnewton\b", text, re.IGNORECASE) is not None


_DEFAULT_NEWTON_GUESS = 1.0


def _whole_label(label: str) -> re.Pattern[str]:
    # A word edge is a word boundary: "near" is not inside "nonlinear" or "linear".
    start = r"\b" if label[0].isalnum() else ""
    end = r"\b" if label[-1].isalnum() else ""
    return re.compile(f"{start}{re.escape(label)}{end}")


# Tried in this order: the longer spelling of a cue before its shorter one.
_GUESS_LABELS = tuple(
    _whole_label(label)
    for label in (
        "starting at x0 =",
        "starting at x=",
        "starting at",
        "starting near",
        "initial guess of",
        "initial guess",
        "near x=",
        "near",
        "guess",
        "x0 =",
    )
)


def _parse_newton_guess(cleaned: str) -> tuple[float, str]:
    """Return ``(guess, text_for_eq)`` after stripping a trailing guess clause."""
    guess = _DEFAULT_NEWTON_GUESS
    text_for_eq = cleaned
    lower = cleaned.lower()
    for label in _GUESS_LABELS:
        found = label.search(lower)
        if found is None:
            continue
        idx = found.start()
        m = DECIMAL_LITERAL.search(cleaned, found.end())
        if m:
            guess = float(m.group(0))
            # Guess clauses are almost always trailing — drop from the cue onward.
            text_for_eq = cleaned[:idx].rstrip()
            if text_for_eq.lower().endswith(" with"):
                text_for_eq = text_for_eq[: -len(" with")].rstrip()
            break
    return guess, text_for_eq


def _strip_newton_leadin(text_for_eq: str) -> str:
    """Strip newton lead-in without poly regex — phrase prefixes only."""
    for prefix in (
        "please use newton's method to find the root of ",
        "please use newton's method for ",
        "please use newton's method on ",
        "use newton's method to find the root of ",
        "use newton's method for ",
        "use newton's method on ",
        "newton's method for ",
        "newton's method on ",
        "newton's method to find the root of ",
        "please numerically solve ",
        "please numerically approximate ",
        "numerically solve ",
        "numerically approximate ",
        "please find the root of ",
        "find the root of ",
    ):
        if text_for_eq.lower().startswith(prefix):
            return text_for_eq[len(prefix) :].strip()
    return text_for_eq


def _request_parameters(text: str) -> tuple[str, str, float] | None:
    if len(text) > 1000:
        return None
    request = " ".join(text.split()).replace("\u2212", "-").replace("\u2019", "'")
    if request.endswith((".", "?")):
        request = request[:-1].rstrip()
    if request.lower().startswith("please "):
        request = request[7:]
    prefix = next((prefix for prefix in _PREFIXES if request.lower().startswith(prefix)), None)
    if prefix is None:
        return None
    match = _START.fullmatch(request[len(prefix) :])
    if match is None or match[1].count("=") != 1:
        return None
    lhs, rhs = (_expression(part.strip()) for part in match[1].split("="))
    if lhs is None or rhs is None:
        return None
    variables = math_solve.guess_variables(f"{lhs} {rhs}")
    if len(variables) != 1:
        return None
    variable = variables[0]
    if match[2] is not None and match[2] != variable:
        return None
    expr = lhs if rhs.strip() in {"0", "0.0"} else f"({lhs})-({rhs})"
    return expr, variable, float(match[3])


def can_direct_newton(verified: VerifiedMathBlock, text: str, fences: list[dict[str, Any]]) -> bool:
    parameters = _request_parameters(text)
    data, result = verified.newton_input, verified.newton_result
    if parameters is None or data is None or result is None:
        return False
    expr, variable, guess = parameters
    if (
        _compact(data.expr) != _compact(expr)
        or data.variable != variable
        or data.initial_guess != guess
        # Precision/iteration overrides are not part of this closed grammar.
        or data.tolerance != 1e-6
        or data.max_iterations != 50
        or not result.converged
        or result.root is None
        or not math.isfinite(result.root)
        or not result.function_latex
        or not result.derivative_latex
        or result.derivative_latex == "0"
        or not result.recurrence_latex
    ):
        return False
    steps = result.iterations
    if (
        not steps
        or result.iterations_used != len(steps)
        or len(steps) > data.max_iterations
        or steps[0].x_n != data.initial_guess
        or steps[-1].x_n != result.root
        or abs(steps[-1].f_x_n) >= data.tolerance
        or any(
            step.n != n or not math.isfinite(step.x_n) or not math.isfinite(step.f_x_n)
            for n, step in enumerate(steps)
        )
    ):
        return False
    answer = f"{result.root:g}"
    return (
        verified.canonical_answer == answer
        and len(fences) == 1
        and fences[0].get("type") == "answer"
        and fences[0].get("content") == answer
    )


def _iterate_text(value: float) -> str:
    # These are the solver's ten-decimal recorded values, not recalculated iterates.
    return f"{value:.10f}".rstrip("0").rstrip(".") or "0"


def format_newton_reply(verified: VerifiedMathBlock) -> str:
    data, result = verified.newton_input, verified.newton_result
    if data is None or result is None:
        raise ValueError("Newton reply requires its verified input and result")
    variable = data.variable
    steps = result.iterations
    shown = steps if len(steps) <= 8 else [*steps[:4], *steps[-3:]]
    iterates: list[str] = []
    for index, step in enumerate(shown):
        if len(steps) > 8 and index == 4:
            iterates.append(text_line("…"))
        iterates.append(math_line(f"{variable}_{{{step.n}}} = {_iterate_text(step.x_n)}"))
    tolerance = _iterate_text(data.tolerance)
    iterates.append(math_line(rf"|f({variable}_n)| < {tolerance}", "stop"))
    workout = Workout(
        given=(math_line(f"f({variable}) = {result.function_latex}"),),
        find=(math_line(variable, "a root"),),
        formula=(
            (math_line(result.recurrence_latex, "Newton's method"),)
            if result.recurrence_latex
            else ()
        ),
        steps=tuple(iterates),
    )
    # The root is an approximation, written as the Answer line; the fence pass
    # puts the verified root in the card in its place.
    root = math_line(rf"{variable} \approx {verified.canonical_answer}")
    return f"{render_workout(workout)}  \n{root}\n"
