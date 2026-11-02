"""Algebra word problems: a cheap gate, one structured translation, a number guard.

"Maria is three times as old as her son; together they are 48" has no
equation for the regex extractors to find. When the gate below fires and no
extractor matched, one bounded call on the fast alias translates the problem
into unknowns and equations (``WordProblemSetup``). The existing secondary
structured-model route is used when the primary provider times out or returns
invalid JSON, so a transient extractor failure does not silently downgrade a
school problem to an unverified one-line chat answer. Before SymPy sees it,
every number in those equations must be one the problem states, in digits or
in words, so a translation cannot smuggle in a value the student never gave.
SymPy then has to find exactly one solution in the stated domain
(``solve/word_problem.py``); otherwise the turn keeps its normal path.

A translation is a model's reading: its solve goes to the model as an unchecked setup to
check against the words, never as a verified card (``tools/prompt.py``). Only a setup the
templates read is certified. A process that never ends is no setup at all.
"""

from __future__ import annotations

import logging
import re
from fractions import Fraction

from app.core.config import Settings
from app.models.routing_lanes import ROUTING
from app.modules.math.request_consumption import request_consumption_complete
from app.modules.math.schemas import MathIntent
from app.modules.math.schemas.word_problem import WordProblemSetup
from app.services.number_text import NUMBER_WORDS

logger = logging.getLogger(__name__)

_MIN_CHARS = 25
_MAX_CHARS = 600

