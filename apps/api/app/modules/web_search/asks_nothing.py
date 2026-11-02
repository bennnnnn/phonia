"""Does this turn ask to know anything? A turn that doesn't never searches.

"Today", "now", "latest" and "news" made every sentence that held them look
live: "you're doing a great job today", "I just watched the news and I feel
overwhelmed", "write a short poem about today" all paid for a search. A time
word only matters in a turn that asks for something out in the world. Three
shapes ask for nothing to look up:

- A statement: no question and no request, and it tells something (about the
  user, the assistant, or something that happened).
- A request to make something: write, teach, quiz, plan, translate, "give me a
  word of the day". Its subject is ours to produce, not to find, unless it is
  the news or the weather.
- A question about us: "how is your day going", "what should I cook tonight".

A bare topic ("latest news about Ethiopia", "bitcoin price today") is a lookup
typed short and stays searchable.
"""

from __future__ import annotations

import re

from app.modules.web_search.patterns import _LATEST_NEWS, _NEWS, collapse_ws, is_weather_request

_LEAD_IN = r"(?:(?:hey|hi|hello|ok(?:ay)?|so|and|also|but|well|please|recall|there)\b[\s,!.]*)*"
# "Can you tell me", "do you know": a polite way in to the question itself.
_POLITE = re.compile(
    r"^(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:tell\s+me\s+)?"
    r"|do\s+you\s+know\s+|please\s+)",
    re.IGNORECASE,
)
# "What a day" exclaims; it does not ask.
_ASK_OPENER = re.compile(
    r"(?!what\s+an?\b)(?:who(?:'s|se|m)?|what(?:'s|re)?|which|when|where(?:'s)?|why|how(?:'s)?|"
    r"is|are|was|were|did|does|do|has|have|will|can|could|should|any)\b",
    re.IGNORECASE,
)
# "In which order did we cover it", "at what point did you say": the question opens with a
# preposition, and reads the same without it.
_PREP_OPENER = re.compile(
    r"^(?:in|at|on|for|by|with|from|to|of|about|after|before|during|since|until)\s+"
    r"(?=(?:which|what)\b)",
    re.IGNORECASE,
)
# Asks for something wherever it sits: "I want the latest news", "let me know the score".
_REQUEST = re.compile(
    r"\b(?:tell\s+me|show\s+me|let\s+me\s+know|find|look\s+up|check|search|google|"
    r"get\s+me|(?:i|we)\s+(?:want|need|would\s+like|'d\s+like|wanna)|i\s+wonder|"
    r"looking\s+for)\b",
    re.IGNORECASE,
)
# Made, not found. Sample, dummy or example data is made up on the spot.
_PRODUCE = re.compile(
    r"(?:write|draft|compose|rewrite|edit|proofread|translate|summari[sz]e|teach|quiz|"
    r"test\s+me|make|create|generate|draw|plan|design|brainstorm|suggest|recommend|"
    r"help\s+me|give\s+me\s+(?:an?|some|\d+)\b(?!\s+(?:list|update|summary)\s+of\s+"
    r"(?:the\s+)?(?:news|headlines))|"
    r"(?:give|show|send)\s+me\s+(?:some\s+|an?\s+)?(?:sample|example|dummy|mock|fake|"
    r"placeholder|random|made[\s-]up)\s+\w+|"
    r"(?:give|show|send)\s+me\s+(?:some\s+)?test\s+(?:data|rows|records|values|inputs|"
    r"cases|users|accounts|emails)\b)\b",
    re.IGNORECASE,
)
# "Give me a table of the exact transaction charges": made in form, found in substance. A
# word that asks for the real figure beside a fee, rate or price is a lookup, not a draft.
_EXACT_FIGURES = re.compile(
    r"\b(?:exact|actual|official|current|real|precise|up[\s-]to[\s-]date)\b[\w\s,()/-]{0,40}?"
    r"\b(?:fees?|charges?|rates?|prices?|costs?|taxes|tax|levy|levies|duty|duties|commissions?|"
    r"yields?|minimums?|limits?|requirements?|interest)\b",
    re.IGNORECASE,
)
_ABOUT_US = re.compile(
    r"\b(?:i|i'm|im|i've|i'd|i'll|me|my|mine|we|we're|us|our|you|you're|your|u|ur|"
    r"mood|feeling)\b",
    re.IGNORECASE,
)
# Someone speaking about themselves or to the assistant. "My" alone only says
# whose: "the score of my team's game today" still asks.
_SPEAKER = re.compile(
    r"\b(?:i|i'm|im|i've|i'd|i'll|we|we're|we've|you|you're|you've|u|mood|feeling)\b",
    re.IGNORECASE,
)
# A sentence that says something happened or how something is.
_TELLS = re.compile(
    r"\b(?:is|was|are|were|been|it's|that's|there's|here's|feel|feels|felt|got|had|made|went|looks?|looked|seems?|"
    r"seemed|tripped|happened|finished|passed|loved?|liked?|hated?|gave|told|said|did|saw|watched|"
    # "Recursion makes no sense to me": a learner stuck on a topic tells; the lesson answers.
    r"makes?\s+no\s+sense|confus(?:e|es|ed|ing)|over\s+my\s+head)\b",
    re.IGNORECASE,
)
_CHATTER = re.compile(
    r"^(?:lol|haha+|omg|ugh|wow|aw+|yay|nice|great|thanks?|thank\s+you|"
    r"good\s+(?:morning|afternoon|evening|night)|what\s+an?)\b",
    re.I,
)
_ASK_WINDOW_WORDS = 4
# "Near me", "in my country": where to look, not a word about the user.
_PLACE = re.compile(
    r"\b(?:near|around|close\s+to)\s+me\b"
    r"|\b(?:in|around|for)\s+my\s+(?:area|city|town|country|neighbou?rhood|region|state)\b",
    re.IGNORECASE,
)
# Something named in the world ("Kenya", "London"). "I" is the user, Recall is
# the assistant, and a day or month is the calendar.
_NAMED = re.compile(
    r"(?<!^)(?<![.!?]\s)\b(?!I\b|Recall\b|(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\b)[A-Z][a-z]+"
)


