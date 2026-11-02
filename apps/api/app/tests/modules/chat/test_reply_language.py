"""A message plainly in the app's language is answered in it, whatever a memory says.

With "User prefers replies in Spanish" saved, an English app's "Teach me how to improve
recall" was answered in Spanish three times in three, though the language line ranked a
saved memory last (2026-10-24). The note beside the message names the app's language, and
only that: a misread message gets no note, never a wrong one.
"""

from __future__ import annotations

import pytest

from app.modules.chat.reply_language import reply_language_hint


@pytest.mark.parametrize(
    ("query", "locale", "language"),
    [
        ("Teach me how to improve recall", "en", "English"),
        ("What?", "en", "English"),
        ("What’s my name?", "en", "English"),  # the iPhone's apostrophe
        ("TypeError: NoneType object is not subscriptable", "en", "English"),
        ("Write a two-line email to my landlord saying the rent is late", "en", "English"),
        ("Explain `for i in range(10)` to me please", "en", "English"),
        ("¿Qué es la fotosíntesis? ¿Y cómo funciona en las plantas?", "es", "Spanish"),
        ("Привет, как дела?", "ru", "Russian"),
    ],
)
def test_a_message_plainly_in_the_apps_language_is_answered_in_it(
    query: str, locale: str, language: str
) -> None:
    hint = reply_language_hint(query, [], locale, None)
    assert hint is not None and hint.startswith(f"Write this reply in {language},")


@pytest.mark.parametrize(
    ("query", "locale"),
    [
        # One stray word is no language: names, places, a loanword.
        ("Los Angeles weather", "en"),
        ("MIT admission requirements", "en"),
        ("Des Moines restaurants", "en"),
        ("Hey, ¿qué tal?", "en"),
        ("Necesito help con mi tarea", "en"),
        # Words two languages share: German "was", Italian "i", Spanish "has".
        ("Was ist das?", "en"),
        ("Was ist das?", "de"),
        ("Quali sono i migliori libri?", "en"),
        ("¿Has visto la película?", "en"),
        # English titles, quotes and code inside another language, and languages the app
        # does not offer, whose "to" and "is" read as English.
        ("Quiero aprender sobre The Beatles y su historia", "en"),
        ("Hazme un resumen de la serie How I Met Your Mother", "en"),
        ('Mi jefe me dijo: "please send the report by Friday". ¿Cómo le respondo?', "en"),
        ("¿Por qué falla esta consulta? SELECT * FROM users WHERE id IS NOT NULL", "en"),
        ("Co to jest fotosynteza?", "en"),
        ("Wat is fotosynthese?", "en"),
        ("Ek het my sleutels verloor", "en"),
        ("El Paso to Los Angeles flights", "es"),
        # The dotless i of Turkish is not every English "i".
        ("Is my CV good? I'm applying in İstanbul", "en"),
        # A word in another script is not the message's language.
        ("Remind me to call Дмитрий tomorrow", "en"),
        ("remind me to call Getachew ነገ at 10am", "en"),
        # Not the app's language, or no language at all.
        ("¿Qué es la fotosíntesis? ¿Y cómo funciona en las plantas?", "en"),
        ("Mi código: for i in range(10): print(i)", "es"),
        ("ok", "en"),
        ("17:00", "en"),
        ("👍", "en"),
    ],
)
def test_a_message_not_plainly_in_the_apps_language_gets_no_note(query: str, locale: str) -> None:
    assert reply_language_hint(query, [], locale, None) is None


@pytest.mark.parametrize(
    "query",
    [
        "Write an email in Spanish to my landlord",
        "Answer in French: what is a verb?",
        "translate good morning to Spanish",
        "Reply in Spanish from now on",
    ],
)
def test_a_message_that_names_a_language_chooses_it(query: str) -> None:
    assert reply_language_hint(query, [], "en", None) is None


@pytest.mark.parametrize(
    "earlier",
    ["reply in Spanish from now on", "Contéstame en inglés a partir de ahora", "Teach me Spanish"],
)
def test_a_language_named_earlier_in_the_chat_stays_theirs(earlier: str) -> None:
    """Only as a language: "Best Italian restaurants near me?" names none."""
    prior = [("user", earlier), ("assistant", "¡Claro!")]
    assert reply_language_hint("Teach me how to improve recall", prior, "en", None) is None


@pytest.mark.parametrize(
    "instructions",
    ["Always answer in Amharic.", "Responde siempre en inglés.", "Antworte immer auf Englisch."],
)
def test_custom_instructions_naming_a_language_win(instructions: str) -> None:
    query = "Teach me how to improve recall"
    assert reply_language_hint(query, [], "en", instructions) is None


def test_other_custom_instructions_leave_the_note() -> None:
    assert reply_language_hint("Teach me how to improve recall", [], "en", "Be brief.")


@pytest.mark.parametrize(
    "earlier", ["Best Italian restaurants near me?", "How do I make French toast?"]
)
def test_a_language_word_as_an_adjective_names_no_language(earlier: str) -> None:
    prior = [("user", earlier), ("assistant", "Here you go.")]
    assert reply_language_hint("Teach me how to improve recall", prior, "en", None)
