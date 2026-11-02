"""Multi-step rate word problems: the everyday questions that need a thinking pass.

"A train leaves at 3pm at 80 km/h, another at 4pm at 120 km/h; when does the
second catch the first?" names no solver and no hard keyword, so it stayed on
the fast lane. With thinking off, the smart model answered it wrong every time
(7pm, 320 km instead of 6pm, 240 km). These problems need two steps: a gap,
then a closing rate. A one-step d = vt question stays fast.

The test needs all three: a pursuit, meeting, current or joint-work cue; two
numbers; and a rate (km/h, per hour) or a job filled or finished. "Let's meet at
3pm, I have 2 meetings" has no rate, so it stays an errand. Working "alone" is
one worker, not a joint-work problem: "I work alone 2 hours at $30 per hour".
"""

from __future__ import annotations

import re

_CUE = re.compile(
    r"\b(?:catch(?:es|ing)?\s+up|catch(?:es)?\s+(?:the|her|him|them|it)|overtak(?:e|es|ing)"
    r"|meets?\b|meeting\s+point|head\s+start|towards?\s+each\s+other"
    r"|opposite\s+directions?|same\s+direction|upstream|downstream"
    r"|(?:against|with)\s+the\s+current|working\s+together|together)\b",
    re.IGNORECASE,
)
_RATE = re.compile(
    r"\b(?:km\s*/\s*h|kmh|kph|mph|m\s*/\s*s|knots?|(?:km|miles?|kilomet(?:er|re)s?)\s+per\s+hour"
    r"|per\s+(?:hour|minute)|an\s+hour)\b"
    # "24 km in 3 hours" states a speed without writing one.
    r"|\d\s*(?:km|kilomet(?:er|re)s?|miles?|mi|m)\b[^.?!]{0,30}?\bin\s+\d+(?:\.\d+)?\s*"
    r"(?:hours?|hrs?|h|minutes?|mins?)\b",
    re.IGNORECASE,
)
_JOB_VERB = (
    r"(?:fill(?:s|ed)?|empt(?:y|ies|ied)|drain(?:s|ed)?|finish(?:es|ed)?|complete(?:s|d)?"
    r"|paint(?:s|ed)?|build(?:s)?|built)"
)
_JOB_OBJECT = r"(?:tank|pool|job|work|task|wall|house|field|room|fence)"
# "fills the tank" and the passive "a tank is filled by one pipe in 3 hours".
_JOB = re.compile(
    rf"\b{_JOB_VERB}\b[^.?!]{{0,40}}\b{_JOB_OBJECT}\b|\b{_JOB_OBJECT}\b[^.?!]{{0,40}}\b{_JOB_VERB}\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ASK = re.compile(
    r"\?|\b(?:when|how\s+(?:long|far|fast|many|much)|what\s+time|where|find|calculate)\b",
    re.IGNORECASE,
)
_ERRAND = re.compile(r"\b(?:remind|reminder|schedule|calendar)\b", re.IGNORECASE)


def is_multi_step_rate_problem(content: str) -> bool:
    """True for a pursuit, meeting, current or joint-work question with its numbers."""
    if len(_NUMBER.findall(content)) < 2 or _ERRAND.search(content):
        return False
    if _CUE.search(content) is None or _ASK.search(content) is None:
        return False
    return _RATE.search(content) is not None or _JOB.search(content) is not None
