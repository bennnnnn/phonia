# ruff: noqa: RUF001, RUF003 - the Turkish dotless i is part of language names matched below
"""The app's language, held when the user writes in it, whatever a memory says.

An English app answered "Teach me how to improve recall" in Spanish (2026-10-24): a saved
memory said "User prefers replies in Spanish". The app's language line, ranking a saved
memory last, did not hold: three replies of three stayed Spanish while the memory was in
the prompt. Reading memory facts for settings hid real ones ("User answers customer emails
in Spanish at work"), so the message is read instead, and a note beside it says to reply in
the app's language when the message is plainly written in it.

The note only ever names the app's language, so a misread message gets no note rather than
a wrong one. It is left out when the reading is unsure (one stray word: "Los Angeles
weather"; a Cyrillic name in an English line), and whenever a language is named — in the
message ("write an email in Spanish", "translate …"), earlier in the chat ("reply in
Spanish from now on", "Teach me Spanish") or in their custom instructions, in any of the
app's languages ("responde en inglés", "auf Englisch"): that choice is theirs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.core.validation import LOCALE_NAMES, normalize_locale_code
from app.modules.todos import language_evidence
from app.services.md_fence_scan import without_fences
from app.services.text_normalize import straighten_apostrophes

_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
# English words the app's other languages do not write ("was" and "will" are German, "i"
# Italian, "has" Spanish, "for" Portuguese, "me", "no", "a", "in" several).
_ENGLISH = frozenset(
    {
        "the", "is", "are", "were", "to", "of", "and", "with", "what", "how", "why", "when",
        "where", "who", "which", "my", "you", "your", "it", "this", "that", "does", "please",
        "teach", "tell", "explain", "help", "show", "give", "about", "from", "have", "not",
        "yes", "make", "want", "need", "know", "think", "should", "would", "could", "just",
        "get", "thanks", "thank", "hello", "hey", "don't", "i'm", "it's", "what's", "can't",
        "mean", "understand",
    }
)  # fmt: skip
_SCRIPTS = ("ru", "am")
_LATIN_WORDS = 2
# English words are at least this share of a message's words before it is English: "the" in
# "Quiero aprender sobre The Beatles" is a title, not the language.
_ENGLISH_SHARE = 0.3
# A short message of English words alone ("What?", "Thanks") is English too.
_SHORT_WORDS = 3
# Letters and marks English does not write: a Spanish line quoting "please send the report"
# or a Polish "Jak to działa?" is not English.
# Case is spelled out: under re.IGNORECASE the dotless "ı" matched every English "i".
_MARKS = "ñçäöüãõàâêîôûèìòùáéíóúşğœæøåłśźżćńęąčřžšěůő"
_NOT_ENGLISH_MARK = re.compile(f"[¿¡ßıİ{_MARKS}{_MARKS.upper()}]")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_NAMES = (
    r"(?:english|ingl[eé]s|anglais|englisch|inglese|ingil[iı]zce|spanish|espa[nñ]ol|"
    r"espagnol|spanisch|spagnolo|espanhol|[iı]spanyolca|french|fran[cç]ais|franc[eé]s|"
    r"franz[oö]sisch|francese|franc[eê]s|frans[iı]zca|german|deutsch|alem[aá]n|alem[aã]o|"
    r"allemand|tedesco|almanca|italian|italiano|italien|italienisch|[iı]talyanca|portuguese|"
    r"portugu[eêé]s|portugais|portugiesisch|portoghese|portekizce|russian|ruso|russe|russisch|"
    r"russo|rus[cç]a|turkish|t[uü]rk[cç]e|turco|turc|t[uü]rkisch|amharic|am[aá]rico|"
    r"amharique|amharisch|amarico|английск\w*|русск\w*|испанск\w*|французск\w*|немецк\w*|"
    r"итальянск\w*|португальск\w*|турецк\w*|амхарск\w*|እንግሊዝኛ|አማርኛ)"
)
# A language named as a language, in any app language: "in Spanish", "en inglés", "auf
# Englisch", "на английском", "по-английски", "teach me Spanish", "Spanish lessons". Not
# "Italian restaurants", "French toast" or "German shepherd".
_LANGUAGE_NAME = re.compile(
    rf"\b(?:in|into|to|en|auf|em|al|à|ins|в|на|da)\s+(?:the\s+)?{_NAMES}(?![\w-])"
    rf"|по-(?:английски|русски|испански|французски|немецки|итальянски|португальски|турецки)"
    rf"|\b(?:speak\w*|learn\w*|teach(?:\s+me)?|stud\w*|practi[cs]\w*|reply|answer|respond|"
    rf"write|talk)\s+{_NAMES}(?![\w-])"
    rf"|{_NAMES}\s+(?:please|only|from now on|lessons?|class(?:es)?|words?|grammar|vocabulary)\b",
    re.IGNORECASE,
)
# "Use my language", "responde en mi idioma": custom instructions about the reply language.
_LANGUAGE_WORD = re.compile(r"\b(?:language|idioma|langue|sprache|lingua|língua|dil)\b|язык", re.I)
_TRANSLATE = re.compile(r"\b(?:translat|tradu|[uü]bersetz|[cç]evir)\w*|перев[её]\w*", re.I)


def _english(text: str, words: list[str], evidence: dict[str, int]) -> bool:
    """English words make up a real share of the message, and nothing says otherwise."""
    if evidence or _NOT_ENGLISH_MARK.search(text):
        return False
    english = sum(word in _ENGLISH for word in words)
    if english == len(words) and 0 < english <= _SHORT_WORDS:
        return True
    return english >= _LATIN_WORDS and english >= _ENGLISH_SHARE * len(words)


def _plainly(text: str) -> str | None:
    """'en', another app language's code, or None when the message is not plainly one."""
    text = _INLINE_CODE.sub(" ", without_fences(text, " "))
    evidence = language_evidence(text)
    letters = sum(char.isalpha() for char in text)
    for code in _SCRIPTS:
        if evidence.get(code, 0) * 2 > letters:
            return code
    words = [word.casefold() for word in _WORD.findall(straighten_apostrophes(text))]
    if _english(text, words, evidence):
        return "en"
    latin = [(found, code) for code, found in evidence.items() if code not in _SCRIPTS]
    other, code = max(latin, default=(0, ""))
    english_words = any(word in _ENGLISH for word in words)
    return code if other >= _LATIN_WORDS and not english_words else None