_MATH_TARGET = (
    r"(?:amounts?|numbers?|integers?|values?|totals?|sums?|differences?|products?|"
    r"quotients?|remainders?|costs?|prices?|ages?|distances?|lengths?|widths?|"
    r"heights?|areas?|perimeters?|volumes?|speeds?|times?|rates?|percentages?|"
    r"shares?|counts?|weights?|masses?|coordinates?|solutions?|roots?)"
)
_HOW_MUCH_TARGET = (
    r"(?:money|amount|total|cost|price|pay|paid|spend|spent|earn|earned|receive|"
    r"received|left|remain|more|less|share|weight|mass|distance|time|length|"
    r"width|height|area|perimeter|volume|speed|rate|percentage|percent)"
)
_QUANTITATIVE_CHANGE = (
    r"(?:paid|spent|earns?|gives?|gave|receives?|received|buys?|bought|sells?|sold|"
    r"loses?|lost|adds?|added|removes?|removed|takes?|took)"
)
_MATH_REQUEST = re.compile(
    r"\b(?:calculate|compute)\b"
    r"|\bhow\s+(?:old|long|far|fast|tall|wide)\b"
    rf"|\bhow\s+much\b[^.?!]{{0,50}}\b{_HOW_MUCH_TARGET}\b"
    r"|\bhow\s+much\s+(?:is|are|was|were)\s+each\b"
    r"|\bhow\s+much\b[^.?!]{0,50}\beach"
    r"(?:\s+[a-z][a-z'-]*){0,3}\s+"
    r"(?:get|gets|receive|receives|have|has|pay|pays|earn|earns|spend|spends)\b"
    rf"|\b(?:find|determine)\b[^.?!]{{0,50}}\b{_MATH_TARGET}\b"
    rf"|\bsolve\s+for\s+(?:the\s+)?{_MATH_TARGET}\b"
    rf"|\bwhat\s+(?:is|are|was|were)\b[^.?!]{{0,50}}\b{_MATH_TARGET}\b"
    rf"|\b(?:what|which)\s+{_MATH_TARGET}\s+(?:is|are|was|were)\b"
    r"|\bwhat\s+(?:does|did)\b[^.?!]{0,50}\b(?:cost|weigh|measure|equal)\b",
    re.IGNORECASE,
)
_WORK_OUT_REQUEST = re.compile(
    rf"\bwork\s+out\b[^.?!]{{0,60}}(?:\bhow\s+(?:many|much|old|long|far|fast|"
    rf"tall|wide)\b|\b{_MATH_TARGET}\b)",
    re.IGNORECASE,
)
_INITIAL_STATE = (
    r"(?:initially|originally|previously|before(?:hand)?|"
    r"at\s+(?:first|the\s+(?:start|beginning)))"
)
_HOW_MUCH_INITIAL_REQUEST = re.compile(
    r"\bhow\s+much\s+(?:"
    rf"(?:do|does|did)\b[^.?!]{{0,45}}\b(?:have|has|had)\b[^.?!]{{0,16}}{_INITIAL_STATE}"
    r"|(?:do|does|did)\b[^.?!]{0,45}\bstart(?:ed)?\s+with\b"
    rf"|(?:was|were)\b[^.?!]{{0,45}}{_INITIAL_STATE}"
    r")",
    re.IGNORECASE,
)
_HOW_MANY_REQUEST = re.compile(
    r"\bhow\s+many\b",
    re.IGNORECASE,
)
_HOW_MANY_ADVICE = re.compile(
    r"\bhow\s+many\b[^.?!]{0,80}\b(?:should|could|would|can|may|might|recommend|suggest)\b",
    re.IGNORECASE,
)
_HOW_MANY_NAMED_TARGET = re.compile(
    r"\bhow\s+many\s+(?!do\b|does\b|did\b|is\b|are\b|was\b|were\b|"
    r"should\b|could\b|would\b|can\b|may\b|might\b)[a-z][a-z'-]*\b",
    re.IGNORECASE,
)
_HOW_MANY_ELLIPSIS_TARGET = re.compile(
    r"\bhow\s+many\s+(?:(?:do|does|did)\b[^.?!]{0,40}\b"
    r"(?:have|has|had|start(?:ed)?\s+with|remain(?:s|ed|ing)?|left)\b"
    r"|(?:is|are|was|were)\s+(?:left|remaining|there)\b)",
    re.IGNORECASE,
)
_PRONOUN_REQUEST = re.compile(
    r"\b(?:what\s+(?:is|are|was|were)\s+(?:it|that|this|they|those|these)"
    r"|what\s+(?:is|was)\s+(?:left|remaining)"
    r"|(?:find|determine)\s+(?:it|that|this|them|those|these)"
    r"|what\s+(?:does|did)\s+(?:[a-z][a-z'-]*\s+){1,3}have)\b",
    re.IGNORECASE,
)
_PRONOUN_MATH_CONTEXT = re.compile(
    rf"\b{_MATH_TARGET}\b|\b(?:times\s+as|twice|double|triple|thrice|half|"
    r"more\s+than|less\s+than|fewer\s+than|greater\s+than|older|younger|"
    rf"together|altogether|combined|consecutive|equally|years\s+old|percent|"
    rf"{_QUANTITATIVE_CHANGE}|left|remain(?:s|ing)?)\b|%",
    re.IGNORECASE,
)
_RELATION = re.compile(
    r"\b(?:times\s+as|twice|double|triple|thrice|half|more\s+than|less\s+than|fewer\s+than"
    r"|greater\s+than|older|younger|sum|total|together|altogether|combined|difference"
    rf"|product|consecutive|each|per|costs?|left|remain(?:s|ing)?|shared?"
    rf"|{_QUANTITATIVE_CHANGE}|gets?|got"
    r"|split|equally|ages?|years\s+old|numbers?|integers?|percent)\b|%",
    re.IGNORECASE,
)
# A stated rate scaled to a third amount is a proportion: "3 cups of flour for
# 12 cookies … for 30 cookies", "2 eggs make 8 pancakes", "8 litres per 100 km".
# "2 rooms for 3 nights, how many towels?" has no third amount.
_STATED_RATE = re.compile(
    r"\b\d+(?:\.\d+)?\s+[a-z]+(?:\s+of\s+[a-z]+)?\s+"
    r"(?:for|per|makes?|serves?|feeds?|to\s+make)\s+\d",
    re.IGNORECASE,
)
# A process that never ends sums an infinite series, which no finite setup holds: "If this
# process continues without end, find the total tax" was summed over three rounds, 3920 Birr
# for 5000 (2026-11-01).
_ENDLESS = re.compile(
    r"\b(?:(?:continues?|goes\s+on|repeats?|keeps?\s+going)\s+(?:on\s+)?(?:without\s+(?:an?\s+)?"
    r"end|for\s*ever|endlessly|indefinitely)|ad\s+infinitum|never\s+(?:ends|stops)"
    r"|infinite(?:ly)?\s+(?:series|sequence|process|number\s+of\s+(?:times|rounds|steps)))\b",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?|\.\d+")
# The cardinals from number_text's one table; the words a word problem adds on top.
_NUMBER_WORDS: dict[str, tuple[int, ...]] = {
    **{word: (value,) for word, value in NUMBER_WORDS.items()},
    "hundred": (100,),
    "thousand": (1000,),
    "twice": (2,),
    "double": (2,),
    "triple": (3,),
    "thrice": (3,),
    "half": (2,),
    "halves": (2,),
    "third": (3,),
    "thirds": (3,),
    "quarter": (4,),
    "quarters": (4,),
    "fourth": (4,),
    "fifth": (5,),
    "dozen": (12,),
    "percent": (100,),
    "consecutive": (1, 2, 3, 4, 6),
    "even": (2,),
    "odd": (2,),
}
_FRACTION_WORDS = frozenset(
    {"half", "halves", "third", "thirds", "quarter", "quarters", "fourth", "fifth"}
)
_WORD = re.compile(r"[a-z]+")
# "1/2" for half and "15/100" for 15% are one stated value, not two numbers.
_FRACTION = re.compile(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])")
# "(1 - 0.2)" for 20% off: the 1 belongs to a stated rate between 0 and 1.
_ONE_AND_RATE = re.compile(r"\(\s*1\s*[+-]\s*(\d*\.\d+|\d+\s*/\s*\d+)\s*\)")

