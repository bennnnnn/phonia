"""One follow-up line read by a positive grammar: a new term, rate or down payment, or nothing.

The server works three changes only, the ones that are both common and safe: the live
"hmm what if i only do 3 years instead", the live "Down payment 3k" (after a car loan of
20k at 6%, the model's own payment was 50 cents off) and the app's own follow-up chips.

- A term: "3 years", "36 months", "over 4 years", "a 15 year mortgage", "pay it off in 2
  years" (and, for savings, "save for 20 years").
- A rate with its words: "at 6%", "6% apr", "6% interest", "the rate is 6%", "a 6% rate".
- A down payment, a sum with its words: "down payment 3k", "down payment of 3,000", "with
  5000 down", a put still to come ("I can put 3 grand down", "I'm putting 3k down", "what
  if I put 3k down"), or "3k down" opening the line or after a change frame. Not one gone
  by or only talked about ("I put 3k down", "it was 3k down", "is it 3k down"), a year
  ("down payment 2026") or a percent down ("20% down"): the model answers those.

The line must ask for a change: it opens (after "hmm", "ok", "so") with "what if", "what
about", "how about", "and", "or", "make it", "try", "do", "go with" or "i only do", or it
ends with "instead" or "instead of N". A down payment needs no such frame: its own words
say it is one. Every other word must belong to a term or rate
phrase or be filler; any word left over means the line is about something else, and the
model answers it as before. Four reviews (2026-10-25) of wider readers found shapes they
misread into numbers the reply then called the answer: a model year as a price, a card
payment as an APR, "it's been 5 years" as a 5-year mortgage, "what's 7%?" as a new rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial

from app.modules.money.phrases import (
    DURATION,
    PERCENT,
    count_value,
    percent_value,
    sum_phrase,
)
from app.modules.money.read import bare_year, read_sum

_MAX_CHARS = 200
_PCT = rf"(?<![\w.]){PERCENT}"
_TIME = rf"(?<![\w.]){DURATION}"
_RATE_WORD = r"(?:interest\s)?(?:rates?|aprs?|apy|interest)"
_FRAME_START = re.compile(
    r"^\W*(?:(?:hmm+|ok(?:ay)?|so)\W+)*"
    r"(?:what\sif|what\sabout|how\sabout|and|or|make\sit|try|do|go\swith|i\sonly\sdo)\b",
    re.I,
)
_FRAME_END = re.compile(
    r"\binstead(?:\sof\s(?:the\s)?\d[\d,.]*(?:\s?(?:%|percent|years?|yrs?|months?|mos?))?)?\W*$",
    re.I,
)
# "The rate is 6% for 10 years", "0% for 18 months": a rate for a while, not a loan's rate
# and term. "At 6% for 5 years" states the loan.
_RATE_FOR_A_WHILE = re.compile(
    r"(?<!\bat\s)(?<![\w.])\d{1,3}(?:\.\d{1,4})?\s?(?:%|percent)\s(?:\w+\s)?for\s\d", re.I
)
# Not a change of this loan: a person's age ("what if I'm 30 years"), time gone by ("it's
# been 5 years"), an interest-only loan (another kind of loan).
_NOT_A_CHANGE = re.compile(
    r"\b(?:i|we|he|she|they|you)(?:'m|'re|\s(?:am|are|was|were))\b|\b(?:im|age|aged|been)\b"
    r"|\binterest[\s-]only\b",
    re.I,
)
_TERM_PHRASES = [
    (rf"\bpay(?:ing)?\s(?:it\s)?off\s(?:in|within|over)\s{_TIME}", False),
    (rf"\b(?:keep\s)?(?:sav(?:e|ing)|invest(?:ing)?)\sfor\s{_TIME}", True),
    (rf"\b(?:(?:over|for|a|an|the|with|to)\s){{0,2}}{_TIME}(?:\s(?:term|loan|mortgage|plan))?",
     False),
]  # fmt: skip
_RATE_PHRASES = [
    rf"\b(?:(?:the|my|a|an)\s)?{_RATE_WORD}(?:\srate)?\s(?:is|was|were|be|of)\s{_PCT}",
    rf"\bat\s{_PCT}",
    rf"\b{_PCT}\s(?:apr|apy|interest(?:\srate)?|rate|fixed)\b",
]
_DOWN_WORDS = r"\sdown(?:\s?payment)?\b"
# A put still to come: "I can put", "we'll put", "I'm putting", "I want to put".
_PUT_AHEAD = (
    r"(?:(?:i|we)\s(?:can|could|will|would|want\sto|plan\sto|(?:am|are)\sgoing\sto)\sput"
    r"|(?:i|we)'(?:ll|d)\sput|(?:i'm|im|i\sam|we're|we\sare)\s(?:going\sto\sput|putting))\s"
)
_DOWNS = [
    re.compile(rf"\b(?:(?:a|the|my)\s)?down\s?payment(?:\s(?:of|is))?\s{sum_phrase('down')}\b"),
    re.compile(rf"\bwith\s{sum_phrase('down')}{_DOWN_WORDS}"),
    re.compile(rf"\b{_PUT_AHEAD}{sum_phrase('down')}{_DOWN_WORDS}"),
    # "3k down" opening the line, or after a frame ("what if 3k down", "and 3k down?").
    re.compile(rf"^\s*{sum_phrase('down')}{_DOWN_WORDS}"),
]
# Right after "what if", a plain put is one too: "what if I put 5000 down?". Not "and I put
# 3k down" or "I put 3k down instead": those tell of one made.
_WHAT_IF = re.compile(r"\bwhat\sif\W*$")
_FRAMED_DOWN = re.compile(rf"^\s*(?:(?:i|we)\s)?put\s{sum_phrase('down')}{_DOWN_WORDS}")
_TERMS = [(re.compile(pattern, re.I), saving) for pattern, saving in _TERM_PHRASES]
_RATES = [re.compile(pattern, re.I) for pattern in _RATE_PHRASES]
# Words a change line may hold beside its frame and its phrases. "Payment", "monthly",
# "make", "paid", "been" and "then" are never filler.
_FILLER = frozenset(
    "i we it it's its is was were be the a an only do just with go please if what about "
    "and so ok okay hmm hmmm".split()
)
# Beside a down payment only these: "it was", "is it" and "so it's" talk about one.
_DOWN_FILLER = frozenset("and so please then".split())
_WORDS = re.compile(r"[a-z0-9']+|[%$€£¥₹₦]")


@dataclass
class Change:
    """A new rate and a new term ("3", "years"), either or both."""

    rate: float | None = None
    term: tuple[float, str] | None = None
    # A new down payment and the currency it names ("" for none).
    down: tuple[float, str] | None = None
    # "Save for 20 years": a term only a savings plan takes.
    saving_term: bool = False
    clash: bool = False

    def take_down(self, match: re.Match[str]) -> str:
        said = None if bare_year(match["down"]) else read_sum(match["down"])
        self.clash = self.clash or self.down is not None or said is None
        self.down = said
        return " " * len(match.group(0))

    def take_rate(self, match: re.Match[str]) -> str:
        rate = percent_value(match["pct"])
        self.clash = self.clash or self.rate is not None or rate is None
        self.rate = rate
        return " " * len(match.group(0))

    def take_term(self, match: re.Match[str], saving: bool) -> str:
        self.clash = self.clash or self.term is not None
        self.term = (count_value(match["n"]), match["unit"])
        self.saving_term = saving
        return " " * len(match.group(0))


def read_change(line: str) -> Change | None:
    """The new term, rate and down payment ``line`` asks for, or None when it asks for no
    such change."""
    text = " ".join(line.lower().replace("\u2019", "'").split())
    if not text or len(text) > _MAX_CHARS or _RATE_FOR_A_WHILE.search(text):
        return None
    start, end = _FRAME_START.match(text), _FRAME_END.search(text)
    if end is not None:
        text = text[: end.start()]
    if start is not None:
        text = text[start.end() :]
    change = Change()
    framed = start is not None or end is not None
    what_if = start is not None and _WHAT_IF.search(start.group(0)) is not None
    for pattern in (*_DOWNS, _FRAMED_DOWN) if what_if else _DOWNS:
        text = pattern.sub(change.take_down, text)
    # "I'm putting 3k down" is read before "I'm" says the line is about the user.
    if (not framed and change.down is None) or _NOT_A_CHANGE.search(text):
        return None
    for pattern, saving in _TERMS:
        text = pattern.sub(partial(change.take_term, saving=saving), text)
    for pattern in _RATES:
        text = pattern.sub(change.take_rate, text)
    if change.rate is None and change.term is None and change.down is None:
        return None
    filler = _FILLER if change.down is None else _DOWN_FILLER
    if change.clash or any(word not in filler for word in _WORDS.findall(text)):
        return None
    return change
