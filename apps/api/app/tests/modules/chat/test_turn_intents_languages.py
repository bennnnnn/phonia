"""A picture and a second request in one message: drawn beside the answer in English only.

"Draw a cat wearing a hat and also explain what a black hole is" draws the cat above the
answer. In the app's other languages the same message is answered in words, as on main:
a line beside a draw-me line is often about it ("¿Cómo se dice en inglés? Dibújame un
gato", "Dime si es educado. Dibújame un gato"), and no rule told those apart from a
second request without drawing some of them. Only a whole-message draw-me request draws.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.turn_intercepts import reply_picture_prompt, start_reply_picture
from app.modules.chat.turn_prep.intents import plan_turn
from app.tests.modules.images.test_gen_intent_languages import DRAWN

# The picture, then "… and also explain what a black hole is"; and the picture asked second.
OTHER_LANGUAGES = [
    "Dibújame un gato con sombrero y también explica qué es un agujero negro",
    "Dessine-moi un chat avec un chapeau et explique aussi ce qu'est un trou noir",
    "Zeichne mir eine Katze mit Hut und erkläre auch, was ein schwarzes Loch ist",
    "Disegnami un gatto con il cappello e spiega anche cos'è un buco nero",
    "Me desenhe um gato com chapéu e também explique o que é um buraco negro",
    "Bana şapkalı bir kedi çiz ve ayrıca kara deliğin ne olduğunu açıkla",
    "Нарисуй мне кошку в шляпе, а также объясни, что такое чёрная дыра",
    "ድመት ሳልልኝ እንዲሁም ጥቁር ቀዳዳ ምን እንደሆነ አስረዳኝ",
    "Explica qué es un agujero negro y dibújame un gato",
    "¿Qué es un agujero negro? ¿Me dibujas un gato?",
    "Erkläre, was ein schwarzes Loch ist, und zeichne mir auch eine Katze",
    "Spiegami cos'è un buco nero e disegnami un gatto",
    "Kara deliğin ne olduğunu açıkla ve bana bir kedi çiz",
    "Объясни, что такое чёрная дыра, и нарисуй мне кошку",
    "ጥቁር ቀዳዳ ምን እንደሆነ አስረዳኝ እንዲሁም ድመት ሳልልኝ",
    # One drawn request per language, then an English question.
    *(f"{cases[0][0]} and also explain what a black hole is" for cases in DRAWN.values()),
]


def _reply_picture(text: str) -> object:
    class _Plan:
        @staticmethod
        def can_use(*_args: object) -> bool:
            return True

    class _Deps:
        plan = _Plan()

    return start_reply_picture(
        _Deps(),  # type: ignore[arg-type]
        Settings(image_generation_enabled=False),
        user=User(id=uuid4(), plan="pro", locale="es"),
        chat_id=uuid4(),
        content=text,
    )


def test_an_english_picture_and_a_question_plan_as_two_parts() -> None:
    text = "Draw a cat with a hat and also explain what a black hole is"
    assert [part.kind for part in plan_turn(text).parts] == ["image", "ask"]
    assert reply_picture_prompt(text, Settings()) == "cat with a hat"
    assert _reply_picture(text) is not None


@pytest.mark.parametrize("text", OTHER_LANGUAGES)
def test_another_language_picture_beside_a_request_is_one_answer(text: str) -> None:
    assert not plan_turn(text).of_kind("image")
    assert reply_picture_prompt(text, Settings()) is None
    assert _reply_picture(text) is None


@pytest.mark.parametrize(
    "text",
    [
        # One picture of two things, a table, a graph, a bare "draw": no picture part.
        "Dibújame un gato y un perro",
        "Zeichne mir eine Tabelle der Ergebnisse und erkläre sie",
        "Нарисуй мне график функции и объясни его",
        "Bana grafik çiz ve açıkla",
        "Dibuja un gato y explica qué es un agujero negro",
    ],
)
def test_no_picture_part_for_a_table_a_graph_or_a_bare_draw(text: str) -> None:
    assert not plan_turn(text).of_kind("image")
    assert reply_picture_prompt(text, Settings()) is None
