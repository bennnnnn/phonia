"""Whether a message is about the user's own life: a disclosure, a personal or career
question, an earlier conversation it recalls (structure ticket ST-04)."""

from __future__ import annotations

import re

from app.modules.turn_reading.locale_cues import has_any_personal_locale_cue, has_locale_cue
from app.modules.turn_reading.routing import is_broad_self_question, is_lightweight_chat_turn
from app.modules.turn_reading.stuck import stuck_on_a_topic
from app.modules.turn_reading.writing_kind import is_email_or_message_request
from app.services.text_normalize import collapse_ws, straighten_apostrophes

# Opt-in cues for loading memory / todos / projects.
# Default is fast (no personal context) — do not grow a greeting allowlist.
_PERSONAL_CONTEXT_CUE = re.compile(
    r"(?:"
    r"\b(?:"
    r"remember|recall|you (?:know|remember)|what do you know|"
    r"don'?t forget|keep in mind|"
    r"we (?:talked|discussed|decided)|last time|"
    r"earlier (?:you|we)|from (?:my|our) (?:last|previous)|"
    r"what was that thing|that thing we (?:talked|discussed|mentioned)"
    r")\b|"
    r"\b(?:about me|tell me about (?:me|myself))\b|"
    r"\bmy\s+(?:"
    r"name|email|preference|preferences|diet|routine|schedule|"
    r"calendar|wife|husband|kids?|dog|cat|job|work|boss|team|"
    r"project|projects|todo|todos|list|lists|reminder|reminders|"
    r"allerg(?:y|ies)|favorite|usual|memory|memories"
    r")\b"
    r")",
    re.IGNORECASE,
)


# Continuity asks that should still search earlier chats on a slim turn.
# Phrase scan (not a regex) so a longer question cannot blow up matching.
_EARLIER_CONVERSATION_PHRASES = (
    "did we",
    "didn't we",
    "didnt we",
    "we pick",
    "we chose",
    "we picked",
    "we decided",
    "we said",
    "we talked",
    "we were talking",
    "last year",
    "last month",
    "last week",
    "last time",
    "what did i say",
    "what did i tell",
    "what did i choose",
    "what did we talk",
    "what did we decide",
    "didn't i mention",
    "didnt i mention",
    "didn't i tell",
    "didnt i tell",
    "didn't i say",
    "didnt i say",
    "did i mention",
    "what were we talking",
    "what were we discussing",
    "which one did i",
    "which one did we",
    "where we left off",
    "pick up from where",
    "continue where we",
    "you know the thing",
    "the thing i told you",
    "what was my idea",
    "what was that idea",
    "i told you about",
    "as i said",
    "like i said",
    "talking about yesterday",
)


def _phrase_at_word_boundary(text: str, phrase: str) -> bool:
    """True when ``phrase`` occurs with a non-letter on each side."""
    start = 0
    while True:
        found = text.find(phrase, start)
        if found < 0:
            return False
        before = found == 0 or not text[found - 1].isalnum()
        end = found + len(phrase)
        after = end == len(text) or not text[end].isalnum()
        if before and after:
            return True
        start = found + 1


def recalls_earlier_conversation(text: str) -> bool:
    """True when the user is asking about something said in an earlier chat."""
    cleaned = collapse_ws(text).lower()
    if not cleaned:
        return False
    return any(
        _phrase_at_word_boundary(cleaned, phrase) for phrase in _EARLIER_CONVERSATION_PHRASES
    )


def needs_rich_context(
    text: str,
    *,
    day_planning: bool = False,
    day_reflection: bool = False,
) -> bool:
    """True when this turn should load personal context (memory/todos).

    Systemic default: casual chat is slim. Opt in via personal/retrieval cues
    or day-planning — not via an ever-growing greeting list.
    Callers may OR in the to-do classifier from ``turn_prep.mode``.
    """
    if day_planning or day_reflection:
        return True
    if is_lightweight_chat_turn(text):
        return False
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    if is_broad_self_question(cleaned):
        return True
    # Direct drafts can benefit from names/relationships in memory. Generic
    # prose, proofreading, and translation should stay on the snappy slim
    # path rather than loading the user's private context without a reason.
    if is_email_or_message_request(cleaned):
        return True
    if has_any_personal_locale_cue(cleaned):
        return True
    return bool(_PERSONAL_CONTEXT_CUE.search(cleaned))


