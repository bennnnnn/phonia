"""Detect reference-photo *lookup* intent in a message: the word rules ``intent.py`` reads.

Cases: ``docs/fixtures/image_intent_cases.json``.

Separate from ``image_gen_intent`` (creative generation). "Show me an ear" /
"what does a golden retriever look like" want a real photo, not AI art —
this module recognizes that distinct phrasing so the router can send it to
``image_search`` instead of ``generate_image``.

Checked *before* generation intent in the caller: none of the trigger verbs
here ("show", "let … see", "what does … look like") overlap with
generation's verb set (create/generate/make/design/render/produce/draw/
paint/illustrate), so this only changes behavior for phrasing generation
did not already own on purpose (see the "show me a picture of X" bug this
fixes — generation's bare colloquial fallback used to mis-parse it).

Matching is linear token scans — no ``\\s+`` / ``.+`` regex on user chat text
(CodeQL ``py/polynomial-redos``), same discipline as ``image_gen_intent``.
"""

from __future__ import annotations

import re
from itertools import pairwise

from app.modules.images.lookup_intent_words import (
    CODE_CONTEXT_WORDS,
    DUAL_USE_WORDS,
    LOOKUP_NON_IMAGE_WORDS,
)
from app.modules.images.unnamed_subjects import is_count_only
from app.services.text_normalize import fold_token

_ARTICLES = frozenset({"a", "an", "the"})
_POSSESSIVES = frozenset({"my", "your", "our", "his", "her", "their", "its"})
_REFERENCE_NOUNS = frozenset(
    {"picture", "pictures", "photo", "photos", "image", "images", "pic", "pics"}
)
# "show me her image", "a photo of him": someone named earlier in the chat.
# "my" / "your" / "our" stay out — "show me my notes" is app content.
_THIRD_PERSON_POSSESSIVES = frozenset({"his", "her", "their", "its"})
_OBJECT_PRONOUNS = frozenset({"her", "him", "them", "it"})
# Subjects that only make sense against the conversation: "it at night",
# "she", "another one". The server reads them from the chat before searching.
_REFERENCE_HEADS = frozenset(
    {
        "it",
        "its",
        "her",
        "him",
        "his",
        "she",
        "he",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "another",
        "more",
        "less",
    }
)
# "can you show me…", "please show me…" ask the same thing as "show me…".
_POLITE_LEADS: tuple[tuple[str, ...], ...] = (
    ("can", "you"),
    ("could", "you"),
    ("would", "you"),
    ("will", "you"),
    ("can", "u"),
    ("please",),
    ("pls",),
    ("just",),
)
# "can I see X", "I want to see X" ask what "let me see X" asks.
_SEE_LEADS: tuple[tuple[str, ...], ...] = (
    ("let", "me", "see"),
    ("lemme", "see"),
    ("can", "i", "see"),
    ("could", "i", "see"),
    ("may", "i", "see"),
    ("i", "want", "to", "see"),
    ("i'd", "like", "to", "see"),
    ("i", "would", "like", "to", "see"),
    ("i", "wanna", "see"),
)
# "do you have a picture of him?", "you got a photo of a gelada?": a photo asked for as a
# question. The model, unasked to look, said it cannot show photos and sent the user to
# search online (2026-10-24). Bare "got" is news ("got a picture of the eclipse today!").
_ASK_LEADS: tuple[tuple[str, ...], ...] = (
    ("do", "you", "have"),
    ("have", "you", "got"),
    ("you", "got"),
)
# "is there a picture of her?" asks for one; "are there pictures of Muhammad allowed in
# Islam?" and "is there a photo of Mozart?" ask whether one exists, which only the answer
# can say. These leads look up only someone named earlier in the chat.
_EXIST_LEADS: tuple[tuple[str, ...], ...] = (("is", "there"), ("are", "there"), ("any",))
_PEOPLE_PRONOUNS = frozenset({"him", "her", "them"})
_SELF_WORDS = frozenset({"i", "i'm", "i've", "me", "myself", "you", "yourself", "yourselves"})
# "send me a photo of X": these verbs need the photo noun, or "find me a
# restaurant" and "give me a list" would turn into photo searches.
_PHOTO_FETCH_VERBS = frozenset({"send", "find", "get", "give", "pull", "bring"})


