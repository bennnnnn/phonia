"""A tip, a tax or a service charge on a bill: "what's a 15% tip on 48 dollars".

"15% of 48" was verified, but "a 15% tip on 48 dollars" went to the model, which wrote
`$48 \\times 0.15 = 7.20$`: its dollar opened maths, so the sign was gone, and asked for
the total next it did the same. The charge is verified in the bill's money, and the
total with it is said under the card, so "so what's the total" is answered already.
Money is kept in exact decimals, never floats.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer

_KIND = r"(?P<kind>tip|gratuity|tax|sales\s+tax|vat|service\s+charge|service\s+fee)"
_RATE = r"(?P<rate>\d{1,3}(?:\.\d{1,2})?)\s*%"
# The sign may be gone (prepare reads "$48 ... $7" as maths); a money word can stand in.
_AMOUNT = (
    r"(?P<sign>[$€£])?\s*(?P<base>\d{1,7}(?:\.\d{1,2})?)"
    r"(?:\s*(?P<word>dollars?|bucks|usd|euros?|eur|pounds?|gbp))?"
)
_BILL = r"(?:\s+(?:bill|check|tab|meal|order|total|dinner|lunch))?"
_ON = r"\s+(?:on|of|for)\s+(?:(?:a|an|the|my)\s+)?(?:(?:bill|check|total)\s+of\s+)?"
_LEAD = (
    r"(?:(?:btw|ok|okay|so|hey|and|quick\s+question)\s*,?\s+)?"
    r"(?:(?:what(?:'s|s|\s+is|\s+would\s+be)|how\s+much\s+(?:is|would\s+be)|calculate|"
    r"work\s+out|find)\s+)?(?:(?:a|an|the|my)\s+)?"
)
_FORMS = (
    # "a 15% tip on $48", "15% tax for a $30 order"
    re.compile(rf"{_LEAD}{_RATE}\s+{_KIND}{_ON}{_AMOUNT}{_BILL}", re.IGNORECASE),
    # "the tip at 15% on $48", "a tip of 20% on a $65.50 bill"
    re.compile(rf"{_LEAD}{_KIND}\s+(?:of|at)\s+{_RATE}{_ON}{_AMOUNT}{_BILL}", re.IGNORECASE),
)
# The sign the answer card draws (LaTeX), and the one the line under it writes.
_SIGNS = {"$": (r"\$", "$"), "€": ("€", "€"), "£": ("£", "£")}
_WORD_SIGN = {
    "dollar": "$", "dollars": "$", "bucks": "$", "usd": "$",
    "euro": "€", "euros": "€", "eur": "€",
    "pound": "£", "pounds": "£", "gbp": "£",
}  # fmt: skip
_CENT = Decimal("0.01")


def extract_charge_intent(cleaned: str) -> MathIntent | None:
    """The whole message asks for a tip, tax or service charge at a rate on an amount."""
    text = " ".join(cleaned.split()).rstrip(" ?.!")
    match = next((m for form in _FORMS if (m := form.fullmatch(text))), None)
    if match is None:
        return None
    rate = Decimal(match.group("rate"))
    if not 0 < rate <= 100:
        return None
    word = (match.group("word") or "").casefold()
    sign = match.group("sign") or _WORD_SIGN.get(word, "")
    kind = " ".join(match.group("kind").casefold().split())
    return MathIntent(
        kind="arithmetic",
        school_op="percent_charge",
        # The bill, the rate, its money sign ("" when none), and the charge's name.
        arithmetic_operands=[match.group("base"), match.group("rate"), sign, kind],
        operation="solve",
    )


def charge_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    operands = intent.arithmetic_operands or []
    if len(operands) != 4:
        return None
    base_text, rate_text, sign, kind = operands
    # The reading lost a written sign ("$48"); the request as typed still has it.
    written = re.search(
        rf"([$\u20ac\u00a3])\s*{re.escape(base_text)}(?!\d)", intent._request_text or ""
    )
    sign = sign or (written.group(1) if written else "")
    base, rate = Decimal(base_text), Decimal(rate_text)
    charge = (base * rate / 100).quantize(_CENT, rounding=ROUND_HALF_UP)
    total = (base + charge).quantize(_CENT)
    card_sign, line_sign = _SIGNS.get(sign, ("", ""))
    answer = f"{card_sign}{charge}"
    lines.append(f"{rate_text}% of {base_text} = {charge}")
    lines.append(f"Total = {base_text} + {charge} = {total}")
    label = "VAT" if kind == "vat" else kind
    direct = f"```answer\n{answer}\n```\n\nWith the {label}, the total is **{line_sign}{total}**.\n"
    return replace(finish_with_answer(lines, answer), direct_reply=direct)
