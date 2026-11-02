"""A worked solution the model writes as parts, read and validated before it is laid out.

When no solver checked a calculation, the model wrote the worked layout itself and it came
out differently each time: bold inline "**Given:** …", no Answer heading, no card
(2026-11-01). Now the model writes the parts in a ```worked block, one record per line,
its fields split by ``|`` (``prompt_constants.worked``):

    given: t | 40 | min | time | 2400\\,\\mathrm{s}
    required: s | displacement
    formula: Constant velocity | s = v t
    solve_for: t | t = \\frac{s}{v}
    step: 2x = 8 | subtract 3 from both sides
    substitution: s = 20 \\times 120
    answer: s | 2400 | m | east
    part: a | Distance in centimetres

Lines, not JSON: LaTeX in a JSON string loses its backslashes silently (the ``\\t`` of
``\\times`` is a tab), and a line is whole as soon as it ends, so the layout streams.
Each record is validated with Pydantic (CLAUDE.md golden rule 6); a line that is no
record, or fails, is left out. ``worked_render`` lays the solution out with
``render_workout``, the renderer of every verified reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

# Maths in LaTeX: one line, no fence, no $ (the renderer adds them).
Tex = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Words = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
Symbol = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
OptionalTex = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]

# The fields each record takes, in order; the last one keeps any further "|".
_FIELDS: dict[str, tuple[str, ...]] = {
    "given": ("symbol", "value", "unit", "meaning", "converted"),
    "required": ("symbol", "meaning"),
    "formula": ("name", "tex"),
    "solve_for": ("symbol", "tex"),
    "step": ("tex", "move"),
    "substitution": ("tex",),
    "answer": ("symbol", "value", "unit", "note"),
    "part": ("letter", "title"),
}
# Records whose first field may hold the symbol and its value together: "v = 20 | m/s".
_SYMBOL_AND_VALUE = frozenset({"given", "answer"})
# Fields that hold maths: a model's $ … $ or \( … \) around them is dropped.
_TEX_FIELDS = frozenset({"symbol", "value", "tex", "converted"})
_RECORD = re.compile(r"^\s*(?:[-*]\s+)?(?P<key>[A-Za-z][A-Za-z_ ]{2,13}?)\s*:\s*(?P<rest>.*)$")
_DELIMITERS = (("$$", "$$"), ("$", "$"), ("\\(", "\\)"), ("\\[", "\\]"))
MAX_PARTS = 8


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Given(_Record):
    symbol: Symbol
    value: Tex
    unit: Short = ""
    meaning: Words = ""
    # The value in the unit the formula uses, when that differs (``2400\,\mathrm{s}``).
    converted: OptionalTex = ""


class Required(_Record):
    symbol: Symbol
    meaning: Words = ""


class Formula(_Record):
    name: Words = ""
    tex: Tex


class Step(_Record):
    """One state of the working: a rearrangement for ``symbol`` (``solve_for``), an
    equation changed by ``move`` (``step``), or a line of substitution."""

    kind: Literal["solve_for", "step", "substitution"]
    tex: Tex
    move: Words = ""
    symbol: Short = ""


class Answer(_Record):
    symbol: Short = ""
    value: Tex
    unit: Short = ""
    note: Words = ""


class PartLabel(_Record):
    letter: Short = ""
    title: Words = ""


class Part(_Record):
    letter: Annotated[str, StringConstraints(pattern=r"^[a-h]?$")] = ""
    title: Words = ""
    formula: Formula | None = None
    working: tuple[Step, ...] = ()
    answers: tuple[Answer, ...] = ()


class WorkedSolution(_Record):
    given: tuple[Given, ...] = ()
    required: tuple[Required, ...] = ()
    parts: tuple[Part, ...] = Field(default=(), max_length=MAX_PARTS)

    @property
    def labelled(self) -> bool:
        """A question in parts: a ``part`` record gave a part its letter."""
        return any(part.letter for part in self.parts)


RecordModel = Given | Required | Formula | Step | Answer | PartLabel


def _unwrapped(value: str) -> str:
    text = value.strip()
    for opener, closer in _DELIMITERS:
        wrapped = text.startswith(opener) and text.endswith(closer)
        if wrapped and len(text) > len(opener) + len(closer):
            return text[len(opener) : -len(closer)].strip()
    return text


def _split(text: str, count: int) -> list[str]:
    """``count`` fields at most; the last keeps any further ``|``."""
    return [value.strip() for value in text.split("|", max(0, count - 1))]


def _fields(key: str, rest: str) -> dict[str, str]:
    names = _FIELDS[key]
    values = _split(rest, len(names))
    if key in _SYMBOL_AND_VALUE and "=" in values[0]:
        symbol, _, value = values[0].partition("=")
        tail = rest.split("|", 1)[1] if "|" in rest else ""
        values = [symbol, value, *(_split(tail, len(names) - 2) if tail.strip() else [])]
    elif key == "answer" and len(values) == 1:
        values = ["", values[0]]  # the value alone, no symbol
    elif key == "formula" and len(values) == 1:
        values = ["", values[0]]  # the formula alone, no name
    return {
        name: _unwrapped(value) if name in _TEX_FIELDS else value
        for name, value in zip(names, values, strict=False)
        if value
    }


_MODELS: dict[str, type[Given | Required | Formula | Answer | PartLabel]] = {
    "given": Given,
    "required": Required,
    "formula": Formula,
    "answer": Answer,
    "part": PartLabel,
}


def _validated(key: str, fields: dict[str, str]) -> RecordModel:
    if key in ("solve_for", "step", "substitution"):
        return Step.model_validate({"kind": key, **fields})
    return _MODELS[key].model_validate(fields)


def read_record(line: str) -> RecordModel | None:
    """One line of a ```worked block as a validated record, or None."""
    match = _RECORD.match(line)
    if match is None:
        return None
    key = match.group("key").strip().lower().replace(" ", "_")
    rest = match.group("rest").strip()
    if key not in _FIELDS or not rest or "```" in rest:
        return None
    try:
        return _validated(key, _fields(key, rest))
    except ValidationError:
        return None


