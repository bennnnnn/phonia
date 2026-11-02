"""Whether a message asks for practice questions."""

from __future__ import annotations

import re

_PRACTICE_NOUN = (
    r"(?:quiz(?:zes)?|flash\s?cards?|true[\s/-]+(?:or[\s-]+)?false|multiple[\s-]+choice|mcqs?)"
)


# "Give me a quick geography quiz": the quiz is what they asked for. "Give me tips for
# my quiz" and "make sure I pass my quiz" name one they already have.
_PRACTICE_ASK = re.compile(
    r"(?:"
    r"\b(?:quiz|test)\s+me\b|"
    r"\b(?:make|give|create|write|generate|build|prepare|do|run)\s+(?:(?:me|us)\s+)?"
    r"(?:(?:a|an|the|some|another|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"\d+[\s-]questions?|\d+|few|quick|short|pop|small|little|fun|simple|hard|easy|tricky|"
    r"practice|review|new|more)\s+){0,3}"
    r"(?:(?!(?:my|our|your|his|her|their|for|to|about|on|of|in|with|sure|i|me)\b)"
    r"[a-z]+\s+){0,2}" + _PRACTICE_NOUN + r"\b|"
    r"^\s*(?:some\s+)?flash\s?cards?\s+(?:on|about|for)\b|"
    r"\btrue[\s/-]+(?:or[\s-]+)?false\s+questions?\b|"
    r"\bmultiple[\s-]+choice\s+questions?\b"
    r")",
    re.IGNORECASE,
)


# Asked how, asked for the answers in the text (a teacher's answer key), or asked to
# build something that runs quizzes ("a quiz app in React").
_NOT_CARDS = re.compile(
    r"\bhow\s+(?:to|(?:do|can|should)\s+(?:i|you|we))\b|"
    r"\banswer\s+key\b|"
    r"\bwith\s+(?:the\s+)?(?:answers|solutions)\b|"
    r"\b(?:quiz(?:zes)?|flash\s?cards?|trivia)\s+(?:app|apps|game|site|website|page|"
    r"component|form|bot|feature|night|show|maker|generator)\b",
    re.IGNORECASE,
)


def is_practice_request(text: str) -> bool:
    """True for "quiz me on X", "make flashcards for Y", "5 true/false questions about Z"."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 400:
        return False
    return _PRACTICE_ASK.search(cleaned) is not None and _NOT_CARDS.search(cleaned) is None
