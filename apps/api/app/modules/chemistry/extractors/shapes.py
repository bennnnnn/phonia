"""A molecule's shape asked in a student's words, read by a closed grammar.

Live failure (2026-10-25): "Why is water bent tho, co2 isnt" got no verified answer. The VSEPR
reader read only "shape of <FORMULA>", so water, lowercase "co2" and "why is … bent" were not
read, and the model answered alone. A shape question in words is now read when the whole line
is one of these phrases, its molecules named as ``species_words`` reads them (water, ammonia,
co2, CH4):

- a question: "what is the shape of X", "what shape is X", "why is X bent", "how come X is
  linear", "is X polar (or nonpolar)", "bond angle in X";
- a bare noun phrase ("shape of X", "the geometry of X", "polarity of X", "X shape") only with
  X written as a formula or followed by "molecule", or the noun made chemistry's ("molecular
  geometry of X"). Review (2026-10-25): "The Shape of Water", the 2017 film, got an instant
  H2O card; a word-named substance in a bare phrase, or a noun in title case, is not read;
- two molecules: "why is X bent tho, Y isnt", "why is X bent but Y linear", "compare the
  shapes of X and Y", "what are the shapes of X and Y".

Every molecule must have one central-atom Lewis structure (``lewis_structure``): oxygen gas,
ethanol, a salt such as CaCl2 or iron is not read, and a charge written apart ("SO3 2-") is no
phrase here. Anything else declines ("what shape is the earth", "the pipe is bent", "is co2
bad", "co2 levels are rising"), and the model answers.
"""

from __future__ import annotations

import re

from app.modules.chemistry.lewis import lewis_structure
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.species_words import (
    Mention,
    lowercase_formula,
    substance_mentions,
    with_formulas,
)

# A shape question is short; a longer line is something else that mentions a molecule.
_MAX_LINE = 200
_LEAD = (
    r"(?:(?:ok(?:ay)?|so|and|but|also|wait|hey|hmm+|um+|q|question|chem(?:istry)?(?:\s+hw)?)"
    r"[\s,.:!?]+)*"
)
_TAIL = r"(?:[\s,]+(?:tho|though|pls|please|lol|then|exactly|again|anyway|btw))*\s*[?.!]*"
_ARTICLE = r"(?:(?:a|an|the)\s+)?"
_ADJECTIVE = (
    r"(?:bent|linear|polar|non-?\s?polar|tetrahedral|trigonal\s+(?:planar|pyramidal)|"
    r"pyramidal|v-?\s?shaped|planar|angular)"
)
_NOUN = r"(?P<noun>(?:shape|geometry))"
# A noun only chemistry uses: the bare phrase is chemistry's whatever names the molecule.
_CHEMISTRY_NOUN = r"(?:(?:molecular|electron(?:ic)?|vsepr)\s+(?:shape|geometry)|bond\s+angles?)"
_QUESTION = r"(?:what(?:'s|s|\s+is|\s+are)|whats)\s+(?:the\s+)?"
_WHY = r"(?:why|how\s+come)"
# "tho," "but" or a comma between the two molecules of a comparison.
_BETWEEN = r"(?:[\s,]+(?:but|tho|though|while|whereas|and|yet|when))*[\s,]+"
_NOT = r"(?:is\s*n[o'\u2019]?t|isnt|isn't|aint|ain't|is\s+not|not)"
_MOLECULE_WORD = r"\s+molecules?"


def _molecule(name: str, substance: str) -> str:
    return rf"{_ARTICLE}(?P<{name}>{substance})(?:{_MOLECULE_WORD})?"


def _bare(name: str, written: str, substance: str) -> str:
    """A molecule in a bare noun phrase: written as a formula, or followed by "molecule"."""
    return (
        rf"{_ARTICLE}(?:(?P<{name}>{written})(?:{_MOLECULE_WORD})?"
        rf"|(?P<{name}_named>{substance}){_MOLECULE_WORD})"
    )


