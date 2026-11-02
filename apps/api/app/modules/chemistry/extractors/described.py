"""A reaction a question tells in words, read through the equation it describes.

Live failure (2026-10-25, a student on the free model): "Ok so chem hw. how much water do i get
if i burn like 4g of h2" got no verified answer. Stoichiometry was read only beside a written
equation ("2H2 + O2 -> 2H2O. how many grams of water from 4 g of H2?"), so the model worked it
alone and wrote three answers in one reply: 4.5 g, then 35.7 g, then 36 g. A reaction told in
words is now written as its equation:

- a fuel that burns ("burn", "combustion of", reacting with oxygen or air) takes O2 and makes
  its oxides: carbon and hydrogen (with or without oxygen) make CO2 and H2O, H2 makes water, C
  and CO make CO2, S makes SO2, and Mg, Ca, Zn, Al and Li their one oxide. Those fuels make
  nothing else: SO3 from sulfur, H2O2 from hydrogen or CO from carbon declines, and so does
  any burning called incomplete, limited or insufficient. Another fuel burns to the oxide the
  question names (iron to Fe2O3, N2 to NO2);
- "X reacts with Y", "X and Y react", "X combines with Y" and "made from X and Y" make the
  product the question asks about or names ("to make water").

The balancer has the last word: a product X and Y cannot make alone ("AgNO3 reacts with NaCl,
grams of AgCl", whose NaNO3 is not named) does not balance and the question is left to the
model. A product is never guessed. What the question asks is read by a closed grammar
(``reaction_ask``): a substance asked as made must be a product, and one asked as used a
reactant. The balanced equation is written in front of the question, each substance as its
formula, and the written-equation readers answer it. A question beside a written equation
that names its substances in words or lowercase ("2H2 + O2 -> 2H2O. how much water from 4g of
h2") is read the same way. Reading the words is pattern work only (the gate asks it);
balancing runs in extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chemistry.equations import balance_equation, format_balanced
from app.modules.chemistry.extractors.equations import extract_equations
from app.modules.chemistry.extractors.reaction_ask import (
    PRODUCT_VERB,
    Question,
    ReactionAsk,
    in_formulas,
    role_fits,
)
from app.modules.chemistry.extractors.stoichiometry import (
    extract_mass_chain,
    extract_reaction_yield,
)
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.request import EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species import ARROWS, parse_reaction
from app.services.number_text import TEXT_NUMBER

_BURN_VERB = r"(?:burn(?:s|ed|t|ing)?|combust(?:s|ed|ing)?)"
_BURN = re.compile(rf"\b(?:{_BURN_VERB}|combustion)\b", re.IGNORECASE)
_MADE_FROM = r"(?:made|formed|produced|make|form|produce)\s+from"
_REACT = re.compile(rf"\b(?:react(?:s|ed|ing)?|combines?|{_MADE_FROM})\b", re.IGNORECASE)
_OXYGEN = "O2"
# Air is the oxygen a fuel burns in.
_IN_AIR = re.compile(r"\b(?:in|with)\s+(?:the\s+)?air\b", re.IGNORECASE)
# A burning the question says is not complete makes CO or soot, which no table here writes.
_INCOMPLETE = re.compile(
    r"\b(?:incomplete(?:ly)?|limited|insufficient|partial(?:ly)?|not\s+enough)\b", re.IGNORECASE
)

# What a fuel burns to. A metal with two common oxides (iron, copper), or one that makes a
# peroxide (sodium, potassium), burns only to the oxide the question names.
_FUEL_OXIDES: dict[str, tuple[str, ...]] = {
    "H2": ("H2O",),
    "C": ("CO2",),
    "CO": ("CO2",),
    "S": ("SO2",),
    "Mg": ("MgO",),
    "Ca": ("CaO",),
    "Zn": ("ZnO",),
    "Al": ("Al2O3",),
    "Li": ("Li2O",),
}
_HYDROCARBON_OXIDES = ("CO2", "H2O")

_FILLER = r"(?:(?:like|about|around|roughly|some|the|up|completely|fully|exactly|only)\s+)*"
_AMOUNT = rf"(?:{TEXT_NUMBER}\s*(?:g|grams?|mol|moles?)\s+(?:of\s+)?)"
_EXCESS = r"(?:(?:an?\s+)?(?:excess|enough|sufficient|plenty)\s+(?:of\s+)?)"
_BEING = (
    r"(?:(?:is|are|was|were|be|being|been|gets?|got|must|will|would|should|can|could|"
    r"completely|fully|then)\s+)*"
)


@dataclass(frozen=True, slots=True)
class DescribedReaction:
    """A reaction read from words, and the question with its substances as formulas."""

    reactants: tuple[str, ...]
    products: tuple[str, ...]
    question: str

    @property
    def skeleton(self) -> str:
        """The unbalanced equation: ``H2 + O2 -> H2O``."""
        return f"{' + '.join(self.reactants)} -> {' + '.join(self.products)}"


def burn_products(fuel: str) -> tuple[str, ...] | None:
    """What a fuel burns to in oxygen, or None when the school answer is not one oxide set."""
    if fuel in _FUEL_OXIDES:
        return _FUEL_OXIDES[fuel]
    atoms = set(parse_formula(fuel) or {})
    return _HYDROCARBON_OXIDES if {"C", "H"} <= atoms <= {"C", "H", "O"} else None


def _oxide_of(fuel: str, product: str) -> bool:
    """An oxide of the fuel's own elements: Fe2O3 of iron, NO2 of nitrogen."""
    atoms = set(parse_formula(product) or {})
    return "O" in atoms and bool(atoms - {"O"}) and atoms - {"O"} <= set(parse_formula(fuel) or {})


