"""A worked solution the model wrote as parts, laid out as a verified reply is.

Every section goes through ``render_workout`` (``services/workout.py``), the renderer of
every verified maths, physics and chemistry reply: **Given** (each value on its line, then
the ``where`` line naming them), **Required**, **Solution**, the formula under its name's
heading (``formula_heading``: **Average speed formula**; **Formula** with no name),
``Solve for`` lines, **Substitution** or **Steps**, then **Answer** with the value. A
question in parts is laid out as a verified one in parts: the givens and what is asked
once, then **Solution** and each part under its letter, closed by its own **Answer (a)**, a hairline
between parts. The value under **Answer** becomes the card in finalize
(``chat.finalize_subjects.check_working``), marked ``verified: false``: no solver
checked it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chat.worked_solution import Answer, Given, Part, Step, WorkedSolution
from app.services.times_sign import with_times
from app.services.worked_parts import WorkedPart, part_letter, render_parts
from app.services.workout import (
    ANSWER,
    Workout,
    formula_heading,
    math_line,
    render_workout,
    solve_for_line,
    text_line,
    where_line,
)

_HARD_BREAK = "  \n"
_SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_POWER = re.compile(r"\^\{?(-?\d+)\}?")
_NOT_TEX = re.compile(r"[{}\\$%&#_^~]")
_LONG_SUBSCRIPT = re.compile(r"_(?![{\\])([A-Za-z0-9]{2,})")
_NUMBERED = re.compile(r"^([A-Za-z])(\d+)$")
_UPRIGHT = re.compile(r"\\(?:mathrm|text)|\\[,;! ]")
# LaTeX syntax or a relation: a field holding any of them is maths.
_MATH_SYNTAX = re.compile(r"[\\{}^_=<>≤≥≈≠]")
_WORDS = re.compile(r"[^\W\d_]{2,}")
_NOT_ALNUM = re.compile(r"[^A-Za-z0-9.]")
_TEXT_WRAP = re.compile(r"^\\(?:text|mathrm)\s*\{(?P<unit>[^{}]*)\}$")
_UNIT_SYMBOLS = {
    "°": r"^\circ",
    "deg": r"^\circ",
    "degree": r"^\circ",
    "degrees": r"^\circ",
    "°C": r"\,^\circ\mathrm{C}",
    "℃": r"\,^\circ\mathrm{C}",
    "degC": r"\,^\circ\mathrm{C}",
    "°F": r"\,^\circ\mathrm{F}",
    "%": r"\,\%",
}


@dataclass(frozen=True)
class WorkedLayout:
    """How one turn's worked block is laid out. ``law_heading``: physics' card holds the
    value alone, as its verified replies do."""

    law_heading: bool = False


def unit_tex(unit: str) -> str:
    """The unit after a number, upright: ``m/s^2`` → ``\\,\\mathrm{m/s²}``."""
    text = unit.strip()
    wrapped = _TEXT_WRAP.match(text)
    if wrapped is not None:
        text = wrapped.group("unit").strip()
    if not text:
        return ""
    if text in _UNIT_SYMBOLS:
        return _UNIT_SYMBOLS[text]
    if "\\" in text:
        return rf"\,{text}"  # written in LaTeX already
    plain = _POWER.sub(lambda match: match.group(1).translate(_SUPERSCRIPTS), text)
    plain = plain.replace("*", "·").replace("{", "").replace("}", "").replace("%", r"\%")
    return rf"\,\mathrm{{{plain}}}"


def tidy_tex(tex: str) -> str:
    """A subscript of several characters in braces: ``x_final`` → ``x_{final}``; a product
    written with a dot, with \\times as every reply writes it (``services/times_sign``)."""
    return with_times(_LONG_SUBSCRIPT.sub(r"_{\1}", tex.strip()))


def tidy_symbol(symbol: str) -> str:
    """``m1`` → ``m_1``: a letter numbered by the digits after it, as a subscript."""
    return tidy_tex(_NUMBERED.sub(r"\1_\2", symbol.strip()))


def is_prose(field: str) -> bool:
    """Words the model put in a maths field ("Let A be the origin"), told by structure:
    no LaTeX syntax and no relation, and a word of two letters or more. Anything with a
    backslash, brace, script or relation is maths, so no LaTeX source is ever shown."""
    return _MATH_SYNTAX.search(field) is None and _WORDS.search(field) is not None


def names_nothing(symbol: str) -> bool:
    """A "symbol" written in words ("length in cm", "a) in cm")."""
    return " " in symbol.strip() and is_prose(symbol)


def _line(tex: str, note: str | None = None) -> str:
    """One state: maths, or the model's sentence as text."""
    return text_line(tex, note) if is_prose(tex) else math_line(tidy_tex(tex), note)


def _plain(tex: str) -> str:
    return _NOT_ALNUM.sub("", _UPRIGHT.sub("", tex)).lower()


def _given_row(given: Given) -> str:
    shown = f"{tidy_tex(given.value)}{unit_tex(given.unit)}"
    # "500 g = 500 g" says nothing: a conversion to the same value is left out.
    if given.converted and _plain(given.converted) != _plain(shown):
        shown = f"{shown} = {tidy_tex(given.converted)}"
    return math_line(f"{tidy_symbol(given.symbol)} = {shown}")


