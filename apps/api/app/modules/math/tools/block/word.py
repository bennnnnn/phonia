"""Word-problem block: the translation shown, the solve verified, a reply to send.

The reply leads with the setup (what each letter stands for, and the words
each equation comes from) so a student can see how the problem was read, then
the verified steps and the answer. Text from the translation is stripped to
plain words before it is shown.
"""

from __future__ import annotations

import re
from typing import Any

from sympy import latex

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.schemas.word_problem import WordProblemSetup
from app.modules.math.solve.declines import declines
from app.modules.math.solve.word_problem import WordSolution, solve_word_problem
from app.modules.math.tools.block.canonical import _answer_canonical
from app.services.solving import VerifiedMathBlock
from app.services.workout import Workout, math_line, render_workout

_PLAIN = re.compile(r"[^A-Za-z0-9 ,.'()%/-]")
_UNIT = re.compile(r"[^A-Za-z ]")
_MONEY = frozenset({"$", "dollar", "dollars", "usd"})


def _verified_block_word_problem(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    setup = intent.word_problem
    if setup is None:
        return None
    solution = solve_word_problem(setup)
    if solution is None:
        return None
    answer = r",\ ".join(
        _value_tex(value, target.unit)
        for target, value in zip(setup.targets, solution.answers, strict=True)
    )
    lines.append("Word problem, translated and solved with SymPy:")
    lines.extend(f"{unknown.symbol} = {_plain(unknown.meaning)}" for unknown in setup.unknowns)
    lines.extend(f"Equation: {equation}" for equation in solution.equations)
    lines.extend(f"{name} = {latex(value)}" for name, value in solution.values)
    lines.append(f"Verified result: {answer}")
    return VerifiedMathBlock(
        text="\n".join(lines),
        canonical_fence=_answer_canonical(answer),
        canonical_answer=answer,
        direct_reply=format_word_problem_reply(setup, solution, answer),
        check_latex=solution.check,
    )


# What the model is told about a setup no reader of the server's read from the words.
UNCHECKED_SETUP_RULE = (
    "This setup is a model's reading of the problem, and SymPy checked only its arithmetic. "
    "Check each equation against the words it comes from before you use it: a misread "
    "condition, a dropped term or quantity, or a process that never ends makes it wrong, and "
    "then set the problem up yourself. Never call the answer verified."
)


@declines(None)
def unchecked_setup_note(setup: WordProblemSetup) -> str | None:
    """A model's translation of a word problem and SymPy's solution of it, for the model to
    check against the words; None when SymPy finds no one solution in the stated domain."""
    solution = solve_word_problem(setup)
    if solution is None:
        return None
    lines = ["Word problem setup, read by a model (not checked against the problem):"]
    lines.extend(f"{unknown.symbol} = {_plain(unknown.meaning)}" for unknown in setup.unknowns)
    for equation, item in zip(solution.equations, setup.equations, strict=True):
        source = _plain(item.source)
        lines.append(f"Equation: {equation}" + (f' (from "{source}")' if source else ""))
    values = ", ".join(f"{name} = {latex(value)}" for name, value in solution.values)
    lines.append(f"SymPy's solution of these equations: {values}")
    lines.append(UNCHECKED_SETUP_RULE)
    return "\n".join(lines)


def _plain(text: str | None) -> str:
    return " ".join(_PLAIN.sub("", text or "").split())


def _unit(unit: str | None) -> str:
    return " ".join(_UNIT.sub("", unit or "").split())


def _money(value: Any) -> str:
    amount = float(value)
    return f"{amount:.0f}" if amount == int(amount) else f"{amount:.2f}"


def _value_tex(value: Any, unit: str | None) -> str:
    if (unit or "").strip().lower() in _MONEY:
        return rf"\${_money(value)}"
    name = _unit(unit)
    return f"{latex(value)}\\ \\text{{{name}}}" if name else str(latex(value))


def _answer_sentence(setup: WordProblemSetup, solution: WordSolution) -> str:
    """``the son's age now: $12$ years``: words outside the math, no bare ``$``."""
    parts = []
    for target, value in zip(setup.targets, solution.answers, strict=True):
        meaning = _plain(target.meaning) or _plain(target.expr)
        unit = "dollars" if (target.unit or "").strip().lower() in _MONEY else _unit(target.unit)
        shown = f"${_money(value)}$" if unit == "dollars" else f"${latex(value)}$"
        parts.append(f"{meaning}: {shown}" + (f" {unit}" if unit else ""))
    return "; ".join(parts)


def format_word_problem_reply(setup: WordProblemSetup, solution: WordSolution, answer: str) -> str:
    """Given: each equation with the words it comes from. Required: what each letter is."""
    from app.modules.math.tools.lesson import numbered_steps

    find = tuple(
        math_line(
            unknown.symbol,
            _plain(unknown.meaning) + (f" ({_unit(unknown.unit)})" if _unit(unknown.unit) else ""),
        )
        for unknown in setup.unknowns
    )
    given = tuple(
        math_line(tex, f'"{_plain(item.source)}"' if _plain(item.source) else None)
        for tex, item in zip(solution.equations, setup.equations, strict=True)
    )
    # The lesson layout: a bold numbered move with its rule, then its working. The
    # check waits until it is asked for (``check_latex``, ``with_requested_check``).
    formulas: list[str] = []
    if solution.steps:
        # "g = 5", not "5 books": the last move ends on the solved letter.
        solved = r",\; ".join(f"{name} = {latex(value)}" for name, value in solution.values)
        formulas, numbered = numbered_steps(
            solution.steps, given_latex="", answer=solved, variable=setup.unknowns[0].symbol
        )
    else:
        values = r",\; ".join(f"{name} = {latex(value)}" for name, value in solution.values)
        numbered = f"**1. Solve the equations**  \n${values}$"
    workout = Workout(given=given, find=find, formula=tuple(formulas))
    return render_workout(
        workout, answer, before_answer=f"{numbered}\n\n{_answer_sentence(setup, solution)}"
    )
