"""A follow-up that changes an amount of a reaction problem, or asks for another substance.

Live failure (2026-10-25): after "how much water do i get if i burn like 4g of h2", the student
asked "ok back to the first one. what if i only had 16g of o2": 4 g of H2 with only 16 g of O2,
so the oxygen runs out first and limits the water to 18 g. The free model opened with "8 g of
hydrogen", wrote "Wait, I made a mistake" and answered another question. The line keeps the
reaction and changes one thing:

- an amount of a substance the problem states replaces it ("what if it was 10 g of h2");
- an amount of another reactant joins it, and the limiting reagent decides ("what if i only had
  16g of o2");
- another substance of the reaction is asked ("and how much o2 do i need", "what about the
  co2"); asked as made it must be a product, asked as needed a reactant.

The problem is read from its own text, written out again whole (balanced equation first) and
used only when it verifies (``followup.py``). It is the latest earlier problem whose reaction
holds the substance the line names. The walk back passes only a newer user line with no number
in it at all (no digit, also none inside "co2", and no number word) that chemistry reads
nothing from: "whats a mole again", "lol ok". Any other line may be a problem of its own, and
"what about 100 g of water" after "raise 50 grams of water by 10 degrees" is not the reaction's
(review, 2026-10-25: a list of units missed "grams", "moles", "liter" and "$", and the methane
was answered twice). So the live chat's "back to the first one", five lines after the problem
and past "is it 4.5 or 36??", goes to the model; with two reactions that hold the substance,
"the first one" is not read either. A change of a change ("what if i had 8 g of h2" after "what
if i only had 16g of o2") is not read: the line before holds a number. Each shape is the whole
line: "how much co2 does a car emit" asks something new.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.chemistry.equations import balance_equation, format_balanced
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.extractors.reaction_ask import MADE_VERB, USED_VERB
from app.modules.chemistry.species_words import substance_mentions, with_formulas
from app.services.number_text import NUMBER_WORDS, TEXT_NUMBER
from app.services.problem_followup import message_role_content

_MAX_LINE = 120
# Earlier user lines searched for the reaction the line continues.
_MAX_PROBLEMS = 8
# Any number in a user line, a digit or a word: the walk back does not pass it.
_HOLDS_A_NUMBER = re.compile(rf"\d|\b(?:{'|'.join(NUMBER_WORDS)})\b", re.IGNORECASE)
# "back to the first one", "the earlier one": a problem before the last.
_BACK = re.compile(
    r"\b(?:back\s+to|first\s+(?:one|question|problem)|earlier|original|previous)\b", re.I
)
_UNITS = {"g": "g", "gram": "g", "grams": "g", "mol": "mol", "mole": "mol", "moles": "mol"}
_UNIT_WORDS = {"g": "grams", "mol": "moles"}
# The operations whose stated amounts, in grams or moles, a follow-up can change.
_READ_AMOUNTS = {"mass_stoichiometry", "limiting_mass", "stoichiometry"}

_LEAD = r"(?:[^.\d]{0,40}[.!]\s+)?(?:(?:and|but|so|ok(?:ay)?|now|then)[ ,]+)*"
_AMOUNT = rf"(?P<value>{TEXT_NUMBER})\s*(?P<unit>g|grams?|mol|moles?)\s+(?:of\s+)?(?:the\s+)?"
_IF_HAD = (
    r"(?:(?:(?:what|how)\s+about|what\s+if|if|with|try|using|use)\s+)?"
    r"(?:(?:i|we|you|they|it|there)\s+(?:only\s+)?"
    r"(?:had|have|has|used|use|start(?:ed)?\s+with|was|were|is|are)\s+)?(?:only\s+|just\s+)?"
)
_ASK_HEAD = (
    r"(?:(?:(?:what|how)\s+about\s+)|(?:how\s+(?:much|many)(?:\s+(?P<asked>grams?|g|moles?|mol))?"
    r"(?:\s+of)?|what\s+(?P<mass>mass|amount)\s+of)\s+)?(?:the\s+)?"
)
_ASK_TAIL = rf"(?:\s+(?:(?P<made>{MADE_VERB})|(?P<used>{USED_VERB})))?"
_END = r"(?:\s+(?:instead|then|now|too))?\s*\??"


@dataclass(frozen=True, slots=True)
class _Reaction:
    """An earlier reaction problem: its equation, stated amounts and what it asked."""

    equation: str
    reactants: frozenset[str]
    products: frozenset[str]
    amounts: dict[str, str]
    unit: str
    target: str
    find: str

    def problem(self, amounts: dict[str, str], unit: str, target: str, find: str) -> str:
        given = " and ".join(f"{typed} {unit} of {formula}" for formula, typed in amounts.items())
        return f"{self.equation}. {given}. How many {_UNIT_WORDS[find]} of {target}?"

    def with_amount(self, formula: str, typed: str, unit: str) -> str | None:
        """The problem with this amount in place of the stated one, or beside it."""
        if set(self.amounts) == {formula}:
            # The one stated amount, now in grams or in moles.
            return self.problem({formula: typed}, unit, self.target, self.find)
        if unit != self.unit:
            return None
        if formula in self.amounts:
            return self.problem({**self.amounts, formula: typed}, unit, self.target, self.find)
        # A second reactant weighed: the limiting reagent decides how much product forms.
        if unit != "g" or formula not in self.reactants or self.target not in self.products:
            return None
        return self.problem({**self.amounts, formula: typed}, unit, self.target, "g")

    @property
    def substances(self) -> frozenset[str]:
        return self.reactants | self.products

    def asking(self, formula: str, unit: str | None, role: str | None) -> str | None:
        """The same amounts, another substance asked; never one the problem states, and
        never a reactant asked as made ("how much oxygen is made")."""
        if formula == self.target or formula in self.amounts:
            return None
        if (role == "made" and formula not in self.products) or (
            role == "used" and formula not in self.reactants
        ):
            return None
        return self.problem(self.amounts, self.unit, formula, unit or self.find)


def _reaction(problem: str) -> _Reaction | None:
    intent = extract_chemistry_intent(problem)
    if intent is None or intent.chemistry_op not in _READ_AMOUNTS or not intent.equation:
        return None
    balanced = balance_equation(intent.equation)
    unit = intent.units.get("known", "mol" if intent.chemistry_op == "stoichiometry" else "g")
    find = intent.units.get("find", "g" if intent.chemistry_op == "limiting_mass" else unit)
    if not balanced.balanced or intent.target is None or unit not in _UNIT_WORDS:
        return None
    if find not in _UNIT_WORDS:
        return None
    amounts = {
        formula: intent.written.get(repr(value), f"{value:g}")
        for formula, value in intent.species.items()
    }
    return _Reaction(
        format_balanced(balanced),
        frozenset(balanced.reactants),
        frozenset(balanced.products),
        amounts,
        unit,
        intent.target,
        find,
    )


def _user_lines(recent: Sequence[Any]) -> Iterator[str]:
    """The user's earlier lines, latest first."""
    seen = 0
    for message in reversed(recent):
        role, content = message_role_content(message)
        if role != "user" or not content or not content.strip():
            continue
        yield content
        seen += 1
        if seen == _MAX_PROBLEMS:
            return


