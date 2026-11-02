"""A follow-up question the chat already holds, by its words.

Live (2026-10-24, one study chat): "Why use Kelvin not Celsius?" came back under four
replies after the user had asked "Why is temperature in Kelvin for Charles's law?", and
one set offered "What if it was $-2x + 5 = 0$?" beside "How does it change for
$-2x + 5 = 0$?". A candidate repeats an earlier line (a user question, a suggestion
already shown, one kept just before it) when it is the same question, holds the same
equation, or names the same topic: its topic words and the line's match but for one, two
words or more ("kelvin" and "celsius" are the question, "why use … not" is its frame). A
problem statement or a long line names many topics, so a what-if on one of them is new.

Live again (2026-10-25): "What if perimeter was 48 cm?" came back after "What if the
perimeter was 48 cm?". The same question without its articles and pronouns is the same
question, and its numbers are part of what it asks, in order, each with its sign, root,
fraction and unit: "What if the perimeter was 60 cm?", "slope 2/3" after "slope 3/2",
minus 5 m/s (typed with the minus sign) after "5 m/s" and "2 g" after "2 kg" are new.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.modules.chat.follow_up_units import SYMBOLS, quantities
from app.services.text_normalize import collapse_ws, straighten_apostrophes

# A word of four letters or more, in any script.
_WORD = re.compile(r"[^\W\d_]{4,}")
_MATH_SPAN = re.compile(r"\$([^$\n]+)\$")
# A question read word by word: a maths span whole, a word or a number, a sign or a root.
_TOKEN = re.compile(r"\$[^$\n]+\$|[^\W_]+(?:\.\d+)?|[-+*/^=<>%\u221a]")
# What a reworded question drops or swaps without asking anything else: "the", "it", "my".
# Not "a": in "What if a = 2?" it is the variable.
_ARTICLES_AND_PRONOUNS = frozenset(
    "an the it its this that these those i you we he she they me him her us them my your "
    "our his their".split()
)
_RELATION = re.compile(r"=|<|>|\\[lg]eq?\b|\\neq\b")
# Words every question frame uses; the topic is what is left.
_FRAME = frozenset(
    {
        "about",
        "also",
        "because",
        "change",
        "changes",
        "could",
        "does",
        "explain",
        "happen",
        "happens",
        "have",
        "instead",
        "into",
        "make",
        "matter",
        "mean",
        "means",
        "more",
        "same",
        "should",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "used",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "work",
        "works",
        "would",
        "your",
    }
)
_MIN_TOPIC_WORDS = 2


def _topic(text: str) -> frozenset[str]:
    """Its topic words, and the numbers it names outside maths as one item, in order, each
    with its unit read one way ("2 seconds" is "2 s"; equations match whole)."""
    words = [w for w in _WORD.findall(text.casefold()) if w not in _FRAME]
    numbers = [str(quantity) for quantity in quantities(_MATH_SPAN.sub(" ", text))]
    return frozenset([*words, "#" + "|".join(numbers)] if numbers else words)


def _equations(text: str) -> frozenset[str]:
    """The equations in ``text``: "$x$" alone is a name, not a question's subject."""
    spans = (re.sub(r"\s+", "", span) for span in _MATH_SPAN.findall(text))
    return frozenset(span for span in spans if _RELATION.search(span))


def _folded(text: str) -> str:
    """The question's words in order, without articles and pronouns, maths unspaced."""
    tokens = _TOKEN.findall(straighten_apostrophes(collapse_ws(text)).translate(SYMBOLS).casefold())
    kept = (re.sub(r"\s+", "", t) for t in tokens if t not in _ARTICLES_AND_PRONOUNS)
    return " ".join(kept)


def repeats_earlier(candidate: str, earlier: Iterable[str]) -> bool:
    """Whether ``candidate`` asks what one of the ``earlier`` lines already asked."""
    folded, topic, equations = _folded(candidate), _topic(candidate), _equations(candidate)
    for line in earlier:
        if not line:
            continue
        if folded == _folded(line) or (equations and equations & _equations(line)):
            return True
        if _same_topic(topic, _topic(line)):
            return True
    return False


def _same_topic(first: frozenset[str], second: frozenset[str]) -> bool:
    """One set of topic words inside the other, at most one word apart. Numbers alone are
    no topic: "What is 3 + 5?" and "Why does 3 + 5 make 8?" ask two things."""
    small, large = sorted((first, second), key=len)
    if len(small) < _MIN_TOPIC_WORDS or not any(_WORD.fullmatch(word) for word in small):
        return False
    return small <= large and len(large) - len(small) <= 1
