"""Regex patterns for web search intent detection."""

from __future__ import annotations

import re

from app.modules.web_search.command import search_command
from app.modules.web_search.weather import is_weather_request as is_weather_request

# Re-export for detection/subject/query_builders (stable import path).
from app.services.text_normalize import collapse_ws as collapse_ws

_EXPLICIT_SEARCH = re.compile(
    r"\b("
    r"search(?: the)? web"
    r"|look(?: it| that)? up(?! to\b)(?: online)?"
    r"|google(?: for| this| it)?"
    r"|web search"
    r"|find(?: me)? (?:online|on the internet)"
    r")\b",
    re.IGNORECASE,
)

# Match against ``collapse_ws``-normalized input (single spaces, no leading/trailing).
_LOOK_IT_UP = re.compile(
    r"^(?:please )?(?:look(?: it| that) up|search(?: for)?(?: it)?)[.!?]*$",
    re.IGNORECASE,
)

# "Where did you get that?" is about the previous question, not a new topic.
_SOURCE_FOLLOWUP = re.compile(
    r"^(?:and )?(?:where|how) (?:did|do) you (?:get|know|find) (?:that|this|it)"
    r"(?: from)?[.!?]*$",
    re.IGNORECASE,
)


def asks_for_prior_subject(text: str) -> bool:
    """True when the whole message points at the previous question.

    That includes a search request that names nothing ("do a search", "check
    that online"): the conversation says what to search.
    """
    cleaned = collapse_ws(text)
    if _LOOK_IT_UP.match(cleaned) or _SOURCE_FOLLOWUP.match(cleaned):
        return True
    command = search_command(cleaned)
    return command is not None and command.subject is None


_CLARIFICATION = re.compile(
    r"^(?:"
    r"no[,!.]? (?:i meant|the|not)|"
    r"(?:i meant|not that|the ongoing|the current|that one|this one)|"
    r"yes[,!.]? (?:that|the)\b"
    r")",
    re.IGNORECASE,
)

_ONGOING = re.compile(
    r"\b(ongoing|current(?:ly)?|right now|happening now|this one|that one)\b",
    re.IGNORECASE,
)

_WORLD_CUP = re.compile(r"\b(world\s+cup|fifa|wc\s*2026|2026\s+world\s+cup)\b", re.IGNORECASE)

_SHORT_FOLLOWUP_WORDS = 12

_RECENCY_PHRASES = (
    "latest",
    "breaking news",
    "today",
    "today's",
    "current",
    "currently",
    "recent",
    "recently",
    "right now",
    "this week",
    "this month",
    "as of",
    "news",
    "headline",
    "stock price",
    "share price",
    "market cap",
    "who won",
    "what happened",
    "score",
    "scores",
    "release date",
)


def has_recency(text: str) -> bool:
    """True when ``text`` (already ``collapse_ws``-normalized) looks time-sensitive.

    Uses substring / index scans — the old ``.+`` alternatives in a single
    regex were CodeQL polynomial-ReDoS sinks on user chat text.
    """
    low = text.lower()

    def _bounded(phrase: str) -> bool:
        start = 0
        while True:
            i = low.find(phrase, start)
            if i == -1:
                return False
            before_ok = i == 0 or not low[i - 1].isalnum()
            if phrase in {"score", "scores"} and i > 0 and low[i - 1] == "-":
                # ``z-score`` is a stable statistics term, not a live sports score.
                before_ok = False
            after = i + len(phrase)
            after_ok = after >= len(low) or not low[after].isalnum()
            if before_ok and after_ok:
                return True
            start = i + 1

    if any(_bounded(p) for p in _RECENCY_PHRASES):
        return True
    idx = low.find("when did ")
    if idx != -1:
        rest = low[idx + 9 :]
        if any(k in rest for k in (" happen", " release", " launch")):
            return True
    idx = 0
    while True:
        i = low.find("is ", idx)
        if i == -1:
            break
        if i == 0 or not low[i - 1].isalnum():
            rest = low[i + 3 :]
            if "still alive" in rest or "currently alive" in rest:
                return True
        idx = i + 1
    return False


