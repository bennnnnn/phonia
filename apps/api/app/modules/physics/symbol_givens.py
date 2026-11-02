"""Read textbook symbol givens: ``F = 20 N, m = 5 kg, find a``.

The law binder reads quantities by name ("a force of 20 N ... find the
acceleration"). A worksheet writes the same problem with symbols, which the
binder never matched, so the line fell through to algebra and ``kg`` became
``k * g``. This module rewrites a line made only of symbol givens and one asked
symbol into the named form, then the ordinary physics path reads it.

It is closed: every given must be ``symbol = number [unit]``, at least one must
carry a unit, each unit must have the dimension its symbol names, and the ask
must be one known symbol. Anything else returns ``None``. An ambiguous symbol
(``P`` is power or pressure) takes its meaning from the unit; an asked one is
tried in each meaning and kept only when exactly one of them binds.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import lru_cache

from app.modules.physics.givens import unit_at
from app.services.law_binding.units import dimension_of
from app.services.number_text import SIGNED_DECIMAL_SCI

# Symbol → (quantity name, SI unit) in order of preference.
_SYMBOLS: dict[str, tuple[tuple[str, str], ...]] = {
    "F": (("force", "N"),),
    "m": (("mass", "kg"),),
    "a": (("acceleration", "m/s^2"),),
    "u": (("initial velocity", "m/s"),),
    "v": (("velocity", "m/s"),),
    "t": (("time", "s"),),
    "d": (("distance", "m"),),
    "s": (("distance", "m"),),
    "h": (("height", "m"),),
    "r": (("radius", "m"),),
    "W": (("work", "J"), ("weight", "N")),
    "E": (("energy", "J"),),
    "KE": (("kinetic energy", "J"),),
    "PE": (("potential energy", "J"),),
    "P": (("power", "W"), ("pressure", "Pa")),
    "p": (("momentum", "kg*m/s"),),
    "I": (("current", "A"),),
    "V": (("voltage", "V"), ("volume", "m^3")),
    "R": (("resistance", "ohm"),),
    "Q": (("charge", "C"),),
    "q": (("charge", "C"),),
    "f": (("frequency", "Hz"),),
    "T": (("period", "s"), ("temperature", "K"), ("tension", "N")),
    "\u03bb": (("wavelength", "m"),),  # lambda
    "\u03c1": (("density", "kg/m^3"),),  # rho
    "k": (("spring constant", "N/m"),),
    "A": (("area", "m^2"),),
}
_SYMBOL = "(?:KE|PE|[A-Za-z\u03bb\u03c1])"
_GIVEN = re.compile(rf"(?P<symbol>{_SYMBOL})\s*=\s*(?P<number>{SIGNED_DECIMAL_SCI})")
_ASK = re.compile(
    rf"(?:find|calculate|compute|determine|what\s+is|solve\s+for)\s+(?:the\s+)?"
    rf"(?P<symbol>{_SYMBOL})\s*[.?!]*\s*$",
    re.IGNORECASE,
)
_PREFIX = re.compile(r"^\s*(?:given\s*:?\s*)?", re.IGNORECASE)
_SEPARATOR = re.compile(r"^[\s,;]*(?:and\s[\s,;]*)?$|^[\s,;.]*$", re.IGNORECASE)
_MAX_GIVENS = 6


@lru_cache(maxsize=64)
def _si_dimension(unit: str) -> str | None:
    found = unit_at(f"1 {unit}", 1)
    return None if found is None else dimension_of(found[1])


def _article(noun: str) -> str:
    return "an" if noun[0] in "aeiou" else "a"


def _named_given(symbol: str, number: str, unit: tuple[str, str] | None) -> str | None:
    meanings = _SYMBOLS.get(symbol)
    if meanings is None:
        return None
    if unit is None:
        if len(meanings) != 1:
            return None
        noun, si_unit = meanings[0]
        return f"{_article(noun)} {noun} of {number} {si_unit}"
    stated = dimension_of(unit[1])
    for noun, si_unit in meanings:
        if stated is not None and stated == _si_dimension(si_unit):
            return f"{_article(noun)} {noun} of {number} {unit[0]}"
    return None


def _read(text: str) -> tuple[list[str], str] | None:
    """The named givens and the asked symbol, when the line is only those."""
    body = _PREFIX.sub("", text, count=1)
    ask = _ASK.search(body)
    if ask is None:
        return None
    asked = ask.group("symbol")
    givens_text = body[: ask.start()]
    stated: list[tuple[str, str, tuple[str, str] | None]] = []
    cursor = 0
    for match in _GIVEN.finditer(givens_text):
        if not _SEPARATOR.match(givens_text[cursor : match.start()]):
            return None
        end = match.end("number")
        unit = unit_at(givens_text, end)
        if unit is not None:
            spelled = givens_text.find(unit[0], end)
            if spelled == -1 or givens_text[end:spelled].strip():
                return None
            end = spelled + len(unit[0])
        stated.append((match.group("symbol"), match.group("number"), unit))
        cursor = end
    symbols = [symbol for symbol, _number, _unit in stated]
    if not stated or len(stated) > _MAX_GIVENS or all(unit is None for *_, unit in stated):
        return None
    if not _SEPARATOR.match(givens_text[cursor:]) or asked not in _SYMBOLS:
        return None
    if asked in symbols or len(set(symbols)) != len(symbols):
        return None
    final_velocity = "u" in symbols or asked == "u"
    named: list[str] = []
    for symbol, number, unit in stated:
        phrase = _named_given(symbol, number, unit)
        if phrase is None:
            return None
        if symbol == "v" and final_velocity:
            phrase = phrase.replace("velocity", "final velocity", 1)
        named.append(phrase)
    return named, asked


def symbol_givens_requests(text: str) -> list[str]:
    """Every named rewrite of a symbol-givens line, one per meaning of the ask."""
    if len(text) > 400:
        return []
    read = _read(text)
    if read is None:
        return []
    named, asked = read
    givens = ", ".join(named[:-1]) + (" and " if len(named) > 1 else "") + named[-1]
    final_velocity = any("initial velocity" in phrase for phrase in named)
    requests = []
    for noun, _unit in _SYMBOLS[asked]:
        if asked == "v" and final_velocity:
            noun = "final velocity"
        requests.append(f"Given {givens}, find the {noun}.")
    return requests


def is_symbol_givens_request(text: str) -> bool:
    """``P = 200 W, t = 10 s, find W``: a physics line, even with no law to bind."""
    return bool(symbol_givens_requests(text))


def named_symbol_request(text: str, binds: Callable[[str], bool]) -> str | None:
    """The one named rewrite that ``binds`` accepts, or None when none or several do."""
    accepted = [request for request in symbol_givens_requests(text) if binds(request)]
    return accepted[0] if len(accepted) == 1 else None
