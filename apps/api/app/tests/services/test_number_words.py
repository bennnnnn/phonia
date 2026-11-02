"""One table of count words: every reader counts as far as the others.

Nine private copies stopped at six, ten, twelve or fourteen: "six notebooks" was a
change-from-payment problem and "seven notebooks" was not (code-health audit DUP-06).
"""

from __future__ import annotations

import re

import pytest

from app.modules.chat.recurring_pay import _parse_interval_days
from app.modules.math.tools.school.shopping import extract_change_intent
from app.services.number_text import NUMBER_WORDS, count_word_pattern, number_word_value
from app.services.time_context import relative_day_offset

_ONE_TO_TWELVE = [word for word, value in NUMBER_WORDS.items() if 1 <= value <= 12]


def test_the_pattern_tries_the_longer_word_first() -> None:
    pattern = re.compile(rf"(?:{count_word_pattern(high=20)})")
    assert pattern.match("fourteen").group(0) == "fourteen"  # type: ignore[union-attr]
    assert number_word_value("Seven") == 7
    assert number_word_value("seventh") is None


@pytest.mark.parametrize("word", _ONE_TO_TWELVE)
def test_a_purchase_counts_any_number_word(word: str) -> None:
    question = (
        f"I bought {word} notebooks at $2 each. I paid with a $50 bill. How much change do I get?"
    )
    assert extract_change_intent(question) is not None


@pytest.mark.parametrize("word", _ONE_TO_TWELVE)
def test_a_day_offset_counts_any_number_word(word: str) -> None:
    assert relative_day_offset(f"{word} days ago") == -NUMBER_WORDS[word]


@pytest.mark.parametrize("word", _ONE_TO_TWELVE)
def test_a_pay_interval_counts_any_number_word(word: str) -> None:
    assert _parse_interval_days(f"I get paid every {word} days") == NUMBER_WORDS[word]