def _passable(line: str) -> bool:
    """A line the walk back may pass: no number in it and nothing chemistry reads."""
    return _HOLDS_A_NUMBER.search(line) is None and extract_chemistry_intent(line) is None


def _reaction_holding(formula: str, recent: Sequence[Any], back: bool) -> _Reaction | None:
    """The latest earlier reaction that holds the substance, reached only past lines with no
    number in them. Asked "back to the first one", it must be the only such reaction."""
    matches: list[tuple[_Reaction, bool]] = []
    passed_a_problem = False
    for line in _user_lines(recent):
        reaction = _reaction(line)
        if reaction is not None and formula in reaction.substances:
            matches.append((reaction, passed_a_problem))
            if not back:
                break
        if reaction is not None or not _passable(line):
            passed_a_problem = True
    if not matches or (back and len(matches) != 1):
        return None
    reaction, blocked = matches[0]
    return None if blocked else reaction


@dataclass(frozen=True, slots=True)
class _Line:
    """A follow-up line of one substance: an amount of it, or an ask of it."""

    formula: str
    amount: re.Match[str] | None
    asked: re.Match[str] | None


def _read_line(line: str) -> _Line | None:
    if len(line) > _MAX_LINE:
        return None
    mentions = substance_mentions(line) or ()
    formulas = {mention.formula for mention in mentions}
    if len(formulas) != 1:
        return None
    formula = formulas.pop()
    written = with_formulas(line, mentions)
    substance = rf"(?-i:{re.escape(formula)})(?![A-Za-z0-9])"
    amount = re.fullmatch(rf"{_LEAD}{_IF_HAD}{_AMOUNT}{substance}{_END}", written, re.IGNORECASE)
    asked = re.fullmatch(rf"{_LEAD}{_ASK_HEAD}{substance}{_ASK_TAIL}{_END}", written, re.IGNORECASE)
    if amount is None and (asked is None or not _asks(asked)):
        return None
    return _Line(formula, amount, asked)


def substance_amount(line: str) -> tuple[str, str, str] | None:
    """ "what about 20 g of H2": the whole line is one amount of one substance, as (value,
    unit, formula); None for anything else."""
    read = _read_line(line)
    if read is None or read.amount is None:
        return None
    return read.amount.group("value"), read.amount.group("unit"), read.formula


def reaction_followup_problem(line: str, recent: Sequence[Any]) -> str | None:
    """The earlier reaction problem with this line's change, written whole; None otherwise."""
    read = _read_line(line)
    if read is None:
        return None
    reaction = _reaction_holding(read.formula, recent, _BACK.search(line) is not None)
    if reaction is None:
        return None
    if read.amount is not None:
        unit = _UNITS[read.amount.group("unit").lower()]
        return reaction.with_amount(read.formula, read.amount.group("value"), unit)
    if read.asked is None:
        return None
    made, used = read.asked.group("made"), read.asked.group("used")
    role = "made" if made else "used" if used else None
    return reaction.asking(read.formula, _asked_unit(read.asked), role)


def _asks(match: re.Match[str]) -> bool:
    """A substance alone is no question: "what about", "how much" or "and the" asks it."""
    return bool(re.search(r"\b(?:about|how|what|and)\b", match.group(0), re.IGNORECASE))


def _asked_unit(match: re.Match[str]) -> str | None:
    if match.group("mass"):
        return "g" if match.group("mass").lower() == "mass" else None
    word = match.group("asked")
    return None if word is None else _UNITS[word.lower()]