# "show me how to solve this" / "what does X mean" — explanation cues embedded
# in the subject, not an object to photograph.
_EXPLANATION_CUES = frozenset(
    {
        "how",
        "why",
        "when",
        "where",
        "what",
        "solve",
        "explain",
        "prove",
        "calculate",
        "compute",
        "work",
        "works",
        "mean",
        "means",
        "becoming",
    }
)

_MAX_SUBJECT_WORDS = 8
_DEICTICS = frozenset({"that", "this", "these", "those"})
_PHOTO_ADJECTIVES = frozenset({"real", "actual", "nice", "good", "clear"})
_REASON_CLAUSE = re.compile(r",\s*(?:i|i'm|im|so|because|since|for|to)\b", re.IGNORECASE)
_NOT_A_NOUN = frozenset({"again", "but", "one", "part", "bit", "more", "in", "with", "please"})


def _reference_subject(tokens: list[str]) -> str | None:
    """ "her image" -> "her"; "her" / "him" alone -> itself. Else None."""
    folded = [fold_token(t) for t in tokens]
    if not folded:
        return None
    if len(folded) == 1 and folded[0] in _OBJECT_PRONOUNS:
        return folded[0]
    if (
        len(folded) == 2
        and folded[0] in _THIRD_PERSON_POSSESSIVES
        and folded[1] in _REFERENCE_NOUNS
    ):
        return folded[0]
    return None


def is_reference_subject(subject: str) -> bool:
    """True when the subject names no one ("she", "it at night", "another one", "both")."""
    words = subject.split()
    if not words:
        return False
    return fold_token(words[0]) in _REFERENCE_HEADS or is_count_only(subject)


# What Recall draws rather than photographs. "can u show me both" after water and carbon
# dioxide was read as "water and carbon dioxide molecules"; the chemistry card draws those,
# and a stock photo of a ball-and-stick model is no answer. Only these words count, so a
# resolved name like "Times Square at night" or "Queen Elizabeth I" is still searched. A
# formula the app draws carries a maths mark; the word alone is "Formula 1" or baby formula.
_DRAWN_WORDS = frozenset(
    {
        "molecule",
        "molecules",
        "molecular",
        "equation",
        "equations",
        "graph",
        "graphs",
    }
)
_MATHS_MARKS = ("=", "^", "\u00d7", "\u00f7", "\\")


def names_a_drawing(subject: str) -> bool:
    """True when *subject* is a molecule, a written formula, an equation or a graph."""
    if any(mark in subject for mark in _MATHS_MARKS):
        return True
    return any(fold_token(word) in _DRAWN_WORDS for word in subject.split())


# "Show the vertex" after a graph asks for a feature of the graph the app draws, not a
# photo to search for. Only a subject made of these words and the filler below counts:
# "the roots of a mangrove tree" still wants a photo.
_GRAPH_FEATURES = frozenset(
    {
        "vertex",
        "vertices",
        "intercept",
        "intercepts",
        "x-intercept",
        "x-intercepts",
        "y-intercept",
        "y-intercepts",
        "root",
        "roots",
        "zero",
        "zeros",
        "zeroes",
        "asymptote",
        "asymptotes",
        "slope",
        "gradient",
        "maximum",
        "minimum",
        "maxima",
        "minima",
        "extrema",
        "domain",
        "range",
        "tangent",
        "intersection",
        "intersections",
        "inflection",
        "turning",
        "critical",
        "points",
        "axis",
        "symmetry",
        "period",
        "amplitude",
    }
)
_GRAPH_FEATURE_FILLER = frozenset(
    {"the", "a", "an", "its", "of", "and", "both", "all", "this", "that", "it", "point", "line"}
    | {"graph", "parabola", "curve", "function", "equation", "x", "y"}
)


def _names_graph_features(folded: list[str]) -> bool:
    return any(w in _GRAPH_FEATURES for w in folded) and all(
        w in _GRAPH_FEATURES or w in _GRAPH_FEATURE_FILLER for w in folded
    )


