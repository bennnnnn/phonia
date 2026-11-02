"""What a physics question asks for, read as physical dimensions.

An extractor that does not recognise how a question is asked falls back to its
default operation: "a ball is dropped from 80 m, what is its speed just before
it hits the ground" was answered with a time, 4.04 s. Reading the asked
quantity independently lets the block refuse a result of another dimension.

Only a confident reading counts. A question whose ask cannot be read, or that
names an ambiguous quantity ("field strength", "components"), gets no guard.
"""

from __future__ import annotations

import re

from app.modules.physics.ask_words import _DIMENSIONLESS, _MONEY, _QUANTITIES, _UNKNOWN
from app.modules.physics.givens import ANGLE, unit_at, unit_dimension, unit_readings
from app.services.law_binding.ask import ASK_VERBS
from app.services.law_binding.ask import ask_clause as _verb_ask_clause

__all__ = [
    "ask_clause",
    "asked_dimensions",
    "asked_phrases",
    "asked_unit",
    "has_ask",
    "result_dimension",
    "result_reading",
]

QUANTITY = re.compile(
    r"\b(?:"
    + "|".join(re.escape(phrase) for phrase in sorted(_QUANTITIES, key=len, reverse=True))
    + r")(?![\w-])",
    re.IGNORECASE,
)
_ADJECTIVES = (
    r"maximum|max|minimum|min|total|final|initial|average|horizontal|vertical|"
    r"resultant|net|peak|new|common|equivalent|effective|kinetic|potential"
)
# A part label between two asked quantities: "find (a) its speed and (b) the distance".
_PART_LABEL = r"(?:\(?(?:[a-h]|i{1,3}|iv)\)\s*)?"
# What may sit between two asked quantities in one list: "the time of flight,
# the maximum height and the range".
_CONNECTOR = re.compile(
    r"\s*,?\s*(?:and\s+|as\s+well\s+as\s+)?"
    + _PART_LABEL
    + r"(?:also\s+)?(?:the\s+|its\s+|their\s+)?"
    rf"(?:(?:{_ADJECTIVES})\s+)*",
    re.IGNORECASE,
)
# A sentence, with a decimal point kept inside it: "I got 19.8 m/s."
SENTENCE = re.compile(r"(?:[^.?!]|(?<=\d)\.(?=\d))+[.?!]*")
# A question asked by its quantity alone: "max speed?", "acceleration?",
# "time to hit the ground?". The fragment after the last stop, before the "?".
# A decimal point stays inside the question: "frequency of a 1.2 m long pendulum?".
_BARE_QUESTION = re.compile(
    r"(?:^|(?<!\d)[.,;:!?]\s*|[.,;:!?](?!\d)\s*|\n)\s*(?P<ask>(?:(?:the|its|their|what)\s+)?"
    rf"(?:(?:{_ADJECTIVES})\s+)*[a-z](?:[^.,;:!?\n]|(?<=\d)\.(?=\d)){{0,60}})\?\s*$",
    re.IGNORECASE,
)


def _bare_question(text: str) -> str | None:
    match = _BARE_QUESTION.search(text)
    if match is None:
        return None
    ask = match.group("ask")
    words = re.sub(rf"^(?:(?:the|its|their)\s+)?(?:(?:{_ADJECTIVES})\s+)*", "", ask, flags=re.I)
    if len(ask.split()) > 8 or QUANTITY.match(words) is None:
        return None
    return ask


def ask_clause(text: str) -> str | None:
    """The last question's asked part; a bare quantity with a "?" asks too.

    "A 0.5 kg mass on a spring oscillates with amplitude 5 cm. max speed?" names
    no question verb, and read as asking nothing it was answered with the period.
    """
    clause = _verb_ask_clause(text)
    if clause is not None:
        return clause
    where = _WHERE_IMAGE.search(text)
    if where is not None:
        end = re.search(r"[?!]|\.(?:\s|$)", text[where.start() :])
        return text[where.start() : where.start() + end.start() if end else len(text)]
    return _bare_question(text)


# "Where is the image?" names no question verb the shared reader knows.
_WHERE_IMAGE = re.compile(r"\bwhere\s+(?:is|will|does|would)\s+(?:the\s+)?image\b", re.IGNORECASE)


