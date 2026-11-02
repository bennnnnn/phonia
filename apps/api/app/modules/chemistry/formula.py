"""Formula text: parsing a formula into atoms, and the conventional order of its elements."""

from __future__ import annotations

from itertools import pairwise

from app.modules.chemistry.elements import BY_SYMBOL

_HYDRATE_DOTS = frozenset({".", "\u00b7"})
_PHASES = frozenset({"aq", "s", "l", "g"})
_MAX_NESTING = 12


def _hydrate_fragments(formula: str) -> list[str]:
    """Split ``CuSO4.5H2O`` / ``CuSO4·5H2O`` into fragments. Linear — no regex."""
    fragments: list[str] = []
    current: list[str] = []
    for ch in formula:
        if ch in _HYDRATE_DOTS:
            if current:
                fragments.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        fragments.append("".join(current))
    return fragments


def _leading_multiplier(fragment: str) -> tuple[int, str]:
    """``5H2O`` → (5, ``H2O``); ``H2O`` → (1, ``H2O``)."""
    i = 0
    n = len(fragment)
    while i < n and fragment[i].isdigit():
        i += 1
    if i == 0 or i == n:
        return 1, fragment
    return int(fragment[:i]), fragment[i:]


def _parse_formula_body(s: str, multiplier: int, atoms: dict[str, int], nesting: int = 0) -> bool:
    """Walk one Hill-formula fragment. False when a leftover char cannot be parsed."""
    if nesting > _MAX_NESTING:
        return False
    i = 0
    n = len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        if s[i] in "([":
            opener = s[i]
            closer = ")" if opener == "(" else "]"
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if s[j] == opener:
                    depth += 1
                elif s[j] == closer:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:
                return False
            inner = s[i + 1 : j]
            k = j + 1
            num_str = ""
            while k < n and s[k].isdigit():
                num_str += s[k]
                k += 1
            inner_mult = int(num_str) if num_str else 1
            if num_str and inner_mult < 1:
                return False
            # ``(aq)`` / ``(s)`` / ``(l)`` / ``(g)`` — skip, not atoms. ``H(2)`` is not a formula.
            if not any(ch.isupper() for ch in inner):
                if inner not in _PHASES:
                    return False
                i = k
                continue
            if not _parse_formula_body(inner, multiplier * inner_mult, atoms, nesting + 1):
                return False
            i = k
            continue
        if s[i].isupper():
            elem = s[i]
            j = i + 1
            while j < n and s[j].islower():
                elem += s[j]
                j += 1
            num_str = ""
            while j < n and s[j].isdigit():
                num_str += s[j]
                j += 1
            count = int(num_str) if num_str else 1
            if count < 1:
                return False
            atoms[elem] = atoms.get(elem, 0) + count * multiplier
            i = j
            continue
        return False
    return True


def parse_formula(formula: str) -> dict[str, int]:
    """Parse a chemical formula into element → count.

    e.g. ``H2O`` → {H:2, O:1}, ``Ca(OH)2`` → {Ca:1, O:2, H:2},
    ``CuSO4.5H2O`` → {Cu:1, S:1, O:9, H:10}.
    Returns {} when the string is not a complete formula.
    """
    cleaned = formula.strip()
    if not cleaned:
        return {}
    if cleaned[0] in _HYDRATE_DOTS or cleaned[-1] in _HYDRATE_DOTS:
        return {}
    if any(a in _HYDRATE_DOTS and b in _HYDRATE_DOTS for a, b in pairwise(cleaned)):
        return {}
    atoms: dict[str, int] = {}
    for fragment in _hydrate_fragments(cleaned):
        count, body = _leading_multiplier(fragment)
        if count < 1:
            return {}
        if not body or not _parse_formula_body(body, count, atoms):
            return {}
    return atoms


# Hydrogen is written after these when it bonds to them (NH3, PH3, AsH3), not before as in
# H2O or HCl.
_HYDRIDE_HEADS = frozenset({"N", "P", "As", "Sb"})


def _en(symbol: str) -> float:
    element = BY_SYMBOL.get(symbol)
    if element is None or element.electronegativity is None:
        return 99.0  # noble gases and unknown symbols go last
    return element.electronegativity


def _order(counts: dict[str, int]) -> list[str]:
    symbols = list(counts)
    if "C" in counts:
        # Hill system: carbon, hydrogen, then the rest alphabetically.
        rest = sorted(symbol for symbol in symbols if symbol not in {"C", "H"})
        return ["C", *(["H"] if "H" in counts else []), *rest]
    # No carbon: the more electropositive element first (NaCl, Fe2O3, H2SO4), by
    # electronegativity, with the hydrogen of NH3-type hydrides written last.
    ordered = sorted(symbols, key=lambda symbol: (_en(symbol), symbol))
    if "H" in counts and _HYDRIDE_HEADS & set(counts):
        ordered.remove("H")
        ordered.append("H")
    return ordered


def hill_formula(counts: dict[str, int]) -> str:
    """``{"O": 1, "C": 1, "H": 2}`` → ``CH2O``; ``{"Cl": 1, "Na": 1}`` → ``NaCl``."""
    return "".join(
        symbol if counts[symbol] == 1 else f"{symbol}{counts[symbol]}"
        for symbol in _order(counts)
        if counts[symbol]
    )
