"""Read a chemistry question in its own words into one law, with the shared binder.

The extractors in ``extractors/`` read the phrasings they were written for ("Strong acid:
0.01 M HCl"). A student writes "What is the pH of 0.01 M HCl?". The binder reads that
second kind after every extractor has declined:

- the text is prepared first: a symbol whose case is its meaning is spelled out ("pH" is
  ``p_h``, "Ka" is ``k_a``), and each named substance becomes its role ("HCl" is
  ``acid_strong``, "sodium acetate" is ``salt_conjugate``), so its digits are never read as
  numbers and the words around a value can say whose it is;
- a law (``laws.LAWS``) is tried only when the question names the substance it is about:
  a strong-acid pH needs exactly one strong acid;
- the shared engine (``services.law_binding.fit``) fills the law's inputs from the stated
  values by dimension and by the words around them, and settings fill the rest (the van 't
  Hoff factor of a named solute, the molar mass of the metal deposited);
- each input is converted to the unit its solver reads, and the solver is the same one a
  template intent reaches.

Anything short of one law with one way to fill it declines.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache, partial

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.formula_laws import FORMULA_LAWS
from app.modules.chemistry.given_units import CHEMISTRY_UNITS
from app.modules.chemistry.input_text import HYDRATE_DOT, read_chemistry_text
from app.modules.chemistry.laws import LAWS, ChemistryLaw
from app.modules.chemistry.request import EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.solvers.constants import STANDARD_REDUCTION, STANDARD_TEMPERATURE_K
from app.modules.chemistry.species_facts import (
    CONJUGATE_SALTS,
    ELEMENT_NAMES,
    NAMED_COMPOUNDS,
    STRONG_ACIDS,
    STRONG_BASES,
    VAN_T_HOFF,
    WEAK_ACIDS,
    WEAK_BASES,
    element_symbol,
    ion_charge,
    is_formula,
)
from app.modules.chemistry.stoichiometry import molar_mass
from app.services.law_binding.ask import ask_clause
from app.services.law_binding.fit import (
    Fit,
    Subject,
    named_strength,
    only_strongest_fit,
    read_question,
)
from app.services.law_binding.spec import VariableSpec
from app.services.units import CELSIUS_OFFSET_K, get_unit_registry

logger = logging.getLogger(__name__)

_VERBS = re.compile(
    r"\b(?:find|calculate|compute|determine|work\s+out|estimate|evaluate|whats?|convert|"
    r"how\s+(?:long|far|fast|high|deep|much|many))\b",
    re.IGNORECASE,
)
# A school question states a handful of values; a paste full of numbers is not one law's.
_MAX_GIVENS = 12
# A second request ("... and explain why") is not a question the verified answer finishes.
_SECOND_REQUEST = re.compile(
    r"\b(?:and|also|then)\s+(?:also\s+)?"
    r"(?:tell|explain|show|write|give|draw|plot|describe)\b",
    re.IGNORECASE,
)
# Water's normal boiling and freezing points in kelvin, for "the boiling point" of a solution.
_WATER_POINTS = {
    "solvent_boiling_point": CELSIUS_OFFSET_K + 100,
    "solvent_freezing_point": CELSIUS_OFFSET_K,
}
_AQUEOUS = re.compile(r"\baqueous\b", re.IGNORECASE)

# Symbols whose case is their meaning, spelled out so lowercase word windows keep it.
_SYMBOLS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), spelled)
    for pattern, spelled in (
        (r"\[A\](?:0|₀)", " a_initial "),
        (r"\[A\]", " a_conc "),
        (r"(?<![A-Za-z])E(?:°|0|º)(?:\s*cell)?(?![A-Za-z0-9])", " e_standard "),
        (r"(?<![A-Za-z])E(?:a|ₐ)(?![A-Za-z0-9])", " e_a "),
        (r"(?<![A-Za-z0-9])E(?![A-Za-z0-9°º₀_])", " e_cell "),
        (r"Δ\s*G\s*(?:°|º)|\bdelta\s*G\s*(?:°|º)\b", " delta_g_standard "),
        (r"Δ\s*G|\bdelta\s*G\b", " delta_g "),
        (r"Δ\s*H|\bdelta\s*H\b", " delta_h "),
        (r"Δ\s*S|\bdelta\s*S\b", " delta_s "),
        (r"(?<![A-Za-z])pOH(?![A-Za-z])", " p_oh "),
        (r"(?<![A-Za-z])pKa(?![A-Za-z0-9])", " p_ka "),
        (r"(?<![A-Za-z])pKb(?![A-Za-z0-9])", " p_kb "),
        (r"(?<![A-Za-z])pH(?![A-Za-z])", " p_h "),
        (r"(?<![A-Za-z])Ksp(?![A-Za-z])", " k_sp "),
        (r"(?<![A-Za-z])Ka(?![A-Za-z0-9])", " k_a "),
        (r"(?<![A-Za-z])Kb(?![A-Za-z0-9])", " k_b "),
        (r"(?<![A-Za-z])Kf(?![A-Za-z])", " k_f "),
        (r"(?<![A-Za-z])R(?:f|F)(?![A-Za-z])", " r_f "),
    )
)
# A hydrate is one substance: CuSO4·5H2O, not CuSO4 beside a stray H2O.
_FORMULA_TOKEN = re.compile(
    rf"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9()]*(?:{HYDRATE_DOT}\d{{0,2}}[A-Z][A-Za-z0-9()]*)*)"
    rf"(?![A-Za-z0-9({HYDRATE_DOT}])"
)
# "Iron-56" and "Fe-56" are a mass number. Only a neutron question is rewritten, so a
# half-life or a binding energy that names the same isotope still reads its own law.
_ISOTOPE = re.compile(r"\b([A-Za-z]{1,20})-(\d{1,3})\b")
_NEUTRON_ASK = re.compile(r"\bneutrons?\b", re.IGNORECASE)
# Subscript digits a typeset answer copies back (K₂, T₁) beside the ASCII labels.
_SUBSCRIPT_DIGITS = "\u2081\u2082"
_SUBSCRIPT_TO_ASCII = str.maketrans(_SUBSCRIPT_DIGITS, "12")
_INDEXED_LABEL = re.compile(
    rf"(?<![A-Za-z])([KT])([12{_SUBSCRIPT_DIGITS}])(?![A-Za-z0-9{_SUBSCRIPT_DIGITS}])"
)
_ION = re.compile(r"(?<![A-Za-z0-9])([A-Z][a-z]?)(\d?)\+")
_ELEMENT_SYMBOL = re.compile(r"(?<![A-Za-z0-9])([A-Z][a-z]?)(?![A-Za-z0-9])")
# Metals a deposition can plate, from the galvanic table (not H, and not K: kelvin).
_METALS = frozenset(STANDARD_REDUCTION) - {"H", "K"}


def _spell_indexed_label(match: re.Match[str]) -> str:
    """Spell K1/K2 and T1/T2, including subscript digits, before formula roles."""
    digit = match.group(2).translate(_SUBSCRIPT_TO_ASCII)
    return f" {match.group(1).lower()}{digit} "


def role(formula: str) -> str:
    """What a named substance is in water, as the word the laws' windows read."""
    if formula in STRONG_ACIDS:
        return "acid_strong"
    if formula in STRONG_BASES:
        return "base_strong"
    if formula in WEAK_ACIDS:
        return "acid_weak"
    if formula in WEAK_BASES:
        return "base_weak"
    if formula in CONJUGATE_SALTS:
        return "salt_conjugate"
    return "water" if formula == "H2O" else "compound"