def _letter(label: str, index: int) -> str:
    """``(a)``, ``a.``, ``A``: the part's letter; anything else, its place."""
    bare = label.strip().strip("().: ").lower()
    return bare if len(bare) == 1 and bare in "abcdefgh" else "abcdefgh"[min(index, 7)]


@dataclass
class _PartDraft:
    letter: str = ""
    title: str = ""
    formula: Formula | None = None
    working: list[Step] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)

    @property
    def started(self) -> bool:
        return bool(self.formula or self.working or self.answers)

    def add(self, record: Formula | Step | Answer) -> None:
        if isinstance(record, Answer):
            self.answers.append(record)
        elif isinstance(record, Step):
            self.working.append(record)
        elif self.formula is None and not self.working:
            self.formula = record
        else:  # a second law in one part is a line of its working
            self.working.append(Step(kind="step", tex=record.tex, move=record.name))

    def part(self) -> Part:
        return Part(
            letter=self.letter,
            title=self.title,
            formula=self.formula,
            working=tuple(self.working),
            answers=tuple(self.answers),
        )


def assemble(records: list[RecordModel]) -> WorkedSolution:
    """The records in the order written, as one solution: the givens and what is asked,
    then each part's formula, working and answer. Records before the first ``part`` are
    the first part's."""
    given: list[Given] = []
    required: list[Required] = []
    drafts = [_PartDraft()]
    labelled = False
    for record in records:
        if isinstance(record, Given):
            given.append(record)
        elif isinstance(record, Required):
            required.append(record)
        elif isinstance(record, PartLabel):
            # The first label names a part begun and not yet answered ("formula: …" then
            # "part: a"); a part already answered is finished.
            begun = labelled or bool(drafts[-1].answers)
            fresh = begun and len(drafts) < MAX_PARTS
            letter = _letter(record.letter, len(drafts) - (0 if fresh else 1))
            if labelled and letter == drafts[-1].letter:
                # The same part named again (before its substitution): still that part.
                drafts[-1].title = drafts[-1].title or record.title
                continue
            if fresh:
                drafts.append(_PartDraft())
            labelled = True
            drafts[-1].letter, drafts[-1].title = letter, record.title
        else:
            drafts[-1].add(record)
    parts = tuple(draft.part() for draft in drafts if draft.started or draft.title)
    return WorkedSolution(given=tuple(given), required=tuple(required), parts=parts)
