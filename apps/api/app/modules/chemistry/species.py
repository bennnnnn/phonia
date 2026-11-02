"""Species, charge, phase, and reaction terms shared by every chemistry solver.

A plus sign is ionic charge only when it is glued to the formula and the next
character is space, end, or another plus (``Fe2+ + Ce4+``, ``Fe2++Ce4+``).
``H2+O2`` and ``H2 + O2`` stay term separators. Polyatomic ions with |charge|
greater than 1 keep an explicit caret (``SO4^2-``). A bare trailing sign on a
polyatomic formula is charge ±1 (``MnO4-``). Digits before the sign are the
charge only for a single element (``Fe2+``). H, N, O, F, Cl, Br, and I
keep those digits as a subscript and take charge ±1 (``O2-``, ``H2+``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.formula import parse_formula
from app.modules.chemistry.input_text import spell_scripts

_PHASE_RE = re.compile(r"\s*\((aq|s|l|g)\)$", re.IGNORECASE)
# These elements are written as molecules. ``O2-`` is superoxide, not oxide.
DIATOMIC_ELEMENTS = frozenset({"H", "N", "O", "F", "Cl", "Br", "I"})
_CARET_CHARGE_RE = re.compile(r"\^(?:\{(\d*)([+-])\}|(\d*)([+-]))$")
# Longest first: "<=>" contains "=>", and "-->" and "<->" contain "->".
ARROWS = ("<=>", "<->", "-->", "->", "→", "⇌", "⇋", "⟶", "↔", "=>")


@dataclass(frozen=True)
class ChemicalSpecies:
    """One chemical species, independent of its stoichiometric coefficient."""

    formula: str
    composition: dict[str, int]
    charge: int
    phase: str | None = None
    electron: bool = False

    @property
    def label(self) -> str:
        return canonical_label(self)


@dataclass(frozen=True)
class ReactionTerm:
    """A species multiplied by a positive coefficient."""

    species: ChemicalSpecies
    coefficient: int


@dataclass(frozen=True)
class ChemicalReaction:
    """A reaction whose terms share one species representation."""

    reactants: tuple[ReactionTerm, ...]
    products: tuple[ReactionTerm, ...]


def _is_charge_plus(text: str, index: int, buf: list[str]) -> bool:
    if not buf or buf[-1].isspace():
        return False
    nxt = text[index + 1] if index + 1 < len(text) else ""
    return nxt == "" or nxt.isspace() or nxt == "+"


def split_terms(side: str) -> list[str]:
    """Split one side of an equation on separator plus signs."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for index, char in enumerate(side):
        if char in "([{":
            depth += 1
            buf.append(char)
            continue
        if char in ")]}":
            depth = max(0, depth - 1)
            buf.append(char)
            continue
        if char == "+" and depth == 0 and not _is_charge_plus(side, index, buf):
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(char)
    if buf:
        parts.append("".join(buf))
    return [part.strip() for part in parts if part.strip()]


def _split_coefficient(token: str) -> tuple[int, str]:
    spaced = re.match(r"^(\d+)\s+(.+)$", token)
    if spaced:
        return int(spaced.group(1)), spaced.group(2).strip()
    glued = re.match(r"^(\d+)(?=[A-Z(e])(.*)$", token)
    if glued:
        return int(glued.group(1)), glued.group(2)
    return 1, token


def _strip_phase(body: str) -> tuple[str, str | None]:
    match = _PHASE_RE.search(body)
    if match is None:
        return body, None
    return body[: match.start()].strip(), match.group(1).lower()


def _strip_charge(body: str) -> tuple[str, int] | None:
    """Split a trailing charge off ``body``.

    ``None`` when the charge is ambiguous: ``SO42-`` could be SO4²⁻ or S O42 ⁻, and
    guessing balances a different equation than the one the user meant. A caret
    (``SO4^2-``) removes the ambiguity.
    """
    caret = _CARET_CHARGE_RE.search(body)
    if caret:
        magnitude = caret.group(1) if caret.group(1) is not None else caret.group(3)
        sign = caret.group(2) if caret.group(2) is not None else caret.group(4)
        charge = int(magnitude or "1")
        if sign == "-":
            charge = -charge
        return body[: caret.start()], charge
    if not body or body[-1] not in "+-":
        return body, 0
    sign = 1 if body[-1] == "+" else -1
    core = body[:-1]
    index = len(core)
    while index > 0 and core[index - 1].isdigit():
        index -= 1
    digits = core[index:]
    stem = core[:index]
    if digits and stem in BY_SYMBOL:
        if stem in DIATOMIC_ELEMENTS:
            return f"{stem}{digits}", sign
        return stem, sign * int(digits)
    if len(digits) > 1:
        return None
    return core, sign


def _single_element(formula: str) -> bool:
    return formula in BY_SYMBOL


def canonical_label(species: ChemicalSpecies) -> str:
    """Stable key. Uncharged formulas without a phase stay exactly as parsed."""
    body = "e" if species.electron else species.formula
    if species.charge:
        magnitude = abs(species.charge)
        sign = "+" if species.charge > 0 else "-"
        magnitude_text = "" if magnitude == 1 else str(magnitude)
        if species.electron or _single_element(species.formula):
            body = f"{body}{magnitude_text}{sign}"
        elif magnitude == 1:
            body = f"{body}{sign}"
        else:
            body = f"{body}^{magnitude}{sign}"
    if species.phase:
        body = f"{body}({species.phase})"
    return body


def parse_species(
    token: str, *, coefficient_already_removed: bool = False
) -> ChemicalSpecies | None:
    """Parse one term. None when the formula is not a complete species."""
    text = spell_scripts(token).strip()
    if not text:
        return None
    if coefficient_already_removed:
        coefficient = 1
        body = text
    else:
        coefficient, body = _split_coefficient(text)
    if coefficient < 1 or not body:
        return None
    body, phase = _strip_phase(body)
    if body.rstrip("+-") == "e":
        return ChemicalSpecies("e", {}, 1 if body.endswith("+") else -1, phase, electron=True)
    stripped = _strip_charge(body)
    if stripped is None:
        return None
    body, charge = stripped
    if not body:
        return None
    composition = parse_formula(body)
    if not composition or any(symbol not in BY_SYMBOL for symbol in composition):
        return None
    return ChemicalSpecies(body, composition, charge, phase, electron=False)


def parse_term(token: str) -> ReactionTerm | None:
    text = spell_scripts(token).strip()
    coefficient, body = _split_coefficient(text)
    species = parse_species(body, coefficient_already_removed=True)
    if species is None or coefficient < 1:
        return None
    return ReactionTerm(species, coefficient)


def split_equation(equation: str) -> tuple[str, str] | None:
    normalized = spell_scripts(equation)
    for arrow in ARROWS:
        if arrow in normalized:
            left, right = normalized.split(arrow, 1)
            return left, right
    return None


def parse_reaction(equation: str) -> ChemicalReaction | None:
    sides = split_equation(equation)
    if sides is None:
        return None
    reactants = tuple(term for token in split_terms(sides[0]) if (term := parse_term(token)))
    products = tuple(term for token in split_terms(sides[1]) if (term := parse_term(token)))
    if len(reactants) != len(split_terms(sides[0])) or len(products) != len(split_terms(sides[1])):
        return None
    if not reactants or not products:
        return None
    return ChemicalReaction(reactants, products)


def counts_in_mass_action(label: str) -> bool:
    """Pure solids and liquids are omitted only when the phase was written."""
    species = parse_species(label, coefficient_already_removed=True)
    if species is None or species.phase is None:
        return True
    return species.phase not in {"s", "l"}