_NEWS = re.compile(
    r"\b("
    r"what(?:['\u2019]s| is) (?:happening|going on|new(?!\s+with\s+(?:you|u|ya|yourself)\b)|in the news)"
    r"|top (?:news|stories|headlines)"
    r"|news (?:today|this week|stories)"
    r"|in the world today"
    r"|world news|current events"
    r"|what(?:['\u2019]s| is) cookin(?:['\u2019]|g)?(?: in the world)?"
    r")\b",
    re.IGNORECASE,
)

# "latest news on AI", "breaking news", "news about the election": always live.
_LATEST_NEWS = re.compile(
    r"\b(?:(?:latest|breaking|recent|today['\u2019]?s)\s+(?:news|headlines|updates?)"
    r"|news\s+(?:on|about|from|for)\s+\w)",
    re.IGNORECASE,
)

# "the new Tesla model", "the newest iPhone", "the latest Django release": what
# is new changes after training, so the answer has to come from a search. "New"
# needs "the" and a product word: "I'm new to Python", "happy new year" and "a
# new way to learn" stay offline, as does "the new model I trained" (no name).
_NEW_PRODUCT = re.compile(
    r"\b(?:the\s+new|(?:the\s+)?(?:newest|latest|brand[- ]new))\s+"
    r"(?:(?:[a-z0-9][\w.+-]*\s+){1,3}"
    r"(?:models?|versions?|releases?|phones?|cars?|laptops?|consoles?|updates?|editions?"
    r"|lineups?|chips?|series|flagships?|launch(?:es)?)"
    r"|(?:iphone|ipad|pixel|galaxy|macbook|playstation|xbox|airpods|apple\s+watch|tesla"
    r"|cybertruck|gpt|gemini|claude|llama)\b)",
    re.IGNORECASE,
)


_SPORTS = re.compile(
    r"\b("
    r"game|games|match|matches|score|scores|result|results|fixture|standings|highlights|"
    r"soccer|football|nba|nfl|mlb|nhl|premier league|world cup|mls|uefa|champions league"
    r")\b",
    re.IGNORECASE,
)

_YESTERDAY = re.compile(r"\byesterday(?:'?s)?\b", re.IGNORECASE)

_SPORTS_LOOKUP = re.compile(
    r"\b("
    r"yesterday(?:'?s)?\s+(?:games?|match(?:es)?|result|score|scores)"
    r"|(?:games?|match(?:es)?|score|scores|results?)\s+(?:from\s+)?yesterday"
    r"|show me (?:the\s+)?yesterday(?:'?s)?\s+(?:games?|match(?:es)?|result|score|scores)"
    r"|show me (?:the\s+)?(?:games?|match(?:es)?|score|scores|results?)"
    r"|who won (?:the\s+)?(?:games?|match(?:es)?|yesterday|last night)"
    r"|last night(?:'s)?\s+(?:games?|match(?:es)?|score|scores)"
    r")\b",
    re.IGNORECASE,
)

# A team name first: ``(?<=..)``, not ``.{2,60}`` (retried from every start; only yes/no is read).
_TEAM_SCORE = re.compile(r"(?<=..)\b(?:games?|match(?:es)?)\s+score", re.IGNORECASE)

# "always result" is maths, not a possessive: "result" counts only after an apostrophe.
# "Ethiopias game score" still matches the game/score branch.
_TEAM_POSSESSIVE_SCORE = re.compile(
    r"(?<=..)(?:"
    r"'s\s+(?:games?|match(?:es)?|score|scores|result|results)"
    r"|s\s+(?:games?|match(?:es)?|score|scores)"
    r")",
    re.IGNORECASE,
)

