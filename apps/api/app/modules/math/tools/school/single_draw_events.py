"""The event of one roll or one draw, read whole.

The event is the outcomes the question names, joined by "or", with a "not" before
them: "not getting a sum 5 or 9" is every roll of two dice but the 8 that make 5 or 9.
Every other word must be one that cannot change the event: the setup ("a pair of
fair dice is tossed", "when two dice are rolled"), the request ("what is the
probability"), the dice or the deck. A word the reader has no meaning for ("and a
double", "if the dice show the same number", "one more than 3", "neither") declines
the question, so a card never answers part of the event. So does a reading that is
not the only one: "a red king or queen" (is the queen red?), "greater than 4 or 5";
and an event no roll misses or none makes, which is the model's to explain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.math.response_intent import strip_ask_frame

# A multiple-choice list after the question: "a. 2/9  b. 8/9", "(A) 1/6 (B) 1/3". Each
# label is found on its own, so no lazy run between them is retried from every "a)".
_FIRST_CHOICE = re.compile(r"(?<!\S)\(?[aA][.)]\s*\S")
_SECOND_CHOICE = re.compile(r"(?<!\S)\(?[bB][.)]\s*\S")
_ABOVE = r"(?:greater|more|bigger|larger|higher)"
_BELOW = r"(?:less|fewer|smaller|lower)"
_COMPARE = (
    rf"(?:(?:{_ABOVE}|{_BELOW})\s+than\s+or\s+equal\s+to|(?:{_ABOVE}|{_BELOW})\s+than"
    r"|at\s+least|at\s+most|exactly)"
)
_NOT = (
    r"(?:(not)\s+(?:(?:getting|get|rolling|roll|throwing|throw|obtaining|obtain|drawing|draw"
    r"|picking|pick|selecting|select)\s+)?)?"
)
_SUM_VALUE = rf"(?:(?:a\s+)?(?:sum|total)\s+(?:of\s+)?)?(?:{_COMPARE}\s+)?\d{{1,2}}"
_SUM_EVENT = re.compile(
    rf"\b{_NOT}(?:(?:a|an|the|their)\s+)?(?:sum|total)"
    r"(?:\s+of\s+(?:the\s+)?(?:two\s+)?(?:numbers|faces|scores)"
    r"(?:\s+(?:on|shown\s+on)\s+(?:the\s+|both\s+)?(?:two\s+)?dice)?)?"
    r"(?:\s+(?:is|will\s+be|equals|of|is\s+equal\s+to|equal\s+to))?(?:\s+(not))?"
    rf"\s+({_SUM_VALUE}(?:\s*,\s*{_SUM_VALUE})*(?:\s*,?\s+or\s+{_SUM_VALUE})?)(?!\d|\.\d)",
    re.IGNORECASE,
)
_DOUBLES_EVENT = re.compile(rf"\b{_NOT}(?:(?:a|an)\s+)?doubles?\b", re.IGNORECASE)
_FACE = (
    rf"(?:\b(?:an?\s+)?(?:(?:even|odd|prime)(?:\s+numbers?)?|(?:number\s+)?{_COMPARE}\s+(?:an?\s+)?"
    r"[1-6]|multiple\s+of\s+[1-6]|(?<![\d.])[1-6](?!\d|\.\d)))"
)
_FACE_EVENT = re.compile(
    rf"{_NOT}(?:the\s+number\s+is\s+(?:(not)\s+)?)?({_FACE}(?:(?:\s*,\s*|\s+or\s+){_FACE})*)",
    re.IGNORECASE,
)
_FACE_PART = re.compile(
    rf"\b(even|odd|prime)\b|({_COMPARE})\s+(?:an?\s+)?([1-6])|multiple\s+of\s+([1-6])|([1-6])",
    re.IGNORECASE,
)
_VALUE_PART = re.compile(rf"(?:({_COMPARE})\s+)?(\d{{1,2}})", re.IGNORECASE)
_SUIT = r"(?:heart|spade|club|diamond)s?"
_CARD = (
    r"(?:\b(?:(?:an?|the)\s+)?(?:(?:red|black)\s+)?(?:(?:king|queen|jack|ace)s?(?:\s+of\s+"
    rf"{_SUIT})?|(?:face|picture|court)\s+cards?|{_SUIT})"
    r"|\b(?:(?:an?|the)\s+)?(?:red|black)\s+cards?)"
)
_CARD_EVENT = re.compile(rf"{_NOT}({_CARD}(?:(?:\s*,\s*|\s+or\s+){_CARD})*)\b", re.IGNORECASE)
_CARD_PART = re.compile(
    r"\b(?:(an?|the)\s+)?(?:(red|black)\s+)?(?:(king|queen|jack|ace)s?"
    r"(?:\s+of\s+(heart|spade|club|diamond)s?)?|(face|picture|court)\s+cards?"
    r"|(heart|spade|club|diamond)s?|cards?)",
    re.IGNORECASE,
)

# The setup each kind of draw is stated with, read before the event is looked for.
_DICE_SETUP = re.compile(
    r"\b(?:two|2|a\s+pair\s+of)\s+(?:fair\s+|unbiased\s+)?(?:(?:six|6)[- ]sided\s+)?di(?:c)?e\b",
    re.IGNORECASE,
)
_DIE_SETUP = re.compile(r"\b(?:six|6)[- ]sided\b", re.IGNORECASE)
_DECK_SETUP = re.compile(
    r"\b(?:deck|pack)\s+of\s+52\s+(?:playing\s+)?cards\b|\b52[- ](?:playing\s+)?cards?\b"
    r"|\b52[- ]card\b",
    re.IGNORECASE,
)
_KIT = (
    r"(?:a|an|one|two|2|the|a\s+pair\s+of)\s+(?:(?:fair|unbiased|standard|ordinary|full"
    r"|well[- ]shuffled|shuffled|(?:six|6)[- ]sided|52[- ]card)\s+)*(?:dice|die|cards?|deck|pack)"
)
_ACT = (
    r"(?:roll|rolls|rolling|throw|throws|throwing|toss|tosses|tossing|cast|casts|casting|draw"
    r"|draws|drawing|pick|picks|picking|select|selects|selecting)"
)
# Phrases that only set the scene. "if", "when", "with", "on", "same" and "one" are
# neutral only inside them: "if the dice show the same number" is a condition.
_SCENE = re.compile(
    rf"\b(?:if|when)\s+{_KIT}(?:\s+of\s+52\s+(?:playing\s+)?cards)?\s+(?:is|are)\s+"
    r"(?:rolled|thrown|tossed|cast|drawn|picked|selected|chosen|taken)\b"
    rf"|\b(?:if|when)\s+(?:(?:you|i|we|he|she|they)\s+)?{_ACT}\s+{_KIT}\b"
    rf"|\b{_ACT}\s+{_KIT}\s+and\s+(?=(?:getting|get|obtaining|obtain|drawing|having)\b)"
    rf"|\b(?:with|on|using|from)\s+{_KIT}\b|\b(?:one|a\s+single)\s+(?:fair\s+)?(?:die|card)\b"
    r"|\bat\s+(?:random|the\s+same\s+time)\b|\bin\s+(?:a|one)\s+(?:single\s+)?"
    r"(?:throw|roll|toss|draw|cast)\b|\b(?:lands?|landing)\s+on\b",
    re.IGNORECASE,
)

# Words that cannot change which outcomes are favourable.
_FILLER = frozenset(
    """
    a an the of that this is are was were be will what s find calculate compute determine
    work out give write probability chance likelihood getting get gets got rolling roll rolls
    rolled throwing throw throws thrown tossing toss tosses tossed cast casting obtaining obtain
    obtained drawing draw draws drawn picking pick picks picked selecting select selected
    choosing choose chosen taking take taken showing show shows shown up randomly once
    simultaneously together fair unbiased standard ordinary single it its i you we he she they
    his her him their someone number
    numbers face faces result outcome your answer as fraction simplest form decimal please
    explain show working steps step by hint only how why briefly me
    """.split()
)
_DICE_WORDS = frozenset({"two", "pair", "dice", "die"})
_DIE_WORDS = frozenset({"die"})
_DECK_WORDS = frozenset({"card", "cards", "deck", "pack", "playing", "shuffled", "well", "full"})
_SUITS = ("heart", "diamond", "spade", "club")
_RANK_VALUE = {"ace": 1, "jack": 11, "queen": 12, "king": 13}
FACE_CARDS = 14


@dataclass(frozen=True)
class DrawEvent:
    """Favourable outcomes of all, and what they are for the block to write.

    ``values`` are the sums for two dice or the faces for one die; ``cards`` the
    (colour, rank, suit) codes of each named kind of card, joined by "or".
    """

    favourable: int
    total: int
    kind: str
    negated: bool = False
    values: tuple[int, ...] = ()
    cards: tuple[tuple[int, int, int], ...] = ()


def _question(text: str) -> str:
    """The question without a multiple-choice list after it, or its frame (openers, an
    actor's name, how the answer is to be written)."""
    first = _FIRST_CHOICE.search(text)
    if first is not None and _SECOND_CHOICE.search(text, first.end()) is not None:
        text = text[: first.start()]
    return strip_ask_frame(text)


def _whole(text: str, spans: list[tuple[int, int]], words: frozenset[str]) -> bool:
    """True when nothing outside the read spans can change the event."""
    rest = list(text.lower())
    for start, end in [*spans, *(match.span() for match in _SCENE.finditer(text))]:
        rest[start:end] = " " * (end - start)
    leftover = re.findall(r"[a-z]+|\d+", "".join(rest))
    return all(word in _FILLER or word in words for word in leftover)


def _holds(value: int, relation: str, bound: int) -> bool:
    words = " ".join(relation.lower().split())
    above = re.match(_ABOVE, words) is not None
    if words.endswith("equal to"):
        return value >= bound if above else value <= bound
    if words.endswith("than"):
        return value > bound if above else value < bound
    if words == "at least":
        return value >= bound
    if words == "at most":
        return value <= bound
    return value == bound


def _one_reading(relations: list[str | None]) -> bool:
    """False for "greater than 4 or 5": does the comparison reach the 5 or not?"""
    return len(relations) == 1 or all(relations) or not any(relations)


def _uncertain(favourable: int, total: int) -> bool:
    return 0 < favourable < total


def two_dice_event(text: str) -> DrawEvent | None:
    question = _question(text)
    setup = [match.span() for match in _DICE_SETUP.finditer(question)]
    if not setup:
        return None
    sums = list(_SUM_EVENT.finditer(question))
    doubles = list(_DOUBLES_EVENT.finditer(question))
    if len(sums) + len(doubles) != 1:
        return None
    event = (sums or doubles)[0]
    if not _whole(question, [*setup, event.span()], _DICE_WORDS):
        return None
    if not sums:
        negated = bool(event.group(1))
        return DrawEvent(30 if negated else 6, 36, "doubles", negated)
    if event.group(1) and event.group(2):
        return None
    parts = list(_VALUE_PART.finditer(event.group(3)))
    if not _one_reading([part.group(1) for part in parts]):
        return None
    totals = {
        total
        for part in parts
        for total in range(2, 13)
        if _holds(total, part.group(1) or "", int(part.group(2)))
    }
    count = sum(6 - abs(total - 7) for total in totals)
    negated = bool(event.group(1) or event.group(2))
    favourable = 36 - count if negated else count
    if not _uncertain(favourable, 36):
        return None
    return DrawEvent(favourable, 36, "sum", negated, tuple(sorted(totals)))


def one_die_event(text: str) -> DrawEvent | None:
    # "a fair 6-sided die": the 6 is no face, so the setup is blanked before faces are read.
    question = _DIE_SETUP.sub(lambda match: " " * len(match.group(0)), _question(text))
    setup: list[tuple[int, int]] = []
    events = list(_FACE_EVENT.finditer(question))
    if len(events) != 1:
        return None
    event = events[0]
    if not _whole(question, [*setup, event.span()], _DIE_WORDS):
        return None
    if event.group(1) and event.group(2):
        return None
    parts = list(_FACE_PART.finditer(event.group(3)))
    if not _one_reading([part.group(2) for part in parts]):
        return None
    faces: set[int] = set()
    for part in parts:
        kind, relation, bound, factor, face = part.groups()
        if kind:
            faces |= {"even": {2, 4, 6}, "odd": {1, 3, 5}, "prime": {2, 3, 5}}[kind.lower()]
        elif relation:
            faces |= {value for value in range(1, 7) if _holds(value, relation, int(bound))}
        elif factor:
            faces |= {value for value in range(1, 7) if value % int(factor) == 0}
        else:
            faces.add(int(face))
    if event.group(1) or event.group(2):
        faces = set(range(1, 7)) - faces
    if not _uncertain(len(faces), 6):
        return None
    return DrawEvent(len(faces), 6, "faces", values=tuple(sorted(faces)))


def card_event(text: str) -> DrawEvent | None:
    question = _question(text)
    setup = [match.span() for match in _DECK_SETUP.finditer(question)]
    events = list(_CARD_EVENT.finditer(question))
    both = _both_kinds(question, events)
    if both is not None:
        return (
            both
            if _whole(question, [*setup, (events[0].start(), events[1].end())], _DECK_WORDS)
            else None
        )
    if len(events) != 1:
        return None
    event = events[0]
    if not _whole(question, [*setup, event.span()], _DECK_WORDS):
        return None
    named = [part for part in _CARD_PART.finditer(event.group(2)) if any(part.groups()[1:])]
    # "a red king or queen", "a king or queen of hearts": does the colour or the suit
    # reach across the "or"? Only when every kind has its own article is that settled.
    modified = any(part.group(2) or part.group(4) for part in named)
    if len(named) > 1 and modified and not all(part.group(1) for part in named):
        return None
    codes = tuple(_card_code(part) for part in named)
    cards = {card for code in codes for card in _cards(code)}
    negated = bool(event.group(1))
    favourable = 52 - len(cards) if negated else len(cards)
    if not codes or not cards or not _uncertain(favourable, 52):
        return None
    return DrawEvent(favourable, 52, "cards", negated, cards=codes)


# What joins the two kinds of one card ("a black card that is a king"), read as words: no
# pattern scans a run of spaces.
_JOINS = (["that", "is"], ["which", "is"], ["that", "is", "also"], ["which", "is", "also"])


def _joins_both(between: str) -> bool:
    edged = between[:1].isspace() and between[-1:].isspace()
    return edged and between.lower().split() in _JOINS


def _both_kinds(question: str, events: list[re.Match[str]]) -> DrawEvent | None:
    """ "A black card that is a king": one card of both kinds, the black kings."""
    if len(events) != 2 or any(event.group(1) for event in events):
        return None
    if not _joins_both(question[events[0].end() : events[1].start()]):
        return None
    parts = [
        [part for part in _CARD_PART.finditer(event.group(2)) if any(part.groups()[1:])]
        for event in events
    ]
    if any(len(named) != 1 for named in parts):
        return None
    first, second = (_card_code(named[0]) for named in parts)
    # Each field is named once: a colour and a rank, never two colours.
    if any(one and other and one != other for one, other in zip(first, second, strict=True)):
        return None
    code = (first[0] or second[0], first[1] or second[1], first[2] or second[2])
    count = len(_cards(code))
    return DrawEvent(count, 52, "cards", cards=(code,)) if _uncertain(count, 52) else None


def _card_code(part: re.Match[str]) -> tuple[int, int, int]:
    _, colour, rank, rank_suit, face, suit = part.groups()
    tint = {"red": 1, "black": 2}.get((colour or "").lower(), 0)
    value = FACE_CARDS if face else _RANK_VALUE.get((rank or "").lower(), 0)
    named_suit = (rank_suit or suit or "").lower()
    return tint, value, _SUITS.index(named_suit) + 1 if named_suit else 0


def _cards(code: tuple[int, int, int]) -> set[tuple[int, str]]:
    tint, value, suit = code
    return {
        (rank, name)
        for rank in range(1, 14)
        for index, name in enumerate(_SUITS, start=1)
        if (not tint or (index <= 2) == (tint == 1))
        and (not value or rank == value or (value == FACE_CARDS and rank > 10))
        and (not suit or index == suit)
    }


def card_label(code: tuple[int, int, int]) -> str:
    """``the king of hearts``, ``red kings``, ``face cards``, ``hearts``, ``red cards``."""
    tint_code, value, suit = code
    tint = ("", "red ", "black ")[tint_code]
    rank = {number: name for name, number in _RANK_VALUE.items()}.get(value)
    suits = f"{_SUITS[suit - 1]}s" if suit else ""
    if rank and suits:
        return f"the {rank} of {suits}"
    if rank:
        return f"{tint}{rank}s"
    if value == FACE_CARDS:
        return f"{tint}face cards"
    return suits or f"{tint}cards"
