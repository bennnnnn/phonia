"""Whether a reply still works a subject problem: the problem's own ground it reuses.

Live (2026-10-25, one chat with the free model): two lines after a rectangle problem,
"cool. i'm going to lisbon next month for 4 days, what should i not miss?" got "What if
perimeter was 48 cm?" under its travel tips. A line that names a topic of its own
(``follow_up_thread``) is checked here against its reply. Still on the problem, a reply
reuses its ground: its nouns ("perimeter", "ball"), its numbers with their units (19.8 m/s,
written any way), and its maths ("x^2 - 5x + 6", "x = 2", the variable x). A day plan's
"Day 1" or a recipe's "2 eggs" is no ground, a single digit counts only with its unit, and
one noun is not enough: a Lisbon itinerary may mention "the Bairro Alto area".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chat.follow_up_units import (
    QUANTITY,
    SYMBOLS,
    Quantity,
    quantities,
    read_unit,
    unit_kind,
)
from app.modules.chat.follow_up_words import LATIN, MEASURES, TOPIC_WORD, topic_words
from app.services.text_normalize import straighten_apostrophes

# Enough of the problem's ground: two of its nouns, a noun and a number, a step of its
# maths and its variable, or one number with its unit.
_ENOUGH = 2.0
# Half a tie: a noun only the problem's reply used (a worked answer says many words), or
# an everyday noun a problem borrows that only this reply uses ("a perfect length for
# Lisbon", "the Baixa area", "heat the water" in a pasta recipe).
_HALF = 0.5
_EVERYDAY_NOUNS = frozenset(
    """area building cost distance food friend ground heat height house length money people
    price room size time water weight width""".split()
)
# 19.8 m/s or 153.9 again is the problem's own quantity; 36 alone, or "2 mol", one thing
# it said.
_NUMBER_WITH_UNIT = 2.0
_NUMBER = 1.0
# A reply's start says what it works on; this keeps a long one quick to read.
_TURN_CHARS = 6000
# The turn's words are read from three letters: "the hit" is the problem's "hits", and a
# problem word is never shorter than three letters once its plural "s" is off.
_TURN_WORD = re.compile(rf"[{LATIN}]{{3,}}")
# Maths written out: "x^2-5x+6=0", "(x-2)(x-3)", "v=gt", in Latin or Greek letters.
_LETTER = re.compile("[a-z\u03b1-\u03c9]")
_PIECE = re.compile("[a-z\u03b1-\u03c90-9.^()+\\-*/=]+")
_OPERATOR = re.compile(r"[=+\-*/^]")
_DIGIT_OR_POWER = re.compile(r"[\d^]")
_GROUP = re.compile(r"\(([^()]*)\)")
_VARIABLE = re.compile("(?<![a-z\u03b1-\u03c9])[a-z\u03b1-\u03c9](?![a-z\u03b1-\u03c9])")
_LATEX_SPACING = re.compile(r"\\(?:left|right|[,!;])")
_LATEX_TIMES = re.compile(r"\\(?:cdot|times)")
_LATEX_FRACTION = re.compile(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}")
_SPACED_OPERATOR = re.compile(r"\s*([=+\-*/^])\s*")


@dataclass(frozen=True)
class _Ground:
    nouns: frozenset[str]
    quantities: tuple[Quantity, ...]
    maths: frozenset[str]

    @property
    def variables(self) -> frozenset[str]:
        return frozenset(v for piece in self.maths for v in _VARIABLE.findall(piece))


def works_the_problem(problem: str, problem_reply: str | None, line: str, answer: str) -> bool:
    """Whether ``answer``, the reply to ``line``, reuses enough of what ``problem`` and its
    first reply said to be still working it. The ground is the reply's alone: "thanks! my
    sister finished her homework, what's a quick dinner?" names the homework problem's
    words, and its recipe shares none. A noun the line names counts in full when the reply
    shares it too."""
    asked, replied = _ground(problem), _ground(problem_reply or "")
    said = _ground(answer, _TURN_WORD)
    named = _ground(line, _TURN_WORD).nouns
    nouns = sum(
        1.0 if noun in named or noun not in _EVERYDAY_NOUNS else _HALF
        for noun in said.nouns & asked.nouns
    ) + _HALF * len((said.nouns & replied.nouns) - asked.nouns)
    maths = len(said.maths & (asked.maths | replied.maths)) + float(
        bool(said.variables & (asked.variables | replied.variables))
    )
    numbers = _shared_numbers(said.quantities, asked.quantities + replied.quantities)
    return nouns + maths + numbers >= _ENOUGH


def _ground(text: str, pattern: re.Pattern[str] = TOPIC_WORD) -> _Ground:
    plain = straighten_apostrophes(text[:_TURN_CHARS]).translate(SYMBOLS)
    nouns = topic_words(plain, pattern) - MEASURES
    return _Ground(nouns, tuple(quantities(plain)), _maths(plain))


def _shared_numbers(said: tuple[Quantity, ...], ground: tuple[Quantity, ...]) -> float:
    """The numbers the problem used, each with a unit of the same kind, or with none on
    either side: "20 minutes" is not the ball's 20 m, and "10 minutes" is not the 10 kg
    that "F = 10 * 3" restates bare. A single digit without its unit counts for nothing."""
    units: dict[str, set[str]] = {}
    for quantity in ground:
        units.setdefault(_size(quantity.number), set()).update(
            [quantity.unit] if quantity.unit else []
        )
    with_unit: set[str] = set()
    alone: set[str] = set()
    for quantity in said:
        known = units.get(_size(quantity.number))
        if known is None:
            continue
        if _same_kind(quantity.unit, known):
            (alone if quantity.small else with_unit).add(quantity.number)
        elif not (quantity.unit and known) and not quantity.small:
            # "153.9" again is the problem's answer; "100" may be anything.
            (with_unit if "." in quantity.number else alone).add(quantity.number)
    return _NUMBER_WITH_UNIT * len(with_unit) + _NUMBER * len(alone - with_unit)


def _size(number: str) -> str:
    """A number without its sign: a reply says "5 m/s^2" of the problem's -5 m/s^2."""
    return number.lstrip("-")