def _names_a_language(*texts: str | None) -> bool:
    return any(isinstance(text, str) and _LANGUAGE_NAME.search(text) for text in texts)


def _instructions_name_a_language(instructions: Any) -> bool:
    if not isinstance(instructions, str):
        return False
    return bool(_names_a_language(instructions) or _LANGUAGE_WORD.search(instructions))


def reply_language_hint(
    query: str, prior: Sequence[tuple[str, str]], locale: Any, instructions: Any
) -> str | None:
    """'Write this reply in English …' when the message is plainly in the app's language."""
    earlier = [text for role, text in prior if role == "user"]
    if _instructions_name_a_language(instructions) or _TRANSLATE.search(query):
        return None
    if _names_a_language(query, *earlier):
        return None
    app = normalize_locale_code(locale if isinstance(locale, str) else None)
    if _plainly(query) != app:
        return None
    name = LOCALE_NAMES.get(app, "English")
    return (
        f"Write this reply in {name}, the language of the user's message, whatever a saved "
        "memory or an earlier reply says."
    )


def line_language(text: str, locale: Any) -> str:
    """The language of a line the server adds to the reply to ``text``: the message's own
    when it is plainly one of the app's languages (the reply follows it), else the app's.

    A German app asked in English got an English answer with a German line under it.
    """
    return _plainly(text) or normalize_locale_code(locale if isinstance(locale, str) else None)
