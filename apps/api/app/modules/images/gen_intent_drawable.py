# ruff: noqa: RUF001, RUF002, RUF003 - Turkish dotless i and Cyrillic are the words matched
"""Whether a picture subject asked in another language names a thing to draw.

An allow-list of the whole subject, not of its head alone: every word must be a listed
drawable noun, a plain descriptor or a function word. "Dibújame un gato negro con
sombrero en la playa" draws; "un gato en ASCII", "un árbol binario", "un puente de
Wheatstone", "una montaña de deudas", "un perro y sugiéreme nombres" are answered in
words, as on main, because "ASCII", "binario", "Wheatstone", "deudas" and "sugiéreme"
are none of these. An unusual subject is simply answered.

- Nouns: ``gen_intent_drawable_romance`` and ``gen_intent_drawable_other``: animals,
  people, creatures, objects, vehicles, buildings and places, nature, food, plants, sky,
  toys, instruments. Russian and Turkish forms are made from the listed one.
- Descriptors and function words: ``gen_intent_drawable_words``. Their forms are made
  here: "rojo" → roja, rojos, rojas; "rot" → rote, roten; "красный" → красного, красную.
- "and" joins two drawable nouns only ("un gato y un perro", not "un gato y negro").
- Turkish and Amharic close the subject with its noun ("şapkalı bir kedi", "ቀይ ድመት").
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.modules.images import gen_intent_drawable_other as other
from app.modules.images import gen_intent_drawable_romance as romance
from app.modules.images import gen_intent_drawable_words as plain

_HEAD_LAST = frozenset({"tr", "am"})
_LONGEST_NAME = 4
# A German compound's first part has at least this many letters ("Feuerdrache").
_MIN_COMPOUND_LEAD = 3
# Between a German compound's parts: "Weihnacht-s-baum", "Piraten-schiff".
_DE_LINKS = ("s", "es", "n", "en", "e", "er")

_RU_ENDINGS = {
    "а": "а у ы и е ой ам ами ах -",
    "я": "я ю и е ей ь ям ями ях",
    "ь": "ь я и ей ю ем ям ями ях",
    "й": "й я и ев ю ем ям ями ях",
    "о": "о а у ом е ам ами ах -",
    "е": "е я а ю ем ям ями ях",
}
_RU_HARD = "- а у ы и ов ей ом е ам ами ах"
_RU_SOFT_ENDS = frozenset("аяьйое")
_RU_FIXED_ENDS = frozenset("иуыюэ")
# Every ending a Russian adjective takes: "красный" → красная, красного, красными …
_RU_ADJECTIVE = "ый ий ой ая яя ое ее ые ие ого его ому ему ую юю ым им ом ем ых их ыми ими ей"
_TR_VOWELS = "aıoueiöü"
_TR_BACK = frozenset("aıou")
_TR_POSSESSIVE = {"a": "ı", "ı": "ı", "o": "u", "u": "u", "e": "i", "i": "i", "ö": "ü", "ü": "ü"}
_TR_SOFT = {"p": "b", "ç": "c", "t": "d", "k": "ğ"}
_TR_HARD_ENDS = frozenset("fsthçşkp")


def fold(word: str) -> str:
    """Lowercase, no accents, so "leon" is "león" and "kopek" is "köpek"; Cyrillic keeps its
    letters (only "ё" is "е"), Ethiopic is as typed."""
    out: list[str] = []
    for char in word.lower():
        if "Ѐ" <= char <= "ӿ" or "ሀ" <= char <= "፿":
            out.append("е" if char == "ё" else char)
        else:
            out.append(unicodedata.normalize("NFD", char)[0])
    return "".join(out).replace("ı", "i").replace("ß", "ss")


def _listed(entry: str) -> list[str]:
    """ "gato+s" → gato, gatos; "león/leones" → both; "Hund+e+en" → Hund, Hunde, Hunden."""
    out: list[str] = []
    for form in entry.split("/"):
        base, *endings = form.split("+")
        out += [base, *(base + ending for ending in endings)]
    return out


def _russian(word: str) -> list[str]:
    """The case and plural forms of a Russian nominative: "кошка" → "кошку", "кошки" …"""
    last = word[-1]
    if last in _RU_FIXED_ENDS:
        return [word]
    stem, endings = (word[:-1], _RU_ENDINGS[last]) if last in _RU_SOFT_ENDS else (word, _RU_HARD)
    return [stem + ending.strip("-") for ending in endings.split()]


def _turkish(word: str) -> list[str]:
    """A Turkish noun and the forms a picture subject uses: plural and compound ("gemiler",
    "gemisi"), "with" ("şapkalı"), "in" ("ormanda"), "of" ("ağacın altında"), "to"."""
    vowels = [char for char in word if char in _TR_VOWELS]
    if not vowels:
        return [word]
    back, last = vowels[-1] in _TR_BACK, vowels[-1]
    mark, open_vowel = _TR_POSSESSIVE[last], "a" if back else "e"
    ends_vowel = word[-1] in _TR_VOWELS
    plural = word + ("lar" if back else "ler")
    soft = word[:-1] + _TR_SOFT[word[-1]] if word[-1] in _TR_SOFT and len(vowels) > 1 else word
    located = ("t" if word[-1] in _TR_HARD_ENDS else "d") + open_vowel
    forms = [
        word,
        plural,
        plural + mark,
        word + "l" + mark,
        word + located,
        plural + "d" + open_vowel,
    ]
    owned = word + "s" + mark if ends_vowel else soft + mark
    forms += [owned, owned + "nd" + open_vowel]
    if ends_vowel:
        return [*forms, word + "n" + mark + "n", word + "y" + open_vowel]
    return [*forms, word + mark, soft + mark + "n", soft + open_vowel]


def _romance(word: str, code: str) -> list[str]:
    """A Romance adjective's gender and number forms: "rojo" → roja, rojos, rojas."""
    if code == "fr":
        return [word, word + "e", word + "s", word + "es"]
    if word.endswith("o"):
        stem = word[:-1]
        return [stem + end for end in ("o", "a", "i", "e") if code == "it" or end in "oa"] + (
            [] if code == "it" else [stem + "os", stem + "as"]
        )
    if word.endswith("e"):
        return [word, word[:-1] + "i"] if code == "it" else [word, word + "s"]
    return [word, word + "s", word + "es", word + "a", word + "as"]


