"""A line that says what a guessed amount was: the guess put right.

After "House buying for 400k" and "60k at 6 percent", the reply reads 60k as the down
payment and says so ("Read as: 60,000 is the down payment …", ``purchase``). "No, 60k is
the loan", "the loan is 60k" and "it's the loan" make it a loan of 60k with no price;
"it's the down payment" after a guessed loan makes it the down payment. Read by a
positive grammar: the whole line is one of these, and a sum it names is the guessed one.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.modules.money.phrases import sum_phrase
from app.modules.money.read import MoneyRequest, read_sum
from app.services.text_normalize import collapse_ws, straighten_apostrophes

_WHAT = r"(?P<what>loan|down\s?payment|down)"
_LEAD = r"(?:(?:no|nope|nah|actually|sorry)\W+)*"
_CORRECTION = re.compile(
    rf"{_LEAD}(?:{sum_phrase('sum')}\s(?:is|was)\s(?:the|my)\s{_WHAT}"
    rf"|(?:the|my)\s{_WHAT.replace('what', 'what2')}\s(?:is|was)\s{sum_phrase('sum2')}"
    rf"|(?:it's|its|it\sis|that's|thats|that\sis)\s(?:the|my)\s{_WHAT.replace('what', 'what3')})"
)


def is_correction(line: str) -> bool:
    return _read(line) is not None


def corrected(request: MoneyRequest, line: str) -> MoneyRequest | None:
    """``request`` with its guessed amount read the other way, or None."""
    found = _read(line)
    if found is None or request.guessed not in ("down", "loan") or request.price is None:
        return None
    what, said = found
    guessed = request.down if request.guessed == "down" else request.values.get("amount")
    if guessed is None or (said is not None and said != guessed) or what == request.guessed:
        return None
    values = dict(request.values)
    if what == "loan":
        values["amount"] = guessed
        return replace(
            request, values=values, changed=("amount",), price=None, down=None, guessed=""
        )
    if not 0 < guessed < request.price:
        return None
    values["amount"] = request.price - guessed
    return replace(request, values=values, changed=("amount",), down=guessed, guessed="")


def _read(line: str) -> tuple[str, float | None] | None:
    """What the line says the amount was ("loan" or "down") and the sum it names."""
    text = collapse_ws(straighten_apostrophes(line)).lower().strip(" .!?…")
    match = _CORRECTION.fullmatch(text)
    if match is None:
        return None
    what = match["what"] or match["what2"] or match["what3"]
    written = match["sum"] or match["sum2"]
    said = read_sum(written) if written else None
    if written and said is None:
        return None
    return ("loan" if what == "loan" else "down"), (said[0] if said else None)