_PROMPT = """Translate the word problem into equations for a symbolic solver.

Return JSON only:
{"found": true,
 "unknowns": [{"symbol": "s", "meaning": "the son's age now", "unit": "years"}],
 "equations": [{"equation": "m = 3*s", "source": "Maria is three times as old as her son"}],
 "targets": [{"expr": "s", "meaning": "the son's age now", "unit": "years"}],
 "whole_numbers": true, "positive": true}

Rules:
- One lowercase letter per unknown (not e or i). At most 3 unknowns, 4 equations.
- Each equation has exactly one "=", in plain ASCII math: * for times, ^ for powers.
- The quantity the question asks you to find is an unknown, not "missing data".
- Accept informal grammar, misspellings, and singular/plural mistakes when the
  quantities and relationships still determine one answer.
- Preserve quantity changes as one balance equation. For example: "Lina has
  12 blue beads and some red beads, gives away 4 red beads, and has 15 beads
  left" becomes `12 + r - 4 = 15` when `r` is the initial red-bead count.
- Use only numbers the problem states. Spelled numbers are fine ("twice" is 2,
  "half" is 1/2, "15%" is 15/100). Never compute, round, or add a number.
- "source" quotes the words of the problem that equation says.
- targets are what the question asks for, as an unknown or an expression in them.
- whole_numbers: true when the unknowns count people or things.
- positive: true when the unknowns are ages, lengths, prices, or amounts.
- Not a word problem, missing data, or more than 3 unknowns: {"found": false}."""


def word_problem_candidate(text: str) -> bool:
    """A math request over at least two stated quantities and a relation word."""
    if not _MIN_CHARS <= len(text) <= _MAX_CHARS or "=" in text:
        return False
    request = _MATH_REQUEST.search(text)
    if request is None:
        request = _WORK_OUT_REQUEST.search(text)
    if request is None:
        request = _HOW_MUCH_INITIAL_REQUEST.search(text)
    if request is None:
        how_many = _HOW_MANY_REQUEST.search(text)
        if (
            how_many is not None
            and _HOW_MANY_ADVICE.search(text) is None
            and (
                _HOW_MANY_NAMED_TARGET.search(text, how_many.start()) is not None
                or _HOW_MANY_ELLIPSIS_TARGET.search(text, how_many.start()) is not None
            )
        ):
            request = how_many
    if request is None:
        pronoun = _PRONOUN_REQUEST.search(text)
        if pronoun is None or _PRONOUN_MATH_CONTEXT.search(text[: pronoun.start()]) is None:
            return False
    digits = len(_DIGITS.findall(text))
    scaled_rate = digits >= 3 and _STATED_RATE.search(text) is not None
    if not (_RELATION.search(text) or scaled_rate):
        return False
    words = sum(1 for word in _WORD.findall(text.lower()) if word in _NUMBER_WORDS)
    # At least one number in digits: "how many calories are in two eggs and
    # three slices" is a lookup, and a false positive here costs the turn a
    # model call and its web-search classifier.
    return digits >= 1 and digits + words >= 2


