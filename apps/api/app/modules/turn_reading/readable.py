# ruff: noqa: RUF001 - the dotless i and other letters of the app's languages are matched
"""Whether the subject readers can read a message: English words, numbers as they read them.

The maths, physics and chemistry readers are English grammars. In another language they
read the numbers and units and skip the words, so a verified card answered the part they
understood: "Deux résistances de 10 ohms sont en parallèle sous 5 V, courant total ?" was
one 10 Ω resistor, 0.5 A, for the 1 A of two in parallel (the count word "deux" unread,
2026-11-01). A number is read the English way too, so "1.200 + 800" from a Spanish user,
whose dot groups thousands, was 801.2 for 2000, and "a car of mass 1 200 kg" had 200 kg. A
message either reader flags gets no verified result; the model answers it.

Another language is read on positive evidence only, so an English question keeps its card:
- a word in a script the app's other languages write (Ethiopic, Cyrillic, Arabic, …);
  Greek is maths notation (θ, λ, Δ), never a language here;
- or words of Spanish, French, German, Italian, Portuguese or Turkish: function words those
  languages write and English never does, or a lowercase word with a letter English does
  not use ("résistances", "velocità"). Two or more need to outnumber the English words; one
  needs none beside it and must be a listed word of four letters or more ("résous 3x + 7 =
  22"): letters alone ("5 ångström in m") or a short word ("distance in au") are none. Particles English names carry ("de Broglie
  et al.", "le Chatelier") are no evidence alone. A word either language writes ("a",
  "in", "die", "per", "pour", "sin", "tan") counts for neither, nor does a unit ("12 um",
  "5 nA", "5.2 au"), a capitalised one- or two-letter word (an element symbol: "La", "Es")
  or a word in capitals (a label: "secant CE").

A message with no words ("1.200 + 800", "2x + 3 = 7") has no language: its numbers decide.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from app.core.validation import normalize_locale_code
from app.services.md_fence_scan import without_fences

Unreadable = Literal["other_language", "number_marks"]

# Code, links and addresses are read for neither words nor numbers (fences go through
# ``md_fence_scan``); maths ("$x = 1$", a LaTeX command) holds numbers and no language.
_CODE = re.compile(r"`[^`\n]*`|\bhttps?://\S+|(?<!\S)[^\s@]+@\S+")
_MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$|\\[A-Za-z]+", re.DOTALL)
# A word, not a unit or a label glued to a number ("2x", "991es").
_WORD = re.compile(r"(?<![^\W_])[^\W\d_]+(?![^\W_])")
_OTHER_SCRIPT_LETTERS = 2
_FOREIGN_WORDS = 2
# A lone word of another language is evidence when it is at least this long: an instruction
# or a question ("résous", "halla", "combien"), not a function word.
_LONE_WORD = 4
# Letters English does not write; a lowercase word holding one is another language's.
_FOREIGN_LETTERS = frozenset("ñçäöüßãõàâêîôûèìòùáéíóúşğıœ¿¡")
# Scripts that are maths notation or letter-like symbols, never a language: Greek (θ, λ),
# the micro, ohm, ångström and Planck signs, script and double-struck letters, and "30º"
# (a degree typed as the ordinal sign).
_NOTATION_SCRIPTS = (
    "LATIN", "GREEK", "MICRO", "OHM", "ANGSTROM", "PLANCK", "SCRIPT", "DOUBLE-STRUCK",
    "BLACK-LETTER", "MATHEMATICAL", "MODIFIER", "SUPERSCRIPT", "SUBSCRIPT", "KELVIN", "ALEF",
    "BET", "GIMEL", "MASCULINE", "FEMININE",
)  # fmt: skip

# Words Spanish, French, German, Italian, Portuguese and Turkish write in a question and
# English never does: articles, pronouns, prepositions, question words, numbers and the
# verbs that set an exercise. Words English writes too stay out: "a", "e", "o", "y", "i",
# "in", "en", "no", "do", "die", "son", "per", "pour", "sin", "tan", "del" (∇), "du" (du/dx),
# "si" (SI units), "al" ("et al."), "six", "sept", "ve" ("I've"), "mil", "hay", "media",
# "comment", "tension", "determine", and unit symbols ("um", "au"). Letters English does not
# write catch the rest.
_FOREIGN = frozenset(
    """
    el la los las una unos unas un que qué cuál cuáles cuánto cuánta cuántos cuántas cómo
    dónde cuando cuándo por para con es está están tiene tienen se halla hallar encuentra
    encontrar calcula calcular calcule resuelve resolver determina factoriza convierte
    pendiente entre grados radianes dos tres cuatro cinco seis siete ocho nueve diez cien
    valor velocidad masa fuerza tiempo distancia corriente resistencia altura volumen de
    le les des une deux trois quatre cinq huit neuf dix est sont avec dans sur sous quelle
    quel quels quelles combien calculez calculer trouvez trouver factoriser convertir résous
    résoudre résolvez simplifie simplifier développe développer dérive dériver
    moyenne pente lorsque vers nombres vitesse masse temps courant hauteur aire aux et ce
    der das dem den ein eine einen einem einer ist sind wird werden wie viel viele welche
    welcher welches berechne berechnen bestimme bestimmen gegeben mit von zu nach auf aus bei
    und oder rechne faktorisiere geschwindigkeit zeit strom spannung widerstand löse lösen
    vereinfache
    il lo gli della dello delle dei degli che sono uno quanto quanta quanti quante quale
    quali calcola calcolare trova trovare risolvi fattorizza tempo corrente di da nel nella
    tra fra
    uma uns umas os qual quais encontre resolva fatore converta velocidade em na dos pelo
    pela com
    bir ile nedir kaç kaçtır hesaplayın hesaplayınız bulun bulunuz olan olarak kütle kütlesi çöz
    zaman akım
    """.split()
)
# Words of those languages that English names carry too ("de Broglie", "le Chatelier",
# "van der Waals", "da Vinci"): one alone is no evidence.
_PARTICLES = frozenset({"de", "la", "le", "der", "von", "da", "di", "el", "et"})
# English words a question writes and the other languages do not ("was" is German, "do"
# Portuguese: neither counts).
_ENGLISH = frozenset(
    """
    the of is are were be been being to on at by for with from and or if then than that
    this these those what which who whom whose how why when where find calculate determine
    solve show prove evaluate simplify compute work out given its it his her their has have
    had does did will would can could should must many much each every
    what's how's it's there here into onto over under between after before during
    """.split()
)
# A capitalised one- or two-letter word is an element symbol ("La" is lanthanum, not "la"),
# and a word in capitals a label or an acronym ("secant CE", "LA", "EST").
_SYMBOL = re.compile(r"[A-Z][a-z]?|[A-Z]{2,}")


def _without_code(text: str) -> str:
    return _CODE.sub(" ", without_fences(text, " "))


def _other_script(char: str) -> bool:
    if not char.isalpha():
        return False
    name = unicodedata.name(char, "")
    return not name.startswith(_NOTATION_SCRIPTS)


def other_language(text: str) -> bool:
    """``text`` is written in a language other than English, on positive evidence."""
    plain = _MATH.sub(" ", _without_code(text))
    if sum(map(_other_script, plain)) >= _OTHER_SCRIPT_LETTERS:
        return True
    foreign: list[str] = []
    english = 0
    for match in _WORD.finditer(plain):
        word, folded = match.group(), match.group().casefold()
        if folded in _ENGLISH:
            english += 1
        elif _SYMBOL.fullmatch(word) or _unit(plain, match.start(), word):
            continue
        elif folded in _FOREIGN or (word == folded and _FOREIGN_LETTERS.intersection(folded)):
            foreign.append(folded)
    # Name particles alone are names: "de Broglie et al.", "le Chatelier".
    if all(word in _PARTICLES for word in foreign):
        return False
    if len(foreign) >= _FOREIGN_WORDS:
        return len(foreign) > english
    # One word of another language and none of English: "résous 3x + 7 = 22", "halla 3x + 1".
    # It must be a listed word, and not a short one: letters alone ("5 ångström in m") or a
    # short word that may be a unit or a name ("distance in au") are no evidence alone.
    word = foreign[0]
    return not english and word in _FOREIGN and len(word) >= _LONE_WORD


# A unit after a number is short ("um", "au", "mol"); "2 résistances" is a word.
_UNIT_LETTERS = 3


def _unit(text: str, start: int, word: str) -> bool:
    """A unit, not a word: short and after a number ("12 um", "5.2 au", "5 nA"), or in
    mixed case. A word with a letter English does not write is never a unit."""
    if _FOREIGN_LETTERS.intersection(word.casefold()):
        return False
    after_number = text[:start].rstrip()[-1:].isdigit() and len(word) <= _UNIT_LETTERS
    return after_number or not (word.islower() or word.istitle())


# How each app language writes 1200.5: the mark that groups thousands, the decimal mark.
# The readers read "1,200" as 1200 and "1.200" as 1.2, as English writes them.
_MARKS: dict[str, tuple[str, str]] = {
    "en": (",", "."),
    "am": (",", "."),
    "es": (".", ","),
    "de": (".", ","),
    "it": (".", ","),
    "pt": (".", ","),
    "tr": (".", ","),
    "fr": (" ", ","),
    "ru": (" ", ","),
}


def _grouped(mark: str) -> re.Pattern[str]:
    """A number with three digits after each ``mark``: "1.200", "12,345", "1 234 567"."""
    return re.compile(rf"(?<![\d.,])[1-9]\d{{0,2}}(?:{mark}\d{{3}})+(?!\d)")


_DOT_GROUPS = _grouped(r"\.")
_COMMA_GROUPS = _grouped(",")
# Groups set apart by a no-break or thin space or an apostrophe: one number, always.
_MARKED_GROUPS = _grouped("[\u00a0\u2009\u202f'\u2019]")
# Groups set apart by a plain space: one number in SI and French style ("1 200 kg",
# "20 000", "100 000"), or a list ("mean of 120 135 150").
_SPACED_GROUPS = _grouped(" ")


# What follows a quantity: its unit ("384 400 km", "299 792 458 m/s"), not a word.
_UNIT_AFTER = re.compile(r"\s?([^\W\d_][^\s,.;:!?()]{0,5})")
_NOT_UNITS = frozenset(
    "and or the to of in on at is are was were then than plus minus times with from for".split()
)


def _one_spaced_number(match: re.Match[str]) -> bool:
    """Spaced groups read as one number: a round thousand ("100 000", "1 500 000"), a short
    lead and one group ("1 200", "12 000"), or a quantity with its unit ("384 400 km").
    Three-digit numbers in a row with no unit are a list ("mean of 120 135 150")."""
    groups = match.group().split(" ")
    if groups[-1] == "000" or (len(groups) == 2 and len(groups[0]) < 3):
        return True
    unit = _UNIT_AFTER.match(match.string, match.end())
    return unit is not None and unit.group(1).casefold() not in _NOT_UNITS


def misread_number(text: str, locale: str | None) -> bool:
    """``text`` holds a number the readers would read otherwise than its writer means:
    "1.200" where a dot groups thousands (1200, not 1.2), "1,200" where a comma is the
    decimal mark (1.2, not 1200), and "1 200" anywhere (1200, not 1 and 200)."""
    group, decimal = _MARKS.get(normalize_locale_code(locale), _MARKS["en"])
    plain = _without_code(text)
    return bool(
        _MARKED_GROUPS.search(plain)
        or any(_one_spaced_number(match) for match in _SPACED_GROUPS.finditer(plain))
        or (group == "." and _DOT_GROUPS.search(plain))
        or (decimal == "," and _COMMA_GROUPS.search(plain))
    )


def unreadable(text: str, locale: str | None) -> Unreadable | None:
    """Why the subject readers cannot read ``text`` whole for a user of ``locale``, or None."""
    if other_language(text):
        return "other_language"
    if misread_number(text, locale):
        return "number_marks"
    return None