_SKIP = re.compile(
    r"\b("
    r"rewrite|proofread|debug|refactor|explain\s+this\s+code"
    r"|help\s+me\s+write|draft\s+(?:an?\s+)?(?:email|message|reply)"
    r"|remember\s+that|add\s+to\s+(?:my\s+)?(?:todo|list|memory)"
    r"|translate|summarize\s+this\s+(?:text|email|article)"
    r"|vocabulary\s+quiz|interactive\s+vocabulary|quiz\s+me\s+in\s+chat"
    r"|quick\s+quiz|begin\s+with\s+the\s+first\s+question"
    r")\b",
    re.IGNORECASE,
)

# A reminder or a request to read the user's own list is not a lookup,
# even when the previous turn searched the web.
_REMINDER_TURN = re.compile(
    r"^(?:please\s+)?(?:can you\s+)?remind\s+me\b"
    r"|^(?:what|which)\s+(?:reminders?|todos?|tasks?)\s+do\s+i\s+have\b",
    re.IGNORECASE,
)

_PERSONAL_PLANNING = re.compile(
    r"\b("
    r"what\s+(?:am\s+I|are\s+we|do\s+I|should\s+I)\s+(?:trying\s+to\s+)?(?:get|have)\s+(?:done|to\s+do)"
    r"|what(?:'s| is)\s+(?:on\s+my\s+(?:plate|list|agenda)|due|still\s+open)"
    r"|what\s+(?:do\s+I|should\s+I)\s+need\s+to\s+(?:do|finish|tackle)"
    r"|(?:my|any)\s+(?:tasks?|todos?|reminders?)\s+(?:for\s+)?(?:today|tonight|this\s+week)"
    r"|how(?:'s| is)\s+my\s+day\s+looking"
    r"|how\s+did\s+my\s+day\s+go"
    r"|help\s+me\s+(?:prioriti[sz]e|plan|wrap\s+up)"
    r"|(?:show|list)\s+(?:me\s+)?(?:my\s+)?(?:tasks?|todos?|reminders?)"
    r"|what\s+(?:should\s+I|can\s+I)\s+(?:tackle|focus\s+on|work\s+on)\s+(?:today|tonight|now)?"
    r"|anything\s+(?:left|open|due)\s+(?:for\s+)?(?:me\s+)?(?:today|tonight)"
    r"|wrap\s+up\s+(?:loose\s+ends|my\s+day)"
    r"|wind\s+down"
    r")\b",
    re.IGNORECASE,
)

# The user's own calendar or schedule. Recall cannot see it and neither can the web.
_OWN_CALENDAR = re.compile(
    r"\b("
    r"google calendar|my calendar|check my calendar|connect my calendar|"
    r"what(?:'s| is) on my calendar|calendar today|calendar tomorrow|"
    r"meetings today|meetings tomorrow|any meetings|"
    r"what do i have (?:on|scheduled)|what am i doing (?:today|tomorrow)|"
    r"what(?:'s| is) my schedule|my schedule (?:today|tomorrow|this week)"
    r")\b",
    re.IGNORECASE,
)

# Proximity intent — any "near me / nearest / closest …" ask, not a venue-type list.
_NEARBY_INTENT = re.compile(
    r"\b("
    r"near\s+me|nearby|around\s+here|in\s+(?:this\s+)?town"
    r"|close\s+(?:by|to\s+me)"
    r"|(?:the\s+)?(?:nearest|closest)\b"
    r")\b",
    re.IGNORECASE,
)

# Abstract "nearest X" subjects — not a maps search. Matched with bounded
# index scans (not ``nearest.+word``) to avoid poly-ReDoS on chat text.
_NON_GEOGRAPHIC_NEAREST_WORDS = (
    "number",
    "numbers",
    "integer",
    "prime",
    "multiple",
    "match",
    "deadline",
    "star",
    "planet",
    "galaxy",
    "sun",
    "moon",
    "approach",
    "analogy",
    "synonym",
    "equivalent",
    "friend",
    "relative",
    "cousin",
    "neighbor",
    "neighbour",
    "guess",
    "approximation",
    "solution",
    "competitor",
    "rival",
)
_GEO_PHRASE_GAP = 120


