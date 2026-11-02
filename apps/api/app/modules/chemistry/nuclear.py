# ruff: noqa: RUF001 -- the decay particles are written with their Greek letters.
"""Nuclear equations from mass number and atomic number.

Mass defect uses a supplied nuclear mass; this module does not invent one.
A missing product is filled only when the missing (A, Z) is a known particle
or a single nuclide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.chemistry.elements import BY_NUMBER, BY_SYMBOL
from app.modules.chemistry.species import split_equation

# ``238U``, ``^238U``, ``^{238}_{92}U``, ``^238_92U`` and ``_{92}^{238}U``.
_NUCLIDE_RE = re.compile(
    r"^\^?\{?(?P<mass>\d+)\}?(?:_\{?(?P<z>\d+)\}?)?(?P<symbol>[A-Z][a-z]?)$"
    r"|^_\{?(?P<z2>\d+)\}?\^\{?(?P<mass2>\d+)\}?(?P<symbol2>[A-Z][a-z]?)$"
)
_HYPHEN_RE = re.compile(r"^(?P<symbol>[A-Z][a-z]?)-(?P<mass>\d+)$")
# name -> (mass number, protons, symbol shown)
_PARTICLE_ALIASES: dict[str, tuple[int, int, str]] = {
    "e-": (0, -1, "e-"),
    "β-": (0, -1, "e-"),
    "β": (0, -1, "e-"),
    "beta": (0, -1, "e-"),
    "beta-": (0, -1, "e-"),
    "electron": (0, -1, "e-"),
    "e+": (0, 1, "e+"),
    "β+": (0, 1, "e+"),
    "beta+": (0, 1, "e+"),
    "positron": (0, 1, "e+"),
    "n": (1, 0, "n"),
    "1n": (1, 0, "n"),
    "neutron": (1, 0, "n"),
    "alpha": (4, 2, "He"),
    "α": (4, 2, "He"),
    "gamma": (0, 0, "γ"),
    "γ": (0, 0, "γ"),
    "p": (1, 1, "H"),
    "proton": (1, 1, "H"),
}
_PARTICLE_PATTERN = "|".join(
    re.escape(name) for name in sorted(_PARTICLE_ALIASES, key=len, reverse=True)
)
_COUNTED_PARTICLE_RE = re.compile(rf"^(\d+)\s*({_PARTICLE_PATTERN})$")
_COEFFICIENT_RE = re.compile(r"^(\d+)\s+(.+)$")
# A ``+`` that follows exactly one of these tokens is a charge sign, not a separator: ``e+``.
_POSITRON_STEM_RE = re.compile(r"^(?:e|β|beta)\^?$")
_PARTICLES = {
    (4, 2): "4He",
    (1, 0): "1n",
    (1, 1): "1H",
    (0, -1): "e-",
    (0, 1): "e+",
}
_PARTICLE_SYMBOLS = frozenset({"e-", "e+", "n", "γ"})
# Heaviest known nuclides have N/Z below ~1.7; anything beyond 3Z + 8 (He-10, H-7 are the
# extremes) is not a nuclide, and Z > A is impossible.
_MAX_EXCESS_NEUTRONS_PER_PROTON = 3
_MAX_EXCESS_NEUTRONS = 8


@dataclass(frozen=True)
class Nuclide:
    mass_number: int
    symbol: str
    protons: int
    coefficient: int = 1

    @property
    def is_particle(self) -> bool:
        """An electron, positron, neutron or photon rather than an element's nuclide."""
        return self.symbol in _PARTICLE_SYMBOLS

    @property
    def label(self) -> str:
        if self.symbol == "n":
            return "1n"
        if self.is_particle:
            return self.symbol
        return f"{self.mass_number}{self.symbol}"


@dataclass(frozen=True)
class NuclearEquation:
    reactants: tuple[Nuclide, ...]
    products: tuple[Nuclide, ...]
    balanced: bool
    error: str | None = None


def _is_nuclide(mass_number: int, protons: int) -> bool:
    """A real nuclide has at least as many nucleons as protons, and a bounded neutron excess."""
    if protons < 1 or mass_number < protons:
        return False
    if protons > 1 and mass_number == protons:
        return False  # only protium has no neutron
    return mass_number <= _MAX_EXCESS_NEUTRONS_PER_PROTON * protons + _MAX_EXCESS_NEUTRONS


def _element_nuclide(
    mass: int, symbol: str, stated_z: int | None, coefficient: int
) -> Nuclide | None:
    element = BY_SYMBOL.get(symbol)
    if element is None or (stated_z is not None and stated_z != element.number):
        return None
    if not _is_nuclide(mass, element.number):
        return None
    return Nuclide(mass, symbol, element.number, coefficient)


