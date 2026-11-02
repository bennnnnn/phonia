"""A worked solution the model writes as parts, read and validated before it is laid out.

When no solver checked a calculation, the model wrote the worked layout itself and it came
out differently each time: bold inline "**Given:** …", no Answer heading, no card
(2026-11-01). Now the model writes the parts in a ```worked block, one record per line,
its fields split by ``|`` (``prompt_constants.worked``):

    given: t | 40 | min | time | 2400\\,\\mathrm{s}
    given (b): t | 1 | s | time
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
_RECORD = re.compile(
    r"^\s*(?:[-*]\s+)?(?P<key>[A-Za-z][A-Za-z_ ]{2,13}?)\s*"
    r"(?:\(\s*(?P<part>[A-Ha-h])\s*\)\s*)?:\s*(?P<rest>.*)$"
)
# A given only some parts use carries its part's letter: "given (a): t | 1 | s", or the
# letter before the symbol, "given: (a) t | 1 | s".
_LETTERED_SYMBOL = re.compile(r"^\(\s*(?P<part>[A-Ha-h])\s*\)\s+(?P<symbol>\S.*)$")
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
    # The letter of the one part that uses it; empty for a given the whole question uses.
    part: Annotated[str, StringConstraints(pattern=r"^[a-h]?$")] = ""


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
    # The givens written after this part's ``part`` record: this part's own.
    given: tuple[Given, ...] = ()
    formula: Formula | None = None
    working: tuple[Step, ...] = ()
    answers: tuple[Answer, ...] = ()


class WorkedSolution(_Record):
    given: tuple[Given, ...] = ()
    required: tuple[Required, ...] = ()
    parts: tuple[Part, ...] = Field(default=(), max_length=MAX_PARTS)
    # A ``part`` record was read, even before any part has a line of its own.
    in_parts: bool = False

    @property
    def labelled(self) -> bool:
        """A question in parts: a ``part`` record gave a part its letter."""
        return self.in_parts or any(part.letter for part in self.parts)


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
        fields = _fields(key, rest)
        if key == "given":
            fields = _lettered(fields, match.group("part"))
        elif key == "part":
            fields = _untitled(fields)
        return _validated(key, fields)
    except ValidationError:
        return None


# The contract's own placeholders, copied as a part's title (live, 2026-11-02): no title,
# so the part is named by what is asked.
_PLACEHOLDER_TITLES = frozenset({"what it finds", "what is asked"})


def _untitled(fields: dict[str, str]) -> dict[str, str]:
    title = fields.get("title", "")
    return {**fields, "title": ""} if title.lower().strip(" .") in _PLACEHOLDER_TITLES else fields


def _lettered(fields: dict[str, str], part: str | None) -> dict[str, str]:
    """A given's part letter, from its key (``given (a):``) or before its symbol."""
    lettered = _LETTERED_SYMBOL.match(fields.get("symbol", ""))
    if lettered is not None:
        fields = {**fields, "symbol": lettered.group("symbol")}
        part = part or lettered.group("part")
    return {**fields, "part": part.lower()} if part else fields


def _letter(label: str, index: int) -> str:
    """``(a)``, ``a.``, ``A``: the part's letter; anything else, its place."""
    bare = label.strip().strip("().: ").lower()
    return bare if len(bare) == 1 and bare in "abcdefgh" else "abcdefgh"[min(index, 7)]


@dataclass
class _PartDraft:
    letter: str = ""
    title: str = ""
    given: list[Given] = field(default_factory=list)
    formula: Formula | None = None
    working: list[Step] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)

    @property
    def started(self) -> bool:
        return bool(self.formula or self.working or self.answers)

    @property
    def reached_a_value(self) -> bool:
        """Its working was carried to a value: substituted into, or answered."""
        return bool(self.answers) or any(step.kind == "substitution" for step in self.working)

    def computes(self, symbol: str) -> bool:
        """A line of its working gives ``symbol`` a value (``v_1 = \\frac{100}{5}``)."""
        target = _bare(symbol)
        return bool(target) and any(
            _bare(step.tex.split("=", 1)[0]) == target for step in self.working if "=" in step.tex
        )

    @property
    def has_content(self) -> bool:
        """A line of its own to show: a part with a label and nothing else is no part."""
        return self.started or bool(self.given)

    def add(self, record: Given | Formula | Step | Answer) -> None:
        if isinstance(record, Given):
            self.given.append(record)
        elif isinstance(record, Answer):
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
            given=tuple(self.given),
            formula=self.formula,
            working=tuple(self.working),
            answers=tuple(self.answers),
        )


def _asked_letter(label: PartLabel, asked: list[Required], index: int) -> str:
    """The label's letter; a title that names exactly one thing asked is that one's part,
    whatever letter the model wrote ("part: a | speed of the train" after the car's
    answer, live 2026-11-02, is the second thing asked: part (b))."""
    title = label.title.strip().lower()
    matches = [at for at, item in enumerate(asked) if title and item.meaning.lower() == title]
    return _letter("", matches[0]) if len(matches) == 1 else _letter(label.letter, index)


