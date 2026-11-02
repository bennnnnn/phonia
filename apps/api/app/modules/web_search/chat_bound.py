"""A message that works on the chat itself: nothing on the web answers it.

In one study chat (2026-10-24) the reply's own ``web_search`` tool ran for three such
messages and wrapped each answer in pages it had nothing to do with:

- "Yes" to "Does that make sense? 😊" searched the word and asked about the band Yes;
- "sure give me a practice problem" attached pre-calculus PDFs and GED videos to a
  Charles's-law problem;
- "ok im done studying for today. can you summarize what we covered?" attached exam-tip
  videos to the recap.

Two shapes, each read whole so a live ask beside one still searches:

- an answer to the last reply's check ("Does that make sense?", "Ready for the next
  one?", "Want a practice problem?"), where a yes, a "got it" or "still confused" is
  about the chat. A yes to any other question, an offer to look something up included
  ("Want the full box score?"), is left to the search rules;
- a request whose last sentence asks the chat to make or redo something: a practice
  problem, another one, a quiz, a recap of what was covered, the last answer again.
  "One more question: what's the weather tomorrow?" and "walk me through the visa
  rules for Kenya" ask something else.
"""

from __future__ import annotations

import re

from app.modules.turn_reading.routing import is_short_confirmation
from app.modules.web_search.patterns import has_recency
from app.services.text_normalize import collapse_ws, straighten_apostrophes

_TAIL = 400
_MAX_ANSWER_WORDS = 6
# "yes please search", "sure, look it up": an answer that asks to go and find something.
_LOOKUP = re.compile(r"\b(?:search|look\s+(?:it\s+|that\s+)?up|google|browse|find\s+out)\b", re.I)
# The last reply's closing question checks the learner, or offers more of the lesson.
_CHECK = re.compile(
    r"\b(?:does|did|do)\s+(?:that|this|it|everything|all\s+(?:of\s+)?(?:that|this))\s+"
    r"(?:make\s+sense|help|click|clear\s+(?:it|things)\s+up)\b"
    r"|\bmakes?\s+sense\s*$"
    r"|\b(?:got|get|following|follow)\s+(?:it|that|this|me|along|so\s+far)\s*$"
    r"|\b(?:is|was)\s+(?:that|this|it|everything)\s+(?:clear|ok|okay|helpful)\b"
    r"|\b(?:clear|ok|okay|good)\s+so\s+far\s*$"
    r"|\bwith\s+me(?:\s+so\s+far)?\s*$"
    r"|\bready(?:\s+(?:for\s+(?:the\s+next\s+\w+|another\s+\w+|more|a\s+(?:quick\s+)?"
    r"(?:quiz|challenge))|to\s+(?:try|move\s+on|continue|practi[cs]e|go)(?:\s+\w+){0,3}))?\s*$"
    r"|\b(?:any|other|more)\s+questions\b"
    r"|\b(?:want|like|wanna)\s+to\s+(?:try|give\s+it\s+a\s+(?:try|go|shot)|practi[cs]e|"
    r"work\s+through|move\s+on|keep\s+going)\b"
    r"|\b(?:shall|should|can)\s+we\s+(?:move\s+on|continue|keep\s+going|go\s+on|try)\b"
    r"|\b(?:try|attempt)\s+(?:one|it|another|this|that)\s+(?:yourself|on\s+your\s+own)\b"
    r"|\bcheck\s+(?:your|the)\s+(?:answer|work|solution)\b"
    r"|\bcan\s+you\s+(?:find|solve|figure\s+out|work\s+out|calculate|spot|guess)\b"
    r"|\bwhat\s+do\s+you\s+think\b"
    # An offer of more from the chat: "Want me to give you a practice problem?"
    r"|\b(?:give|make|write|send|show)\s+(?:you\s+)?(?:an?\s+|another\s+|one\s+more\s+|some\s+"
    r"|a\s+few\s+|\d+\s+)?(?:(?:practice|quick|similar|harder|easier|new)\s+)?"
    r"(?:problems?|questions?|exercises?|examples?|quiz)\b"
    r"|\b(?:quiz|test)\s+you\b|\bwalk\s+you\s+through\s+(?:it|that|this|one|an?\s+example)\b"
    r"|\b(?:another|one\s+more)\s+(?:one|problem|question|example|round)\b",
    re.IGNORECASE,
)