def _clean_subject(raw: str) -> str | None:
    # "a habesha kemis, i want to describe it in my caption": the reason is not the subject.
    reason = _REASON_CLAUSE.search(raw)
    if reason is not None:
        raw = raw[: reason.start()]
    subject = raw.strip().rstrip(".!?").strip()
    if not subject or len(subject) < 2:
        return None
    if any(symbol in subject for symbol in ("\u00d7", "\u00f7", "=", "^")) or any(
        operator in subject for operator in (" + ", " - ", " / ", " * ", " \u2212 ")
    ):
        return None
    words = subject.split()
    if not words or len(words) > _MAX_SUBJECT_WORDS:
        return None
    folded = [fold_token(w) for w in words]
    if not folded[0] or folded[0] in _POSSESSIVES:
        return None
    # "a picture of me", "of you", "of the receipt I uploaded": the user, Recall or the
    # user's own files, never a web search.
    if any(w in _SELF_WORDS for w in folded):
        return None
    # "Show me that again but simpler" asks to repeat an answer.
    if folded[0] in _DEICTICS and len(folded) > 1 and folded[1] in _NOT_A_NOUN:
        return None
    if any(w in LOOKUP_NON_IMAGE_WORDS or w in _EXPLANATION_CUES for w in folded):
        return None
    if _names_graph_features(folded):
        return None
    # "show me the bug (again)" is about code; "show me a bed bug" wants a photo.
    if folded[0] in DUAL_USE_WORDS and all(w in _NOT_A_NOUN for w in folded[1:]):
        return None
    # "show me the git branch" is about code; "show me the main stage" wants a photo.
    pairs = [{a, b} for a, b in pairwise(folded)]
    if any(pair & DUAL_USE_WORDS and pair & CODE_CONTEXT_WORDS for pair in pairs):
        return None
    return subject


def _strip_reference_noun_prefix(tokens: list[str]) -> list[str]:
    """ "[a/an/the]? picture/photo/image of SUBJECT" -> SUBJECT tokens."""
    i = 0
    if i < len(tokens) and tokens[i].lower() in _ARTICLES:
        i += 1
    # "a real photo of", "an actual picture of"
    if i + 1 < len(tokens) and tokens[i].lower() in _PHOTO_ADJECTIVES:
        if tokens[i + 1].lower() in _REFERENCE_NOUNS:
            i += 1
    if i < len(tokens) and tokens[i].lower() in _REFERENCE_NOUNS:
        i += 1
        if i < len(tokens) and tokens[i].lower() == "of":
            i += 1
        return tokens[i:]
    return tokens


def _strip_leading_article(tokens: list[str]) -> list[str]:
    if tokens and tokens[0].lower() in _ARTICLES:
        return tokens[1:]
    return tokens


def _strip_polite_lead(tokens: list[str]) -> list[str]:
    changed = True
    while changed:
        changed = False
        for lead in _POLITE_LEADS:
            n = len(lead)
            if len(tokens) > n and tuple(t.lower() for t in tokens[:n]) == lead:
                tokens = tokens[n:]
                changed = True
                break
    return tokens


def _photo_subject(tokens: list[str]) -> str | None:
    """SUBJECT from "[a/an/the]? [picture/photo/image of]? SUBJECT"."""
    remaining = _strip_leading_article(tokens)
    remaining = _strip_reference_noun_prefix(remaining)
    remaining = _strip_leading_article(remaining)
    if not remaining:
        return None
    return _reference_subject(remaining) or _clean_subject(" ".join(remaining))


def _match_show_me(tokens: list[str]) -> str | None:
    """ "show me [a/an/the]? [picture/photo/image of]? SUBJECT" """
    if len(tokens) < 2 or tokens[0].lower() != "show":
        return None
    i = 1
    if i < len(tokens) and tokens[i].lower() == "me":
        i += 1
    return _photo_subject(tokens[i:])


def _match_let_me_see(tokens: list[str]) -> str | None:
    """ "let me see / can I see / I want to see [a/an/the]? SUBJECT" """
    folded = [t.lower() for t in tokens]
    for lead in _SEE_LEADS:
        n = len(lead)
        if len(tokens) > n and tuple(folded[:n]) == lead:
            return _photo_subject(tokens[n:])
    return None


def _match_fetch_photo(tokens: list[str]) -> str | None:
    """ "send / find / get me a photo of SUBJECT", "pull up a picture of SUBJECT" """
    if len(tokens) < 3 or tokens[0].lower() not in _PHOTO_FETCH_VERBS:
        return None
    i = 1
    if i < len(tokens) and tokens[i].lower() == "up":
        i += 1
    if i < len(tokens) and tokens[i].lower() == "me":
        i += 1
    rest = _strip_leading_article(tokens[i:])
    if rest and rest[0].lower() == "some":
        rest = rest[1:]
    if not rest or rest[0].lower() not in _REFERENCE_NOUNS:
        return None
    return _photo_subject(rest)


