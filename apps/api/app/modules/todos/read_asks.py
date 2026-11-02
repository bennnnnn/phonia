"""Whether a message asks what is saved, so the saved rows answer it.

Live (2026-10-25): "ok last thing, what's on my to do list right now?" and "hmm are you
sure? check my to-do list again" were answered by the model from the chat. It listed a
reminder whose card was never tapped, and left out the one saved for that evening. Only
"what are my reminders" and the like were read, and only at the very start of the
message. The app calls the list To-do: "to-do list", "to do list" and "todo list" are how
people name it, and each is read as one. A clause asks it when it is the read and
nothing more, but for when ("…right now", "…for tomorrow", "…at 3pm") and a word like
"again" or "please": "check my todo list app for bugs" asks about code. The clauses
beside it may only be chatter ("ok last thing, what's on…", "hmm are you sure? check
my…"): "Is Monday a holiday? what's on my schedule" keeps its holiday, and "what's on my
to-do list? push gym to friday" its move.
"""

from __future__ import annotations

import re

from app.modules.todos.spoken_change import prepare_words

_READ_OPENINGS = (
    "what reminders do i have",
    "what are my reminders",
    "what are my todos",
    "whats on my schedule",
    "what is on my schedule",
    "what is scheduled",
    "whats scheduled",
    "what do i have scheduled",
    "what do i have on my schedule",
    "do i have any reminders",
    "do i have reminders",
    "show my reminders",
    "show my schedule",
    "show me my reminders",
    "show me my schedule",
    "list my reminders",
    "list my todos",
    "list my schedule",
    "read my reminders",
    "read my schedule",
    "whats on my todo list",
    "what is on my todo list",
    "whats in my todo list",
    "what is in my todo list",
    "whats on my todos",
    "show my todo list",
    "show me my todo list",
    "show my todos",
    "show me my todos",
    "check my todo list",
    "check my todos",
    "check my reminders",
    "read my todo list",
    "read my todos",
    "list my todo list",
)
# Openings that do not say "my": a place after them is somewhere else's schedule.
_BARE_READS = frozenset({"what is scheduled", "whats scheduled"})
_ELSEWHERE = re.compile(
    r"\s+(?:at|in)\s+(?!\d|noon\b|midnight\b|the (?:morning|afternoon|evening)\b)"
)
# The list's names, as one: "to-do list", "to do list", "todo-list", "to-dos".
_LIST_NAME = re.compile(r"\bto[- ]do(?=s?\b)")
_LIST_DASH = re.compile(r"\btodo-(?=lists?\b)")
_CLAUSE = re.compile(r"(?:[,;:!?]|\.(?=\s))\s*|\s+(?:and|also)\s+|\s[\u2014\u2013-]\s")
_DAY = r"(?:to(?:day|night|morrow)|(?:mon|tues|wednes|thurs|fri|satur|sun)day|the weekend)"
# What may follow the read in its clause: when, and words that ask nothing more.
_READ_TAIL = re.compile(
    rf"(?:\s+(?:again|now|right now|so far|currently|at the moment|please|pls|then|real quick"
    rf"|{_DAY}|this (?:week|weekend|morning|afternoon|evening)|next week"
    rf"|(?:for|on) {_DAY}|for (?:this|next) week|in the (?:morning|afternoon|evening)"
    r"|at \d{1,2}(?::\d{2})?\s*(?:am|pm)?))*"
)
# The chatter a read may come with: "ok last thing", "hmm are you sure", "really?".
_ASIDE = re.compile(
    r"(?:(?:ok(?:ay)?|hmm+|so|well|wait|oh|hey|lol|haha|also|actually|please|thanks|thank you"
    r"|(?:one )?(?:more|last) thing|quick question|are you sure|really|seriously|again)\s*)+"
)


def asks_to_read_reminders(user_text: str | None) -> bool:
    """True when they asked what is saved, not to change it."""
    text = _folded(user_text)
    if not text:
        return False
    clauses = [_folded(part) for part in _CLAUSE.split(text)]
    clauses = [clause for clause in clauses if clause]
    reads = [clause for clause in clauses if _is_a_read(clause)]
    if not reads:
        return False
    return all(clause in reads or _ASIDE.fullmatch(clause) for clause in clauses)


def _folded(text: str | None) -> str:
    lowered = prepare_words(text).lower().replace("'", "").replace("\u2019", "")
    return _LIST_DASH.sub("todo ", _LIST_NAME.sub("todo", lowered))


def _is_a_read(clause: str) -> bool:
    for opening in _READ_OPENINGS:
        if clause.startswith(opening):
            rest = clause[len(opening) :]
            # "What's scheduled at the Hollywood Bowl" asks about a venue.
            if opening in _BARE_READS and _ELSEWHERE.match(rest):
                return False
            return _READ_TAIL.fullmatch(rest) is not None
    return False