# Leads a request may open with: "ok", "sure", "can you", "i want".
_LEAD = (
    r"(?:(?:ok(?:ay)?|sure|yes|yeah|yep|alright|cool|great|nice|now|and|so|then|please|pls|"
    r"lets|let's|can\s+you|could\s+you|would\s+you|will\s+you|can\s+i\s+(?:have|get)|"
    r"i\s+(?:want|need|would\s+like|'d\s+like|wanna)(?:\s+to\s+(?:try|do|see))?)[,!.]?\s+)*"
)
_COUNT = r"(?:(?:an?|another|one\s+more|some|a\s+few|\d+|more)\s+)?"
_KIND = r"(?:(?:practice|quick|similar|harder|easier|new|different|short)\s+)*"
_THING = r"(?:problems?|questions?|exercises?|examples?|quiz(?:zes)?|drills?)"
# "on this", "about that topic", "like the last one", "for me": the chat's own subject.
_ABOUT = r"(?:\s+(?:on|about|for|like|similar\s+to|with)(?:\s+[\w']+){1,5})?"
_REQUEST = re.compile(
    rf"{_LEAD}(?:"
    rf"(?:give|make|write|send|show|try|do|create|get)(?:\s+(?:me|us))?\s+{_COUNT}{_KIND}"
    rf"{_THING}{_ABOUT}"
    rf"|(?:give|send|show)\s+(?:me|us)\s+(?:another|one\s+more)(?:\s+one)?"
    rf"|{_COUNT}{_KIND}{_THING}{_ABOUT}"
    r"|(?:another|one\s+more)(?:\s+(?:one|problem|question|example|round))?"
    rf"|(?:quiz|test)\s+(?:me|us){_ABOUT}"
    r"|walk\s+(?:me|us)\s+through\s+(?:it|that|this|one|an?\s+example|the\s+(?:steps|solution|"
    r"problem|answer|example))(?:\s+again)?"
    r"|(?:summari[sz]e|recap|review|go\s+over)\s+(?:what|everything|all)\s+(?:that\s+)?(?:we|you|i)"
    r"(?:'ve|\s+have)?\s+(?:covered|discussed|talked\s+about|did|done|learned|went\s+over)"
    r"(?:\s+(?:today|so\s+far))?"
    r"|(?:summari[sz]e|recap)(?:\s+(?:it|that|this|everything))?"
    r"|(?:an?\s+)?(?:quick\s+)?(?:recap|summary)"
    r"|explain\s+(?:it|that|this)(?:\s+(?:again|more\s+simply|simpler|differently|slower|"
    r"step\s+by\s+step)){1,2}"
    r"|(?:make|say)\s+(?:it|that)\s+(?:simpler|shorter|easier)"
    r"|(?:repeat|say)\s+(?:the|that|your)\s+(?:last\s+)?(?:answer|step|part|problem|question)"
    r"(?:\s+again)?"
    # "… so i can review before thursday": why, not what.
    r")(?:\s+so\s+(?:that\s+)?(?:i|we)\s+(?:can|could)(?:\s+[\w']+){1,6})?"
    r"(?:\s+(?:please|pls|thanks|thx))?",
    re.IGNORECASE,
)
# A sentence ends at . ! ? : ; — "one more question: what's the weather?" is two.
_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+")
_TRAILING = re.compile(r"[^\w')]+$")


def _last_question(prior_assistant: str) -> str | None:
    """The last reply's closing question, without its ``?``."""
    tail = collapse_ws(straighten_apostrophes(prior_assistant))[-_TAIL:]
    end = tail.rfind("?")
    if end < 0:
        return None
    start = max(tail.rfind(mark, 0, end) for mark in ".!?:") + 1
    return tail[start:end].strip(" *_")


def ends_on_a_check(prior_assistant: str | None) -> bool:
    """True when the last reply closes on a check of the learner or an offer of more
    from the chat: "Does that make sense?", "Ready for the next one?", "Want to try
    one yourself?", "Want me to give you a practice problem?"."""
    question = _last_question(prior_assistant) if prior_assistant else None
    return bool(question) and _CHECK.search(question or "") is not None


def answers_a_check(text: str, prior_assistant: str | None) -> bool:
    """A yes, a "got it" or a short "still confused" to the last reply's check."""
    cleaned = collapse_ws(text)
    if not cleaned or "?" in cleaned or _LOOKUP.search(cleaned):
        return False
    if not ends_on_a_check(prior_assistant):
        return False
    return is_short_confirmation(cleaned) or len(cleaned.split()) <= _MAX_ANSWER_WORDS


def _is_request(sentence: str) -> bool:
    request = _TRAILING.sub("", sentence)
    return bool(request) and _REQUEST.fullmatch(request) is not None and not has_recency(request)


def works_from_the_chat(text: str) -> bool:
    """True when the message asks the chat to make or redo something and nothing else:
    its last sentence is such a request, and every other question in it is one too.
    "ok im done studying for today. can you summarize what we covered?" and "can you quiz
    me on gas laws? 3 quick questions" qualify; "one more question: what's the weather
    tomorrow?" does not."""
    sentences = _SENTENCE_END.split(straighten_apostrophes(collapse_ws(text)))
    if not _is_request(sentences[-1]):
        return False
    return not any(
        sentence.rstrip().endswith(("?", ":")) and not _is_request(sentence)
        for sentence in sentences[:-1]
    )
