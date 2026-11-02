"""A maths question after a few words of chat: "ok cool. what is 2+2".

The readers take the whole message, so the chat before a question kept it from the
solver: "lol got the second one wrong. random but whats 72 fahrenheit in celsius" and
"random question but what is 2+2" went to the model unchecked. Sentences before it that
hold no given are chat, so the question is the last sentence, without "random but",
"btw" or "ok cool". A digit before it may be a given ("x = 3. What is 2x + 1?"), and so is
a sentence naming a die, coin, deck or bag ("An eight-sided die is rolled."): a reader of
the question alone would assume the fair one, so then nothing is dropped.
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_CHAT_LEAD = re.compile(
    r"^(?:(?:lol|lmao|haha|ha|ok(?:ay)?|cool|nice|so|and|also|anyway|btw|by\s+the\s+way|hey|"
    r"hmm|oh|wait|alright|random(?:\s+question)?|quick\s+question|unrelated|"
    r"different\s+question|one\s+more|another\s+one)\s*[,:!.]?\s*(?:but\s+)?)+",
    re.IGNORECASE,
)

# The chance devices the probability readers assume when the question names none: a fair
# six-sided die, a fair coin, a standard deck, a bag of balls, a spinner. A sentence that
# names one sets the question up ("An eight-sided die is rolled.", "A biased coin is
# tossed."), so it is never dropped as chat; "The homework is due Friday." still is.
_CHANCE_SETUP = re.compile(
    r"\b(?:dice|die|coins?|cards?|decks?|bags?|box(?:es)?|urns?|jars?|balls?|marbles?"
    r"|spinners?)\b",
    re.IGNORECASE,
)


def question_after_chat(text: str) -> str | None:
    """The question after the chat before it, or None when nothing was chat."""
    cleaned = " ".join(text.split())
    sentences = [part for part in _SENTENCE_END.split(cleaned) if part]
    if not sentences:
        return None
    *before, last = sentences
    if any(char.isdigit() for sentence in before for char in sentence):
        return None
    if any(_CHANCE_SETUP.search(sentence) for sentence in before):
        return None
    question = _CHAT_LEAD.sub("", last).strip()
    if not question or question == cleaned:
        return None
    return question