def _describing(code: str, word: str) -> list[str]:
    if code in ("es", "fr", "it", "pt"):
        return _romance(word, code)
    if code == "de":
        return [word + end for end in ("", "e", "en", "er", "es", "em")]
    if code == "ru" and word.endswith(("ый", "ий", "ой")):
        return [word[:-2] + end for end in _RU_ADJECTIVE.split()]
    return [word]


def _describers(code: str, text: str) -> frozenset[str]:
    """Each descriptor's forms: those made from its first, then any listed after "/"."""
    out: set[str] = set()
    for entry in text.split():
        first, *more = entry.split("/")
        out.update(fold(word) for word in (*_describing(code, first), *more))
    return frozenset(out)


@dataclass(frozen=True)
class Nouns:
    words: frozenset[str]
    names: frozenset[tuple[str, ...]]
    # German compounds end with these ("Feuerdrache").
    compounds: tuple[str, ...] = ()
    # Each entry as written: Turkish "ayı" (a bear) is no definite "-yı" object.
    entries: frozenset[str] = frozenset()


def _forms_of(word: str, index: int, forms: Callable[[str], list[str]] | None) -> list[str]:
    """The forms made from a listed noun. A later Russian form with a moved stem makes its
    own too: "замок/замка" also gives "замке", "лев/льва" "львом"."""
    if forms is None:
        return [word]
    if not index:
        return forms(word)
    return [word, *forms(word[:-1])] if word.endswith(("а", "я")) and forms is _russian else [word]


def _nouns(text: str, forms: Callable[[str], list[str]] | None = None) -> Nouns:
    """The language's nouns; ``forms`` makes the inflected forms of each entry's first."""
    words: set[str] = set()
    names: set[tuple[str, ...]] = set()
    compounds: set[str] = set()
    entries: set[str] = set()
    for entry in text.split():
        marked = entry.startswith("*")
        for index, form in enumerate(_listed(entry.lstrip("*"))):
            *lead, last = form.split("_")
            made = {fold(word) for word in _forms_of(last, index, forms)}
            entries.add(fold(form))
            if lead:
                names.update((*map(fold, lead), made_word) for made_word in made)
            else:
                words.update(made)
            if marked:
                compounds.update(made)
    return Nouns(
        frozenset(words),
        frozenset(names),
        tuple(sorted(compounds)),
        frozenset(entries),
    )


