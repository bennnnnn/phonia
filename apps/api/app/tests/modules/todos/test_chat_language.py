"""Chat adds and changes to-dos only from English messages; others use To-do."""

from __future__ import annotations

import pytest

from app.modules.todos.chat_language import (
    message_language,
    todo_screen_line,
    writes_todos_in_todo_screen,
)


@pytest.mark.parametrize(
    "text",
    [
        "recuérdame mañana a las 9 llamar a mamá",
        "agrega pan a mi lista",
        "¿qué tengo hoy?",
        "rappelle-moi demain d'appeler ma mère",
        "ajoute du lait à ma liste",
        "erinnere mich morgen um 9 Uhr an den Zahnarzt",
        "ricordami domani alle 9 di chiamare la mamma",
        "lembra-me amanhã às 9 de ligar para a minha mãe",
        "yarın saat 9'da annemi aramayı hatırlat",
        "напомни завтра в 9 позвонить маме",
        "ነገ 9 ሰዓት እናቴን እንድደውል አስታውሰኝ",
    ],
)
def test_a_message_in_another_language_changes_to_dos_in_the_todo_screen(text: str) -> None:
    assert writes_todos_in_todo_screen(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "remind me to call mom tomorrow at 9",
        "add milk to my list",
        "mark the dentist done",
        # An English to-do word keeps a mixed message English.
        "remind me to call Getachew ነገ at 10am",
        "remind me to fly to Los Angeles on Friday",
        "remind me tonight at 9 to text selam happy birthday 🎂",
        "done ✅ just talked to her",
        # One word of another language is not enough to tell.
        "call mom mañana",
        "",
        "   ",
        None,
    ],
)
def test_an_english_message_still_changes_to_dos_in_chat(text: str | None) -> None:
    assert writes_todos_in_todo_screen(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "recuérdame mañana a las 9 llamar a mamá",
        "¿qué tengo hoy?",
        "rappelle-moi demain d'appeler ma mère",
        "erinnere mich morgen an den Zahnarzt",
        "ricordami domani di chiamare la mamma",
        "lembra-me amanhã de ligar para a minha mãe",
        "напомни завтра позвонить маме",
        "yarın annemi aramayı hatırlat",
        "ነገ እናቴን እንድደውል አስታውሰኝ",
    ],
)
def test_a_to_do_message_in_any_app_language_loads_the_list(text: str) -> None:
    """The list reaches the prompt, so a question is answered from it and an ask to add
    one gets the To-do button instead of a guess."""
    from app.modules.todos import query_implies_todos

    assert query_implies_todos(text) is True


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("recuérdame mañana a las 9 llamar a mamá", "es"),
        ("rappelle-moi demain d'appeler ma mère", "fr"),
        ("erinnere mich morgen um 9 Uhr an den Zahnarzt", "de"),
        ("ricordami domani alle 9 di chiamare la mamma", "it"),
        ("lembra-me amanhã às 9 de ligar para a minha mãe", "pt"),
        ("yarın saat 9'da annemi aramayı hatırlat", "tr"),
        ("напомни завтра в 9 позвонить маме", "ru"),
        ("ነገ 9 ሰዓት እናቴን እንድደውል አስታውሰኝ", "am"),
        # Another script the app has no language for, and plain English.
        ("ذكرني غدا بالاتصال بأمي", None),
        ("remind me to call mom", None),
        ("", None),
        (None, None),
    ],
)
def test_message_language_names_the_app_language_a_message_is_in(
    text: str | None, language: str | None
) -> None:
    assert message_language(text) == language


@pytest.mark.parametrize("language", ["es", "fr", "de", "it", "pt", "tr", "ru", "am"])
def test_every_app_language_has_its_own_to_do_line(language: str) -> None:
    line = todo_screen_line(language)
    assert line != todo_screen_line("en")
    # It names the screen and never claims the change was made.
    assert line.count("**") == 2


def test_an_unknown_language_gets_the_english_line() -> None:
    assert (
        todo_screen_line(None) == todo_screen_line("xx") == "You can add or change it in **To-do**."
    )


@pytest.mark.parametrize(
    ("text", "prior", "locale", "read_only"),
    [
        # An answer to a question asked in Spanish follows the chat: it never writes.
        ("a las 5", "añade comprar leche a mis tareas", "en", True),
        ("17:00", "recuérdame llamar a mamá", "en", True),
        ("sí", "напомни позвонить маме", "en", True),
        # With nothing earlier to go by, the app language decides.
        ("17:00", "", "es", True),
        ("17:00", None, "en", False),
        # An English chat, or an English to-do word, still writes.
        ("5pm", "remind me to call mom", "es", False),
        ("remind me at 5pm", "recuérdame llamar a mamá", "es", False),
        # A message with a language of its own decides alone.
        ("recuérdame mañana a las 9", "remind me to call mom", "en", True),
    ],
)
def test_a_message_with_no_language_of_its_own_follows_the_chat(
    text: str, prior: str | None, locale: str, read_only: bool
) -> None:
    assert writes_todos_in_todo_screen(text, prior_user=prior, locale=locale) is read_only
