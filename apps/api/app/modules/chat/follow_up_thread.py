"""Which subject problem a line follows up on.

"Why do we divide distance by time?" names no subject itself; it belongs to the bike
problem a line or two back. Any question within three user lines continues the problem,
with one exception. Live (2026-10-25), "cool. i'm going to lisbon next month for 4 days,
what should i not miss?" two lines after a rectangle problem got "What if perimeter was
48 cm?" under its travel tips. A line that names a topic of its own (three topic words or
more) and points nowhere back ("it", "that", "same", "what if", "why?", "again", "more
simply") must have a reply that still works the problem (``follow_up_ground``). A follow-up
the chat showed and the user tapped, a line that points back and a short line continue it,
as before: a missed new topic shows odd questions, a lost follow-up shows none. A read of
the user's To-do list follows up on nothing (``related_questions``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.chat.continuation_subject import (
    BIOLOGY_CUES,
    is_new_problem_request,
    is_pure_continuation,
)
from app.modules.chat.follow_up_ground import works_the_problem
from app.modules.chat.follow_up_words import topic_words
from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.services.problem_followup import message_role_content
from app.services.subjects.dispatch import detect_subject
from app.services.text_normalize import collapse_ws, straighten_apostrophes

# A follow-up ("why?") belongs to a problem a few user lines back; further is stale.
_THREAD_USER_TURNS = 3
_FOLLOW_UP_LEADS = frozenset(
    {
        "why",
        "how",
        "what",
        "when",
        "where",
        "which",
        "can",
        "could",
        "is",
        "are",
        "does",
        "do",
        "explain",
        "show",
        "give",
        "try",
        "solve",
        "find",
        "and",
        "but",
        "so",
        "if",
    }
)
# A line that points back at the problem: "what if", "why?", "is that fast for a car?",
# "what if i used a ramp instead?", "can you explain it more simply?". A question about
# the reasoning does too: "why must temperatures be in kelvin for gas laws?", "how come
# it's squared?", "what does the negative sign tell us?". "This week" and "that night"
# point at a time, not at the problem.
_POINTS_BACK = re.compile(
    r"^(?:what|and) if\b|^(?:why|how come)\b|"
    r"^what (?:does|do)\b.*\b(?:mean|tell|show|represent|stand for)\b|"
    r"\b(?:it|its|they|them|their|same|instead|again|another|simpler|simply)\b|"
    r"\b(?:this|that|these|those)\b(?!\s+(?:week|weekend|morning|afternoon|evening|night|"
    r"year|month|summer|winter|spring|fall)\b)",
    re.IGNORECASE,
)
# Three topic words name a topic of their own; "why the product rule?" names a part of it.
_OWN_TOPIC_WORDS = 3
# English function words. The topic-word rules are English: "¿por qué restamos tres en los
# dos lados?" holds four words that are no topic, and a reply in Spanish shares no English
# word with the problem. A line without one keeps the rule that came before: it continues.
_ENGLISH = re.compile(
    r"\b(?:the|and|of|to|you|your|my|it|what|why|how|when|where|which|who|does|did|can|"
    r"could|would|should|this|that|with|for|are|is)\b",
    re.IGNORECASE,
)


def subject_for_related(text: str) -> str | None:
    """Math, physics, chemistry, or biology. Anything else is skipped."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return None
    detected = detect_subject(cleaned)
    if detected is not None:
        return detected
    lowered = cleaned.casefold()
    if any(cue in lowered for cue in BIOLOGY_CUES):
        return "biology"
    return None


def _continues_thread(text: str) -> bool:
    """A question or a "one more" about the open problem, not small talk."""
    cleaned = collapse_ws(text)
    if not cleaned or is_lightweight_chat_turn(cleaned):
        return False
    if is_pure_continuation(cleaned) or is_new_problem_request(cleaned):
        return True
    words = cleaned.casefold().split()
    return cleaned.endswith("?") or (bool(words) and words[0].strip(",.") in _FOLLOW_UP_LEADS)


def thread_problem(
    question: str,
    prior: Sequence[Any] | None,
    answer: str | None = None,
    shown: Sequence[str] | None = (),
) -> str | None:
    """The subject problem this line follows up on, or None.

    "Why do we divide distance by time?" names no subject itself, so the
    follow-ups would stop after the first tapped "why". It still belongs to
    the bike problem two lines back. Given the turn's ``answer`` and the
    follow-ups the chat ``shown`` (None while they are not known), a line on a
    topic of its own needs a reply that still works the problem: travel tips
    under a Lisbon question do not, nor does a line after them.
    """
    if subject_for_related(question) is not None:
        return question
    if not prior or not _continues_thread(question):
        return None
    since: list[tuple[str, str]] = []
    users = 0
    for message in reversed(prior):
        role, content = message_role_content(message)
        if role not in ("user", "assistant") or not content or not content.strip():
            continue
        if role == "user":
            users += 1
            if users > _THREAD_USER_TURNS:
                return None
            if subject_for_related(content) is not None:
                turn = (question, answer)
                return content if _still_on(content, since[::-1], turn, shown) else None
        since.append((role, content))
    return None


def _still_on(
    problem: str,
    since: list[tuple[str, str]],
    turn: tuple[str, str | None],
    shown: Sequence[str] | None,
) -> bool:
    """Whether this turn still works ``problem``. ``since`` is the chat after it, oldest
    first. A tapped follow-up and a line that points back continue it. Otherwise, once a
    question in between names its own topic and its reply leaves the problem, the turn's
    own reply must work it, however short the line ("what about the food there?" after
    Lisbon tips). A remark in between ("she says thanks!") asks nothing and leaves
    nothing."""
    question, answer = turn
    if answer is None or shown is None or _follows_on(question, shown):
        return True
    reply = since[0][1] if since and since[0][0] == "assistant" else None
    left = any(
        _continues_thread(line)
        and _names_its_own_topic(line, shown)
        and not works_the_problem(problem, reply, line, said)
        for line, said in _turns(since[1:] if reply is not None else since)
    )
    if left or _names_its_own_topic(question, shown):
        return works_the_problem(problem, reply, question, answer)
    return True


def _turns(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Each user line with the reply after it."""
    turns: list[tuple[str, str]] = []
    for role, content in messages:
        if role == "user":
            turns.append((content, ""))
        elif turns and not turns[-1][1]:
            turns[-1] = (turns[-1][0], content)
    return turns


def _names_its_own_topic(question: str, shown: Sequence[str]) -> bool:
    """An English line with three topic words or more that does not follow on."""
    line = straighten_apostrophes(collapse_ws(question))
    if _follows_on(line, shown) or not _ENGLISH.search(line):
        return False
    return len(topic_words(line)) >= _OWN_TOPIC_WORDS


def _follows_on(question: str, shown: Sequence[str]) -> bool:
    """A follow-up the chat showed (written for the problem), or a line that points back."""
    line = straighten_apostrophes(collapse_ws(question))
    if line.casefold() in {straighten_apostrophes(collapse_ws(q)).casefold() for q in shown}:
        return True
    return _POINTS_BACK.search(line) is not None
