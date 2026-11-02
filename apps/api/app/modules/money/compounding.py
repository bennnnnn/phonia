"""How often a request says interest compounds: "compounded quarterly" is 4 times a year.

Live (2026-10-31, an Ethiopian grade 11 book): "6% interest rate per year, compounded
quarterly" was worked monthly, and the card's interest was off by birr. A product that
grows money (``Product.settings`` has ``per_year``) works the frequency said. Each word of
compounding is read with what follows it ("compounded per quarter", "compounded on a
quarterly basis"), else with the one word before it ("semi annual compounding",
"quarterly compounded"). Any compounding word whose frequency is not read so
("compounded continuously", "compounded and paid quarterly", "compounding happens
quarterly", a bare "compounded"), or two frequencies that disagree, is ``UNKNOWN``: the
request gets no worked numbers, never monthly ones.
"""

from __future__ import annotations

import re

# (said after the word, said as the one word before it, times a year). Spaces and hyphens
# are one: "semi annual", "semi-annual" and "semiannual" are read alike.
_FREQUENCIES: tuple[tuple[str, str, int], ...] = (
    (r"semi-?annual(?:ly)?|half-?year(?:ly)?|twice\s(?:a|per|each)\syear|every\s(?:6|six)\smonths"
     r"|every\shalf-?year|per\shalf-?year", r"semi-?annual(?:ly)?|half-?yearly", 2),
    (r"quarterly|(?:every|each|per)\squarter|every\s(?:3|three)\smonths"
     r"|(?:4|four)\stimes\s(?:a|per)\syear", "quarterly", 4),
    (r"monthly|(?:every|each|per)\smonth|(?:12|twelve)\stimes\s(?:a|per)\syear", "monthly", 12),
    (r"weekly|(?:every|each|per)\sweek", "weekly", 52),
    (r"daily|(?:every|each|per)\sday", "daily", 365),
    (r"annual(?:ly)?|yearly|(?:every|each|per)\syear|per\sannum|once\s(?:a|per)\syear",
     r"annual(?:ly)?|yearly", 1),
)  # fmt: skip
_COMPOUND = re.compile(r"\bcompound(?:ed|ing|s)?\b", re.I)
# What may stand between the word and its frequency: "compounded interest is paid ...".
_LEAD = r"(?:\s+interest)?(?:\s+(?:is|are))?\s+(?:on\s+an?\s+)?"
_AFTER = [(re.compile(rf"{_LEAD}(?:{after})\b", re.I), count) for after, _, count in _FREQUENCIES]
_BEFORE = [
    (re.compile(rf"(?<![\w-])(?:{before})\s+$", re.I), count) for _, before, count in _FREQUENCIES
]

UNKNOWN = 0


def compounding_per_year(text: str) -> int | None:
    """Times a year ``text`` says interest compounds; None when no word of compounding is
    in it, ``UNKNOWN`` (0) when one is that this does not read, or two disagree."""
    text = re.sub(r"\b(semi|bi|half)[\s-]+(?=\w)", r"\1-", text)
    said: set[int] = set()
    for word in _COMPOUND.finditer(text):
        after, before = text[word.end() :], text[: word.start()]
        count = next((count for pattern, count in _AFTER if pattern.match(after)), None)
        if count is None:
            count = next((count for pattern, count in _BEFORE if pattern.search(before)), None)
        if count is None:
            return UNKNOWN
        said.add(count)
    if len(said) > 1:
        return UNKNOWN
    return said.pop() if said else None
