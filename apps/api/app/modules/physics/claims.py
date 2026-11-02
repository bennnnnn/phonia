"""A result the student states as theirs: a value to check, never a given.

"A 2 kg ball is dropped from 20 m. I got 19.8 m/s for its impact speed. Am I
right?" was solved with v₀ = 19.8 m/s and answered 28 m/s; the student was
right. A claimed value is taken out of the question before anything reads its
givens, and when the claim was the only ask, it becomes one: the quantity it
names, or the kind of its unit ("I got 3 A" asks for a current).

Two shapes are claims:

- a statement of one's own result: "I got", "I calculated", "my answer is",
  "my friend says";
- a yes/no question about a value: "Does it hit the ground at 19.8 m/s?",
  "Is its final speed more than 10 m/s?".

The direct reply says whether a stated result matches the verified one
(``claim_verdict``). A yes/no question is left to the model, with the check.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.modules.physics.ask import QUANTITY, SENTENCE, has_ask
from app.modules.physics.givens import scan_givens, unit_dimension, unit_expression
from app.services.law_binding.units import dimension_of
from app.services.student_claim import CHECK_ONLY as CHECK_ONLY
from app.services.student_claim import OWN as _OWN
from app.services.student_claim import QUESTION_WORD as _QUESTION_WORD
from app.services.student_claim import STATED as _STATED
from app.services.student_claim import TRAILING_CHECK as _TRAILING_CHECK

# The claimed value follows its lead-in closely: "I got a range of 35.3 m".
_CLAIM_REACH = 48
# A yes/no question about a value, at the start of its sentence.
_YES_NO = re.compile(
    r"^\s*(?:so\s+|and\s+|then\s+)?(?:does|did|will|would|is|was|can|could)\s+"
    r"(?:it|he|she|they|this|that|(?:the|its|his|her|their)\s+[a-z]+(?:\s+[a-z]+)?)\b",
    re.IGNORECASE,
)
# "more than 10 m/s", "before 3 s": a threshold, not a value to match.
_THRESHOLD = re.compile(
    r"\b(?:more|less|greater|smaller|faster|slower|higher|lower|longer|shorter|further|"
    r"farther)\s+than\s*$|\b(?:over|under|above|below|before|after|within|at\s+least|"
    r"at\s+most|beyond|exceed\w*)\s*$",
    re.IGNORECASE,
)
# A yes/no question that asks how, not whether a value is right.
_NOT_A_CHECK = re.compile(
    r"\b(?:possible|able|enough|find|calculate|compute|determine|work\s+out|solve|explain|"
    r"show|use|need)\b",
    re.IGNORECASE,
)

# The quantity a claimed unit's kind is, when the claim names none.
_KIND_NOUNS = {
    "meter / second": "speed",
    "second": "time",
    "meter": "distance",
    "meter / second ** 2": "acceleration",
    "newton": "force",
    "joule": "energy",
    "watt": "power",
    "ampere": "current",
    "volt": "voltage",
    "ohm": "resistance",
    "pascal": "pressure",
    "hertz": "frequency",
    "kilogram": "mass",
    "coulomb": "charge",
    "kilogram * meter / second": "momentum",
}


_NOUN_BY_KIND = {
    kind: noun for expression, noun in _KIND_NOUNS.items() if (kind := dimension_of(expression))
}


@dataclass(frozen=True, slots=True)
class Claim:
    """One claimed value, where it sits, and what kind of claim it is."""

    value: float
    unit: str
    start: int
    end: int
    sentence_start: int
    sentence_end: int
    yes_no: bool
    threshold: bool
    # The student's own ("I got") rather than someone else's ("my friend says").
    own: bool = True

    @property
    def dimension(self) -> str | None:
        expression = unit_expression(self.unit)
        return None if expression is None else dimension_of(expression)


def _value_end(text: str, start: int, end: int, unit: str) -> int:
    """Where the claimed value's text ends: after its unit ("19.8 m/s")."""
    at = text.find(unit, end, end + 2 + len(unit))
    return end if not unit or at < 0 else at + len(unit)


def read_claims(text: str) -> list[Claim]:
    """Every value the text claims as a result, in order."""
    claims: list[Claim] = []
    givens = [given for given in scan_givens(text) if given.unit]
    for sentence in SENTENCE.finditer(text):
        body = sentence.group()
        start, end = sentence.span()
        yes_no = (
            _YES_NO.match(body) is not None
            and body.rstrip().endswith("?")
            and _NOT_A_CHECK.search(body) is None
        )
        stated = _STATED.search(body)
        if stated is not None and _QUESTION_WORD.search(body, 0, stated.start()):
            # "how far do I get in 30 minutes" asks; it states nothing.
            stated = None
        if not yes_no and stated is None:
            continue
        inside = [given for given in givens if start <= given.start < end]
        if stated is not None:
            reach = start + stated.end()
            inside = [given for given in inside if reach <= given.start <= reach + _CLAIM_REACH]
        else:
            # Only the question's own value: "Does it hit the ground at 19.8 m/s?"
            inside = inside[-1:]
        for given in inside:
            before = text[start : given.start]
            claims.append(
                Claim(
                    value=given.value,
                    unit=given.unit,
                    start=given.start,
                    end=_value_end(text, given.start, given.end, given.unit),
                    sentence_start=start,
                    sentence_end=end,
                    yes_no=stated is None,
                    threshold=_THRESHOLD.search(before) is not None,
                    own=stated is None or _OWN.match(stated.group()) is not None,
                )
            )
    return claims