NOUNS: dict[str, Nouns] = {
    "es": _nouns(romance.SPANISH),
    "fr": _nouns(romance.FRENCH),
    "it": _nouns(romance.ITALIAN),
    "pt": _nouns(romance.PORTUGUESE),
    "de": _nouns(other.GERMAN),
    "ru": _nouns(other.RUSSIAN, forms=_russian),
    "tr": _nouns(other.TURKISH, forms=_turkish),
    "am": _nouns(other.AMHARIC),
}
DESCRIBE = {code: _describers(code, text) for code, text in plain.DESCRIBE.items()}
GLUE = {code: frozenset(fold(word) for word in text.split()) for code, text in plain.GLUE.items()}
AND = {code: frozenset(text.split()) for code, text in plain.AND.items()}
_DE_LEADS = frozenset(plain.GERMAN_LEADS.split())
_AM_PREFIXES = tuple(plain.AMHARIC_PREFIXES.split())


class Kind(Enum):
    NOUN = "noun"
    DESCRIBE = "describe"
    GLUE = "glue"
    AND = "and"


def _german_lead(lead: str) -> bool:
    """The first part of a German compound: a listed noun or descriptor ("Piraten-",
    "Rot-"), or a few festive leads ("Weihnachts-"), with or without a linking letter."""
    known = NOUNS["de"].words | DESCRIBE["de"] | _DE_LEADS
    return lead in known or any(
        lead.endswith(link) and lead[: -len(link)] in known for link in _DE_LINKS
    )


def _is_noun(code: str, word: str) -> bool:
    nouns = NOUNS[code]
    if word in nouns.words:
        return True
    if "-" in word:
        # "loup-garou" is listed whole; "Wheatstone-Brücke" needs every part listed.
        parts = [part for part in word.split("-") if part]
        return bool(parts) and all(_is_noun(code, part) for part in parts)
    if code == "am":
        return any(
            word.startswith(prefix) and word[len(prefix) :] in nouns.words
            for prefix in _AM_PREFIXES
        )
    if code != "de":
        return False
    return any(
        word.endswith(end)
        and len(word) - len(end) >= _MIN_COMPOUND_LEAD
        and _german_lead(word[: -len(end)])
        for end in nouns.compounds
    )


def _kinds(code: str, words: list[str]) -> list[Kind] | None:
    """What each word of the subject is, a name of several words as nouns; None when a word
    is none of them ("ASCII", "binario", "sugiéreme")."""
    nouns = NOUNS[code]
    out: list[Kind] = []
    i = 0
    while i < len(words):
        name = next(
            (
                size
                for size in range(min(_LONGEST_NAME, len(words) - i), 1, -1)
                if tuple(words[i : i + size]) in nouns.names
            ),
            0,
        )
        if name:
            out += [Kind.NOUN] * name
            i += name
            continue
        word = words[i]
        if _is_noun(code, word):
            out.append(Kind.NOUN)
        elif word in AND[code]:
            out.append(Kind.AND)
        elif word in GLUE[code]:
            out.append(Kind.GLUE)
        elif word in DESCRIBE[code]:
            out.append(Kind.DESCRIBE)
        else:
            return None
        i += 1
    return out


def _well_formed(code: str, kinds: list[Kind]) -> bool:
    """A noun in every stretch "and" joins; no "and" or function word at the end; Turkish and
    Amharic end on their noun."""
    if kinds[-1] in (Kind.AND, Kind.GLUE) or (code in _HEAD_LAST and kinds[-1] is not Kind.NOUN):
        return False
    stretch_has_noun = False
    for kind in kinds:
        if kind is Kind.AND:
            if not stretch_has_noun:
                return False
            stretch_has_noun = False
        stretch_has_noun = stretch_has_noun or kind is Kind.NOUN
    return stretch_has_noun


def is_entry(code: str, word: str) -> bool:
    """``word`` is a noun of ``code``'s list as written there: "ayı", not "ayıyı"."""
    return fold(word) in NOUNS[code].entries


def names_drawable(code: str, words: list[str]) -> bool:
    """True when every word of the subject ``words`` is a drawable noun, a plain descriptor
    or a function word, with a noun to draw: "un gato negro en la playa"."""
    folded = [fold(word) for word in words]
    if not folded:
        return False
    kinds = _kinds(code, folded)
    return kinds is not None and _well_formed(code, kinds)
