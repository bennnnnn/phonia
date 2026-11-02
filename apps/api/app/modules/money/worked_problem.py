"""A money question from a lesson: a number to work out from values it all states.

"Ato Alula deposited Birr 3,000 … What is the amount of interest obtained at the end of
seven years?" and "Moges wants to buy a house that costs Birr 250,000 …" got the right
numbers in two lines over a calculator card (2026-10-31): nothing a student could follow
or hand in. A worked problem's reply is laid out the way the STEM replies are.

It is read from what the question asks, never from who is in it (a name is a brand as
often as a person): a number to work out ("What is …?", "Find …", "Calculate …") from
values the question sets out first (a sentence before the ask, or "If …"/"Suppose …"), or
ordered worked out, that is not about the asker's own money ("I", "my", "we": a textbook's
"Suppose you borrow …" is the reader's exercise) and not a choice or advice ("should",
"better", "compare", "refinance"). "Mortgage $300k at 6.5% 30 years payment?" is anyone's
quick ask. And the layout is only used when the server read every value it worked with from
the question (``lays_out_working``): laid out as homework, a term, a rate or a compounding
the app assumed would look like the book's own.
"""

from __future__ import annotations

import math
import re

from app.modules.money.read import MoneyRequest, stated_sums
from app.modules.money.solve import Worked

_OWN = re.compile(
    r"\b(?:i|i'm|i've|i'd|i'll|me|my|mine|we|we're|we've|we'd|our|ours|us)\b", re.IGNORECASE
)
_CHOICE = re.compile(
    r"\b(?:should|shall|better|best|worth|recommend\w*|advi[cs]e|compar\w*|refinanc\w*"
    r"|versus|vs\.?|afford|or\s+(?:a|an|the)\s+\d|which\s+(?:one|is|are|of|would|should))",
    re.IGNORECASE,
)
_ORDER = re.compile(r"\b(?:calculate|compute|find|determine|work\s+out)\b", re.IGNORECASE)
# The values set out before the ask: "If you deposit $1,000 …, how much …?", "Suppose …".
_CONDITION = re.compile(r"^\W*(?:if|suppose|assume|given)\b", re.IGNORECASE)
# A sentence ends at ".", "!" or ";" before a space, or at a line's end: "$250.000" and
# "4.5%" go on.
_SENTENCE = re.compile(r"(?<=[.!;])\s+|\s*\n\s*")


def _sets_out_values(text: str) -> bool:
    """The question states its values before it asks: a sentence with a number ahead of
    the last one ("A loan of $20,000 at 6% for 5 years. What is the payment?"), or a
    condition it opens with. "Hey, what would a $15,000 car loan … cost?" asks at once."""
    sentences = _SENTENCE.split(text.strip())
    return _CONDITION.match(text) is not None or any(
        re.search(r"\d", sentence) for sentence in sentences[:-1]
    )


def is_worked_problem(text: str) -> bool:
    """A number to work out, set out as an exercise, not about the asker's own money and
    not a choice."""
    asked = _ORDER.search(text) is not None or ("?" in text and _sets_out_values(text))
    return asked and _OWN.search(text) is None and _CHOICE.search(text) is None


def lays_out_working(text: str, request: MoneyRequest, worked: Worked | None) -> bool:
    """A worked problem whose numbers are all the question's: no term, rate or sum assumed
    (a flow the question leaves out, no monthly deposit beside a lump sum, is no
    assumption), every sum and rate it states used, and no follow-up. Compounding must be
    the question's (``request.settings``): "6% per year" worked monthly is 4,561.11 where
    a book compounding yearly prints 4,510.89 (2026-11-01). A monthly deposit is never laid
    out: when in the month it is paid, and a recurring deposit's simple interest (ICSE's
    Rs 39,885 against the app's 39,930.10), are the book's convention, not the question's."""
    if worked is None or request.changed or request.rates_only:
        return False
    product = request.product
    if "per_year" in product.settings and "per_year" not in request.settings:
        return False
    if request.values.get("deposit"):
        return False
    defaults = product.defaults
    if any(defaults.get(name) != 0 for name in worked.assumed):
        return False
    # Every sum and rate it states is one the numbers use: "a house that costs 250,000 …
    # saved 50,000 … as a deposit" worked as a 250,000 loan left the 50,000 unread.
    used = [value for value in (*request.values.values(), request.price, request.down) if value]
    if request.rates_given > 1 or any(
        not any(math.isclose(stated, value) for value in used) for stated in stated_sums(text)
    ):
        return False
    return is_worked_problem(text)