def _given_section(solution: WorkedSolution, *, streaming: bool) -> tuple[str, ...]:
    rows = [_given_row(given) for given in solution.given]
    # While the block streams, the line naming the givens waits until they are all in:
    # one more given would change it, and the phone has drawn what went out.
    if rows and (not streaming or solution.required or solution.parts):
        naming = where_line(
            [
                (tidy_symbol(given.symbol), given.meaning)
                for given in solution.given
                if given.meaning
            ]
        )
        if naming:
            rows.append(naming)
    return tuple(rows)


def _working(part: Part) -> tuple[list[str], list[str], list[str]]:
    """The formula's rows, the substitution's and the steps', in the order written.

    A rearrangement or a move before any substitution belongs to the formula when there
    is one (``Solve for $t$`` under the law); with no formula it is a step, and so is
    every line after it. Lines after the first substitution carry it on.
    """
    formula: list[str] = []
    if part.formula is not None:
        formula.append(math_line(tidy_tex(part.formula.tex)))
    substitution: list[str] = []
    steps: list[str] = []
    for step in part.working:
        # With no formula, moves come first and the lines after them carry them on: one
        # Steps section, never a Substitution above the moves it follows.
        if step.kind == "substitution" and not (steps and part.formula is None):
            substitution.append(_line(step.tex))
            continue
        target = substitution if substitution else formula if part.formula else steps
        target.extend(_step_rows(step))
    return formula, substitution, steps


def _step_rows(step: Step) -> list[str]:
    if step.kind == "solve_for" and step.symbol:
        return [solve_for_line(tidy_symbol(step.symbol)), math_line(tidy_tex(step.tex))]
    return [_line(step.tex, step.move or None)]


def _answer_line(answer: Answer, layout: WorkedLayout) -> str:
    """The value with its unit, and a note ("east") upright inside the maths: the card draws
    one line of maths, where a word outside it would be read as italic letters."""
    value = f"{tidy_tex(answer.value)}{unit_tex(answer.unit)}"
    # A symbol that only repeats the unit ("cm | 10000 | cm") or is a word names nothing.
    named = answer.symbol and answer.symbol != answer.unit and not names_nothing(answer.symbol)
    symbol = tidy_symbol(answer.symbol) if named else ""
    shown = value if layout.law_heading or not symbol else f"{symbol} = {value}"
    note = _NOT_TEX.sub("", answer.note).strip()
    return math_line(f"{shown}\\ \\text{{{note}}}" if note else shown)


def _part_body(
    part: Part,
    layout: WorkedLayout,
    opening: tuple[tuple[str, ...], tuple[str, ...]],
    answer_heading: str | None,
) -> str:
    """One part's sections; with ``answer_heading``, closed by its answer's value."""
    formula, substitution, steps = _working(part)
    given, find = opening
    body = render_workout(
        Workout(
            given=given,
            find=find,
            formula=tuple(formula),
            substitution=tuple(substitution),
            steps=tuple(steps),
            # The formula's name heads it, never a note on its line.
            formula_heading=formula_heading(part.formula.name if part.formula else None),
        ),
        answer_heading=answer_heading if part.answers else None,
    )
    if not part.answers or answer_heading is None:
        return body
    values = _HARD_BREAK.join(_answer_line(answer, layout) for answer in part.answers)
    return f"{body}\n\n{values}"


def _find_rows(solution: WorkedSolution) -> tuple[str, ...]:
    return tuple(
        text_line(item.symbol, item.meaning or None)
        if names_nothing(item.symbol)
        else math_line(tidy_symbol(item.symbol), item.meaning or None)
        for item in solution.required
    )


def render_worked(
    solution: WorkedSolution, layout: WorkedLayout, *, streaming: bool = False
) -> str:
    """The solution as a worked reply. ``streaming``: the block is still being written, so
    a line that a later record could change is left out until it cannot."""
    # While the block streams, what is asked waits until the working shows whether the
    # question is in parts: in parts it is lettered, and a drawn line is never rewritten.
    settled = (
        not streaming
        or solution.labelled
        or any(part.formula or part.working or part.answers for part in solution.parts)
    )
    opening = (
        _given_section(solution, streaming=streaming),
        _find_rows(solution) if settled else (),
    )
    if not solution.labelled:
        part = solution.parts[0] if solution.parts else Part()
        return _part_body(part, layout, opening, ANSWER)
    # The one layout every question in parts has (``services/worked_parts``): one Given,
    # one Required naming what each part finds, then each part closed by its answer. What
    # is asked comes before the parts, so it is lettered by its own order: a part that
    # streams in later never rewrites it.
    required = opening[1]
    lettered = len(required) > 1
    parts = [
        WorkedPart(
            title=part.title
            or (solution.required[index].meaning if index < len(solution.required) else ""),
            working=_part_body(part, layout, ((), ()), None),
            after=_HARD_BREAK.join(_answer_line(answer, layout) for answer in part.answers),
        )
        for index, part in enumerate(solution.parts)
    ]
    asked = [f"({part_letter(index)}) {row}" for index, row in enumerate(required)]
    return render_parts(parts, opening[0], required=asked if lettered else required)
