"""Which kind of a product a message names: a catalog ``Variant`` ("a used car").

The kind counts only when the vehicle being bought or financed is described as that
kind, in two fixed phrases:

- "buying a used car" (also buy, financing, finance, getting, get, purchasing, purchase,
  thinking of buying, looking at; used, pre-owned, second-hand or certified pre-owned;
  car, truck, SUV or vehicle),
- "a loan for a used car".

Nothing else names it, and none counts after "or", "vs", "instead of", "than",
"rather", "not", "sold", "selling" or "paid off" anywhere earlier in the message: that
used car is the alternative or another one. Reviews (2026-10-25) found looser readers
working a new 30k loan at the used-car rate for "... or buy a used car for 12000 cash?",
"I just sold a used car for 8000" and "my old used car loan is paid off". Missing a used
car is the safe direction: the reply then uses the new-car average and says so. The live
line was "i'm thinking of buying a used car for 14000".
"""

from __future__ import annotations

import re
from functools import cache

from app.modules.money.catalog import Product

_VEHICLE = r"(?:car|truck|suv|vehicle)"
_BUYING = (
    r"(?:buying|buy|financing|finance|getting|get|purchasing|purchase|thinking\sof\sbuying|"
    r"looking\sat)"
)
# The used car named after any of these is the alternative, or another car.
_ANOTHER_CAR_BEFORE = re.compile(
    r"\b(?:or|vs\.?|versus|instead\sof|than|rather|not|don'?t|never|sold|selling|paid\soff)\b",
    re.I,
)


@cache
def _phrases(words: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    kind = "(?:certified\\s)?(?:" + "|".join(re.escape(word) for word in words) + ")"
    return (
        re.compile(rf"\b{_BUYING}\s(?:a|an)\s{kind}[\s-]{_VEHICLE}\b", re.I),
        re.compile(rf"\ba\sloan\sfor\s(?:a|an)\s{kind}[\s-]{_VEHICLE}\b", re.I),
    )


def named_variant(product: Product, text: str) -> str:
    """The kind of ``product`` the message names ("buying a used car": "used"), or ""."""
    lowered = " ".join(text.lower().split())
    for variant in product.variants:
        for pattern in _phrases(variant.words):
            for match in pattern.finditer(lowered):
                if _ANOTHER_CAR_BEFORE.search(lowered, 0, match.start()) is None:
                    return variant.key
    return ""