# Instructions that ask without a question word: "Solve for v.", "Use Gauss's law
# for ...", "Faraday's law for 100 turns ...", "resolve a 10 N force".
_IMPERATIVE = re.compile(
    r"(?:^\s*|[.?!;:]\s+|\n[^\S\n]*)(?:please\s+|now\s+)?"
    r"(?:solve|resolve|use|apply|convert|give|state|express|show|list|tell|derive|obtain|"
    r"predict|plot|graph|draw|get|balance|i\s+need|i\s+want)\b",
    re.IGNORECASE,
)
# "Use Gauss's law for ...", "Kirchhoff's junction rule: currents of 2 A and 3 A ...".
_NAMED_LAW = re.compile(
    r"\b(?:law|rule|equation|principle|formula|relation|theorem|effect)"
    r"(?:\s+(?:for|to|on|with)\b|\s*:)",
    re.IGNORECASE,
)
# Question words that ASK_VERBS does not list: "where is the image", "how does it move".
_INTERROGATIVE = re.compile(r"\b(?:where|which|whether|how)\b", re.IGNORECASE)
# A sentence that is its quantity: "momentum of a 2 kg object at 3 m/s", "power
# dissipated by a 4 ohm resistor". A quantity followed by a verb is a statement.
_SENTENCE_START = re.compile(r"(?:^|[.?!;]\s+|\n)\s*", re.IGNORECASE)
_STATEMENT_VERB = re.compile(r"^\s+(?:is|are|was|were|has|have|had|equals|=)\b", re.IGNORECASE)


_WORD = re.compile(r"^[a-z'-]+\s+", re.IGNORECASE)
_VERB_WORD = re.compile(r"(?:is|are|was|were|has|have|had|does|do|did)\s+", re.IGNORECASE)


def _names_its_quantity(text: str) -> bool:
    for start in _SENTENCE_START.finditer(text):
        rest = text[start.end() : start.end() + 120]
        words = re.sub(
            rf"^(?:(?:the|its|their|a|an)\s+)?(?:(?:{_ADJECTIVES})\s+)*", "", rest, flags=re.I
        )
        at = 0
        # The quantity itself, or up to two words naming its kind first
        # ("centripetal force on a 2 kg mass"); a verb before it is a statement.
        for _ in range(3):
            noun = QUANTITY.match(words, at)
            if noun is not None:
                if not _STATEMENT_VERB.match(words[noun.end() :]):
                    return True
                break
            word = _WORD.match(words[at:])
            if word is None or _VERB_WORD.fullmatch(word.group()):
                break
            at += word.end()
    return False


def has_ask(text: str) -> bool:
    """Whether the text asks anything at all.

    "A ball is dropped from 80 m." states a situation and asks nothing; answering
    it with a fall time picks a question for the student.
    """
    return bool(
        "?" in text
        or ASK_VERBS.search(text)
        or _IMPERATIVE.search(text)
        or _NAMED_LAW.search(text)
        or _INTERROGATIVE.search(text)
        or _names_its_quantity(text)
    )


# "a planet of mass 6e24 kg": a quantity followed by its own value is a given.
# "the energy equivalent of 2 kg" is still the ask: kg is not an energy.
_VALUE_AFTER = re.compile(
    r"\s*(?P<link>of\s+|=\s*|is\s+|:\s*)?(?P<number>[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?)",
    re.IGNORECASE,
)
# The asked quantity follows its verb closely: "find the speed", "what is the
# magnitude of the resultant force". Further on, a noun is part of a given.
_ASK_REACH = 60
# "lens" misses "lenses": the boundary after the singular is the next letter.
_LENS = re.compile(r"\blens(?:es)?\b|\bdiopt", re.IGNORECASE)


# "How long must the runway be?" and "how long is the rope?" ask for a length.
# The article keeps "how long will it be before it lands" a time.
_LENGTH_NOUNS = (
    r"runway|track|road|rope|string|wire|ramp|pendulum|rod|bridge|cable|tube|pipe|slide"
    r"|ladder|plank|board|strip|beam|bar|lane|path|wall|side|edge"
)
_HOW_LONG_IS_LENGTH = re.compile(
    r"\bhow long\s+(?:"
    r"(?:must|should|would|will|does|do|has\s+to|have\s+to|needs?\s+to)\s+"
    r"(?:the|a|an|its|this|that|each)\s+(?:[\w-]+\s+){0,2}?be\b"
    r"|(?:is|was|are|were|must|should)\s+(?:the|a|an|its|this|that|each)\s+"
    rf"(?:[\w-]+\s+){{0,2}}?(?:{_LENGTH_NOUNS})s?\b)",
    re.IGNORECASE,
)


def _labels_a_value(clause: str, noun: re.Match[str], text: str) -> bool:
    value = _VALUE_AFTER.match(clause, noun.end())
    if value is None:
        return False
    link = (value.group("link") or "").strip()
    unit = unit_at(clause, value.end("number"))
    if unit is None:
        # "strain of 0.001" is a label; "the energy of 2" is too vague to call.
        return link != "of" or _dimension(noun.group(), text) == _DIMENSIONLESS
    if link == "=":
        return True
    reading = unit_dimension(unit[1])
    return reading is not None and reading[0] == _dimension(noun.group(), text)


