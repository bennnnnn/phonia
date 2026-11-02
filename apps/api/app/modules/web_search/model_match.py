"""A search hit about a much older model of the thing a release question names.

"Is iPhone 19 out?" searched well, but two of its five sources were "Apple to Release
iPhone 6 Models Sept. 19" (2014) and "Apple iPhone 3GS Sold Out? Nope!" (2009): the
engine matched "iPhone", "19" and "out". A hit whose every model of the asked product
is more than two generations older (iPhone 6, iPhone 3GS) goes. A page about a near or
newer model stays: Wikipedia's list ending at the iPhone 17 and Apple's store selling the
iPhone 18 are how a reply knows the 19 is not out, and dropping them left none. So does
a hit naming the asked model or no model; years are not model numbers. When every hit
would go, all stay: a reply with sources beats "I couldn't verify that".
"""

from __future__ import annotations

import re

from app.gateways.web_search_gateway import WebSearchHit
from app.modules.web_search.release_asks import released_thing

# A name and its number: "iPhone 19", "GTA 6", "PS6", "GPT-6", "season 5", "Python 3.13".
_NUMBER = r"\d{1,4}(?:\.\d{1,3})*"
_MODEL = re.compile(
    rf"(?<![\w.])(?P<name>[^\W\d_][\w+]*?)[ -]?(?P<number>{_NUMBER})(?!\d)", re.IGNORECASE
)
_YEAR = re.compile(r"(?:19|20)\d{2}")


def asked_model(query: str) -> tuple[str, str] | None:
    """The product and number a release question names: ("iphone", "19"), else None."""
    thing = released_thing(query)
    if thing is None:
        return None
    models = [m for m in _MODEL.finditer(thing) if not _YEAR.fullmatch(m.group("number"))]
    if not models:
        return None
    last = models[-1]
    return last.group("name").casefold(), last.group("number")


def _numbers_after(name: str, text: str) -> set[str]:
    pattern = re.compile(rf"(?<![\w.]){re.escape(name)}[ -]?({_NUMBER})(?!\d)", re.IGNORECASE)
    return {number for number in pattern.findall(text) if not _YEAR.fullmatch(number)}


# How many generations older a model may be and still say something about the asked one.
_NEAR = 2


def _generation(number: str) -> int:
    return int(number.split(".", 1)[0])


def is_another_model(hit: WebSearchHit, model: tuple[str, str]) -> bool:
    """``hit`` names the asked product only with models over two generations older."""
    name, number = model
    numbers = _numbers_after(name, f"{hit.title}\n{hit.snippet}")
    return bool(numbers) and max(map(_generation, numbers)) < _generation(number) - _NEAR


def drop_other_models(hits: list[WebSearchHit], query: str) -> list[WebSearchHit]:
    """``hits`` without those about a much older model than the one ``query`` asks about."""
    model = asked_model(query)
    if model is None:
        return hits
    kept = [hit for hit in hits if not is_another_model(hit, model)]
    return kept or hits
