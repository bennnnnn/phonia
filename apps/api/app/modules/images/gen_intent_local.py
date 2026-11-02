# ruff: noqa: RUF001, RUF003 - Turkish dotless i, Cyrillic and maths signs are the words matched
"""One picture request in the app's eight other languages: only the unmistakable shapes.

"Dibújame un dragón", "¿Me dibujas un dragón?", "Zeichne mir einen Drachen", "Mi disegni
un panda?", "Bana bir panda çizer misin?", "Crea una imagen de un león" draw. "Dibuja un
gato", "Illustra il problema" and "Mal den Teufel nicht an die Wand" are answered in
words, as on main: a picture there could be homework, an idiom or a plan. The shapes are
``gen_intent_languages.py``; what a subject may hold is ``gen_intent_drawable.py``.

The subject must be short and plain: at most six words, no digits, units or maths signs,
every word a listed drawable noun, plain descriptor or function word ("un gato negro en
la playa", not "un gato en ASCII" or "un árbol binario"), and nothing pointing back
("eso", "das nochmal": no revisions here). When in doubt, nothing is drawn. Matching is
linear token scans, as in ``gen_intent``: no ``\\s+`` / ``.+`` regex on user chat text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.modules.chemistry.request import extract_compound_name
from app.modules.images.gen_intent_drawable import is_entry, names_drawable
from app.modules.images.gen_intent_languages import ALSO, ARTICLES, LANGUAGES, Language, Shape
from app.services.text_normalize import straighten_apostrophes

_MAX_CHARS = 500
_WORDS = re.compile(r"\S+")
# Punctuation around a word: Spanish "¿¡", Ethiopic stops. Not quote marks: a quoted line
# is no request, and a word kept in its quotes matches nothing.
_EDGES = ".,!?;:()[]{}¿¡…።፣፤፥፦፧፨"
# Inside a subject they join two sentences or a request and its content: "ቀይ? ድመት".
_STOPS = frozenset(".!?;:።፧፥፦")
# Any of these makes the line a quotation: «Dibújame un cordero», „Zeichne mir …“, "…".
_QUOTE_MARKS = frozenset('"«»‹›„“”‟「」『』〝〞＂')
# A single quote opens a quotation at the start of a word ("'Dibújame un gato': …"); inside
# a word it is an apostrophe ("d'un", "un'immagine", "Fransa'nın").
_SINGLE_QUOTES = ("'", "\u2018", "\u2019", "\u201a", "\u201b")
_BEFORE_QUOTE = "¿¡([{—–-"
# "d'un", "l'image", "un'immagine", "s'il": the elided word is its own token.
_ELISIONS = frozenset(
    "d' l' m' t' s' j' n' c' qu' un' dell' all' dall' nell' sull' quest' cos'".split()
)
# "dessine-moi", "peux-tu", "desenha-me": the pronoun after the hyphen is its own token.
_HYPHEN_CLITICS = frozenset({"moi", "toi", "nous", "vous", "tu", "me", "te", "lo", "la", "il"})
# Maths, units and formulas: "45°", "y=x²", "20 m/s", "H2O" are the subjects' to draw.
_MATHS_MARKS = frozenset("=^√∫×÷<>+*/%°²³π∑")
_MAX_SUBJECT_WORDS = 6


@dataclass(frozen=True)
class _Token:
    start: int
    end: int
    word: str


def _fold(piece: str) -> str:
    word = piece.lower().strip(_EDGES)
    return word if word.endswith("'") else word.strip("'")


def _pieces(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    word = text[start:end].lower()
    quote = word.find("'")
    if 0 < quote < len(word) - 1 and word[: quote + 1].strip(_EDGES) in _ELISIONS:
        yield start, start + quote + 1
        yield from _pieces(text, start + quote + 1, end)
        return
    hyphen = word.rfind("-")
    if 0 < hyphen < len(word) - 1 and word[hyphen + 1 :].strip(_EDGES) in _HYPHEN_CLITICS:
        yield from _pieces(text, start, start + hyphen)
        yield start + hyphen + 1, end
        return
    yield start, end


def _tokens_of(text: str) -> list[_Token]:
    """The words of ``text`` with where each sits, lowercase, elisions and clitics apart."""
    out: list[_Token] = []
    for match in _WORDS.finditer(text):
        for start, end in _pieces(text, *match.span()):
            word = _fold(text[start:end])
            if word:
                out.append(_Token(start, end, word))
    return out


def _phrase_at(phrases: Iterable[tuple[str, ...]], words: list[str], i: int) -> int:
    """How many words a phrase from ``phrases`` covers at ``i`` (the longest), else 0."""
    best = 0
    for phrase in phrases:
        n = len(phrase)
        if n > best and tuple(words[i : i + n]) == phrase:
            best = n
    return best


def _lead_at(shape: Shape, words: list[str], start: int) -> int | None:
    """How many words a lead of ``shape`` covers at ``start``; None when none starts there."""
    leads = shape.leads
    return next((n for n in shape.lead_sizes if tuple(words[start : start + n]) in leads), None)


def _tail_at(shape: Shape, words: list[str], end: int) -> int | None:
    """How many words a tail of ``shape`` covers before ``end``; None when none ends there."""
    tails = shape.tails
    return next(
        (n for n in shape.tail_sizes if n <= end and tuple(words[end - n : end]) in tails), None
    )


def _span(lang: Language, words: list[str]) -> tuple[int, int, Shape] | None:
    """Where the subject of ``lang``'s request sits, and its shape; None for no request."""
    start, end = _phrase_at(lang.polite, words, 0), len(words)
    for size in (2, 1):
        if end - size > start and _phrase_at(lang.polite, words, end - size) == size:
            end -= size
            break
    for shape in lang.shapes:
        lead, tail = _lead_at(shape, words, start), _tail_at(shape, words, end)
        if lead is not None and tail is not None and (lead or tail):
            i = start + lead
            # "zeichne mir bitte …", "… und zeichne mir auch eine Katze".
            while i < end - tail and (
                words[i] in lang.fillers or words[i] in ALSO or _phrase_at(lang.polite, words, i)
            ):
                i += max(1, _phrase_at(lang.polite, words, i))
            if i < end - tail and words[i] in ARTICLES:
                i += 1
            return i, end - tail, shape
    return None


