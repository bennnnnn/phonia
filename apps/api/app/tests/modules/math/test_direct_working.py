"""A direct reply writes its working above the answer card, which holds the answer alone."""

from __future__ import annotations

import pytest

from app.modules.math.tools.direct_working import typeset_working, working_above_card


def test_a_reply_that_was_only_its_card_shows_the_working_above_it() -> None:
    reply = "```answer\n1 ÷ 2 + 1 ÷ 4 = \\frac{3}{4}\n```\n"
    assert working_above_card(reply, "What if it was 1/2 + 1/4?") == (
        "$\\frac{1}{2} + \\frac{1}{4}$\n\n```answer\n\\frac{3}{4}\n```\n"
    )


def test_the_working_is_its_own_paragraph_after_text_above_the_card() -> None:
    reply = "4 rows of 4 strawberries make 16 strawberries.\n```answer\n4 × 4 = 16\n```\n"
    assert working_above_card(reply, "what is 4 x 4") == (
        "4 rows of 4 strawberries make 16 strawberries.\n\n$4 \\times 4$\n\n```answer\n16\n```\n"
    )


def test_a_card_header_stays_with_the_card() -> None:
    reply = "```answer\nverified: true\n5! = 5 × 4 × 3 × 2 × 1 = 120\n```"
    assert working_above_card(reply, "5!") == (
        "$5! = 5 \\times 4 \\times 3 \\times 2 \\times 1$\n\n```answer\nverified: true\n120\n```"
    )


@pytest.mark.parametrize(
    "reply", ["```answer\nx = 1\n```\n", "**Answer**\n```answer\n\\frac{5}{6}\n```\n", "No card."]
)
def test_a_reply_without_working_is_unchanged(reply: str) -> None:
    assert working_above_card(reply, "solve 2x + 3 = 5") == reply


@pytest.mark.parametrize(
    ("working", "user_text", "typeset"),
    [
        ("1 ÷ 2 + 1 ÷ 3", "1/2 + 1/3", "\\frac{1}{2} + \\frac{1}{3}"),
        ("1 ÷ 2 + 1 ÷ 4", "What if it was 1 / 2 + 1/4?", "\\frac{1}{2} + \\frac{1}{4}"),
        # The user divided: the sign stays, misspelt or not.
        ("12 ÷ 4", "12 ÷ 4", "12 \\div 4"),
        ("12 ÷ 4", "12 divided by 4", "12 \\div 4"),
        ("59595 ÷ 54", "59595 devided by 54", "59595 \\div 54"),
        # A chain of divisions is not a fraction.
        ("12 ÷ 3 ÷ 2", "12/3/2", "12 \\div 3 \\div 2"),
        ("1.5 ÷ 3", "1.5/3", "1.5 \\div 3"),
        ("8 − 8 · 2", "8-8*2", "8 - 8 \\cdot 2"),
    ],
)
def test_typeset_working(working: str, user_text: str, typeset: str) -> None:
    assert typeset_working(working, user_text) == typeset
