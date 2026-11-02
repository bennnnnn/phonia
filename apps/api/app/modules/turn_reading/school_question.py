"""Whether a message is a school exercise, and whether it needs a reasoned choice."""

from __future__ import annotations

import re

from app.modules.turn_reading.question_kinds import (
    anyones,
    is_science_question,
    mentions_science,
    names_or_news,
)
from app.services.question_parts import labelled_parts

# "a) …", "(b) …", "C. …", "[D] …", "(iii) …": an option's label, after a space or the start.
_OPTION = re.compile(r"(?:^|(?<=[\s\[(]))\(?([a-dA-D]|i{1,3}|iv)[).\]]\s+", re.MULTILINE)


_LETTERS = ("abcd", ("i", "ii", "iii", "iv"))


_JOINED_LABELS = re.compile(r"(?:,|\band)\s*\(?(?:b|ii)\)\s", re.IGNORECASE)


_CHOOSE = re.compile(
    r"\b(?:which\s+(?:one\s+)?of\s+the\s+following|choose|select|pick\s+out|tick|correct\s+"
    r"(?:option|answer|statement|explanation|sequence|order|pair))\b",
    re.IGNORECASE,
)


# A request for every item, not a choice of one: "Plan a trip covering a) Rome b) …",
# "opening hours of a) the Louvre b) …", "Compare the specs of a) …".
_ALL_ITEMS = re.compile(
    r"^\s*(?:plan|write|compare|make|create|draft|list|give|generate|suggest|rank|rate|sort"
    r"|summari[sz]e|help|pick|choose|recommend|name)\b(?!\s+the\s+correct)"
    r"|\b(?:of|for|between|covering|about|these|each|both|all)\s*:?\s*$",
    re.IGNORECASE,
)


_CODE = re.compile(r"\(\s*AS\s*\d\s*\)|\[[ \t]+\]\s*(?:$|\(?[aA][).])", re.MULTILINE)


# An exercise's own order, opening the message or a sentence of it. "Define success." and
# "Explain decorators" are anyone's, so define, describe, explain and list are not here:
# the factual note has them.
_OPENING = re.compile(
    r"(?:^|[.?!:]\s+)(?:\d{1,2}[.)]\s*)?(?:distinguish\s+between|differentiate\s+between"
    r"|give\s+(?:two|three|four|five|any\s+two|any\s+three)\s+examples?\s+each"
    r"|write\s+the\s+differences?\s+between|identify|justify|indicate|illustrate"
    r"|arrange\s+the|classify\s+the\s+following|match\s+the\s+following"
    r"|fill\s+in\s+the\s+blanks?|choose\s+the\s+correct|tick|state\s+whether"
    r"|calculate|determine|estimate|predict|give\s+reasons?\s+(?:why|for\s+the)"
    r"|complete\s+the\s+(?:table|following)|verify\s+(?:whether|that|the)"
    r"|write\s+(?:down\s+)?the\s+(?:formulae?|chemical|balanced|electronic|symbols?|correct)"
    # "Write one equation each for…", "Write a balanced equation for…".
    r"|write\s+(?:down\s+)?(?:an?|one|two|three)\s+(?:\w+\s+){0,2}(?:equations?|formulae?)"
    r"|write\s+a\s+short\s+note\s+on|give\s+an\s+account\s+of|mention\s+(?:two|three|any|the)"
    r"|what\s+is\s+meant\s+by|(?:change|correct|rewrite|punctuate)\s+the\s+following"
    r"|use\s+the\s+following\s+words|name\s+the\s+following|give\s+reasons?(?=\s*:)|outline\s+the"
    r"|account\s+for|balance\s+the|convert)\b",
    re.IGNORECASE,
)


ASSERTION = re.compile(r"\bassertion\b.*\breason\b", re.IGNORECASE | re.DOTALL)


# A run that may mark a word to fill in: "is called ________.", "The ........ is".
_RUN = re.compile(r"_{3,}|…{2,}|\.{6,}")
# Dots glued to the word before them trail it ("so......", "Trip ideas.........."): a
# pause, not a gap.
_TRAILING_DOTS = re.compile(r"(?<=[^\W_])(?:…{2,}|\.{6,})")
_FILL_ORDER = re.compile(
    r"\b(?:fill\s+in|complete\s+the\s+(?:sentences?|statements?|following))\b", re.IGNORECASE
)
_SENTENCE_END = re.compile(r"[.?!](?=\s|$)|\n")
_WORD = re.compile(r"[^\W_]+")
# A sentence to complete has words of its own around its gap: "lol ok ___ whatever" has
# three (2026-11-01: it, "so......" and "Trip ideas.......... Paris or Rome?" read as a
# textbook's blank, so their replies lost their emoji and the trip its search).
_BLANK_SENTENCE_WORDS = 4
# An operand of an equation or a label's value is a slot to fill however short its line:
# "5 + 3 = ___", "___ + 3 = 8", "Capital of France: ____".
_SLOT_BEFORE = re.compile(r"[=+\-\u2212\u00d7÷*/<>:]\s*$")
_SLOT_AFTER = re.compile(r"\s*[=+\-\u2212\u00d7÷*/<>]")


