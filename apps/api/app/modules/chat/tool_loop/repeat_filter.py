"""The answer after a reply's search never opens by repeating what came before it.

"Purecart" (live chat): the reply's first call wrote "Thanks, Dev. I'll look into
Purecart now.", called ``web_search``, and the call that answered from the results
opened "Thanks, Dev." again, so the saved reply greeted the user twice. The second
call reads the first call's text as its own turn, yet models still restate it.

Its opening is held while it may be such a repeat: a sentence the text before the
search already holds (the same words, whatever the case and punctuation) is dropped,
and the first sentence that is new lets everything through. A reply that starts new
waits only for its first word. The phone never draws a dropped sentence, so the saved
reply is the text it drew.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, AsyncIterator

# A sentence ends at ".", "!" or "?" (past a closing quote, bracket or bold) before a
# space, or at a line break.
_SENTENCE_END = re.compile(r"[.!?][\"')\]*_]*(?=\s)|\n")
_NOT_A_WORD = re.compile(r"[\W_]+")
# A heading, list item, quote or table row is the reply's shape, not a sentence it said:
# "1." or "## Purecart" opening the answer is the answer's own.
_STRUCTURE = re.compile(r"\s*(?:#{1,6}\s|[-*+>]\s|\d+[.)](?:\s|$)|\|)")
# A one-word sentence repeats only as an interjection ("Sure!", "Okay."), not "Dr.".
_MIN_LONE_WORD = 4


def _key(text: str) -> str:
    """The sentence's words: "**Thanks, Dev!**" and "thanks dev." are one sentence."""
    return _NOT_A_WORD.sub(" ", text.casefold()).strip()


def _counts(sentence: str) -> bool:
    """A sentence whose repeat is a repeat: words, not a list marker or an abbreviation."""
    if _STRUCTURE.match(sentence):
        return False
    words = _key(sentence).split()
    if len(words) >= 2:
        return not all(word.isdigit() for word in words)
    if len(words) != 1 or not words[0].isalpha():
        return False
    return len(words[0]) >= _MIN_LONE_WORD or sentence.rstrip(" *_\n").endswith(("!", "?"))


def _sentences(text: str) -> set[str]:
    pieces: list[str] = []
    start = 0
    for end in _SENTENCE_END.finditer(text):
        pieces.append(text[start : end.end()])
        start = end.end()
    pieces.append(text[start:])
    return {_key(piece) for piece in (p.lstrip() for p in pieces) if _counts(piece)}


class RepeatFilter:
    """Holds an answer's opening until it says something the text before did not."""

    def __init__(self, before: str) -> None:
        self._said = _sentences(before)
        self._held = ""
        self._dropped = False
        self._open = not self._said

    def feed(self, token: str) -> str:
        """What may go out now; "" while the opening may still be a repeat."""
        if self._open:
            return token
        self._held += token
        return self._settle(final=False)

    def flush(self) -> str:
        """The end of the answer: what it held goes out, unless it was a repeat."""
        return "" if self._open else self._settle(final=True)

    def _settle(self, *, final: bool) -> str:
        while True:
            body = self._held.lstrip()
            end = _SENTENCE_END.search(body)
            sentence = body[: end.end()] if end else body
            if _STRUCTURE.match(body):
                break
            if _key(sentence) in self._said and (end is not None or final):
                self._held, self._dropped = body[len(sentence) :], True
                continue
            if end is None and not final and self._may_repeat(_key(body)):
                return ""
            break
        self._open = True
        out, self._held = (self._held.lstrip() if self._dropped else self._held), ""
        return out

    def _may_repeat(self, key: str) -> bool:
        """An unfinished sentence that is still the start of one said before."""
        return not key or any(said.startswith(key) for said in self._said)


async def without_repeats(tokens: AsyncIterator[str], before: str) -> AsyncGenerator[str]:
    """``tokens`` with any opening sentence that repeats ``before`` left out."""
    repeats = RepeatFilter(before)
    async for token in tokens:
        if kept := repeats.feed(token):
            yield kept
    if tail := repeats.flush():
        yield tail