# A word before the quantity that is part of its name: "impact speed", "total resistance".
_QUALIFIER = re.compile(r"(?:\b|\B(?<![a-z]))([a-z]+)\s+\Z", re.IGNORECASE)
_NOT_A_QUALIFIER = frozenset(
    {"a", "an", "the", "its", "his", "her", "their", "my", "our", "for", "of", "got", "get"}
)


def _named_quantity(sentence: str) -> str | None:
    """The quantity a claim names, written as the ask would: "impact speed"."""
    noun = QUANTITY.search(sentence)
    if noun is None:
        return None
    phrase = noun.group().lower()
    qualifier = _QUALIFIER.search(sentence, 0, noun.start())
    if qualifier is not None and qualifier.group(1).lower() not in _NOT_A_QUALIFIER:
        phrase = f"{qualifier.group(1).lower()} {phrase}"
    return phrase


def question_without_claims(text: str) -> str:
    """The question with each claimed value taken out, and the claim as its ask.

    A check sentence ("Am I right?") goes too. When nothing else asks, the
    claim's quantity is appended as the ask: "What is the impact speed?"
    """
    claims = read_claims(text)
    if not claims:
        return text
    pieces: list[str] = []
    cursor = 0
    for claim in claims:
        pieces.append(text[cursor : claim.start])
        cursor = claim.end
    pieces.append(text[cursor:])
    masked = "".join(pieces)
    sentences = [
        sentence.group()
        for sentence in SENTENCE.finditer(masked)
        if CHECK_ONLY.match(sentence.group()) is None
    ]
    kept = _TRAILING_CHECK.sub("", " ".join(part.strip() for part in sentences)).strip()
    claim_sentences = {(claim.sentence_start, claim.sentence_end) for claim in claims}
    others = [
        sentence.group()
        for sentence in SENTENCE.finditer(text)
        if (sentence.start(), sentence.end()) not in claim_sentences
        and CHECK_ONLY.match(sentence.group()) is None
    ]
    if has_ask(" ".join(others)):
        return kept
    first = claims[0]
    noun = _named_quantity(text[first.sentence_start : first.sentence_end])
    if noun is not None:
        # The claim names its quantity: that is the ask, and the claim sentence
        # has nothing else to say ("I got a range of 35.3 m").
        return f"{' '.join(part.strip() for part in others)} What is the {noun}?".strip()
    kind = first.dimension
    noun = None if kind is None else _NOUN_BY_KIND.get(kind)
    if noun is None:
        return kept
    # The claim sentence keeps its situation ("to hit the ground") without its value.
    return f"{kept} What is the {noun}?"


def _plain_value(value: float) -> str:
    return f"{value:g}"


def claim_verdict(text: str, value: float, unit: str) -> str | None:
    """One line saying whether the student's stated result is the verified one.

    Only for a stated result ("I got 19.8 m/s") whose kind is the answer's.
    None when there is no such claim, or it cannot be compared.
    """
    expression = unit_expression(unit)
    answer = None if expression is None else unit_dimension(expression)
    if answer is None:
        return None
    for claim in read_claims(text):
        if claim.yes_no or claim.threshold:
            continue
        claimed_expression = unit_expression(claim.unit)
        reading = None if claimed_expression is None else unit_dimension(claimed_expression)
        if reading is None or reading[0] != answer[0]:
            continue
        claimed_si = claim.value * reading[1] + reading[2]
        verified_si = value * answer[1] + answer[2]
        shown = f"{_plain_value(claim.value)} {claim.unit}"
        whose = "Your" if claim.own else "The"
        if _matches(claim.value, claimed_si, verified_si, reading[1]):
            return f"{whose} {shown} is right."
        return f"{whose} {shown} is not right; the verified answer is below."
    return None


def _matches(written: float, claimed_si: float, verified_si: float, scale: float) -> bool:
    """Equal to the precision the student wrote, or within 1%."""
    if math.isclose(claimed_si, verified_si, rel_tol=0.01, abs_tol=1e-12):
        return True
    decimals = _decimals(written)
    half_step = 0.5 * 10.0**-decimals * abs(scale)
    return abs(claimed_si - verified_si) <= half_step + 1e-12


def _decimals(value: float) -> int:
    text = f"{value:g}"
    if "e" in text:
        return 0
    return len(text.split(".", 1)[1]) if "." in text else 0
