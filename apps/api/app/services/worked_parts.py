"""One layout for a worked answer in parts, whoever worked it.

A question in parts reads as a single worked answer does, once:

- **Given**: the givens every part shares, closed by one ``where`` line; a given only one
  part uses (or a symbol with another value in another part) is listed at that part
- **Required**: one line per part, ``(a) $v$ (speed after 1 s)``
- **Solution**, then each part: its label (``**(a) Speed after 1 s**``), its formula
  under its name's heading, its substitution or steps, and **Answer (a)** with that part's
  card; a hairline between parts

Physics' own parts (``modules/physics/direct.py``), the separate questions of one message
solved one by one (``services/subjects/dispatch.py``) and the model-written ```worked
block in parts (``modules/chat/worked_render.py``) all render here. Before November 2026
the separate questions came back as whole replies one after another: the givens repeated
under each part, the part above its givens, and no card under any answer (the finalize
pass for one verified part dropped the others').
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.md_fence_scan import iter_fences
from app.services.workout import (
    ANSWER,
    GIVEN,
    REQUIRED,
    REQUIRED_HEADINGS,
    SOLUTION,
    asked_line,
)

_HARD_BREAK = "  \n"
# "$v_0$ = initial speed" or "$m_1$, $m_2$ = masses": one name in a where-line.
_WHERE_PIECE = re.compile(r"[,;] (?=\$[^$]+\$(?:, \$[^$]+\$)* = )")


@dataclass(frozen=True)
class WorkedPart:
    """One part. ``working``: its rendered sections, from the formula to the last line
    before its answer. ``answer``: its card's body, or None when the value follows the
    heading as a line (``after``) for finalize to card. ``after``: what follows the card
    (a picture)."""

    title: str
    working: str
    answer: str | None = None
    after: str = ""
    required: tuple[str, ...] = ()
    given: tuple[str, ...] = ()


def part_letter(index: int) -> str:
    """``a``, ``b``, … for a part; past ``z`` its number, so no part is ever dropped."""
    return chr(ord("a") + index) if index < 26 else str(index + 1)


def _section(heading: str, lines: Sequence[str]) -> str:
    return f"**{heading}**{_HARD_BREAK}" + _HARD_BREAK.join(lines)


def _where_pieces(line: str) -> list[str]:
    """``$a$ = x, $b$, $c$ = ys`` → ``["$a$ = x", "$b$, $c$ = ys"]``: a comma between two
    symbols of one meaning is no cut."""
    text = line.removeprefix("where ")
    pieces: list[str] = []
    start = 0
    for cut in _WHERE_PIECE.finditer(text):
        if " = " in text[start : cut.start()]:
            pieces.append(text[start : cut.start()].strip())
            start = cut.end()
    pieces.append(text[start:].strip())
    return [piece for piece in pieces if piece]


def merged_given(lines: Sequence[str]) -> list[str]:
    """Each given once, in order, then one ``where`` line naming every symbol once."""
    values: list[str] = []
    names: list[str] = []
    for line in lines:
        text = line.strip()
        if text.startswith("where "):
            names.extend(piece for piece in _where_pieces(text) if piece not in names)
        elif text and text not in values:
            values.append(text)
    if names:
        grouped = any(re.search(r"\$, \$", piece) for piece in names)
        values.append(f"where {('; ' if grouped else ', ').join(names)}")
    return values


_VALUE_SYMBOL = re.compile(r"^\$\s*(?P<symbol>[^=$]+?)\s*=")
_PIECE_SYMBOLS = re.compile(r"\$([^$]+)\$")


def _value_key(line: str) -> str:
    """What a given line gives: its symbol, or the whole line when it names none."""
    match = _VALUE_SYMBOL.match(line)
    return match.group("symbol").strip() if match else line


def _piece_symbols(piece: str) -> set[str]:
    return {symbol.strip() for symbol in _PIECE_SYMBOLS.findall(piece.split(" = ", 1)[0])}


def _values_and_names(lines: Sequence[str]) -> tuple[list[str], list[str]]:
    values = [line.strip() for line in lines if line.strip() and not line.startswith("where ")]
    names = [piece for line in lines if line.startswith("where ") for piece in _where_pieces(line)]
    return values, names


def _given_section(values: Sequence[str], names: Sequence[str]) -> list[str]:
    """``values`` with a where-line naming only their symbols."""
    keys = {_value_key(value) for value in values}
    named = [piece for piece in names if _piece_symbols(piece) & keys]
    return merged_given([*values, *(f"where {piece}" for piece in named)])


def split_given(parts: Sequence[WorkedPart]) -> tuple[list[str], list[list[str]]]:
    """(the givens every part shares, each part's own). A given is shared when every part
    gives it with the same value; one only some parts use, or a symbol with another value
    in another part (t = 1 s for (a) while (b) asks for t), stays with its part."""
    read = [_values_and_names(part.given) for part in parts]
    names = [piece for _values, part_names in read for piece in part_names]
    if len(parts) < 2:
        values = [value for part_values, _names in read for value in part_values]
        return _given_section(values, names), [[] for _part in parts]
    shared = [value for value in read[0][0] if all(value in values for values, _n in read[1:])]
    own = [[value for value in values if value not in shared] for values, _n in read]
    # A symbol a part gives on its own is named at that part, never in the shared line.
    own_keys = {_value_key(value) for values in own for value in values}
    shared_names = [piece for piece in names if not _piece_symbols(piece) & own_keys]
    return _given_section(shared, shared_names), [
        _given_section(values, part_names) if values else []
        for values, (_v, part_names) in zip(own, read, strict=True)
    ]


def _required_line(letter: str, line: str) -> str:
    """``(a) $v$ (speed)``: the part's letter before what it finds, as its solver named it."""
    return f"({letter}) {line}"


def render_parts(
    parts: Sequence[WorkedPart],
    given: Sequence[str] = (),
    *,
    required: Sequence[str] = (),
    hoist: bool = True,
) -> str:
    """The question in parts in the one layout: Given and Required once, then Solution and
    each part closed by its own Answer and card. ``required``: lines no part owns.
    ``hoist`` False keeps each part's givens at the part, for a reply still streaming: a
    given moved up to the shared Given would rewrite what the phone has drawn."""
    if hoist:
        shared, own = split_given(parts)
    else:
        shared, own = [], [merged_given(part.given) for part in parts]
    givens = merged_given([*given, *shared])
    asked = [
        asked_line(line)
        for line in (
            *required,
            *(
                _required_line(part_letter(index), line)
                for index, part in enumerate(parts)
                for line in part.required
            ),
        )
    ]
    opening = [
        _section(heading, lines) for heading, lines in ((GIVEN, givens), (REQUIRED, asked)) if lines
    ]
    sections: list[str] = []
    for index, part in enumerate(parts):
        letter = part_letter(index)
        label = f"**({letter}) {part.title.strip()}**" if part.title.strip() else ""
        # A given only this part uses is listed at the part, before its formula.
        mine = _section(GIVEN, own[index]) if own[index] else ""
        pieces = [label, mine, part.working.strip()]
        # A part still streaming has no answer yet: its heading waits with it.
        if part.answer is not None or part.after.strip():
            pieces.append(f"**{ANSWER} ({letter})**")
        if part.answer is not None:
            pieces.append(f"```answer\n{part.answer.strip()}\n```")
        pieces.append(part.after.strip())
        sections.append("\n\n".join(piece for piece in pieces if piece))
    head = "\n\n".join([*opening, f"**{SOLUTION}**"]) if opening else ""
    body = "\n\n---\n\n".join(sections)
    return f"{head}\n\n{body}" if head else body


_HEADING = re.compile(r"^\*\*(?P<title>[^*\n]+)\*\*(?:  )?$")


@dataclass(frozen=True)
class _Read:
    given: tuple[str, ...]
    required: tuple[str, ...]
    working: str
    answer: str
    after: str


def read_worked_reply(reply: str) -> _Read | None:
    """A whole worked reply the server wrote, back in its sections; None for any other
    shape (a lead sentence, no Answer heading, no card), which is then shown as written."""
    head, found, tail = reply.strip().partition(f"\n\n**{ANSWER}**\n\n")
    card = next(iter_fences(tail), None) if found else None
    if card is None or card.start != 0 or card.lang != "answer" or not card.closed:
        return None
    answer = tail[card.body_start : card.body_end].strip("\n")
    after = tail[card.end :].strip()
    given: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    working: list[str] = []
    for block in head.split("\n\n"):
        first, _, rest = block.partition("\n")
        heading = _HEADING.match(first)
        title = heading.group("title") if heading else ""
        lines = tuple(
            line.strip() for line in rest.replace("  \n", "\n").split("\n") if line.strip()
        )
        if title == GIVEN and not working:
            given = lines
        elif title in REQUIRED_HEADINGS and not working:
            required = lines
        elif title == SOLUTION and not working:
            continue
        elif not given and not required:
            return None  # a lead before the givens: not the worked layout
        else:
            working.append(block)
    if not required or not working:
        return None
    return _Read(given, required, "\n\n".join(working), answer, after)


def parts_in_one_layout(questions: Sequence[str], replies: Sequence[str]) -> str | None:
    """Separate questions' worked replies as one question in parts; None when a reply is
    not the worked layout."""
    parts: list[WorkedPart] = []
    for question, reply in zip(questions, replies, strict=True):
        read = read_worked_reply(reply)
        if read is None:
            return None
        parts.append(
            WorkedPart(
                # The part's question as the student wrote it, never reworded.
                title=question.strip(),
                working=read.working,
                answer=read.answer,
                after=read.after,
                required=read.required,
                given=read.given,
            )
        )
    return render_parts(parts)
