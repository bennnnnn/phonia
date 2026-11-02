"""A to-do change asked in another language gets the To-do button from the server."""

from __future__ import annotations

import pytest

from app.modules.todos.chat_language import todo_screen_answer
from app.modules.todos.write_asks import asks_to_change_todos, todo_screen_reply

_BUTTON = "Puedes añadirlo o cambiarlo en **Tareas**.\n\n```todo_link\n```"


@pytest.mark.parametrize(
    "text",
    [
        "recuérdame mañana a las 9 llamar a mamá",
        "añade comprar leche a mis tareas",
        "agrega pan a mi lista",
        "¿puedes añadir leche a mi lista?",
        "pon un recordatorio para el lunes",
        "rappelle-moi demain d'appeler ma mère",
        "ajoute du lait à ma liste",
        "erinnere mich morgen um 9 Uhr an den Zahnarzt",
        "füge Milch zu meiner Liste hinzu",
        "lösche den Zahnarzt aus meinen Aufgaben",
        "ricordami domani alle 9 di chiamare la mamma",
        "aggiungi il latte alla mia lista",
        "lembra-me amanhã às 9 de ligar para a minha mãe",
        "adiciona leite à minha lista",
        "yarın saat 9'da annemi aramayı hatırlat",
        "süt almayı listeme ekle",
        "напомни завтра в 9 позвонить маме",
        "добавь молоко в список",
        "ነገ 9 ሰዓት እናቴን እንድደውል አስታውሰኝ",
        "ወተት ወደ ዝርዝሬ ጨምር",
    ],
)
def test_a_to_do_change_in_another_language_is_read_as_one(text: str) -> None:
    assert asks_to_change_todos(text) is True


@pytest.mark.parametrize(
    "text",
    [
        # Reading the list.
        "¿qué tengo hoy?",
        "qu'est-ce que j'ai aujourd'hui ?",
        "was habe ich heute?",
        "cosa ho oggi?",
        "o que tenho hoje?",
        "bugün neler var?",
        "что у меня сегодня?",
        "ዛሬ ምን አለኝ?",
        # Everyday words the to-do ones share: homework, a recipe, a maths problem,
        # "I remember", a playlist, a brand, "details".
        "ayúdame con mi tarea de matemáticas",
        "añade un ejemplo a mi tarea",
        "añade sal a la receta",
        "añade todo a la mezcla",
        "pon música de mi lista",
        "¿qué marca de leche está en mi lista?",
        "elimina los errores de este texto",
        "recuerdo cuando era niño",
        "je me rappelle de mon enfance",
        "ajoute du sel à la sauce",
        "ich erinnere mich an meine Kindheit",
        "füge einen Absatz hinzu",
        "mi ricordo di te",
        "aggiungi sale alla pasta",
        "você lembra de mim?",
        "adiciona sal à receita",
        "çaya biraz şeker ekle",
        "добавь условие в задачу",
        "реши задачу про поезд",
        "ዝርዝር መረጃ ጨምር",
        "",
        None,
    ],
)
def test_reading_or_an_everyday_ask_is_not_a_to_do_change(text: str | None) -> None:
    assert asks_to_change_todos(text) is False


@pytest.mark.parametrize(
    ("text", "after_button", "asks"),
    [
        # After the button, a time or a yes is the same request again.
        ("a las 5", True, True),
        ("17:00", True, True),
        ("sí, mañana", True, True),
        # A question is a new one; without the button, a time is just a time.
        ("¿cuánto es 2+2?", True, False),
        ("¿a qué hora es mi cita?", True, False),
        ("a las 5", False, False),
        ("gracias", True, False),
    ],
)
def test_a_time_after_the_button_asks_again(text: str, after_button: bool, asks: bool) -> None:
    prior = _BUTTON if after_button else "Hola."
    assert asks_to_change_todos(text, prior_assistant=prior) is asks


def test_the_server_answers_a_spanish_ask_with_the_button() -> None:
    assert todo_screen_reply("añade comprar leche a mis tareas") == _BUTTON
    assert todo_screen_reply("напомни позвонить маме") == todo_screen_answer("ru")


@pytest.mark.parametrize(
    ("text", "prior_user", "prior_assistant", "locale"),
    [
        # English writes in chat: the model answers and the card is the user's to tap.
        ("remind me to call mom at 9", None, None, "es"),
        ("add milk to my list", None, None, "en"),
        # Another language that isn't a change: the model answers from the list.
        ("¿qué tengo hoy?", None, None, "en"),
        # A time in an English chat.
        ("5pm", "remind me to buy milk", "What time?", "en"),
    ],
)
def test_the_model_answers_everything_else(
    text: str, prior_user: str | None, prior_assistant: str | None, locale: str
) -> None:
    reply = todo_screen_reply(
        text, prior_user=prior_user, prior_assistant=prior_assistant, locale=locale
    )
    assert reply is None


def test_a_time_after_the_button_in_a_spanish_chat_gets_it_again() -> None:
    reply = todo_screen_reply(
        "a las 5", prior_user="añade leche a mis tareas", prior_assistant=_BUTTON, locale="en"
    )
    assert reply == _BUTTON
