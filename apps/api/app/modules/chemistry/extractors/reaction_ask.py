"""What a reaction question asks, read by a closed grammar.

Review (2026-10-25): "how much water do i need to drink if i burn 200 g of sugar running" was
verified as 116 g of water, "how much co2 do i exhale" as the CO2 made, "how much co2 is left
over" likewise, "4 g of h2 burns in 100 g of air" ignored the air, and "to make co2 and co"
dropped the lowercase "co". Every word around the asked substance now belongs to a known
phrase:

- a head: "how much", "how many (grams|moles|molecules) of", "what mass of", "find the mass of";
- the substance, with "vapour" or "gas" after it, and a unit ("molecules", "in grams");
- a verb that makes it ("do i get", "is produced", "forms") or uses it ("do i need", "is
  needed", "reacts", "must burn");
- then the end of the clause, or a word that carries on to the reaction ("if", "when",
  "from", "to burn").

Anything else ("should i drink", "do i exhale", "is left", "in ml", "and h2") declines and the
model answers. Every amount the question states must be of a substance it names ("100 g of
air", "5 g of fuel" are not), and every word of a product list ("to make CO2 and co") must be
a substance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.modules.chemistry.extractors.parsing import asked_quantity
from app.modules.chemistry.extractors.stoichiometry import YIELD_ASK
from app.modules.chemistry.species_words import substance_mentions, with_formulas
from app.services.number_text import TEXT_NUMBER

Role = Literal["made", "used"] | None

_PRONOUN = r"(?:i|we|you|they|it)"
# A verb that makes the asked substance, and one that uses it up.
MADE_VERB = (
    rf"(?:(?:do|does|did|would|will|can|could)\s+{_PRONOUN}\s+(?:get|make|produce|form|obtain)"
    r"|(?:(?:is|are|was|were|will\s+be|would\s+be|can\s+be|could\s+be|gets?|got)\s+)?"
    r"(?:made|formed|produced|released|given\s+off|created|obtained|generated)"
    r"|forms?|comes?\s+out)"
)
USED_VERB = (
    rf"(?:(?:do|does|did|would|will)\s+{_PRONOUN}\s+need"
    r"|(?:(?:is|are|was|were|will\s+be|would\s+be)\s+)?(?:needed|required|used(?:\s+up)?|consumed)"
    r"|reacts?|must\s+(?:burn|react)|(?:is|are)\s+burn(?:ed|t)|burns?|needs?)"
)
# What may follow the ask: the end of its clause, or a word that goes on to the reaction.
_CARRY_ON = (
    r"(?=\s*(?:[?.!,;]|$)|\s+(?:if|when|from|by|after|for|once|with|"
    r"to\s+(?:burn|react|make|form|produce|get)|burning|reacting|combusting)\b)"
)
_HEAD = (
    r"\b(?:how\s+(?:much|many)(?:\s+(?:grams?|g|moles?|mol|molecules))?(?:\s+of)?"
    r"|what\s+(?:is\s+the\s+)?(?:mass|amount|number\s+of\s+moles)\s+of"
    r"|(?:find|calculate|determine|work\s+out)\s+the\s+"
    r"(?:mass|amount|moles|number\s+of\s+(?:moles|molecules))\s+of)"
)
# Every head that asks an amount must be read whole, or the question is not one.
_AMOUNT_HEAD = re.compile(
    r"\b(?:how\s+(?:much|many)|what\s+(?:is\s+the\s+)?(?:mass|amount|volume|number)\s+of"
    r"|(?:find|calculate|determine|work\s+out)\s+the\s+(?:mass|amount|moles|volume|number)\b)",
    re.IGNORECASE,
)
_STATED_AMOUNT = re.compile(
    rf"(?<![A-Za-z0-9.])(?:{TEXT_NUMBER})\s*"
    r"(?:g|grams?|kg|mg|mol|moles?|mmol|L|mL|ml|liters?|litres?)(?![A-Za-z])",
    re.IGNORECASE,
)
_LIMITING = re.compile(r"\blimiting\b", re.IGNORECASE)
# A verb before what a reaction makes: "to make water", "produces CO2 and H2O".
PRODUCT_VERB = (
    r"(?:to\s+(?:make|form|produce|give|yield)|mak(?:es|ing)|form(?:s|ing)|"
    r"produc(?:es|ing)|giv(?:es|ing)|yield(?:s|ing))"
)
_PRODUCT_LIST = re.compile(rf"\b{PRODUCT_VERB}\b", re.IGNORECASE)
# A product list ends at a clause mark or at a word that starts the next phrase.
_LIST_END = re.compile(
    r"[?.!;]|\s(?:when|if|from|by|after|with|in|at|for|which|how|what|then|is|are|was|were)\b",
    re.IGNORECASE,
)
_LIST_SPLIT = re.compile(r"\s*(?:,|\band\b|&|\+)\s*", re.IGNORECASE)
_LIST_WORDS = re.compile(
    rf"^(?:(?:the|some|a|an)\s+)*(?:{TEXT_NUMBER}\s*(?:g|grams?|mol|moles?)\s+(?:of\s+)?)?"
    r"(?:the\s+)?|\s+(?:vapou?r|gas|steam)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ReactionAsk:
    """The substance asked (None for a limiting reagent or a percent yield), and whether the
    question says it is made or used."""

    species: str | None
    role: Role


@dataclass(frozen=True, slots=True)
class Question:
    """A question with each substance written as its formula, and those formulas."""

    text: str
    formulas: tuple[str, ...]

    @property
    def substance(self) -> str:
        """The formulas as one case-exact alternative, longest first."""
        ordered = sorted(self.formulas, key=len, reverse=True)
        return "(?-i:" + "|".join(re.escape(formula) for formula in ordered) + ")(?![A-Za-z0-9])"

    def ask(self) -> ReactionAsk | None:
        """The one amount asked, when every amount, ask and product list reads whole."""
        if not self._amounts_are_named() or not self._products_are_named():
            return None
        if _AMOUNT_HEAD.search(self.text) is None:
            limiting = YIELD_ASK.search(self.text) or _LIMITING.search(self.text)
            return ReactionAsk(None, None) if limiting else None
        ask = self._one_ask()
        # The readers that answer it must ask the same substance.
        asked = asked_quantity(self.text)
        if ask is None or asked is None or asked.species != ask.species:
            return None
        return ask

    def _one_ask(self) -> ReactionAsk | None:
        pattern = (
            rf"{_HEAD}\s+(?:the\s+|some\s+)?(?P<asked>{self.substance})"
            r"(?:\s+(?:vapou?r|gas|steam))?(?:\s+(?:in\s+)?(?:molecules|grams|moles))?"
            rf"(?:\s+(?:(?P<made>{MADE_VERB})|(?P<used>{USED_VERB})))?{_CARRY_ON}"
        )
        asks = list(re.finditer(pattern, self.text, re.IGNORECASE))
        if len(asks) != 1 or len(_AMOUNT_HEAD.findall(self.text)) != 1:
            return None
        found = asks[0]
        role: Role = "made" if found.group("made") else "used" if found.group("used") else None
        return ReactionAsk(found.group("asked"), role)

    def _amounts_are_named(self) -> bool:
        """Every amount stated is of a substance named, and there is one."""
        named = re.compile(rf"\s*(?:of\s+)?(?:the\s+|some\s+|pure\s+)?{self.substance}", re.I)
        found = list(_STATED_AMOUNT.finditer(self.text))
        return bool(found) and all(named.match(self.text, amount.end()) for amount in found)

    def _products_are_named(self) -> bool:
        """Every word of a product list ("to make CO2 and co") is a named substance."""
        for verb in _PRODUCT_LIST.finditer(self.text):
            rest = self.text[verb.end() :]
            end = _LIST_END.search(rest)
            for piece in _LIST_SPLIT.split(rest[: end.start() if end else len(rest)].strip()):
                item = _LIST_WORDS.sub("", piece.strip()).strip()
                if item and item not in self.formulas:
                    return False
        return True


def in_formulas(text: str) -> Question | None:
    """The question with its substances written as formulas, or None when it names none."""
    mentions = substance_mentions(text)
    if not mentions:
        return None
    formulas = tuple(dict.fromkeys(mention.formula for mention in mentions))
    return Question(with_formulas(text, mentions), formulas)


def role_fits(ask: ReactionAsk, reactants: set[str], products: set[str]) -> bool:
    """A substance asked as made is a product, and one asked as used is a reactant: "how much
    oxygen is made when 4 g of h2 burns" asks a reactant as a product."""
    if ask.species is None or ask.role is None:
        return True
    return ask.species in (products if ask.role == "made" else reactants)
