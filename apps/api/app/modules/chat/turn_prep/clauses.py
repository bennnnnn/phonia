"""Where one message asks for more than one thing: the text rules.

``request_clauses`` cuts a message where a new request can start and keeps a cut
only when what follows is a request of its own:

- strong: "…, and also …", "… Also, …", "btw", "one more thing", "I also want …";
- sentence: a new sentence after "?", "!", "." or a line break;
- comma: ", and how …", ", and tell me …", "; …";
- and: "… and tell me a joke".

A clause that points back ("and when to use each", "and graph it", "which is
faster") stays with the one before it, and so does one that names nothing of its
own ("and give me an example"). A statement is context, not a request. Code, a
quote, text after "translate this:" and long pasted text are never cut.
``intents.plan_turn`` then keeps a weaker cut only when the two sides go to
different places, or name different subjects.

A wrong single part is how every turn behaved before plans existed; a wrong cut
breaks one answer into sections. So every doubt keeps clauses together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

from app.modules.turn_reading.coding import has_code_syntax
from app.services.text_normalize import collapse_ws


class Cut(IntEnum):
    """How a clause was cut from the one before it, weakest first."""

    START = 0
    AND = 1
    COMMA = 2
    SENTENCE = 3
    STRONG = 4


@dataclass(frozen=True)
class Clause:
    text: str
    cut: Cut
    # What the clause is about (``topic_words``).
    topics: frozenset[str]


@dataclass(frozen=True)
class RequestSplit:
    # Statements before the first request: the user's situation, for every part.
    context: str
    clauses: tuple[Clause, ...]


# Pasted articles and long briefs are one request with a lot of detail.
_MAX_CHARS = 600
_MAX_CLAUSES = 5

_WH = r"what|what's|whats|who|who's|whose|whom|when|where|where's|why|how|how's|which"
_AUX = r"is|are|was|were|can|could|should|would|will|do|does|did|has|have|any"
# A fresh task. "Include", "keep", "use", "avoid" only shape the request before them.
_TASK_VERBS = (
    "tell explain describe define write draft compose give show find search look google "
    "recommend suggest list compare translate summarize summarise teach draw create generate "
    "design plan solve calculate compute convert graph plot remind switch change set turn "
    "build implement debug review proofread rewrite brainstorm quiz check add make help"
).split()
_TASK = "|".join(_TASK_VERBS)
_OPENER = rf"(?:{_WH}|{_AUX}|{_TASK})\b"
_LEAD_WORDS = (
    r"(?:and |but |oh )?also|btw|by the way|oh and|plus|separately|unrelated(?:ly)?|"
    r"on (?:another|a different) note|another (?:question|thing)|one more (?:question|thing)"
)
_CUTS = re.compile(
    r"(?P<strong>,? and also\b,?|[,;] also\b,?|,? and (?=(?:i|we) also\b)"
    r"|, (?=(?:i|we) also\b)|[,;] (?=(?:btw|by the way|oh and|one more (?:thing|question)"
    r"|another (?:thing|question)|on another note)\b))"
    r"|(?P<sentence>(?<=[?!]) |(?-i:(?<=[a-z0-9)\]\"'%])\. (?=[A-Z]))|(?<=\w): (?=\w))"
    rf"|(?P<comma>, and (?={_OPENER})|; )"
    rf"|(?P<and> and (?={_OPENER}))",
    re.IGNORECASE,
)
_CUT_KIND = {"strong": 4, "sentence": 3, "comma": 2, "and": 1}
_LINE_ITEM = re.compile(r"^(?:\d{1,2}[.)]|[-*\u2022]) ?")
_LEAD = re.compile(rf"^(?:{_LEAD_WORDS}|and|so|ok(?:ay)?)\b[,:]? ?", re.IGNORECASE)
_STRONG_START = re.compile(rf"^(?:{_LEAD_WORDS})\b", re.IGNORECASE)
# Politeness, and a length or manner said first: "in one sentence, what is DNS?".
_POLITE = re.compile(
    r"^(?:please|pls|hey|hi|hello|now|quick question|(?:can|could|would|will) (?:you|u)|"
    r"do you know|i was wondering|briefly|quickly|simply|honestly|in short|in brief|"
    r"in simple terms|in detail|in (?:one|a|two|three|\d+|a few) "
    r"(?:sentence|line|word|paragraph|bullet)s?)\b[,!:]? ?",
    re.IGNORECASE,
)
_QUESTION = re.compile(rf"^(?:{_WH})\b", re.IGNORECASE)
_AUX_QUESTION = re.compile(rf"^(?:{_AUX})\b", re.IGNORECASE)
_TASK_START = re.compile(rf"^(?:{_TASK})\b(?! (?:it|that|this|them)\b)", re.IGNORECASE)
_WANT = re.compile(
    r"^(?:i|we) (?:also |really |just )?(?:want|need|would like|'d like|wanna|"
    r"am looking for|'m looking for)\b",
    re.IGNORECASE,
)
# "Translate this: where is the station and how much is a ticket" is one text to translate.
_CONTENT_COLON = re.compile(
    r"\b(?:write|draft|translate|rewrite|reword|proofread|summari[sz]e|compose|reply|"
    r"respond|edit|correct|paraphrase|format)\b[^:]{0,80}:",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"\"[^\"]{1,200}\"|\u201c[^\u201d]{1,200}\u201d|(?<!\w)'[^']{1,120}'(?!\w)")
# "What time is it", "is it going to rain": an "it" that names nothing earlier.
_EMPTY_IT = re.compile(
    r"\b(?:what (?:time|day|date|year|month) is it|(?:time|day|date) it is|"
    r"(?:is|will) it (?:going to )?(?:be )?(?:rain|snow|cold|hot|warm|sunny|windy|cloudy)\w*|"
    r"it(?:'s| is) (?:going to )?(?:rain|snow)\w*|how (?:long|far) (?:does|will|would|is) it)\b",
    re.IGNORECASE,
)
_POINTS_BACK = re.compile(
    r"\b(?:it|its|itself|they|them|their|theirs|these|those|he|him|his|she|her|hers|each|"
    r"both|either|neither|the same|the former|the latter|the other|why not|"
    r"(?:what|how) about|same for|compared? (?:with|to|against)|"
    r"which (?:is|are|was|were|one|ones|to|should|would|will|of)|"
    r"one of (?:them|those|these)|(?:which|that|this|a good|the best|get|buy|pick|choose|"
    r"recommend) one)\b"
    # "Go there", not "is there a museum".
    r"|(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bwere )\bthere\b(?! (?:is|are|was|were)\b)(?!')"
    # "Is that true", not "how do I know that my code works" or "this week".
    r"|\b(?:that|this)\b(?! (?:my|your|our|the|a|an|i|you|we|week|weekend|year|month|"
    r"morning|afternoon|evening|time|summer|winter|spring|fall|season)\b)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W_][\w'+#-]*")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
_MATH = re.compile(r"[\w^.()]+ ?(?:[-+*/^=<>] ?[\w^.()]+)+")
_STOP = frozenset(
    """a about above after again all also am an and any are as at be because been before
    being below between both but by can can't could did didn't do does doesn't doing don't
    done down during each few for from further going gonna got gotta had has have having he
    her here hers him his how how's i i'd i'll i'm i've if in into is isn't it it's its just
    know let let's like me mine more most much must my no nor not now of off ok okay on once
    only or other our ours out over own please pls really right same say she should so some
    such than thank thanks that that's the their them then there there's these they this
    those through to too under until up us very want wanna was we well were what what's
    whats when where where's which while who who's whom whose why will with would yeah yes
    you your yours actually maybe need think see looking way ways get use using used today
    tomorrow tonight yesterday current currently latest recent good best better great nice
    new thing things stuff something anything everything example examples summary tip tips
    detail details step steps code version answer explanation table pros cons difference
    differences idea ideas option options question questions info information overview
    breakdown work works working time quick another one ones lot made mean means happen
    happens""".split()
)
_TASK_WORD_SET = frozenset(_TASK_VERBS)
_MAX_LEADS = 4


def topic_words(text: str) -> frozenset[str]:
    """What a clause is about: its content words, each maths expression whole, and its
    numbers ("And what's 15% of 80?" asks about 15% and 80, not nothing)."""
    lowered = text.lower()
    found = {re.sub(r"\s", "", span) for span in _MATH.findall(lowered) if _is_math(span)}
    found.update(_NUMBER.findall(lowered))
    for raw in _WORD.findall(lowered):
        word = raw.strip("'-").removesuffix("'s")
        if len(word) >= 3 and word not in _STOP and word not in _TASK_WORD_SET:
            found.add(word)
    return frozenset(found)


def _is_math(span: str) -> bool:
    return any(ch.isdigit() for ch in span) or "=" in span


def points_back(text: str) -> bool:
    """True when the clause leans on the one before it ("graph it", "which is faster")."""
    return _POINTS_BACK.search(_EMPTY_IT.sub(" ", text)) is not None


_DEFINITE = re.compile(r"\bthe ([a-z][\w'-]*)(?! of\b)", re.IGNORECASE)


def leans_on_definite(text: str) -> bool:
    """ "Who scored the goals": "the goals" are the ones just asked about.

    "The capital of Australia" says whose; "the best" names no thing.
    """
    return any(
        word.lower() not in _STOP and word.lower() not in _TASK_WORD_SET
        for word in _DEFINITE.findall(request_body(text))
    )


def without_connector(text: str) -> str:
    """The clause without the "and also" / "btw" that joined it to the one before."""
    body = text.strip(" ,;")
    for _ in range(_MAX_LEADS):
        stripped = _LEAD.sub("", body).strip(" ,;")
        if stripped == body:
            break
        body = stripped
    return body


def request_body(text: str) -> str:
    """The clause without its connector or politeness: "and also, can you tell me" → "tell me"."""
    body = text.strip(" ,;")
    for _ in range(_MAX_LEADS):
        stripped = _POLITE.sub("", _LEAD.sub("", body)).strip(" ,;")
        if stripped == body:
            break
        body = stripped
    return body


def is_request(text: str, cut: Cut) -> bool:
    """A question, a fresh instruction, or (first, or after a strong cut) "I also want …"."""
    body = request_body(text)
    if not body:
        return False
    if _QUESTION.match(body) or _TASK_START.match(body):
        return True
    if _AUX_QUESTION.match(body):
        return body.endswith("?")
    return bool(_WANT.match(body)) and cut in (Cut.START, Cut.STRONG)


def _segments(line: str, first_cut: Cut) -> list[tuple[str, Cut]]:
    """One line cut at every candidate boundary, each with the cut before it."""
    # A quote keeps its length, so cuts found in the mask fall in the same place.
    masked = _QUOTED.sub(lambda match: "\u2063" * len(match.group(0)), line)
    pieces: list[tuple[str, Cut]] = []
    start, cut = 0, first_cut
    for match in _CUTS.finditer(masked):
        pieces.append((line[start : match.start()], cut))
        start = match.end()
        cut = Cut(_CUT_KIND[match.lastgroup or "and"])
    pieces.append((line[start:], cut))
    out: list[tuple[str, Cut]] = []
    for text, how in pieces:
        text = text.strip(" ,;")
        if not text:
            continue
        # "… Also, how do I …": a sentence that opens with "also" is a strong cut.
        if how == Cut.SENTENCE and _STRONG_START.match(text):
            how = Cut.STRONG
        out.append((text, how))
    return out


def _lines(text: str) -> list[str]:
    lines = (_LINE_ITEM.sub("", collapse_ws(line)) for line in text.splitlines())
    return [line for line in lines if line]


def _cuttable(text: str) -> bool:
    if len(text) > _MAX_CHARS or "```" in text or has_code_syntax(text):
        return False
    return _CONTENT_COLON.search(text) is None


def _whole(text: str) -> RequestSplit:
    # One clause is compared with nothing, so its topics are never read (and a long
    # paste is never scanned for them).
    return RequestSplit("", (Clause(text, Cut.START, frozenset()),))


def request_clauses(text: str) -> RequestSplit:
    """The message's requests in order; a cut that fails the rules above is merged back."""
    whole = collapse_ws(text)
    if not whole or not _cuttable(text):
        return _whole(whole)
    segments: list[tuple[str, Cut]] = []
    for index, line in enumerate(_lines(text)):
        segments.extend(_segments(line, Cut.START if index == 0 else Cut.SENTENCE))
    # "Why does it look like that? What are the scales made of": a follow-up to the
    # chat, all of it.
    if not segments or points_back(segments[0][0]):
        return _whole(whole)
    context: list[str] = []
    clauses: list[Clause] = []
    for raw, cut in segments:
        topics = topic_words(request_body(raw))
        if not clauses:
            if is_request(raw, Cut.START):
                clauses.append(Clause(raw, Cut.START, topics))
            else:
                context.append(raw)
        elif is_request(raw, cut) and topics and not points_back(raw):
            clauses.append(Clause(raw, cut, topics))
        else:
            last = clauses[-1]
            clauses[-1] = Clause(f"{last.text} {raw}", last.cut, last.topics | topics)
    if not clauses or len(clauses) > _MAX_CLAUSES:
        return _whole(whole)
    return RequestSplit(" ".join(context), tuple(clauses))
