"""Whether a named thing is out yet, or when it comes out: an ask whose answer is live.

"Is iPhone 19 out?" was answered from training data on 2026-10-23: "the current model
is the iPhone 16 (released in late 2024)". A release ask searches before the model
writes, and a product, a title or a model is what makes "out" a release: "is the power
out", "Is Tom out yet?" and "is the cake out" stay ordinary chat.

Match against ``collapse_ws``-normalized input (single spaces).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.web_search.live_asks import NOT_A_PRICE
from app.modules.web_search.patterns import collapse_ws

# "Is iPhone 19 out (yet)?", "has GTA 6 been released", "did season 5 drop", "when does
# Windows 12 come out", "when will the new Zelda be released". The thing is a group.
_OUT = r"(?:released|launched|announced|out|dropped|available|on sale)"
_RELEASE_ASK = re.compile(
    r"^(?:(?:so|wait|hey|btw|ok|okay|and)\s*,?\s+)?(?:"
    rf"(?:is|are|was|were) (?P<is>.{{2,48}}?) (?:already |finally |even )?{_OUT}"
    r"|(?:has|have) (?P<has>.{2,48}?) (?:been (?:released|launched|announced)|come out"
    r"|came out|dropped|launched|released)"
    r"|did (?P<did>.{2,48}?) (?:come out|drop|launch|release|get released)"
    r"|when (?:is|are|will|does|do|did|was|were) (?P<when>.{2,48}?) (?:(?:be |get )?"
    r"(?:released|launched|announced|out|available)|com(?:e|ing) out|came out"
    r"|drop(?:ping)?|launch(?:ing)?|releas(?:e|ing)|going to (?:come out|be released|drop"
    r"|launch))"
    r")(?: (?:on|in) [\w+ ]{2,20}?)?(?: (?:yet|already|now|yet or not))?[\s?!.]*$",
    re.IGNORECASE,
)
# "GTA 6 release date", "release date of the iPhone 19".
_RELEASE_DATE = re.compile(r"\b(?:release|launch) date\b", re.IGNORECASE)
# Words a release names: "the new Kendrick album", "Stranger Things season 5".
_RELEASE_NOUN = re.compile(
    r"\b(?:games?|movies?|films?|albums?|songs?|singles?|seasons?|episodes?|series|sequel"
    r"|trailer|updates?|versions?|models?|phones?|consoles?|books?|novels?|shows?|patch"
    r"|dlc|expansion|chapters?|manga|anime|mixtape|ios|android|macos|windows|iphone|ipad"
    r"|macbook|pixel|galaxy|playstation|xbox|switch|airpods|gpt|gemini|claude|llama)\b",
    re.IGNORECASE,
)
_NEW = re.compile(r"\b(?:new|next|upcoming)\b", re.IGNORECASE)
# A person, the user's own things or the world outside: "is my order out", "is the
# power out", "is it out yet" (the last reply's subject is the follow-up rule's).
_NOT_A_RELEASE = frozenset(
    {
        "it", "he", "she", "they", "you", "i", "we", "my", "your", "his", "her", "their",
        "our", "its", "this", "that", "there", "someone", "anyone", "everyone",
    }
)  # fmt: skip


def _names_a_release(thing: str) -> bool:
    """A product, a title or a model: a number, a release word, a name of two capitalized
    words ("Grand Theft Auto") or a new one ("the new Zelda"). One name alone may be a
    person ("is Tom out")."""
    words = thing.split()
    if not words or words[0].casefold() in _NOT_A_RELEASE:
        return False
    if any(char.isdigit() for char in thing) or _RELEASE_NOUN.search(thing):
        return True
    names = sum(1 for word in words if word[:1].isupper())
    # "The new Zelda", "the next Batman": one name is a title once it is new.
    return names >= 2 or (names == 1 and _NEW.search(thing) is not None)


def released_thing(text: str) -> str | None:
    """What a release question asks about ("iPhone 19" in "Is iPhone 19 out?"), else None."""
    cleaned = collapse_ws(text)
    match = _RELEASE_ASK.match(cleaned)
    if match is not None:
        thing = next(group for group in match.groups() if group)
        return thing if _names_a_release(thing) else None
    if _RELEASE_DATE.search(cleaned) is None or NOT_A_PRICE.search(cleaned) is not None:
        return None
    thing = _RELEASE_DATE.sub(" ", cleaned).strip(" ?!.")
    thing = re.sub(r"^(?:what(?:'s| is)\s+)?(?:the\s+)?|\s+(?:of|for)\s*$", "", thing).strip()
    thing = re.sub(r"^(?:of|for)\s+", "", thing)
    return thing if thing and _names_a_release(thing) else None


# A release ask inside a longer message. "Which chip does the iPhone 18 Pro Max have and
# when was it released?" was answered from training data on 2026-10-24 ("it hasn't been
# released yet"): the ask above has to be the whole message. Each clause is read alone,
# after a lead-in ("do you know", "can you tell me"); an ask inside a question keeps
# statement order ("if GTA 6 is out", "when the Galaxy S26 came out"); and "it" or "they"
# is a product the message names ("the Pixel 11, is it out yet?").
_CLAUSE_BREAK = re.compile(
    r"[?!;:]+\s*|\s+[\u2014\u2013-]+\s+|,?\s+(?:and|but|also)\s+|,\s+", re.IGNORECASE
)
_LEAD_IN = re.compile(
    r"^(?:(?:do|does) (?:you|anyone) know|(?:can|could) you (?:tell me|check|find out|look up)"
    r"|tell me|i(?:'m| am) wondering|i wonder|i was wondering|any idea|i want to know"
    r"|let me know)\s+",
    re.IGNORECASE,
)
_ASKED_ABOUT = re.compile(
    rf"^(?:(?:if|whether) (?P<if>.{{2,48}}?) (?:is|are|was|were|has been|have been) "
    rf"(?:already |finally )?{_OUT}"
    r"|(?:if|whether) (?P<has>.{2,48}?) (?:has|have) (?:come out|dropped|launched|been "
    r"(?:released|launched|announced))"
    r"|when (?P<came>.{2,48}?) (?:came|comes|will come|is coming) out"
    r"|when (?P<was>.{2,48}?) (?:was|were|is|are|will be) (?:released|launched|out|available)"
    r"|when (?P<did>.{2,48}?) (?:launched|dropped|released|launches|drops|releases))"
    r"(?: (?:yet|already|now))?$",
    re.IGNORECASE,
)
_PRONOUNS = frozenset({"it", "they"})
_BRAND = (
    r"iphone|ipad|pixel|galaxy|macbook|playstation|xbox|switch|airpods|windows|ios|android"
    r"|macos|gpt|gemini|claude|llama|gta"
)
# A named product: a brand, a name with a capital past its first letter ("iPhone", "GTA")
# or a capitalized word inside a sentence ("the Pixel"), then a model number within three
# words. "My phone is 2 years old" and "I have 2 dogs" name none.
_PRODUCT = re.compile(
    rf"(?:\b(?i:{_BRAND})\b|\b(?:[a-z]+[A-Z]|[A-Z][\w+-]*[A-Z])[\w+-]*|(?<=[\w,] )[A-Z][a-z][\w+-]*)"
    r"(?:[ -][\w+-]+){0,2}?[ -][\w.+-]*\d[\w.+-]*"
    r"(?i:\s+(?:pro|max|plus|ultra|mini|air|fold|flip|lite|fe|xl|edge|neo|e)\b)*"
)
# "And" left at a clause's start once "?" ended the one before: "…out? and how much".
_JOINER = re.compile(r"^(?:and|but|also|so|then)\s+", re.IGNORECASE)
# "if GTA 6 is out yet" searches as "GTA 6 is out yet".
_IF = re.compile(r"^(?:if|whether)\s+", re.IGNORECASE)
# A clause that asks something, once its lead-in is gone: "how much will it cost".
_QUESTION = re.compile(
    r"^(?:what|what's|which|who|whose|where|why|how|when|is|are|was|were|do|does|did|can"
    r"|could|will|would|should|has|have|any)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ClauseAsk:
    # The ask, its lead-in gone: "is it out yet", "when the Galaxy S26 came out".
    clause: str
    # What it asks about: the thing it names, or the product its "it" stands for.
    thing: str
    pronoun: str | None
    # Another clause asks something too ("…and how much will it cost?").
    more_asked: bool


def _clause_ask(cleaned: str) -> _ClauseAsk | None:
    clauses = [
        _LEAD_IN.sub("", _JOINER.sub("", part.strip(" ,.")))
        for part in _CLAUSE_BREAK.split(cleaned)
    ]
    clauses = [clause for clause in clauses if clause]
    for index, clause in enumerate(clauses):
        match = _RELEASE_ASK.match(clause) or _ASKED_ABOUT.match(clause)
        if match is None:
            continue
        thing = next(group for group in match.groups() if group)
        pronoun: str | None = None
        if not _names_a_release(thing):
            product = _PRODUCT.search(cleaned)
            if thing.casefold() not in _PRONOUNS or product is None:
                continue
            thing, pronoun = product.group(0), thing
        others = clauses[:index] + clauses[index + 1 :]
        more = any(_QUESTION.match(other) for other in others)
        return _ClauseAsk(clause, thing, pronoun, more)
    return None


def asks_if_released(text: str) -> bool:
    """Whether a named thing is out yet, or when it comes out: "Is iPhone 19 out?", also
    inside a longer message ("…and when was it released?")."""
    cleaned = collapse_ws(text)
    return released_thing(cleaned) is not None or _clause_ask(cleaned) is not None


def release_search_query(text: str) -> str | None:
    """The search for a release ask inside chatter: "is Pixel 11 out yet".

    "I'm thinking of getting the Pixel 11, is it out yet?" searched its own words and found
    a company called Thinking Pixel and the launch-day post, and replies said the phone was
    "available for pre-order". The ask alone, its "it" named, found Wikipedia and the date
    it went on sale. A message that is only the ask is its own query already, and one that
    asks more ("which chip does it have and when was it released?") keeps every question.
    """
    cleaned = collapse_ws(text)
    if released_thing(cleaned) is not None:
        return None
    ask = _clause_ask(cleaned)
    if ask is None or ask.more_asked:
        return None
    clause = _IF.sub("", ask.clause)
    if ask.pronoun is not None:
        return re.sub(rf"\b{ask.pronoun}\b", ask.thing, clause, count=1, flags=re.IGNORECASE)
    # "When is season 3 coming out" alone loses whose season ("I loved Severance season 2,
    # …"): only an ask that names its product by name searches without the rest.
    named = _PRODUCT.search(ask.thing) or any(char.isupper() for char in ask.thing)
    return clause if named else None