@dataclass(frozen=True, slots=True)
class Prepared:
    """A question with its substances replaced by their roles, and what they were."""

    text: str
    species: tuple[str, ...]
    original: str


def _spell_isotope(text: str) -> str:
    """Turn Iron-56 into the words the neutron law already binds: mass number 56."""
    if _NEUTRON_ASK.search(text) is None:
        return text

    def replace(match: re.Match[str]) -> str:
        if element_symbol(match.group(1)) is None:
            return match.group(0)
        return f"mass number {match.group(2)}"

    return _ISOTOPE.sub(replace, text)


def _one_isotope(text: str) -> str | None:
    symbols = [
        symbol
        for match in _ISOTOPE.finditer(text)
        if (symbol := element_symbol(match.group(1))) is not None
    ]
    return symbols[0] if len(symbols) == 1 else None


def prepare(text: str) -> Prepared:
    """Spell out case-sensitive symbols and replace each named substance by its role."""
    original = text
    text = _spell_isotope(text)
    species: list[str] = []

    def substance(formula: str) -> str:
        if formula not in species:
            species.append(formula)
        return f" {role(formula)} "

    names = "|".join(re.escape(name) for name in sorted(NAMED_COMPOUNDS, key=len, reverse=True))
    prepared = re.sub(
        rf"\b({names})\b",
        lambda match: substance(NAMED_COMPOUNDS[match.group(1).lower()]),
        text,
        flags=re.IGNORECASE,
    )
    # K1 and K2 are the two equilibrium constants in a van 't Hoff question. K2 is also
    # a formula (K₂), so spell them out before formulas are replaced by their roles.
    # A typeset answer copies the same labels back with subscript digits (K₁, T₁).
    prepared = _INDEXED_LABEL.sub(_spell_indexed_label, prepared)
    prepared = _ION.sub(lambda match: f" ion_{match.group(1).lower()} ", prepared)
    prepared = _FORMULA_TOKEN.sub(
        lambda match: substance(match.group(1)) if is_formula(match.group(1)) else match.group(0),
        prepared,
    )
    for pattern, spelled in _SYMBOLS:
        prepared = pattern.sub(spelled, prepared)
    return Prepared(re.sub(r"[ \t]+", " ", prepared), tuple(species), original)