def _found(patterns: tuple[str, ...], question: str, *groups: str) -> list[tuple[str, ...]]:
    """Each match's groups, in the order the question writes them."""
    found = [
        (match.start(), tuple(match.group(group) for group in groups))
        for pattern in patterns
        for match in re.finditer(pattern, question, re.IGNORECASE)
    ]
    return [values for _start, values in sorted(found)]


def _fuel(question: str, formulas: tuple[str, ...], substance: str) -> str | None:
    """What burns: the object of "burn" or the subject of "burns", "reacts with O2".

    Without that grammar, the one substance that is neither oxygen nor a named product, or the
    one whose oxides are every other substance named.
    """
    named = rf"(?<![A-Za-z0-9])(?P<x>{substance})"
    grammar = (
        rf"\b(?:{_BURN_VERB}|combustion\s+of)\s+{_FILLER}{_AMOUNT}?{named}",
        rf"{named}\s+{_BEING}(?:{_BURN_VERB}\b|react(?:s|ed|ing)?\s+(?:completely\s+)?with)",
    )
    fuels = {x for (x,) in _found(grammar, question, "x") if x != _OXYGEN}
    if len(fuels) == 1:
        return fuels.pop()
    made_by = (rf"\b{PRODUCT_VERB}\s+{_FILLER}{_AMOUNT}?{named}",)
    made = {product for (product,) in _found(made_by, question, "x")}
    candidates = [f for f in formulas if f != _OXYGEN and f not in made]
    covering = [
        fuel
        for fuel in candidates
        if set(formulas) - {fuel, _OXYGEN} <= set(burn_products(fuel) or ())
    ]
    if len(covering) == 1:
        return covering[0]
    return candidates[0] if len(candidates) == 1 else None


def _burning(question: str, formulas: tuple[str, ...], substance: str) -> DescribedReaction | None:
    fuel = _fuel(question, formulas, substance)
    if fuel is None:
        return None
    others = tuple(f for f in formulas if f not in {fuel, _OXYGEN})
    oxides = burn_products(fuel)
    if oxides is not None:
        # A fuel the table knows burns to its own oxides and to nothing else.
        products = oxides if set(others) <= set(oxides) else ()
    else:
        products = others if all(_oxide_of(fuel, product) for product in others) else ()
    return DescribedReaction((fuel, _OXYGEN), products, question) if products else None


