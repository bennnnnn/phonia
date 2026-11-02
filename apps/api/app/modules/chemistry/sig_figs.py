# ruff: noqa: RUF001, RUF002 -- answers write the multiplication sign of scientific notation.
"""How a question wrote its numbers, so the answer keeps that precision.

A chemistry answer carries as many significant figures as the least precise value the
question measured, the rule a chemistry class grades, kept between two and four. A value the
student typed is echoed as typed, trailing zeros included: 1.10 V is not 1.1 V. A pH or a pK is
a logarithm, so its precision is its decimal places: as many as the concentration it came from
has significant figures, or as many as a typed pH, pOH or pK has decimals. A sum or difference of
the givens (a cell potential, Hess's law) keeps the fewest decimal places instead: 0.34 V and
−0.76 V make 1.10 V.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache

from app.modules.chemistry.request import EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.schemas.intent import MAX_DECIMALS, MAX_WRITTEN
from app.services.units import CELSIUS_OFFSET_K, get_unit_registry

MIN_FIGURES = 2
MAX_FIGURES = 4
# Counts, not measurements: an electron count, a van 't Hoff factor, the atoms of an element
# in a formula or a neutralization's mole ratio never limits an answer.
EXACT_KEYS = frozenset(
    {"i", "valence", "electrons", "bonding", "nonbonding", "neighbors", "count", "ratio"}
)
# Exact only in one operation: Hess's law multiplies each step by a whole number (m1, m2).
# A mass number and an atomic number are counts, so 238 and 92 give 146 neutrons.
_EXACT_IN_OP = {
    "hess": re.compile(r"m\d+"),
    "neutron_count": re.compile(r"mass_number|atomic_number"),
}
# Given as logarithms: their precision is their decimal places.
LOG_KEYS = frozenset({"ph", "poh", "pka", "pkb", "pka1", "pka2"})
# A Celsius reading, whose precision is that of the kelvin value it becomes.
CELSIUS_KEYS = frozenset({"temperature_c"})
# Answers that only add and subtract the givens, so decimal places limit them, not figures.
ADDITIVE_OPS = frozenset(
    {"bond_enthalpy", "cell_potential", "dalton", "formation_enthalpy", "hess"}
)
# An average atomic mass is a mean of the isotope masses weighted by abundances that add to
# 100%. An abundance moves it only by its share of the masses' spread, a few u, so the
# abundances never cut it to their figures (75% does not make chlorine 35 u). It has the four
# figures a table of atomic masses gives, but no more decimal places than its least precise
# stated mass; whole-number masses are mass numbers, exact, so their mean is exact: boron's
# 10 and 11 at 20% and 80% average to 10.8.
WEIGHTED_MEAN_OPS = frozenset({"average_atomic_mass"})

# Units an extractor converts between. A converted value keeps its typed literal's figures.
_CONVERTIBLE = (
    ("atm", "pascal", "kilopascal", "bar", "mmHg", "torr"),
    ("liter", "milliliter", "meter ** 3", "centimeter ** 3"),
    ("gram", "kilogram", "milligram"),
    ("second", "minute", "hour", "day", "year"),
    ("joule", "kilojoule", "calorie", "kilocalorie"),
    ("mole", "millimole"),
)

# A number as the extracted text writes it ("1.10", "0.0050", "1.8e-5"); a digit inside a
# formula ("H2O") follows a letter and is not one. A full stop may end the sentence after it
# ("Ka = 1.8e-5."); only a decimal point followed by a digit continues it.
_LITERAL = re.compile(r"(?<![\w.])-?(?:\b\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?!\d|\.\d)")


def figures_of(literal: str) -> int:
    """Significant figures of a typed number: 0.0050 has 2, 1.10 has 3, 200 has 3."""
    mantissa = re.split(r"[eE]", literal.lstrip("+-"))[0]
    return max(len(mantissa.replace(".", "").lstrip("0")), 1)


def decimals_of(literal: str) -> int:
    """Decimal places of a typed number: 4.50 has 2."""
    mantissa = re.split(r"[eE]", literal)[0]
    return len(mantissa.split(".", 1)[1]) if "." in mantissa else 0


def as_written(literal: str) -> str:
    """A typed literal for display: ``1.80e-5`` is shown as ``1.80 × 10^-5``."""
    mantissa, _, exponent = literal.partition("e") if "e" in literal else literal.partition("E")
    return f"{mantissa} × 10^{int(exponent)}" if exponent else literal


def _exact(op: str, key: str) -> bool:
    pattern = _EXACT_IN_OP.get(op)
    return key in EXACT_KEYS or (pattern is not None and pattern.fullmatch(key) is not None)


@lru_cache(maxsize=1)
def _unit_factors() -> tuple[float, ...]:
    """Every factor an extractor multiplies a typed value by to change its unit."""
    registry = get_unit_registry()
    return tuple(
        sorted(
            {
                float(registry.Quantity(1, source).to(target).magnitude)
                for group in _CONVERTIBLE
                for source in group
                for target in group
                if source != target
            }
        )
    )


def _forms(text: str) -> dict[float, list[str]]:
    """Each number the question typed, with every way it was written ("0.80" and "0.8").

    A reaction's coefficients ("2 H2 + O2 -> 2 H2O") are counts, not measurements, so the
    equation is not read for them.
    """
    forms: dict[float, list[str]] = {}
    for match in _LITERAL.finditer(EQUATION_RE.sub(" ", text)):
        typed = match.group()
        written = forms.setdefault(float(typed), [])
        if typed not in written and len(typed) <= MAX_WRITTEN:
            written.append(typed)
    return forms


def _reading(value: float, forms: dict[float, list[str]]) -> tuple[list[str], str] | None:
    """How the question wrote ``value``: as typed, in Celsius, or in another unit.

    An extractor stores 700 mmHg as 0.921 atm and 25 °C as 298.15 K; the typed literal still
    sets the precision, so a converted value is traced back to it by the conversion.
    """
    typed = forms.get(value)
    if typed:
        return typed, "typed"
    sources: list[tuple[list[str], str]] = []
    for number, written in forms.items():
        if not written or number == 0:
            continue
        if math.isclose(value, number + CELSIUS_OFFSET_K, rel_tol=0, abs_tol=1e-9):
            sources.append((written, "celsius"))
        elif any(math.isclose(value, number * factor, rel_tol=1e-9) for factor in _unit_factors()):
            sources.append((written, "scaled"))
    if len(sources) > 1:
        # 1800 s is 30 min, or 0.50 h: two literals explain it, so both limit the answer and
        # neither is echoed as the value typed.
        return [form for written, _how in sources for form in written], "ambiguous"
    return sources[0] if sources else None


def written_numbers(text: str, intent: ChemistryIntent) -> ChemistryIntent:
    """The intent with its givens' precision read from the text it was extracted from."""
    forms = _forms(text)
    written: dict[str, str] = {}
    converted: dict[str, str] = {}
    figures: list[int] = []
    log_places: list[int] = []
    places: list[int] = []
    measured = [
        *intent.params.items(),
        *(("species", value) for value in intent.species.values()),
        *(("sample", value) for value in intent.samples),
    ]
    for key, value in measured:
        reading = _reading(value, forms)
        if reading is None:
            continue
        typed_forms, how = reading
        # A value typed two ways (cathode 0.80 V, anode 0.8 V) cannot be told apart by its
        # value, so neither is echoed; both still limit the answer.
        if how == "typed" and len(typed_forms) == 1:
            written[repr(value)] = typed_forms[0]
        elif how in {"scaled", "celsius"} and len(typed_forms) == 1:
            converted[repr(value)] = typed_forms[0]
        if _exact(intent.chemistry_op, key):
            continue
        for typed in typed_forms:
            typed_places = min(decimals_of(typed), MAX_DECIMALS)
            if how in {"typed", "celsius"}:
                # A unit change moves the decimal point; a Celsius offset does not.
                places.append(typed_places)
            if how == "typed" and key in LOG_KEYS:
                log_places.append(typed_places)
            elif how == "celsius" or key in CELSIUS_KEYS:
                # 25 °C is 298 K: adding 273.15 keeps the decimal places, not the figures.
                kelvin = value if how == "celsius" else value + CELSIUS_OFFSET_K
                figures.append(figures_of(f"{kelvin:.{decimals_of(typed)}f}"))
            else:
                figures.append(figures_of(typed))
    # A concentration from a typed pH has as many figures as the pH has decimals.
    measured_figures = figures or log_places
    answer = min(max(min(measured_figures), MIN_FIGURES), MAX_FIGURES) if measured_figures else None
    if intent.chemistry_op in WEIGHTED_MEAN_OPS:
        answer, decimals = _weighted_mean_precision(intent, forms)
    elif intent.chemistry_op in ADDITIVE_OPS:
        decimals = min(places, default=None)
    else:
        # Every given limits a pH: pKa 4.756 + log10(0.20 / 0.10) keeps the ratio's two places.
        limits = [*log_places, *([answer] if figures and answer is not None else [])]
        decimals = min(limits) if limits else answer
    return intent.model_copy(
        update={
            "figures": answer,
            "decimals": decimals,
            "written": written,
            "converted": converted,
        }
    )