def _same_kind(unit: str | None, known: set[str]) -> bool:
    return unit is not None and any(unit_kind(unit) == unit_kind(other) for other in known)


def _maths(text: str) -> frozenset[str]:
    """The maths written in ``text``: each expression or equation, its sides and its
    bracketed parts, units taken off first so "9.8 m/s^2" is the number 9.8."""
    pieces: set[str] = set()
    for piece in _PIECE.findall(_written_maths(_without_units(text)).casefold()):
        piece = _balanced(piece.strip("."))
        if not (_LETTER.search(piece) and _OPERATOR.search(piece)):
            continue
        if not (_DIGIT_OR_POWER.search(piece) or "=" in piece):
            continue
        pieces.add(piece)
        parts = [*piece.split("="), *_GROUP.findall(piece)]
        pieces.update(
            _balanced(part)
            for part in parts
            if _LETTER.search(part) and _DIGIT_OR_POWER.search(part)
        )
    return frozenset(pieces)


def _balanced(piece: str) -> str:
    """Without the bracket a sentence opened or closed: "(x-2)(x-3)=0" stays whole."""
    opened, closed = piece.count("("), piece.count(")")
    start, end = 0, len(piece)
    while start < end and piece[start] == "(" and opened > closed:
        start, opened = start + 1, opened - 1
    while end > start and piece[end - 1] == ")" and closed > opened:
        end, closed = end - 1, closed - 1
    return piece[start:end]


def _without_units(text: str) -> str:
    def number_only(match: re.Match[str]) -> str:
        currency, sign, whole, _split, _part, space, unit = match.groups()
        if currency or read_unit(space or "", unit or ""):
            return f"{sign}{whole}"
        return match.group(0)

    return QUANTITY.sub(number_only, text)


def _written_maths(text: str) -> str:
    """LaTeX and spaced maths in one plain form: "$x - 2 = 0$" is "x-2=0"."""
    text = _LATEX_SPACING.sub("", text)
    text = _LATEX_TIMES.sub("*", text)
    text = _LATEX_FRACTION.sub(r"(\1)/(\2)", text)
    text = text.replace("$", " ").replace("{", "(").replace("}", ")")
    return _SPACED_OPERATOR.sub(r"\1", text)