def parse_nuclide(token: str) -> Nuclide | None:
    """A nuclide or particle such as ``238U``, ``U-238``, ``^{238}_{92}U``, ``alpha`` or ``2 n``."""
    text = token.strip()
    coefficient = 1
    counted = _COUNTED_PARTICLE_RE.match(text)
    if counted is not None:
        coefficient, text = int(counted.group(1)), counted.group(2)
    elif (spaced := _COEFFICIENT_RE.match(text)) is not None and not _NUCLIDE_RE.match(text):
        coefficient, text = int(spaced.group(1)), spaced.group(2)
    if coefficient < 1:
        return None
    text = re.sub(r"^(e|β)\^([+-])$", r"\1\2", text)
    alias = _PARTICLE_ALIASES.get(text)
    if alias is not None and text != "1n":
        mass, protons, symbol = alias
        if symbol in _PARTICLE_SYMBOLS:
            return Nuclide(mass, symbol, protons, coefficient)
        return _element_nuclide(mass, symbol, protons, coefficient)
    if text == "1n":
        return Nuclide(1, "n", 0, coefficient)
    parsed = _NUCLIDE_RE.match(text)
    if parsed is not None:
        mass_text = parsed.group("mass") or parsed.group("mass2")
        z_text = parsed.group("z") or parsed.group("z2")
        symbol = parsed.group("symbol") or parsed.group("symbol2")
        return _element_nuclide(
            int(mass_text), symbol, int(z_text) if z_text else None, coefficient
        )
    hyphen = _HYPHEN_RE.match(text)
    if hyphen is None:
        return None
    return _element_nuclide(int(hyphen.group("mass")), hyphen.group("symbol"), None, coefficient)


def _split_terms(side: str) -> list[str]:
    """Split on ``+``, keeping the sign of a written positron (``e+``)."""
    terms: list[str] = []
    buffer = ""
    for char in side:
        if char == "+" and not (
            buffer and not buffer[-1].isspace() and _POSITRON_STEM_RE.match(buffer.strip())
        ):
            terms.append(buffer.strip())
            buffer = ""
        else:
            buffer += char
    terms.append(buffer.strip())
    return terms


def _split_side(side: str) -> list[Nuclide] | None:
    nuclides = []
    for piece in _split_terms(side):
        if not piece or piece == "?":
            return None
        nuclide = parse_nuclide(piece)
        if nuclide is None:
            return None
        nuclides.append(nuclide)
    return nuclides


def _totals(nuclides: list[Nuclide]) -> tuple[int, int]:
    mass = sum(item.coefficient * item.mass_number for item in nuclides)
    protons = sum(item.coefficient * item.protons for item in nuclides)
    return mass, protons


def _format(nuclides: tuple[Nuclide, ...]) -> str:
    return " + ".join(
        f"{item.coefficient} {item.label}" if item.coefficient != 1 else item.label
        for item in nuclides
    )


def balance_nuclear(equation: str) -> NuclearEquation:
    """Balance nucleons, or complete one ``?`` product."""
    sides = split_equation(equation)
    if sides is None:
        return NuclearEquation((), (), False, "no arrow in equation")
    left, right = sides
    reactants = _split_side(left)
    if reactants is None:
        return NuclearEquation((), (), False, "cannot parse nuclear equation")
    raw_products = [part for part in _split_terms(right) if part]
    if raw_products.count("?") > 1:
        return NuclearEquation((), (), False, "more than one missing nuclide")
    products: list[Nuclide] = []
    missing = False
    for part in raw_products:
        if part == "?":
            missing = True
            continue
        nuclide = parse_nuclide(part)
        if nuclide is None:
            return NuclearEquation((), (), False, "cannot parse nuclear equation")
        products.append(nuclide)
    if not products:
        error = "missing nuclide is not unique" if missing else "cannot parse nuclear equation"
        return NuclearEquation((), (), False, error)
    if missing:
        delta_mass, delta_z = _totals(reactants)
        have_mass, have_z = _totals(products)
        delta = (delta_mass - have_mass, delta_z - have_z)
        label = _PARTICLES.get(delta)
        if label is None:
            element = BY_NUMBER.get(delta[1])
            if element is None or delta[0] < 1:
                return NuclearEquation((), (), False, "missing nuclide is not unique")
            label = f"{delta[0]}{element.symbol}"
        extra = parse_nuclide(label)
        if extra is None:
            return NuclearEquation((), (), False, "missing nuclide is not unique")
        products.append(extra)
    if _totals(reactants) != _totals(products):
        return NuclearEquation(tuple(reactants), tuple(products), False, "nucleons do not balance")
    return NuclearEquation(tuple(reactants), tuple(products), True)


def format_nuclear(equation: NuclearEquation) -> str:
    return f"{_format(equation.reactants)} → {_format(equation.products)}"


def conservation_lines(equation: NuclearEquation) -> tuple[str, ...]:
    """``A: 238 = 234 + 4`` and ``Z: 92 = 90 + 2``: what each side adds up to."""

    def side(nuclides: tuple[Nuclide, ...], value: str) -> str:
        parts = []
        for nuclide in nuclides:
            amount = nuclide.coefficient * (
                nuclide.mass_number if value == "A" else nuclide.protons
            )
            parts.append(f"({amount})" if amount < 0 else str(amount))
        return " + ".join(parts)

    return (
        f"A: {side(equation.reactants, 'A')} = {side(equation.products, 'A')}",
        f"Z: {side(equation.reactants, 'Z')} = {side(equation.products, 'Z')}",
    )