def _weighted_mean_precision(
    intent: ChemistryIntent, forms: dict[float, list[str]]
) -> tuple[int | None, int | None]:
    """(figures, decimals) of a weighted mean of the masses in ``params``."""
    typed = [forms.get(value, []) for value in intent.params.values()]
    places = [decimals_of(form) for forms_of in typed for form in forms_of]
    if all(typed) and not any(places):
        return None, None
    return MAX_FIGURES, min((place for place in places if place), default=None)


@dataclass(frozen=True, slots=True)
class WrittenNumbers:
    figures: int | None = None
    decimals: int | None = None
    written: dict[str, str] = field(default_factory=dict)
    # A converted given's literal as typed, by the stored value's repr (0.5 L from "500").
    converted: dict[str, str] = field(default_factory=dict)
    # Every number of the answer is a sum of givens, so it keeps ``decimals`` places.
    additive: bool = False


_CURRENT: ContextVar[WrittenNumbers | None] = ContextVar("chemistry_written_numbers", default=None)


@contextmanager
def numbers_as_written(intent: ChemistryIntent) -> Iterator[None]:
    """Format every number of one solve to the precision its question was written in."""
    token = _CURRENT.set(
        WrittenNumbers(
            intent.figures,
            intent.decimals,
            intent.written,
            intent.converted,
            additive=intent.chemistry_op in ADDITIVE_OPS,
        )
    )
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current() -> WrittenNumbers | None:
    return _CURRENT.get()