def _reacting(question: str, substance: str) -> tuple[str, ...] | None:
    """The two reactants of "X reacts with Y", "react X with Y", "X and Y react", "X combines
    with Y" or "made from X and Y"."""
    x, y = rf"(?<![A-Za-z0-9])(?P<x>{substance})", rf"(?P<y>{substance})"
    pairs = _found(
        (
            rf"{x}\s+{_BEING}react(?:s|ed|ing)?\s+(?:completely\s+)?with\s+{_EXCESS}?{_AMOUNT}?{y}",
            rf"\breact(?:s|ed|ing)?\s+{_AMOUNT}?{x}\s+with\s+{_EXCESS}?{_AMOUNT}?{y}",
            rf"{x}\s+and\s+{_AMOUNT}?{y}\s+{_BEING}react",
            rf"{x}\s+{_BEING}combines?\s+with\s+{_EXCESS}?{_AMOUNT}?{y}",
            rf"\b{_MADE_FROM}\s+{_AMOUNT}?{x}\s+and\s+{_AMOUNT}?{y}",
        ),
        question,
        "x",
        "y",
    )
    # One pair, however often the question repeats it.
    if len({frozenset(pair) for pair in pairs}) != 1 or pairs[0][0] == pairs[0][1]:
        return None
    return pairs[0]


def described_reaction(text: str) -> DescribedReaction | None:
    """The reaction a question describes, with a stated amount and an asked substance."""
    burning = _BURN.search(text) is not None
    if (not burning and _REACT.search(text) is None) or any(arrow in text for arrow in ARROWS):
        return None
    question = in_formulas(text)
    ask = None if question is None or _INCOMPLETE.search(text) else question.ask()
    if question is None or ask is None:
        return None
    reaction = _reaction(question, burning)
    if reaction is None or not role_fits(ask, set(reaction.reactants), set(reaction.products)):
        return None
    return reaction


def _reaction(question: Question, burning: bool) -> DescribedReaction | None:
    formulas, substance = question.formulas, question.substance
    in_air = _IN_AIR.search(question.text) is not None
    if in_air and _OXYGEN not in formulas:
        formulas = (*formulas, _OXYGEN)
    reactants = _reacting(question.text, substance)
    if burning or in_air or (reactants is not None and _OXYGEN in reactants):
        return _burning(question.text, formulas, substance)
    if reactants is None:
        return None
    # Whatever else the question names is made; with nothing named, nothing is guessed.
    products = tuple(formula for formula in formulas if formula not in reactants)
    return DescribedReaction(reactants, products, question.text) if products else None


def written_reaction_question(text: str) -> str | None:
    """A written equation of real species and an amount question about it, its substances
    written as formulas: "2H2 + O2 -> 2H2O. how much water from 4g of h2" asks about H2O and
    H2. None for anything else ("plan A -> B, how much will it cost")."""
    if not any(arrow in text for arrow in ARROWS):
        return None
    question = in_formulas(text)
    ask: ReactionAsk | None = None if question is None else question.ask()
    equation = None if question is None else EQUATION_RE.search(question.text)
    reaction = None if equation is None else parse_reaction(equation.group(1))
    if question is None or ask is None or reaction is None:
        return None
    reactants = {term.species.label for term in reaction.reactants}
    products = {term.species.label for term in reaction.products}
    return question.text if role_fits(ask, reactants, products) else None


def reaction_question(text: str) -> bool:
    """A reaction, written or told in words, with an amount stated and one asked."""
    return described_reaction(text) is not None or written_reaction_question(text) is not None


def _stoichiometry(written: str) -> ChemistryIntent | None:
    for read in (extract_equations, extract_mass_chain, extract_reaction_yield):
        intent = read(written)
        if intent is not None:
            return intent if intent.kind == "stoichiometry" else None
    return None


def extract_described_reaction(text: str) -> ChemistryIntent | None:
    """A reaction in a student's words, asked of the readers that know a written equation."""
    written = written_reaction_question(text)
    if written is not None:
        # Unchanged, the written-equation readers have read it already.
        return None if written == text else _stoichiometry(written)
    described = described_reaction(text)
    if described is None:
        return None
    balanced = balance_equation(described.skeleton)
    if not balanced.balanced:
        return None
    return _stoichiometry(f"{format_balanced(balanced)}. {described.question}")