def _has_blank(text: str) -> bool:
    """A word to fill in: a run that stands apart from the words around it, in a sentence
    with words of its own, as an equation's operand or a label's value, or in a message
    that orders the blanks filled."""
    for run in _RUN.finditer(text):
        if _TRAILING_DOTS.match(text, run.start()):
            continue
        if (
            _FILL_ORDER.search(text)
            or _SLOT_BEFORE.search(text, 0, run.start())
            or _SLOT_AFTER.match(text, run.end())
        ):
            return True
        ends = [end.end() for end in _SENTENCE_END.finditer(text, 0, run.start())]
        after = _SENTENCE_END.search(text, run.end())
        sentence = text[ends[-1] if ends else 0 : after.start() if after else len(text)]
        if len(_WORD.findall(_RUN.sub(" ", sentence))) >= _BLANK_SENTENCE_WORDS:
            return True
    return False


# Someone a textbook's scenario is about: "A student said", "Two students, Renu and
# Rohit", "A farmer wants", "Vibha claims to her friend that, “…”".
_SCENARIO = re.compile(
    r"\b(?i:a|an|the|two|three|some)\s+(?:\w+\s+)?(?:students?|girl|boy|teacher|farmer"
    r"|researchers?|scientists?|class(?:mates)?|classroom)\b"
    r"|\b[A-Z][a-z]+\s+and\s+[A-Z][a-z]+\s+(?:were|are|observed|noticed|had)\b"
    r"|\b[A-Z][a-z]+\s+(?:claims?|argues|counter\s+argues|says|said)\b[^\"\u201c\n]{0,40}[\"\u201c]",
)


# An exercise's verb: what a book asks a student to do.
_ORDER = re.compile(
    r"\b(?:explain|justify|predict|suggest|identify|discuss|calculate|find|determine"
    r"|estimate|verify|obtain|express|state|give\s+reasons?|provide|what\s+do\s+you\s+think)\b",
    re.IGNORECASE,
)


# A quantity a word problem gives: "24 m/s", "50 g", "6 s", "5 minutes", "70%".
_QUANTITY = re.compile(
    r"\d(?:[\d,]*\d)?(?:\.\d+)?\s*(?:%|°\s*[CF]\b|(?:km|cm|mm|m|kg|g|mg|s|min|minutes?|h|hours?"
    r"|seconds?|N|J|kJ|W|kW|Hz|kHz|K|Pa|L|mL|u|mol|V|A|Ω)"
    r"(?:\s*(?:/|per)\s*(?:s²|s\^?2|s|h|m³|m\^?3|L|mol))?\b)"
)


_COMPUTE = re.compile(r"\b(?:calculate|compute|find|determine|work\s+out)\b", re.IGNORECASE)


_CLOSING = re.compile(
    r"[.?!]\s*(?:explain(?:\s+why)?|justify|discuss|(?:give|specify)\s+reasons?)"
    r"(?P<yours>\s+(?:for\s+)?your\s+answer)?\s*[.?!]?\s*$",
    re.IGNORECASE,
)


_TEXTBOOK = re.compile(
    r"\bwith\s+suitable\s+examples?\b|\bin\s+(?:our|your)\s+daily\s+life\b"
    # The statement in quotes, then an exercise's order: "… “friction is good and evil”.
    # Explain with examples."; "Do you agree with the statement “remote work kills …”?" is
    # an opinion asked.
    r"|\bdo\s+you\s+(?:agree|support)\b.*\bstatement\s*[.:]?\s*[\"\u201c'\u2018].*"
    r"\b(?:explain|justify|give\s+reasons?|with\s+examples?)\b",
    re.IGNORECASE | re.DOTALL,
)


def _options(text: str) -> tuple[str, list[str], bool] | None:
    """The stem, the option texts, and whether each option opens its own line, when
    ``text`` has options labelled in order: a), b), c) or (i), (ii), (iii)."""
    found = list(_OPTION.finditer(text))
    labels = [match.group(1).lower() for match in found]
    for sequence in _LETTERS:
        for start in range(len(labels) - 2):
            if tuple(labels[start : start + 3]) != tuple(sequence[:3]):
                continue
            chosen = found[start:]
            ends = [match.start() for match in chosen[1:]] + [len(text)]
            texts = [text[match.end() : end] for match, end in zip(chosen, ends, strict=False)]
            lines = all(text[: match.start()].rstrip(" \t").endswith("\n") for match in chosen[:3])
            return text[: chosen[0].start()], texts, lines
    return None