# Advice / recommendation — load memory only (not to-dos).
# Require a life-domain word so "what should I return" / "recommend a library"
# stay slim. Day-planning is classified separately and supersedes this path.
# Ordinary phrasing ("I need dinner", "plan a workout") must match too — not
# only "recommend" / "what should I".
_ADVICE_INTENT = re.compile(
    r"\b("
    r"recommend(?:ation)?s?|suggest(?:ion)?s?|"
    r"any ideas|ideas for|help me (?:choose|pick|decide)|"
    r"what should i|where should i|what(?:'s| is) for|"
    r"(?:can|could|should|may) i (?:eat|drink|wear|try|do|have)|"
    r"what to (?:eat|cook|wear|watch|get|buy|order|drink)|"
    r"pick (?:a |an )|"
    r"i(?:'m| am) (?:hungry|starving)"
    r")\b",
    re.IGNORECASE,
)


_ADVICE_DOMAIN = re.compile(
    r"\b("
    r"drink|coffee|tea|"
    r"eat|eating|cook|cooking|dinner|lunch|breakfast|brunch|"
    r"food|restaurant|recipe|meal|hungry|starving|snack|"
    r"wear|outfit|clothes|clothing|"
    r"movie|film|show|series|watch|"
    r"listen|playlist|song|music|"
    r"workout|exercise|gym|"
    r"gift|present"
    r")\b",
    re.IGNORECASE,
)


_ADVICE_STANDALONE = re.compile(
    r"\b("
    r"what(?:'s| is) for (?:dinner|lunch|breakfast|brunch)|"
    r"(?:dinner|lunch|breakfast) ideas|"
    r"i(?:'m| am) (?:hungry|starving)"
    r")\b",
    re.IGNORECASE,
)


_ADVICE_PROGRAMMING = re.compile(
    r"("
    r"\brecommend (?:a |an )?(?:\w+ )?library\b|"
    r"\bwhat should i return\b|"
    r"\b(function|typescript|javascript|codebase|npm |pip install|"
    r"api endpoint|react native)\b"
    r")",
    re.IGNORECASE,
)


# Need/plan path. Omit show/watch so "I need to show you this" stays slim.
# Do not use a bare "for me" cue — it pairs with any later/earlier domain word
# ("summarize this movie review for me").
_ADVICE_NEED_PLAN = re.compile(
    r"\b("
    r"i need|i want|"
    r"need (?:a |an |some )|"
    r"want (?:a |an )|"
    r"plan (?:a |an |my )|"
    r"help me plan|"
    r"(?:make|create|build|design) (?:me |my )|"
    r"quick dinner|easy dinner|"
    r"dinner tonight|lunch tonight|breakfast tonight"
    r")\b",
    re.IGNORECASE,
)


_ADVICE_NEED_DOMAIN = re.compile(
    r"\b("
    r"eat|eating|cook|cooking|dinner|lunch|breakfast|brunch|"
    r"food|restaurant|recipe|meal|hungry|starving|snack|"
    r"wear|outfit|clothes|clothing|"
    r"movie|film|series|"
    r"playlist|song|music|"
    r"workout|exercise|gym|"
    r"gift|present"
    r")\b",
    re.IGNORECASE,
)


# Domain must sit in the same short clause as the need/plan cue.
_ADVICE_NEED_LOOKBEHIND = 12


_ADVICE_NEED_LOOKAHEAD = 48


_ADVICE_NEED_NEGATION_TAILS = (
    "don't ",
    "dont ",
    "do not ",
    "doesn't ",
    "doesnt ",
    "never ",
    "won't ",
    "wont ",
    "can't ",
    "cant ",
    "cannot ",
)