def _stated_numbers(text: str) -> set[Fraction]:
    lowered = text.lower()
    stated: set[Fraction] = set()
    for number in _DIGITS.findall(lowered):
        stated.add(Fraction(number.replace(",", "")))
    for word in _WORD.findall(lowered):
        for value in _NUMBER_WORDS.get(word, ()):
            stated.add(Fraction(value))
            if word in _FRACTION_WORDS:
                stated.add(Fraction(1, value))
    if "%" in lowered or "percent" in lowered:
        # "15%" may be written 15/100 or 0.15.
        stated |= {Fraction(100)} | {value / 100 for value in stated}
    return stated


def _unstated(piece: str, stated: set[Fraction]) -> list[str]:
    """The numbers in ``piece`` that the problem does not state."""

    def rate(match: re.Match[str]) -> str:
        try:
            value = Fraction(match.group(1).replace(" ", ""))
        except (ValueError, ZeroDivisionError):
            return match.group(0)
        return f" {match.group(1)} " if 0 < value < 1 and value in stated else match.group(0)

    def fraction(match: re.Match[str]) -> str:
        numerator, denominator = int(match.group(1)), int(match.group(2))
        if denominator and Fraction(numerator, denominator) in stated:
            return " "
        return match.group(0)

    piece = _FRACTION.sub(fraction, _ONE_AND_RATE.sub(rate, piece))
    numbers = _DIGITS.findall(piece)
    return [number for number in numbers if Fraction(number.replace(",", "")) not in stated]


def grounded(setup: WordProblemSetup, text: str) -> bool:
    """Every number in the translation is one the problem states.

    A 1 counts only when the problem implies it: stated in digits or words
    ("one", "consecutive"), as a stated fraction ("1/2" for half), or in a
    stated rate ("(1 - 0.2)" for 20% off). "A number plus 7 is 19" cannot
    become ``n + 1 = 19``.
    """
    stated = _stated_numbers(text)
    written = [item.equation for item in setup.equations] + [t.expr for t in setup.targets]
    return not any(_unstated(piece, stated) for piece in written)


async def word_problem_intent(text: str, settings: Settings) -> MathIntent | None:
    """Translate on independent bounded routes, then accept only verified input.

    A classic shape one closed template reads whole (``word_templates``) needs
    no model call; its setup is checked the same way.
    """
    if not settings.math_word_problems_enabled or _ENDLESS.search(text):
        return None
    from app.modules.math.tools.word_templates import word_template_setup

    template = word_template_setup(text)
    if template is not None:
        intent = MathIntent(kind="word_problem", word_problem=template, operation="solve")
        if request_consumption_complete(text, intent):
            return intent
    if not word_problem_candidate(text):
        return None
    # Here, not at module top: the maths gate reads ``word_problem_candidate`` in the SymPy
    # pool's workers, which must not load the model client.
    from app.gateways import litellm_gateway
    from app.models import model_catalog

    aliases = [ROUTING.word_problems]
    fallback = model_catalog.structured_fallback_alias()
    if fallback and fallback not in aliases:
        aliases.append(fallback)
    for alias in aliases:
        try:
            setup = await litellm_gateway.complete_structured(
                settings=settings,
                model_alias=alias,
                messages=[
                    {"role": "system", "content": _PROMPT},
                    {"role": "user", "content": text.strip()},
                ],
                schema=WordProblemSetup,
                max_tokens=500,
                timeout_seconds=settings.math_word_problem_timeout_seconds,
                allow_fallback=False,
            )
        except Exception:
            logger.warning("word problem extract failed on %s", alias, exc_info=True)
            continue
        if setup is not None and setup.found and grounded(setup, text):
            intent = MathIntent(kind="word_problem", word_problem=setup, operation="solve")
            if request_consumption_complete(text, intent):
                return intent
    return None
