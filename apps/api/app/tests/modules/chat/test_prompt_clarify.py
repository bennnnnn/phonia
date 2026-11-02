"""Which turns may ask with a clarify card: open questions, not a set shape."""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import (
    CLARIFICATION_HINT,
    CLARIFY_CARD_HINT,
    COMPARISON_FORMAT_HINT,
)
from app.modules.chat.prompt_constants.clarify import RANKING_FORMAT_HINT
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.turn_reading.clarify import names_its_purpose


def _hints(query: str, *, multi: bool = False) -> list[str]:
    return _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        multi=multi,
    )


@pytest.mark.parametrize(
    "query",
    [
        "how can I understand integrals",
        "What is the best country",
        "which laptop should I buy",
        "plan my week",
        "help me understand recursion",
    ],
)
def test_an_open_question_may_ask_with_a_card(query: str) -> None:
    hints = _hints(query)
    assert CLARIFY_CARD_HINT in hints
    assert CLARIFICATION_HINT in hints


@pytest.mark.parametrize(
    "query",
    [
        # A problem, a lesson, a draft with its purpose, pasted code.
        "solve 2x + 5 = 17",
        "teach me python",
        "write an email to my landlord asking him to fix the heating",
        "why does this fail?\n```python\nprint(1/0)\n```",
    ],
)
def test_a_turn_with_its_own_shape_does_not_ask(query: str) -> None:
    assert CLARIFY_CARD_HINT not in _hints(query)


@pytest.mark.parametrize(
    "query",
    [
        # Asked with a card after three suggestions: business was the "best for what".
        "What are the best countries for business",
        "best laptop for coding",
        "best phone under $500",
        "what's the best way to learn Spanish",
        "best country to live in",
        "top universities for computer science",
        "which laptop should I buy for video editing",
        "best restaurants in Paris",
    ],
)
def test_a_best_question_that_says_what_it_is_for_does_not_ask(query: str) -> None:
    assert names_its_purpose(query)
    hints = _hints(query)
    assert CLARIFY_CARD_HINT not in hints
    # Answered as picks: the reply came back as four paragraphs of countries.
    assert RANKING_FORMAT_HINT in hints


@pytest.mark.parametrize(
    "query",
    [
        "What is the best country?",
        "What's the best country for me?",
        "which laptop should I buy?",
        "best country in the world",
        "who is the best footballer ever",
    ],
)
def test_a_best_question_without_a_purpose_names_none(query: str) -> None:
    assert not names_its_purpose(query)
    assert RANKING_FORMAT_HINT not in _hints(query)


@pytest.mark.parametrize(
    "query",
    [
        "compare the best laptops for coding in a table",
        "best countries for business in one paragraph",
        "best laptops for coding vs gaming",
        "chart the best countries for business by tax rate",
    ],
)
def test_a_shape_they_asked_for_wins_over_the_ranking_list(query: str) -> None:
    assert RANKING_FORMAT_HINT not in _hints(query)


def test_a_multi_part_message_does_not_ask() -> None:
    assert CLARIFY_CARD_HINT not in _hints("plan my week and tell me a joke", multi=True)


_CARD_REPLY = (
    "**But let me ask you one thing.**\n\nWhat do you mean by *best*?\n\n```clarify\n"
    '{"request":"Recommend the best country for me.","questions":[{"id":"priority",'
    '"label":"Main priority","question":"What matters most to you?","options":'
    '["💰 Making money","🌿 Quality of life"]},{"id":"region","label":"Geographic preference",'
    '"question":"Which region are you considering?","options":["🌍 Anywhere","🇪🇺 Europe"]}],'
    '"closing":"Compare the strongest options with practical pros and cons.",'
    '"submit":"Find my best country"}\n```'
)
_AFTER_CARD = [("user", "What is the best country"), ("assistant", _CARD_REPLY)]
_PICKS = (
    "Recommend the best country for me. Main priority: Making money. Geographic preference: "
    "Anywhere. Compare the strongest options with practical pros and cons."
)


def test_the_picks_get_the_answer_not_another_card() -> None:
    hints = _style_format_hints(
        query_text=_PICKS,
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=_AFTER_CARD,
    )
    assert CLARIFY_CARD_HINT not in hints
    # The reply opens with its recommendation: the card's "compare ... pros and cons" is
    # not an X-vs-Y turn that leads with a table.
    assert COMPARISON_FORMAT_HINT not in hints


def test_a_message_typed_after_a_card_asks_nothing_either() -> None:
    # The turn after a card answers; asking again ignored what the user just said.
    hints = _style_format_hints(
        query_text="which laptop should I buy",
        is_day_plan=False,
        minimal_personal_context=False,
        prior_messages=_AFTER_CARD,
    )
    assert CLARIFY_CARD_HINT not in hints


def test_the_same_words_without_a_card_still_compare() -> None:
    hints = _style_format_hints(
        query_text=_PICKS, is_day_plan=False, minimal_personal_context=False
    )
    assert COMPARISON_FORMAT_HINT in hints