def _clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|,\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _asks_about_us(clause: str) -> bool:
    """A question about the user or the assistant, naming nothing out in the world."""
    # "Where should I eat", "where did you get that": a place or a source to find.
    if _NAMED.search(clause) or clause.casefold().startswith("where"):
        return False
    words = clause.split()[1 : 1 + _ASK_WINDOW_WORDS]
    return any(_ABOUT_US.fullmatch(w.strip("?.,!")) for w in words)


def _questions(text: str) -> list[str]:
    asked = []
    for clause in _clauses(text):
        body = re.sub(rf"^{_LEAD_IN}", "", clause, flags=re.IGNORECASE)
        body = _PREP_OPENER.sub("", _POLITE.sub("", body))
        if _ASK_OPENER.match(body):
            asked.append(body)
    return asked


def _live_subject(text: str) -> bool:
    return bool(_NEWS.search(text) or _LATEST_NEWS.search(text) or is_weather_request(text))


def asks_nothing_to_look_up(text: str) -> bool:
    """True when the turn tells, makes or asks about us: nothing in the world to look up."""
    cleaned = _PLACE.sub("here", collapse_ws(text))
    if not cleaned:
        return True
    body = _POLITE.sub("", re.sub(rf"^{_LEAD_IN}", "", cleaned, flags=re.IGNORECASE))
    if _PRODUCE.match(body):
        return not (_live_subject(cleaned) or _EXACT_FIGURES.search(cleaned))
    questions = _questions(cleaned)
    if questions:
        return all(_asks_about_us(q) for q in questions)
    if _REQUEST.search(cleaned):
        return False
    # Nothing asked: a statement tells; a bare topic ("latest news about Ethiopia") asks short.
    if "?" in cleaned:
        return False
    if _CHATTER.match(body) or _SPEAKER.search(cleaned):
        return True
    # "Today was a good day" tells; "gold went up today in London" names the world.
    return bool(_TELLS.search(cleaned)) and not _NAMED.search(cleaned)