def _match_have_photo(tokens: list[str]) -> str | None:
    """ "do you have [a/any]? picture of SUBJECT", "is there a picture of him" — the noun
    and its "of" are required: "do you have a photo editing app?" and "is there a
    picture limit?" ask about something else."""
    folded = [fold_token(t) for t in tokens]
    for lead in (*_ASK_LEADS, *_EXIST_LEADS):
        n = len(lead)
        if tuple(folded[:n]) != lead:
            continue
        i = n
        if i < len(folded) and folded[i] in {*_ARTICLES, "any", "some"}:
            i += 1
        # The noun, its "of" (as ``_strip_reference_noun_prefix`` reads it), a subject.
        if not (i + 2 < len(tokens) and folded[i] in _REFERENCE_NOUNS):
            return None
        if tokens[i + 1].lower() != "of":
            return None
        named_earlier = len(folded) == i + 3 and folded[i + 2] in _PEOPLE_PRONOUNS
        if lead in _EXIST_LEADS and not named_earlier:
            return None
        return _photo_subject(tokens[i:])
    return None


def _match_show_what_looks_like(tokens: list[str]) -> str | None:
    """ "show me what SUBJECT looks like" """
    if len(tokens) < 5 or tokens[0].lower() != "show":
        return None
    i = 1
    if tokens[i].lower() == "me":
        i += 1
    if i >= len(tokens) or tokens[i].lower() != "what":
        return None
    if tokens[-1].lower().rstrip("?.!") != "like" or tokens[-2].lower() not in {"looks", "look"}:
        return None
    subject_tokens = _strip_leading_article(tokens[i + 1 : -2])
    if not subject_tokens:
        return None
    return _clean_subject(" ".join(subject_tokens))


def _match_look_like(tokens: list[str]) -> str | None:
    """ "what does/do [a/an/the]? SUBJECT look like" """
    if len(tokens) < 5 or tokens[0].lower() != "what":
        return None
    if tokens[1].lower() not in {"does", "do"}:
        return None
    if tokens[-1].lower().rstrip("?.!") != "like" or tokens[-2].lower() != "look":
        return None
    subject_tokens = _strip_leading_article(tokens[2:-2])
    if not subject_tokens:
        return None
    return _clean_subject(" ".join(subject_tokens))


def extract_image_lookup_query(text: str) -> str | None:
    """Return the reference-photo subject if ``text`` clearly wants a real photo, else None."""
    trimmed = text.strip()
    if not trimmed or len(trimmed) > 200:
        return None

    tokens = _strip_polite_lead(trimmed.split())
    # "what does a gelada look like 🐒": a trailing emoji is not part of the ask.
    while tokens and not any(char.isalnum() for char in tokens[-1]):
        tokens = tokens[:-1]
    if not tokens:
        return None

    for match in (
        _match_show_what_looks_like,
        _match_show_me,
        _match_let_me_see,
        _match_fetch_photo,
        _match_have_photo,
        _match_look_like,
    ):
        matched = match(tokens)
        if matched:
            return matched
    return None


# "New" means new now: image search ranks the year, not the word. Place names
# that start with "new" keep it ("new york skyline").
_RECENCY_WORDS = frozenset({"new", "newest", "latest", "current", "brand-new"})
_NEW_PLACES = frozenset(
    {
        "york",
        "zealand",
        "delhi",
        "jersey",
        "mexico",
        "orleans",
        "hampshire",
        "england",
        "guinea",
        "caledonia",
        "brunswick",
        "haven",
        "south",
    }
)


def dated_lookup_query(query: str, year: int) -> str:
    """ "new tesla model" → "tesla model 2026": the photo of what is new this year."""
    tokens = query.split()
    kept: list[str] = []
    dated = False
    for index, word in enumerate(tokens):
        folded = fold_token(word)
        following = fold_token(tokens[index + 1]) if index + 1 < len(tokens) else ""
        if folded in _RECENCY_WORDS and not (folded == "new" and following in _NEW_PLACES):
            dated = True
            continue
        kept.append(word)
    if not dated or not kept:
        return query
    if str(year) not in kept:
        kept.append(str(year))
    return " ".join(kept)