def _advice_need_plan_with_domain(cleaned: str) -> bool:
    """True when a need/plan cue and a life-domain word share a short span.

    Independent whole-message searches treated “summarize this movie review
    for me” and “I don't need a workout” as advice.
    """
    plan = _ADVICE_NEED_PLAN.search(cleaned)
    if plan is None:
        return False
    prefix = cleaned[: plan.start()].lower()
    if any(prefix.endswith(tail) for tail in _ADVICE_NEED_NEGATION_TAILS):
        return False
    start = max(0, plan.start() - _ADVICE_NEED_LOOKBEHIND)
    end = min(len(cleaned), plan.end() + _ADVICE_NEED_LOOKAHEAD)
    return bool(_ADVICE_NEED_DOMAIN.search(cleaned[start:end]))


_CAREER_PERSONAL = re.compile(
    r"\b(?:my career|my job|my work|career advice|job interview|interviews?|"
    r"resume|résumé|\bcv\b|cover letters?|promotion|workplace)\b",
    re.IGNORECASE,
)


def is_career_personal_question(text: str) -> bool:
    """True when the ask is about their work, so a known job should shape the answer."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    return bool(_CAREER_PERSONAL.search(cleaned))


def is_personal_advice_question(text: str) -> bool:
    """True for recommendation / 'what should I eat' / 'plan a workout' turns.

    Does not imply full rich context. Callers load memory only.
    """
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    if _ADVICE_PROGRAMMING.search(cleaned):
        return False
    if has_locale_cue(cleaned, "advice"):
        return True
    if _ADVICE_STANDALONE.search(cleaned):
        return True
    if _advice_need_plan_with_domain(cleaned):
        return True
    return bool(_ADVICE_INTENT.search(cleaned) and _ADVICE_DOMAIN.search(cleaned))


_PERSONAL_DISCLOSURE_PREFIXES = (
    "i'm ",
    "i\u2019m ",
    "i am ",
    "i work ",
    "i currently ",
    "i have ",
    "i prefer ",
    "i like ",
    "i love ",
    "i dislike ",
    "i use ",
    "i live ",
    "i study ",
    "i learn ",
    "i got ",
    "i started ",
    "i moved ",
    "i finished ",
    "i decided ",
    "my ",
    "remember that ",
    "remember this ",
    "please remember ",
    "don't forget ",
    "do not forget ",
)


_PERSONAL_REQUEST_MARKERS = (
    " can you ",
    " could you ",
    " would you ",
    " will you ",
    " should i ",
    " help me ",
    " tell me ",
    " give me ",
    " find ",
    " search ",
    " look up ",
    " write ",
    " draft ",
    " compose ",
    " email ",
    " message ",
    " text ",
    " reply ",
    " rewrite ",
    " create ",
    " make ",
    " build ",
    " show ",
    " explain ",
    " plan ",
    " compare ",
    " recommend ",
    " advise ",
    " advice ",
    " what ",
    " how ",
    " why ",
    " when ",
    " where ",
    " which ",
    " who ",
    " latest ",
    " news ",
    " need ",
    " needs ",
    " looking for ",
)


_COLLECTIVE_DISCLOSURE = re.compile(
    r"^(?:"
    r"we\s+(?:work|live|study|learn|prefer|like|love|dislike|use|moved|started|finished|decided)\b|"
    r"we\s+are\s+(?:based|employed|living|working|studying|learning|moving)\b|"
    r"we(?:'|\u2019)re\s+(?:based|employed|living|working|studying|learning|moving)\b"
    r")",
    re.IGNORECASE,
)


def is_personal_disclosure_turn(text: str) -> bool:
    """True for a first-person fact/goal asking nothing; a topic they're stuck on asks."""
    cleaned = straighten_apostrophes(collapse_ws(text)).casefold()
    if not cleaned or "?" in cleaned or stuck_on_a_topic(cleaned):
        return False
    if not cleaned.startswith(_PERSONAL_DISCLOSURE_PREFIXES) and not _COLLECTIVE_DISCLOSURE.match(
        cleaned
    ):
        return False
    padded = " " + re.sub(r"[^\w']+", " ", cleaned) + " "
    return not any(marker in padded for marker in _PERSONAL_REQUEST_MARKERS)