def _phrases(substance: str, written: str) -> tuple[str, ...]:
    one, two = _molecule("one", substance), _molecule("two", substance)
    bare_one, bare_two = _bare("one", written, substance), _bare("two", written, substance)
    shapes = r"(?P<noun>(?:shapes?|geometr(?:y|ies)))"
    return (
        rf"{_QUESTION}(?:{_CHEMISTRY_NOUN}|{_NOUN}|polarity)\s+(?:of|for|in)\s+{one}",
        rf"(?:the\s+)?{_CHEMISTRY_NOUN}\s+(?:of|for|in)\s+{one}",
        rf"(?:the\s+)?(?:{_NOUN}|(?P<noun2>polarity))\s+(?:of|for)\s+{bare_one}",
        rf"what\s+(?:shape|geometry)\s+(?:is|does)\s+{one}(?:\s+have)?",
        rf"{_WHY}\s+(?:is|are)\s+{one}\s+{_ADJECTIVE}",
        rf"{_WHY}\s+{one}\s+is\s+{_ADJECTIVE}",
        rf"is\s+{one}\s+{_ADJECTIVE}(?:\s+or\s+{_ADJECTIVE})?",
        rf"(?P<one>{written})\s+(?:shape|geometry|bond\s+angle|polarity)",
        rf"{_WHY}\s+(?:is|are)\s+{one}\s+{_ADJECTIVE}{_BETWEEN}{two}"
        rf"(?:\s+(?:{_NOT}|is\s+{_ADJECTIVE}|{_ADJECTIVE}))?",
        rf"compare\s+(?:the\s+)?(?:shapes?|geometr(?:y|ies)|bond\s+angles?)\s+(?:of\s+)?{one}"
        rf"\s+(?:and|&|with|to|vs\.?|versus)\s+{two}",
        rf"{_QUESTION}{shapes}\s+of\s+{one}\s+(?:and|&|vs\.?|versus)\s+{two}",
        rf"(?:the\s+)?{shapes}\s+of\s+{bare_one}\s+(?:and|&|vs\.?|versus)\s+{bare_two}",
    )


def _alternative(formulas: set[str]) -> str:
    ordered = sorted(formulas, key=len, reverse=True)
    return "(?-i:" + "|".join(re.escape(formula) for formula in ordered) + ")(?![A-Za-z0-9])"


def _written_as_formula(text: str, mention: Mention) -> bool:
    """ "h2o" or "H2O" names the formula itself; "water" names it in a word."""
    span = text[mention.start : mention.end]
    return span == mention.formula or lowercase_formula(span) == mention.formula


def _title_cased(found: re.Match[str], start: int) -> bool:
    """ "The Shape of Water": a capital noun after the line's first word is a title."""
    for group in ("noun", "noun2"):
        at = found.start(group) if group in found.groupdict() else -1
        if at > start and found.group(group)[:1].isupper():
            return True
    return False


def shape_question(text: str) -> tuple[str, ...] | None:
    """The molecules (one or two, as formulas) whose shape the whole line asks; else None."""
    if len(text) > _MAX_LINE:
        return None
    mentions = substance_mentions(text)
    if not mentions:
        return None
    named = {mention.formula for mention in mentions}
    written = {mention.formula for mention in mentions if _written_as_formula(text, mention)}
    line = with_formulas(text, mentions).strip()
    substance = _alternative(named)
    formula = _alternative(written) if written else r"(?!)"
    for phrase in _phrases(substance, formula):
        found = re.fullmatch(rf"(?P<lead>{_LEAD}){phrase}{_TAIL}", line, re.IGNORECASE)
        if found is None:
            continue
        if _title_cased(found, found.end("lead")):
            return None
        asked = tuple(
            dict.fromkeys(
                value
                for key, value in found.groupdict().items()
                if value is not None and key.startswith(("one", "two"))
            )
        )
        # The line names nothing else, and every molecule has one central atom to read.
        if set(asked) != named:
            return None
        return asked if all(lewis_structure(formula) for formula in asked) else None
    return None


def extract_shape(text: str) -> ChemistryIntent | None:
    """A shape question in words: one molecule's VSEPR, or two compared ("H2O, CO2")."""
    asked = shape_question(text)
    if asked is None:
        return None
    return ChemistryIntent(kind="structure", chemistry_op="vsepr", formula=", ".join(asked))