def _formula_for(law: ChemistryLaw, species: tuple[str, ...]) -> str | bool | None:
    """The formula the law is about; None when it needs none; False when none fits."""
    if law.species is None:
        return None
    if law.species == "compound":
        return species[0] if len(species) == 1 else False
    if law.species == "solute":
        solutes = [formula for formula in species if formula != "H2O"]
        return solutes[0] if len(solutes) == 1 else False
    matching = [formula for formula in species if role(formula) == law.species]
    return matching[0] if len(matching) == 1 else False


def _metal(original: str) -> str | None:
    """The one metal a deposition question names, by symbol ("Cu") or name ("copper")."""
    found = {match.group(1) for match in _ELEMENT_SYMBOL.finditer(original)}
    found |= {match.group(1) for match in _ION.finditer(original)}
    found |= {
        ELEMENT_NAMES[word]
        for word in re.findall(r"[a-z]+", original.lower())
        if word in ELEMENT_NAMES
    }
    found &= _METALS
    return next(iter(found)) if len(found) == 1 else None


def _fallback(prepared: Prepared, variable: VariableSpec, _text: str, _lower: str) -> float | None:
    """A setting an unstated input takes from the substances the question names."""
    if variable.fallback == "element_atomic_number":
        symbol = _one_isotope(prepared.original)
        if symbol is None:
            return None
        return float(BY_SYMBOL[symbol].number)
    if variable.fallback == "van_t_hoff":
        solutes = [formula for formula in prepared.species if formula != "H2O"]
        factor = VAN_T_HOFF.get(solutes[0]) if len(solutes) == 1 else None
        return None if factor is None else float(factor)
    if variable.fallback == "standard_temperature":
        return STANDARD_TEMPERATURE_K
    if variable.fallback in _WATER_POINTS:
        # Water's normal point is a setting only when water is the solvent the question names.
        aqueous = "H2O" in prepared.species or _AQUEOUS.search(prepared.original) is not None
        return _WATER_POINTS[variable.fallback] if aqueous else None
    if variable.fallback == "species_molar_mass":
        solutes = [formula for formula in prepared.species if formula != "H2O"]
        named = solutes if len(solutes) == 1 else list(prepared.species)
        return molar_mass(named[0]) if len(named) == 1 else None
    if variable.fallback not in {"deposited_molar_mass", "ion_charge"}:
        return None
    metal = _metal(prepared.original)
    if metal is None:
        return None
    if variable.fallback == "deposited_molar_mass":
        return BY_SYMBOL[metal].mass
    # "Cu2+" states the ion; otherwise it is the galvanic table's school ion (Cu²⁺).
    charge = ion_charge(prepared.original, metal)
    return float(charge if charge is not None else STANDARD_REDUCTION[metal][1])


