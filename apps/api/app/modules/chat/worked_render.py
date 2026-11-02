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
from collections.abc import Sequence
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


def _given_rows(givens: Sequence[Given], *, naming: bool = True) -> tuple[str, ...]:
    """Each given on its line, then (with ``naming``) the ``where`` line naming them."""
    rows = [_given_row(given) for given in givens]
    named = where_line(
        [(tidy_symbol(given.symbol), given.meaning) for given in givens if given.meaning]
    )
    if rows and naming and named:
        rows.append(named)
    return tuple(rows)


def _given_section(solution: WorkedSolution, *, streaming: bool) -> tuple[str, ...]:
    # While the block streams, the line naming the givens waits until they are all in:
    # one more given would change it, and the phone has drawn what went out.
    complete = not streaming or bool(solution.required or solution.parts)
    return _given_rows(solution.given, naming=complete)


def _started(part: Part) -> bool:
    return bool(part.formula or part.working or part.answers)


def _symbol(given: Given) -> str:
    return tidy_symbol(given.symbol)


def _place_givens(
    shared: Sequence[Given], parts: Sequence[Part]
) -> tuple[list[Given], list[list[Given]]]:
    """(the givens left for the whole question, each part's own). A symbol has one value
    in a part, so a given written for the whole question whose symbol a part gives on its
    own is the other parts' (``d = 100`` first, ``d = 300`` after "part: b": the first is
    part (a)'s), and a symbol given once per part, all first, is one value per part in
    order. Anything else stays the whole question's."""
    placed: dict[int, list[int]] = {}  # a shared given's index → the parts it is placed in
    for symbol in dict.fromkeys(_symbol(given) for given in shared):
        values = [at for at, given in enumerate(shared) if _symbol(given) == symbol]
        lacking = [
            at for at, part in enumerate(parts) if all(_symbol(g) != symbol for g in part.given)
        ]
        if len(values) == 1 and 0 < len(lacking) < len(parts):
            placed[values[0]] = lacking
        elif len(values) > 1 and len(values) == len(lacking):
            placed.update((value, [at]) for value, at in zip(values, lacking, strict=True))
    own = [
        [given for at, given in enumerate(shared) if index in placed.get(at, ())] + list(part.given)
        for index, part in enumerate(parts)
    ]
    return [given for at, given in enumerate(shared) if at not in placed], own


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
    required = _find_rows(solution) if settled else ()
    # A question asking for several things may come apart at its next law
    # (``worked_solution.assemble``), so while it streams it is drawn in parts: a part
    # added later extends what was drawn, never moves it.
    in_parts = solution.labelled or (streaming and settled and len(solution.required) > 1)
    if not in_parts:
        part = solution.parts[0] if solution.parts else Part()
        opening = (_given_section(solution, streaming=streaming), required)
        return _part_body(part, layout, opening, ANSWER)
    return _render_in_parts(solution, layout, required, streaming=streaming)


def _render_in_parts(
    solution: WorkedSolution,
    layout: WorkedLayout,
    required: tuple[str, ...],
    *,
    streaming: bool,
) -> str:
    """The one layout every question in parts has (``services/worked_parts``), as the
    server's own parts: one Given holding what every part shares (``split_given``), one
    Required naming what each part finds, then each part with its own givens, closed by its
    answer. What is asked comes before the parts, so it is lettered by its own order: a
    part that streams in later never rewrites it. While the block streams, each given
    stays where it was written; the shared ones are drawn together once it is whole."""
    shown = list(solution.parts)
    if streaming:
        # A part waits for the answer above it: one written later, with the others at the
        # end, would land above what was drawn after it.
        unanswered = next((at for at, part in enumerate(shown) if not part.answers), None)
        shown = shown if unanswered is None else shown[: unanswered + 1]
        shared, own = list(solution.given), [list(part.given) for part in shown]
    else:
        shared, own = _place_givens(solution.given, shown)
    last = len(shown) - 1
    parts = [
        WorkedPart(
            title=part.title
            or (solution.required[index].meaning if index < len(solution.required) else ""),
            working=_part_body(part, layout, ((), ()), None),
            after=_HARD_BREAK.join(_answer_line(answer, layout) for answer in part.answers),
            # The last part's where-line waits, while it streams, until its givens are in.
            given=_given_rows(own[index], naming=not streaming or index < last or _started(part)),
        )
        for index, part in enumerate(shown)
    ]
    asked = [f"({part_letter(index)}) {row}" for index, row in enumerate(required)]
    complete = not streaming or bool(required or solution.parts)
    return render_parts(
        parts,
        _given_rows(shared, naming=complete),
        required=asked if len(required) > 1 else required,
        hoist=not streaming,
    )