def option_choice(text: str) -> bool:
    """Options to choose one of, about nothing that changes or is a matter of taste."""
    read = _options(text)
    if read is None:
        return False
    stem, texts, own_lines = read
    # "what is its (i) distance, (ii) displacement and (iii) speed?" lists asks, and an
    # option that is itself a question, or a blank to fill, is a part.
    if _JOINED_LABELS.search(text) or _has_blank(text) or any("?" in o for o in texts[:-1]):
        return False
    asked = (
        all(len(option.split()) <= 8 for option in texts)
        or _CHOOSE.search(stem) is not None
        or (own_lines and stem.rstrip().endswith(("?", ":", ".")))
    )
    return (
        asked and len(stem.split()) >= 3 and _ALL_ITEMS.search(stem) is None and not anyones(text)
    )


def _closes_as_exercise(text: str) -> bool:
    """An exercise's closing order ("… Explain."). "Explain your answer." closes anyone's
    opinion too ("Was Napoleon a good leader? Explain your answer."): only about science."""
    closing = _CLOSING.search(text)
    if closing is None or len(text.split()) < 8:
        return False
    return closing.group("yours") is None or mentions_science(text)


def is_school_exercise(query: str) -> bool:
    text = query.strip()
    if option_choice(text):
        return True
    if anyones(text):
        return False
    if _CODE.search(text) or _closes_as_exercise(text):
        return True
    if _TEXTBOOK.search(text) or ASSERTION.search(text) or _has_blank(text):
        return True
    if _OPENING.search(text):
        return True
    if _ORDER.search(text) is None and "?" not in text:
        return False
    quantities = len(_QUANTITY.findall(text))
    return bool(
        (labelled_parts(text) and (_ORDER.search(text) or quantities or mentions_science(text)))
        or _SCENARIO.search(text)
        or quantities >= 2
        or (quantities == 1 and _COMPUTE.search(text))
    )


# A verdict to reason out: "Who is correct?", "Which element is more reactive?", "State
# whether the claim is correct". Answered first and reasoned after, it opened "Rohan is
# correct" over a body that showed Rajiv was, and "A is more reactive" over the trend that
# made B so (2026-10-30).
_VERDICT = re.compile(
    r"\bwho\s+is\s+(?:correct|right)\b"
    r"|\bwhich\s+(?:\w+\s+){0,3}(?:is|are|will\s+be|would\s+be|has)\s+(?:more|less|most|least"
    r"|greater|smaller|larger|higher|lower|correct|incorrect|true|false)\b"
    r"|\b(?:correct|true|valid)\s+or\s+(?:not|false|incorrect)\b|\bstate\s+whether\b"
    r"|\bcritically\s+examine\b|\bwhat\s+do\s+you\s+think\s+about\s+this\s+statement\b"
    # A class to read from clues: "Which type of pollination happens in these flowers?"
    r"|\bwhich\s+(?:type|kind|group|category|class|kingdom|phylum)\s*(?:\(s\)|s)?\s+of\b",
    re.IGNORECASE,
)


def needs_reasoned_choice(query: str) -> bool:
    """An exercise's choice to reason out first: its options, its assertion and reason,
    or a verdict on a textbook scenario ("Two students… Who is correct?"). An everyday
    "which is more reliable" stays on its own lane."""
    text = query.strip()
    if not is_school_exercise(text):
        return False
    verdict = _SCENARIO.search(text) is not None and _VERDICT.search(text) is not None
    return bool(option_choice(text) or ASSERTION.search(text) or verdict)


def has_nothing_to_look_up(query: str) -> bool:
    """An exercise in a textbook's own form (options, an assertion and its reason, a blank,
    an assessment code), or a plain science question: a search only finds worse answers
    ("…is called its a) Ignition temperature b) …" was answered from a YouTube comment)."""
    text = query.strip()
    if is_science_question(text):
        return True
    if anyones(text):
        return False
    # A science exercise written as an order: "Differentiate between RER and SER", "Explain
    # osmosis with an example".
    if is_school_exercise(text) and mentions_science(text) and not names_or_news(text):
        return True
    return in_textbook_form(text)


def in_textbook_form(query: str) -> bool:
    """An exercise only a textbook prints this way: options to choose from, an assertion and
    its reason, a blank to fill, an assessment code; never anyone's own matter."""
    text = query.strip()
    if anyones(text):
        return False
    return bool(
        option_choice(text) or ASSERTION.search(text) or _has_blank(text) or _CODE.search(text)
    )