def _declared(variable: VariableSpec) -> str:
    return variable.dimension or ""


def _converted(law: ChemistryLaw, filled: Fit) -> tuple[dict[str, float], dict[str, str]] | None:
    """The filled inputs in the units the law's solver reads, and the units it is told."""
    registry = get_unit_registry()
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    for variable in law.spec.variables:
        if variable.name not in filled.params:
            continue
        value, written = filled.params[variable.name], filled.units[variable.name]
        if variable.dimensionless or variable.name in law.keep_units:
            params[variable.name] = value
            if variable.name in law.keep_units:
                units[variable.name] = written
            continue
        if written == variable.dimension:
            params[variable.name] = value
            continue
        expression = CHEMISTRY_UNITS.expression(written)
        if expression is None or variable.dimension is None:
            return None
        try:
            quantity = registry.Quantity(value, expression).to(variable.dimension)
        except Exception as exc:
            # A stated unit that does not convert to the input the law reads declines the law.
            logger.debug(
                "%s: %s does not convert to %s: %s",
                law.op,
                expression,
                variable.dimension,
                type(exc).__name__,
            )
            return None
        params[variable.name] = float(quantity.magnitude)
        if law.op in FORMULA_LAWS:
            # The formula solver echoes the given as typed before the converted value.
            units[variable.name] = written
    units.update(dict(law.labels))
    return params, units


# A sentence ends at ? or !, or at a full stop before a space: not inside "0.10".
_SENTENCE_BREAK = re.compile(r"[?!]+|\.(?=\s)")


def _verbless_ask(text: str) -> str | None:
    """The asked part of a question with no question verb.

    "pH of 0.0025 M HCl", "Freezing point of a solution with 10.0 g NaCl in 250 g of water?
    Kf = 1.86 °C/m", "theoretical yield was 25.0 g but I got 21.3 g. percent yield?": the
    sentence that ends in a question mark asks, and a single sentence asks for what it names.
    """
    stripped = text.strip()
    marks = [match.start() for match in re.finditer(r"\?", stripped)]
    if marks:
        end = marks[-1]
        breaks = [match.end() for match in _SENTENCE_BREAK.finditer(stripped, 0, end)]
        start = breaks[-1] if breaks else 0
        return stripped[start:end].strip() or None
    body = stripped.rstrip(".!")
    if _SENTENCE_BREAK.search(body):
        return None
    return body or None


def bind_chemistry_intent(text: str) -> ChemistryIntent | None:
    """The one chemistry law this question states and asks for, or None.

    The gate and extraction both ask about the same line, so it is read once and each
    caller gets its own copy.
    """
    intent = _bind(read_chemistry_text(text))
    return None if intent is None else intent.model_copy(deep=True)


@lru_cache(maxsize=128)
def _bind(text: str) -> ChemistryIntent | None:
    if _SECOND_REQUEST.search(text):
        return None
    prepared = prepare(text)
    clause = ask_clause(prepared.text, _VERBS) or _verbless_ask(prepared.text)
    if clause is None:
        return None
    lower = prepared.text.lower()
    equation = EQUATION_RE.search(text) is not None
    named = [
        ((law, formula), law.spec, strength)
        for law in LAWS
        if (binding := law.spec.binding) is not None
        and not (law.no_equation and equation)
        and (formula := _formula_for(law, prepared.species)) is not False
        and (strength := named_strength(binding, clause, lower, CHEMISTRY_UNITS))
    ]
    if not named:
        return None
    question = read_question(prepared.text, clause, CHEMISTRY_UNITS, max_givens=_MAX_GIVENS)
    if question is None:
        return None
    subject = Subject(
        units=CHEMISTRY_UNITS, fallback=partial(_fallback, prepared), unit_of=_declared
    )
    strongest = only_strongest_fit(named, question, subject)
    if strongest is None:
        return None
    (law, formula), filled = strongest
    converted = _converted(law, filled)
    if converted is None:
        return None
    params, units = converted
    try:
        return ChemistryIntent(
            # The catalog's kind is a str; the model validates it against its Literal.
            kind=law.kind,  # type: ignore[arg-type]
            chemistry_op=law.op,
            params=params,
            units=units,
            formula=formula if isinstance(formula, str) else None,
        )
    except ValueError:
        return None
