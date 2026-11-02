"""A turn about the chat's loan that builds no card of its own: the loan's figures, the app's.

Live (2026-10-25): "House buying for 400k" then "60k at 6 percent" (card: 340,000 at 6% over
30 years, $2,038.47 a month), then "How", "Yes" and "Yes", the last taking the reply's
offer of a 15-year comparison. No line after the card was a money request, so the model
worked the 15-year loan itself: $2,921.00 a month and $185,780.00 interest, where the loan
costs $2,869.11 and $176,440.38.

While the chat's last money request stands in the user's recent lines
(``follow_up.standing_request``) and this message is about that loan (``about_the_loan``),
the model reads the loan's figures at its own term and the common others
(``block.standing_block``). A message is about the loan when it names the loan's own
subject (its payment, interest, rate, term, "the loan", "the mortgage", a term with a
number) or asks for its maths, or when it is a short "yes" / "how" right after a reply
whose last sentence offered something about the loan. The reply's own sums are never
rewritten: a review (2026-10-26) found a nearness test turned rent, budgets, other
principals and totals with taxes into the loan's figures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.money.catalog import Product
from app.modules.money.solve import Worked, output_value

# The terms a reply about a loan most often compares, by product; the rest are the card's.
COMMON_TERMS: dict[str, tuple[float, ...]] = {
    "mortgage": (15, 20, 30),
    "car": (36, 48, 60, 72),
    "student": (5, 10, 20),
    "personal": (24, 36, 60),
    "loan": (3, 5, 10),
    "savings": (5, 10, 20, 30),
    "investing": (5, 10, 20, 30),
}
# The loan's own subject: its payment, interest, rate or term, the loan by name, or its maths.
# A count of years or months is a term only with a term's words ("over 15 years", "a 15-year
# loan", "what about 20 years?", "3 years instead", "15 or 30 years"): "how many years did
# WW2 last?" is not.
_LOAN_SUBJECT = re.compile(
    r"\b(?:monthly\s+)?payments?\b|\binterest\b|\b(?:interest\s+)?rates?\b|\baprs?\b"
    r"|\b(?:the|this|that|my|our|loan)\s+term\b|\bterm\s+(?:length|of)\b"
    r"|\b(?:the|this|that|my|our)\s+(?:loan|mortgage|car\s+loan|home\s+loan)\b"
    r"|\bmortgages?\b|\bcar\s+loans?\b"
    r"|\b(?:over|for|in)\s+\d{1,3}\s+(?:years?|yrs?|months?)\b|\b\d{1,3}-(?:year|month)\b"
    r"|\ba\s+\d{1,3}\s+(?:year|month)\s+(?:term|loan|mortgage)\b"
    r"|\b(?:what|how)\s+about\s+(?:a\s+)?\d{1,3}\s?(?:years?|yrs?|months?)\b"
    r"|\b\d{1,3}\s?(?:years?|yrs?|months?)\s+instead\b"
    r"|\b\d{1,3}\s+(?:or|vs\.?|versus)\s+\d{1,3}[\s-]?(?:years?|yrs?|months?)\b"
    r"|\bshow\s(?:me\s)?(?:the\s)?(?:math|maths|working|steps|calculation)\b"
    r"|\bhow\sdid\syou\s(?:get|work\sout|calculate)\b",
    re.IGNORECASE,
)
_SHORT = re.compile(
    r"^\W*(?:(?:yes|yeah|yep|yup|sure|ok(?:ay)?|please|go\sahead|do\sit|do\sthat|sounds\sgood"
    r"|let'?s\sdo\sit|show\sme|how|why|how\sso|go\son)\W*){1,3}"
    r"(?:(?:please|thanks|thank\syou)\W*)?$",
    re.IGNORECASE,
)
# The last sentence of a reply that offers the loan's figures: "If you'd like, I can also
# show how a 15-year term changes the monthly payment", "Want a breakdown?". One that only
# mentions a payment or the loan ("Want me to email your lender about the loan?") does not.
_OFFER = re.compile(r"\b(?:want|like|can|could|shall|should|happy\sto)\b", re.IGNORECASE)
_OFFER_ABOUT = re.compile(
    r"\b(?:compar\w*|break\s?down|breakdown|math|maths|calculation|amorti[sz]\w*|schedule"
    r"|\d{1,3}[\s-](?:year|month)|(?:other|another|different|shorter|longer)\s+terms?)\b",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Figures:
    """The loan's outputs at every term its slider offers, at its own rate."""

    term_name: str
    by_term: dict[float, dict[str, float]]


def about_the_loan(text: str, last_reply: str) -> bool:
    """``text`` is about the loan the chat is discussing: it names the loan's own subject or
    asks for its maths, or it is a short "yes" / "how" taking the last reply's offer about it."""
    if not text or len(text) > 600:
        return False
    if _LOAN_SUBJECT.search(text):
        return True
    return bool(_SHORT.match(text.strip()) and _offers_about_the_loan(last_reply))


def _offers_about_the_loan(reply: str) -> bool:
    sentences = [part.strip() for part in _SENTENCES.split(reply or "") if part.strip()]
    if not sentences:
        return False
    last = sentences[-1]
    return bool(_OFFER.search(last) and _OFFER_ABOUT.search(last))


def term_name(product: Product) -> str | None:
    return next((item.name for item in product.inputs if item.name in ("years", "months")), None)


def figures(worked: Worked) -> Figures | None:
    """The loan's outputs at each term on its slider; None for a product with no term."""
    product = worked.product
    name = term_name(product)
    item = product.input(name) if name else None
    if name is None or item is None:
        return None
    span = item.span
    step = span.step or 1.0
    by_term: dict[float, dict[str, float]] = {}
    term = span.low
    while term <= span.high + 1e-9:
        values = {**worked.values, name: term}
        outputs = {
            name: output_value(expression, values)
            for name, expression in worked.expressions().items()
        }
        by_term[term] = {key: value for key, value in outputs.items() if value is not None}
        term += step
    return Figures(name, by_term)