def _plain(lang: Language, words: list[str], typed: list[str]) -> bool:
    """A short, plain subject: a new thing ("un dragón", not "la pirámide" or "eso" the
    chat would have to name), no maths, and only listed words."""
    if not 1 <= len(words) <= _MAX_SUBJECT_WORDS:
        return False
    if any(char.isdigit() or char in _MATHS_MARKS for word in typed for char in word):
        return False
    first, last = words[0], words[-1]
    definite_end = last.endswith(lang.definite_endings) and not is_entry(lang.code, last)
    if first in lang.pronouns or first in lang.definite or definite_end:
        return False
    if first in lang.particles or last in lang.particles:
        return False
    if any(_phrase_at(lang.again, words, i) for i in range(len(words))):
        return False
    return names_drawable(lang.code, words)


def _read(lang: Language, text: str, tokens: list[_Token]) -> str | None:
    """The subject of ``lang``'s request; "" when its shape matched but the subject is no
    plain picture; None when the shape is not there."""
    words = [t.word for t in tokens]
    span = _span(lang, words)
    if span is None:
        return None
    i, end, shape = span
    if i >= end:
        return ""
    start, checked = tokens[i].start, words[i:end]
    typed = [text[t.start : t.end].strip(_EDGES) for t in tokens[i:end]]
    if shape.of_prefix and checked[0].startswith(shape.of_prefix):
        # Amharic "የድመት ምስል": the picture of a cat draws "ድመት".
        start += len(shape.of_prefix)
        checked[0] = checked[0].removeprefix(shape.of_prefix)
        typed[0] = typed[0].removeprefix(shape.of_prefix)
    subject = text[start : tokens[end - 1].end].strip().strip(_EDGES).strip()
    if len(subject) < 2 or not _STOPS.isdisjoint(subject) or not _plain(lang, checked, typed):
        return ""
    return subject


def _read_picture(text: str, tokens: list[_Token]) -> str | None:
    """The subject when the whole of ``text`` asks for one picture in one of the narrow
    shapes, in any language that reads it."""
    if not tokens:
        return None
    found: list[str] = []
    for lang in LANGUAGES:
        subject = _read(lang, text, tokens)
        if subject == "":
            return None
        if subject is not None:
            found.append(subject)
    if not found:
        return None
    # "Zeichne mir Ethanol": a compound the chemistry card draws, as for "draw ethanol".
    return None if extract_compound_name(f"draw {found[0]}") is not None else found[0]


def _quoted(text: str) -> bool:
    """``text`` quotes something: a quote mark, or a word that opens with a single quote."""
    if not _QUOTE_MARKS.isdisjoint(text):
        return True
    return any(chunk.lstrip(_BEFORE_QUOTE).startswith(_SINGLE_QUOTES) for chunk in text.split())


def extract_other_language_prompt(text: str) -> str | None:
    """The picture ``text`` asks for in Spanish, French, German, Italian, Portuguese,
    Russian, Turkish or Amharic, in the user's words, when the whole message is that one
    request; None otherwise.

    A message that asks for anything beside the picture ("Dibújame un gato y explica qué
    es un agujero negro") is answered in words, as on main: its other words are no listed
    ones, and no other-language message is cut into a picture and a request, since a line
    beside a draw-me line is often about it ("¿Cómo se dice en inglés? Dibújame un gato").
    A quoted line ("«Dibújame un cordero»: ¿quién lo dijo?") is no request at all.
    """
    trimmed = straighten_apostrophes(text.strip())
    if not trimmed or len(trimmed) > _MAX_CHARS or _quoted(trimmed):
        return None
    return _read_picture(trimmed, _tokens_of(trimmed))