def _dimension(phrase: str, text: str) -> str | None:
    expression = _QUANTITIES[phrase.lower()]
    if expression == "watt" and _LENS.search(text):
        return None
    if expression in {ANGLE, _DIMENSIONLESS, _MONEY}:
        return expression
    if expression == _UNKNOWN:
        return None
    reading = unit_dimension(expression)
    return None if reading is None else reading[0]


def asked_phrases(text: str) -> tuple[str, ...]:
    """The quantities the last question asks for, lowercased, in order.

    "Find the time of flight, the maximum height and the range" asks for three.
    Empty when no asked quantity follows the question's verb closely.
    """
    clause = ask_clause(text)
    if clause is None:
        return ()
    nouns = [noun for noun in QUANTITY.finditer(clause) if not _labels_a_value(clause, noun, text)]
    if not nouns or nouns[0].start() > _ASK_REACH:
        return ()
    phrases: list[str] = []
    previous_end = nouns[0].start()
    for noun in nouns:
        if phrases and not _CONNECTOR.fullmatch(clause, previous_end, noun.start()):
            break
        phrase = re.sub(r"\s+", " ", noun.group().lower())
        if phrase == "how long" and _HOW_LONG_IS_LENGTH.search(clause):
            phrase = "length"
        phrases.append(phrase)
        previous_end = noun.end()
    return tuple(phrases)


def asked_dimensions(text: str) -> tuple[str, ...]:
    """Dimensions of the asked quantities; empty unless every one is certain."""
    dimensions = [_dimension(phrase, text) for phrase in asked_phrases(text)]
    if None in dimensions:
        return ()
    return tuple(dict.fromkeys(dimension for dimension in dimensions if dimension is not None))


def result_reading(unit: str) -> tuple[str, float, float] | None:
    """(dimension, scale, offset) of a solver's result unit; None when unreadable."""
    spelled = unit.strip()
    if not spelled or spelled == "%" or spelled.lower() in {"db", "decibel", "decibels"}:
        return _DIMENSIONLESS, 1.0, 0.0
    for reading in unit_readings(spelled):
        expression = reading.replace("·", "*").replace("^", "**")
        if expression in {"deg", "°"}:
            expression = "degree"
        if expression in {"D", "dioptre", "diopter", "dioptres", "diopters"}:
            expression = "1 / meter"
        if expression in {"Bq", "becquerel"}:
            # Pint counts decays; an activity is a rate, per second.
            expression = "1 / second"
        found = unit_dimension("radian" if expression == "rad" else expression)
        if found is not None:
            return found
    return None


def result_dimension(unit: str) -> str | None:
    """Dimension of a solver's result unit; None when it cannot be read."""
    reading = result_reading(unit)
    return None if reading is None else reading[0]


# "How much energy does it use in kWh?", "what is its speed in km/h".
_IN_UNIT = re.compile(r"\b(?:in|into)\s+(?:units?\s+of\s+)?", re.IGNORECASE)
# The unit ends its phrase: the clause ends, or a phrase about where or when
# follows it ("the gauge pressure in psi at a depth of 10 m").
_CLAUSE_END = re.compile(
    r"^\s*(?:[?.!,;)]|$)"
    r"|^\s+(?:at|for|when|after|before|during|on|from|below|above|under|inside|of|if)\b",
    re.IGNORECASE,
)


# "How many kWh does a 60 W bulb use": the unit counted is the one asked in.
_HOW_MANY = re.compile(r"\bhow\s+many\s+", re.IGNORECASE)


def asked_unit(text: str) -> str | None:
    """The unit the question wants its answer in, as written; None when unsaid."""
    found: str | None = None
    for match in _HOW_MANY.finditer(text):
        unit = unit_at(text, match.end())
        reading = None if unit is None else unit_dimension(unit[1])
        # A count of things ("how many turns") asks for a number, not a unit,
        # and "how many moles" or "how many joules" is the SI answer already.
        if (
            unit is not None
            and reading is not None
            and reading[0] != _DIMENSIONLESS
            and not (reading[1] == 1.0 and reading[2] == 0.0)
        ):
            found = unit[0]
    for match in _IN_UNIT.finditer(text):
        unit = unit_at(text, match.end())
        if unit is None:
            continue
        end = match.end() + len(unit[0]) + (1 if text[match.end() : match.end() + 1] == " " else 0)
        if _CLAUSE_END.match(text[end:]):
            found = unit[0]
    return found