def _find_word(haystack: str, word: str, start: int = 0) -> int:
    """Index of a whole-word match of ``word`` in lowercase ``haystack``, or -1."""
    n = len(word)
    i = start
    while True:
        i = haystack.find(word, i)
        if i == -1:
            return -1
        before_ok = i == 0 or not haystack[i - 1].isalnum()
        after = i + n
        after_ok = after >= len(haystack) or not haystack[after].isalnum()
        if before_ok and after_ok:
            return i
        i = after


def non_geographic_nearest(text: str) -> bool:
    """True for 'nearest prime' / 'closest friend' — not venue search."""
    low = text.lower()
    for anchor in ("nearest", "closest"):
        start = 0
        while True:
            i = _find_word(low, anchor, start)
            if i == -1:
                break
            rest = low[i + len(anchor) : i + len(anchor) + _GEO_PHRASE_GAP]
            if any(_find_word(rest, w) != -1 for w in _NON_GEOGRAPHIC_NEAREST_WORDS):
                return True
            start = i + 1
    return False


def best_near_phrase(text: str) -> bool:
    """True for 'best … in/near/around/by …' without ``best.+near`` ReDoS."""
    low = text.lower()
    start = 0
    while True:
        i = _find_word(low, "best", start)
        if i == -1:
            return False
        rest = low[i + 4 : i + 4 + _GEO_PHRASE_GAP]
        if any(_find_word(rest, w) != -1 for w in ("in", "near", "around", "by")):
            return True
        start = i + 1


# Implicit nearby intent without saying "near me" (e.g. "where should I eat tonight?").
_IMPLICIT_LOCAL = re.compile(
    r"\b(?:"
    r"where\s+(?:should|can|do)\s+(?:I|we)\s+(?:eat|get|find|go|stay|park)"
    r"|where\s+to\s+(?:eat|go|get|stay|park)"
    r"|what(?:'s| is)\s+(?:good|open)\s+(?:around|near|nearby)"
    r")\b",
    re.IGNORECASE,
)

# Real-estate asks that need sale/rent/address clarified — not generic "places near me".
_AMBIGUOUS_NEARBY_SUBJECT = re.compile(
    r"\b(?:"
    r"house|houses|home|homes|property|properties|building|buildings"
    r"|apartment|apartments|condo|condos|flat|flats|unit|units"
    r")\b",
    re.IGNORECASE,
)

_QUALIFIED_NEARBY = re.compile(
    r"\b(?:"
    r"for\s+sale|to\s+(?:buy|rent|lease)|for\s+rent|rentals?|buying|leasing"
    r"|open\s+(?:now|today)|24\s*hours?"
    r"|near\s+\d|at\s+\d|from\s+\d|\d+\s+\w+\s+(?:st|street|ave|avenue|rd|road|blvd|dr|drive|way|ln|lane)\b"
    r")\b",
    re.IGNORECASE,
)

_PROXIMITY_PHRASES = (
    r"\bnear\s+me\b",
    r"\bnearby\b",
    r"\baround\s+here\b",
    r"\bin(?:\s+this)?\s+town\b",
    r"\bclose\s+(?:by|to\s+me)\b",
    r"\b(?:the\s+)?(?:nearest|closest)\b",
    r"\bbest\b",
)

_QUERY_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:can\s+you\s+)?(?:please\s+)?"
    r"(?:search(?:\s+the)?\s+web(?:\s+for)?|"
    r"look\s+up(?:\s+online)?(?:\s+for)?|"
    r"google(?:\s+for)?|"
    r"find(?:\s+online)?(?:\s+for)?)"
    r")\s*",
    re.IGNORECASE,
)

