"""Follow-up questions in the user's language: every app locale's script, and its accents."""

import pytest

from app.modules.chat.follow_up_prompts import GENERAL_SYSTEM, SHAPE, SUBJECT_SYSTEM
from app.modules.chat.related_questions import (
    accepted_questions,
    answer_excerpt,
    follow_up_topic,
    topic_anchors,
)

# A Russian and an Amharic everyday question (both app locales), each with a full reply.
PLOV = "Как приготовить плов дома?"
PLOV_REPLY = (
    "Обжарьте мясо в казане, добавьте лук и морковь соломкой, залейте водой и тушите "
    "сорок минут. Затем всыпьте промытый рис, добавьте зиру и чеснок, долейте воды на "
    "два пальца выше риса и готовьте на слабом огне под крышкой, пока вода не впитается. "
    "Дайте плову постоять пятнадцать минут и перемешайте перед подачей."
)
PLOV_FOLLOWUPS = [
    "Какой рис лучше всего подходит для плова?",
    "Сколько времени нужно тушить мясо?",
    "Можно ли приготовить плов в мультиварке?",
]
DORO = "ዶሮ ወጥ እንዴት ይሰራል?"
DORO_REPLY = (
    "ሽንኩርቱን ያለ ዘይት በደንብ ቀቅለው፣ ከዚያ ዘይትና በርበሬ ጨምረው ለረጅም ጊዜ ያብስሉት። "
    "የታጠበውን ዶሮ ጨምረው በትንሽ እሳት ያብስሉት፣ በመጨረሻም የተቀቀለ እንቁላል ይጨምሩበት። "
) * 3
DORO_FOLLOWUPS = [
    "ለዶሮ ወጥ ምን ያህል በርበሬ ያስፈልጋል?",
    "ዶሮ ወጥ ምን ያህል ጊዜ ይበስላል?",
    "እንቁላሉን መቼ ነው የምጨምረው?",
]
# French: the topic words carry accents ("pâte", "pétrir").
PAIN = "Comment faire du pain maison ?"
PAIN_REPLY = (
    "Mélangez 500 g de farine, 350 ml d'eau tiède, 7 g de levure et 10 g de sel. "
    "Pétrissez la pâte dix minutes, laissez-la lever deux heures, puis façonnez le pain "
    "et faites-le cuire à 230 degrés pendant trente minutes, avec un bol d'eau dans le four. "
    "Laissez-le refroidir une heure avant de le couper."
)
PAIN_FOLLOWUPS = [
    "Combien de temps faut-il pétrir la pâte ?",
    "Pourquoi ma pâte ne lève-t-elle pas ?",
    "Peut-on utiliser de la farine complète ?",
]


def _kept(question: str, answer: str, candidates: list[str]) -> list[str]:
    """What the server keeps of the model's candidates for an everyday question."""
    assert follow_up_topic(question, answer, None, allow_general=True) == ("general", None)
    return accepted_questions(
        question, candidates, None, topic_anchors(question, answer_excerpt(answer))
    )


@pytest.mark.parametrize(
    ("question", "answer", "followups"),
    [
        (PLOV, PLOV_REPLY, PLOV_FOLLOWUPS),
        (DORO, DORO_REPLY, DORO_FOLLOWUPS),
        (PAIN, PAIN_REPLY, PAIN_FOLLOWUPS),
    ],
    ids=["russian", "amharic", "french"],
)
def test_follow_ups_in_the_users_language_are_kept(
    question: str, answer: str, followups: list[str]
) -> None:
    # All three on the first ask: three or none, and no second model call.
    assert _kept(question, answer, followups) == followups


def test_an_off_topic_accented_follow_up_still_leaves() -> None:
    off_topic = "Quelle est la capitale de la Belgique ?"
    assert _kept(PAIN, PAIN_REPLY, [off_topic, *PAIN_FOLLOWUPS]) == PAIN_FOLLOWUPS


def test_every_follow_up_prompt_names_the_users_language() -> None:
    assert "language" in SHAPE
    assert SHAPE in SUBJECT_SYSTEM
    assert SHAPE in GENERAL_SYSTEM
