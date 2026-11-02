"""What an average-atomic-mass question asks, and which of its numbers are not data.

The reader certifies one thing: the element's average atomic mass, when that is the whole
ask. A question that also asks for moles, a percent composition, an explanation or an
isotope's mass or abundance gets no card, nor does one that states the element's atomic mass
itself (then it asks for something else). A value quoted as the answer ("Show that its
relative atomic mass is 10.8", "compare it with 10.81 u", "[Ans. 10.8 amu]") is a check, never
an input.
"""

from __future__ import annotations

import re

from app.modules.chemistry.extractors.parsing import _N

# A whole number, never a prefix of one: "6.01" is not read out of "6.015".
NUMBER = rf"{_N}(?!\d|\.\d)"
NUMBER_RE = re.compile(NUMBER)
_PERCENT = re.compile(r"\s*%")
# Spans of text an isotope token covers: (start, end).
Spans = list[tuple[int, int]]

# A cue followed by the value it quotes, which ends the span.
_QUOTED = re.compile(
    rf"(?i:\b(?:show|verify|prove|check|confirm)\s+that\b[^.;?!\n]*?"
    rf"\b(?:is|=|equals|of)\s+(?:about\s+|approximately\s+)?"
    rf"|\bcompare\s+(?:it|this|that|your\s+\w+|the\s+(?:result|answer|value))?\s*(?:with|to)\s+"
    rf"(?:the\s+value\s+(?:of\s+)?)?"
    rf"|\b(?:accepted|actual|expected|known|standard)\b[^.;?!\n]*?\b(?:is|=|of|as)\s+"
    rf"|\bperiodic\s+table\b[^.;?!\n]*?"
    rf"|\bans(?:wer)?\b\.?\s*(?:is\s+)?:?\s*"
    rf"|\b(?:close\s+to|should\s+be)\s+(?:about\s+)?"
    rf"|\b(?:says?|said|got|gets|claims?|thinks?)\b[^.;?!\n]*?)"
    rf"{NUMBER}"
)
# The element's atomic mass, stated with a value: "has an atomic mass of 10.81", "its atomic
# mass is 6.94". An isotope's ("the atomic mass of 10B is 10.013 u") names the isotope.
_STATED_AVERAGE = re.compile(
    r"(?i:\batomic\s+(?:mass|weight)\b(?:\s+of\s+(?:the\s+)?(?P<whose>[\w^-]+))?)"
    r"\s*(?:(?i:is|=|:|was|of|equals|equal\s+to)\s*)?(?i:about\s+|approximately\s+)?"
    rf"{NUMBER}(?![A-Za-z%])"
)
_ISOTOPE_TOKEN = re.compile(r"\^?\d{1,3}[A-Z][a-z]?|[A-Za-z]+-\d{1,3}")

# Clauses end at sentence or clause punctuation, a line break or a part label "(b)".
_CLAUSE = re.compile(r"[.?!;:](?!\d)|\n|\((?:[a-h]|i{1,3}|iv|v)\)")
_PARENTHETICAL = re.compile(r"\((?!(?:[a-h]|i{1,3}|iv|v)\))[^()]*\)")
_ASK_WORDS = (
    r"calculate|find|determine|compute|work\s+out|what|how|why|explain|show|verify|prove"
    r"|check|confirm|compare|estimate|evaluate|give|predict|deduce|describe|identify"
)
_ASK = re.compile(rf"(?i:\b(?:{_ASK_WORDS})\b)|\?")
_AVERAGE = (
    r"(?:(?:average|relative|mean)\s+)?atomic\s+(?:mass|weight)"
    r"(?:\s+of\s+(?:an?\s+|the\s+)?(?:natural\s+|naturally\s+occurring\s+)?[a-z]+)?"
)
# Data after the ask, which asks nothing more: "from the following data", "which has three
# isotopes", "and compare it with the value in the periodic table".
_NO_ASK = rf"(?:(?!\b(?:{_ASK_WORDS})\b|\?).)*"
_TAIL = (
    rf"(?:\s*,?\s*(?:from|using|with|given|if|for|in|which|that|whose|where)\b{_NO_ASK})?"
    rf"(?:\s*,?\s*and\s+compare\s+(?:it|this|the\s+(?:result|answer|value))\s+(?:with|to)\b"
    rf"{_NO_ASK})?"
)
_ASKS_THE_AVERAGE = re.compile(
    r"(?is)(?:(?:hence|now|then|so|thus|therefore|please)\W+)?"
    r"(?:(?:using|from|with|given)\b[^,]*,\s*)?"
    rf"(?:(?:calculate|find|determine|compute|work\s+out|estimate|evaluate|what\s+is|what's)"
    rf"\s+(?:the\s+|its\s+)?(?:value\s+of\s+(?:the\s+)?)?{_AVERAGE}"
    rf"|(?:show|verify|prove|check|confirm)\s+that\s+(?:the\s+|its\s+)?{_AVERAGE}"
    r"\s+(?:is|=|equals)(?:\s+(?:about|approximately))?(?:\s+(?:u|amu))?"
    rf"|(?:the\s+)?{_AVERAGE}(?=\s*\?))"
    rf"{_TAIL}\W*"
)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def without_quoted(text: str, isotopes: Spans) -> str:
    """The text with each quoted answer's value blanked; isotopes and percents stay."""
    for quoted in _QUOTED.finditer(text):
        number = NUMBER_RE.search(text, quoted.start(), quoted.end())
        while number is not None and number.end() < quoted.end():
            number = NUMBER_RE.search(text, number.end(), quoted.end())
        if number is None or _PERCENT.match(text, number.end()):
            continue
        if not any(start <= number.start() < end for start, end in isotopes):
            text = _blank(text, number.start(), number.end())
    return text


def states_the_average(text: str) -> bool:
    """Whether the text gives the element's atomic mass a value (outside quoted answers)."""
    for match in _STATED_AVERAGE.finditer(text):
        whose = match.group("whose")
        if whose is None or not _ISOTOPE_TOKEN.fullmatch(whose):
            return True
    return False


# An average asked in another unit ("in grams per atom", "in kg") is another number: the
# card's value is in u (2026-11-01: "in grams per atom" got a 107.9 u card). g/mol is the
# same number as u. Symbols keep their case, so "exists as Mg-24" is magnesium, not mg.
_OTHER_UNIT = re.compile(
    r"\b(?i:in|as)\s+(?i:units?\s+of\s+)?(?:(?:g|(?i:grams?))(?!\s*(?:/|(?i:per)\s)\s*(?i:mol))"
    r"|[kmµ]g|[kM]?J|[kMG]?eV|(?i:kilograms?|milligrams?|joules?|electron\s*volts?))\b"
)


def asks_only_the_average(text: str, isotopes: Spans) -> bool:
    """Whether every clause that asks something asks the average atomic mass, and one does."""
    words = text
    for start, end in isotopes:
        words = _blank(words, start, end)
    if _OTHER_UNIT.search(words):
        return False
    words = _PARENTHETICAL.sub(lambda match: " " * len(match.group()), words)
    words = NUMBER_RE.sub(lambda match: " " * len(match.group()), words)
    asked = False
    start = 0
    for end in [*(match.end() for match in _CLAUSE.finditer(words)), len(words)]:
        clause = words[start:end]
        start = end
        if not _ASK.search(clause):
            continue
        if not _ASKS_THE_AVERAGE.fullmatch(clause.strip()):
            return False
        asked = True
    return asked
