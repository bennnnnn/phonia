"""Check a student's worked lines against the problem they started from.

Each line is one relation in one unknown. A line is right when it has exactly
the solutions of the first line (the problem as the student wrote it); SymPy's
``solveset`` over the reals decides. The first line that changes the solutions
holds the mistake, and ``work_slips`` names what went wrong in the move to it.
Every corrected line a diagnosis proposes is itself checked, and the steps
from there to the answer are the verified equation and inequality traces.

Scope is deliberately narrow: polynomial sides of degree at most two in one
unknown. Anything else returns None, and the message keeps the normal path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sympy import Symbol

from app.modules.math.solve.key_steps import KeyStep, equation_check_latex, equation_key_steps
from app.modules.math.solve.traces import inequality_key_steps
from app.modules.math.solve.work_lines import (
    Line,
    answer_tex,
    gradeable,
    parse_line,
    states_solution,
)
from app.modules.math.solve.work_slips import Mistake, diagnose

__all__ = ["Mistake", "WorkCheck", "check_work"]


@dataclass(frozen=True)
class WorkCheck:
    variable: str
    lines: tuple[str, ...]
    # "given" (line 1), "ok", "wrong" (first mistake), then "carried" for a
    # later line that follows from the one before it, or "off".
    verdicts: tuple[str, ...]
    answer: str
    mistake: Mistake | None
    finished: bool
    # From the corrected line (or the last good line) to the answer; for
    # unfinished correct work, from the last line.
    steps: tuple[KeyStep, ...] = field(default_factory=tuple)
    check: str | None = None
    # The last line states the problem's solution although an earlier line
    # has a slip (the slip is still named).
    right_answer: bool = False


def check_work(raw_lines: list[str] | tuple[str, ...], variable: str) -> WorkCheck | None:
    """Grade each line against line 1. None when a line is out of scope."""
    var = Symbol(variable)
    lines: list[Line] = []
    for raw in raw_lines:
        line = parse_line(raw, var)
        if line is None:
            return None
        lines.append(line)
    first = lines[0]
    if first.op == "or" or not gradeable(first.solutions):
        return None
    answer = answer_tex(first.solutions, var)
    if answer is None:
        return None
    verdicts = ["given"]
    wrong: int | None = None
    for index in range(1, len(lines)):
        line = lines[index]
        if wrong is None:
            if line.solutions == first.solutions:
                verdicts.append("ok")
                continue
            wrong = index
            verdicts.append("wrong")
            continue
        # A later line is graded against the problem too: ``4x+2=10, 4x=12,
        # x=2`` reaches the right answer, and its last line is right even
        # though the line before it is not.
        if line.solutions == first.solutions:
            verdicts.append("ok")
            continue
        follows = line.solutions == lines[index - 1].solutions
        verdicts.append("carried" if follows else "off")
    texts = tuple(line.tex for line in lines)
    if wrong is None:
        finished = states_solution(lines[-1], var)
        return WorkCheck(
            variable=variable,
            lines=texts,
            verdicts=tuple(verdicts),
            answer=answer,
            mistake=None,
            finished=finished,
            steps=() if finished else tuple(_steps_from(lines[-1], variable)),
            check=_check_tex(first, variable) if finished else None,
        )
    mistake, fixed = diagnose(lines[wrong - 1], lines[wrong], var, wrong + 1)
    steps: list[KeyStep] = []
    if fixed is not None and mistake.fixed_tex is not None:
        steps.append(
            KeyStep(label=mistake.fixed_label or "Corrected line", formula=mistake.fixed_tex)
        )
        steps.extend(_steps_from(fixed, variable))
    else:
        steps.extend(_steps_from(lines[wrong - 1], variable))
    return WorkCheck(
        variable=variable,
        lines=texts,
        verdicts=tuple(verdicts),
        answer=answer,
        mistake=mistake,
        finished=False,
        steps=tuple(steps),
        right_answer=verdicts[-1] == "ok" and states_solution(lines[-1], var),
    )


def _steps_from(line: Line, variable: str) -> list[KeyStep]:
    if line.op == "or" or states_solution(line, Symbol(variable)):
        return []
    if line.op == "=":
        return equation_key_steps(line.lhs, line.rhs, variable)
    return inequality_key_steps(line.lhs, line.rhs, variable, line.op)


def _check_tex(first: Line, variable: str) -> str | None:
    if first.op != "=":
        return None
    return equation_check_latex(first.lhs, first.rhs, variable)