def _labelled_part(
    drafts: list[_PartDraft],
    current: int,
    label: PartLabel,
    *,
    first: bool,
    asked: list[Required],
) -> tuple[int, bool]:
    """The draft a ``part`` record opens, by its index, and whether the label closed it
    (it came after that part's answer). The first label names a part begun and not yet
    answered ("formula: …" then "part: a"); a label after an unlabelled part's working
    with that part's own letter names it ("…, answer: …, part: a", live 2026-11-02, so
    what follows is the next part); a letter named before is that part again, whatever
    came between; any other label opens a part of its own."""
    letter = _asked_letter(label, asked, len(drafts))
    named = next((at for at, draft in enumerate(drafts) if draft.letter == letter), None)
    if named is not None:
        drafts[named].title = drafts[named].title or label.title
        return named, False
    draft = drafts[current]
    if first and not draft.answers:
        # The first part's fallback letter is (a), whatever index the drafts reached.
        draft.letter, draft.title = _asked_letter(label, asked, 0), label.title
        return current, False
    if not draft.letter and draft.has_content:
        # The part above, unlabelled: a label naming what it was asked for (or naming
        # nothing else) with its letter is its own; one naming another ask is the next.
        own = asked[current].meaning.lower() if current < len(asked) else ""
        title = label.title.strip().lower()
        if letter == _letter("", current) and (not own or not title or title == own):
            draft.letter, draft.title = letter, label.title
            return current, bool(draft.answers)
    if len(drafts) >= MAX_PARTS:
        return current, False
    if "abcdefgh".find(letter) < len(drafts):
        # A letter already behind the parts shown ("part: a" after part (a)) is the next.
        letter = _letter("", len(drafts))
    drafts.append(_PartDraft(letter=letter, title=label.title))
    return len(drafts) - 1, False


def _bare(tex: str) -> str:
    return re.sub(r"[\s{}$]", "", tex)


def _unlabelled_part(
    drafts: list[_PartDraft], current: int, record: Formula | Step | Answer, asked: int
) -> int:
    """The draft an unlabelled record goes to. A question asking for several things is in
    parts whether or not the model labelled them: a new law after the working reached a
    value opens the next part, while fewer parts than things asked are open, and an
    answer goes to the first part not yet answered whose working gave its symbol a value."""
    if isinstance(record, Formula):
        opens = drafts[current].reached_a_value and len(drafts) < min(asked, MAX_PARTS)
        if opens:
            drafts.append(_PartDraft(formula=record))
            return len(drafts) - 1
    if isinstance(record, Answer) and len(drafts) > 1:
        # Answers written together at the end are the parts' in order.
        waiting = [
            at
            for at, draft in enumerate(drafts)
            if not draft.answers and (not record.symbol or draft.computes(record.symbol))
        ]
        if waiting:
            drafts[waiting[0]].answers.append(record)
            return current
    drafts[current].add(record)
    return current


def assemble(records: list[RecordModel]) -> WorkedSolution:
    """The records in the order written, as one solution. Before the first ``part``, the
    givens and what is asked are the whole question's, and a formula or working is the
    first part's, and a given lettered with its part (``given (a):``) keeps its letter in
    the one Given. After a ``part`` record every record is that part's, its givens too, so a given one part uses is never mixed with another
    part's; a label written after its part's answer closes that part. A part that holds
    nothing (a label alone) is left out, so the parts shown are lettered in order. With no label,
    a question asking for several things still comes apart at each new law
    (``_unlabelled_part``)."""
    given: list[Given] = []
    required: list[Required] = []
    drafts = [_PartDraft()]
    current = 0
    labelled = False
    # The current part's label came after its answer: the next line starts the next part.
    closed = False
    for record in records:
        if isinstance(record, Required):
            required.append(record)
        elif isinstance(record, Given) and not labelled:
            given.append(record)
        elif isinstance(record, PartLabel):
            current, closed = _labelled_part(
                drafts, current, record, first=not labelled, asked=required
            )
            labelled = True
        elif labelled or isinstance(record, Given):
            if closed and len(drafts) < MAX_PARTS:
                drafts.append(_PartDraft())
                current, closed = len(drafts) - 1, False
            # A given after a part's label is that part's, whatever letter it carries.
            drafts[current].add(
                record.model_copy(update={"part": ""}) if isinstance(record, Given) else record
            )
        else:
            current = _unlabelled_part(drafts, current, record, len(required))
    parts = tuple(draft.part() for draft in drafts if draft.has_content)
    return WorkedSolution(
        given=tuple(given),
        required=tuple(required),
        parts=parts,
        in_parts=labelled or len(parts) > 1,
    )