_STREET_SUFFIX = (
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Pl|Place|"
    r"Ct|Court|Sq|Square|Pkwy|Parkway)"
)
_ADDRESS_RE = re.compile(
    rf"\b(\d+\s+[\w\s.'#-]{{2,40}}{_STREET_SUFFIX}\b(?:,\s*[\w\s.'-]{{2,30}})?)",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"(?<![\w$])(\$\$\$|\$\$|\$)(?![\w$])")

_GENERIC_NEWS_QUERY = re.compile(
    r"^(?:"
    r"what(?:'s| is) (?:happening|going on|new)(?: in the world(?: today)?| in the news)?"
    r"|top (?:news|stories|headlines)"
    r"|news (?:today|this week|stories)"
    r"|(?:what(?:'s| is) )?(?:cookin(?:'|g)?(?: in the world)?|in the world(?: today)?)"
    r"|world news|current events"
    r")\s*[.!?]*$",
    re.IGNORECASE,
)

_NUMBERED_VENUE_LINE = re.compile(r"^\s*\d+\.\s+")


# A text or email the user is writing ("write a text to cancel my haircut at
# 2pm today") mentions times for its reader; it is not a question about the news.
_CORRESPONDENCE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:help\s+me\s+)?"
    r"(?:write|draft|compose|send|text|reply|respond)\b(?:\s+\w+){0,4}?\s+"
    r"(?:text|message|sms|email|e-mail|note|reply|dm|whatsapp|invite|invitation)\b",
    re.IGNORECASE,
)


# "Add a line saying the rent for this month is paid": an edit of a draft.
_DRAFT_EDIT = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:also\s+)?"
    r"(?:add|remove|delete|change|rewrite|reword|shorten|expand)\s+"
    r"(?:a|an|the|one|another|this|that|my)?\s*(?:[\w'-]+\s+){0,2}?"
    r"(?:line|sentence|paragraph|section|bullet|point|p\.?s\.?|greeting|signature"
    r"|subject|closing|opening|intro)s?\b",
    re.IGNORECASE,
)


def is_correspondence_request(text: str) -> bool:
    """True for "write a text / email / note …" or an edit of one: a draft, not a search."""
    return bool(_CORRESPONDENCE.search(text) or _DRAFT_EDIT.search(text))


# "scores = [78, 92]", "print(avg)", "add 25 + 38": a sum or code, never a search topic.
_MATH_OR_CODE = re.compile(
    r"=|\bprint\(|\bdef\s|\bfunction\s|\breturn\s|```|=>|\d\s*[+*/\u00d7\u00f7^]\s*\d"
    r"|\badd\s+\d+\s+(?:and|to|\+)\s+\d+",
    re.IGNORECASE,
)


def looks_like_math_or_code(text: str) -> bool:
    return bool(_MATH_OR_CODE.search(text))


# Word problems borrow live words ("today", "latest", "news", "score") but are
# solved on the page: "what day is it in 100 days", "every 3 days", "2, 6, 18,
# 54, …", "3/5 of the 450 students", "twice as many in the second half".
_WORD_PROBLEM = re.compile(
    r"\b(?:in|after)\s+\d+\s+(?:days?|weeks?|months?)\b"
    r"|\bevery\s+\d+\s+(?:days?|weeks?|hours?|minutes?)\b"
    r"|\bwhat\s+day\s+of\s+the\s+week\b"
    r"|\b\d+,\s+\d+,\s+\d+"
    r"|\b\d+\s*/\s*\d+\s+of\s+(?:the\s+)?\d"
    r"|\b(?:twice|half|(?:two|three|four|five|\d+)\s+times)\s+as\s+(?:many|much|long|fast|far)\b",
    re.IGNORECASE,
)


def is_word_problem(text: str) -> bool:
    return bool(_WORD_PROBLEM.search(text))
