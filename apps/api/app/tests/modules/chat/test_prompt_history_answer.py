"""A verified answer stays in the model's history as a line, never as a card, and never
under a second Answer label."""

import pytest

from app.modules.chat.prompt_window import strip_prompt_owned_fences


@pytest.mark.parametrize(
    ("reply", "history"),
    [
        ("```answer\nverified: true\nx = 6\n```", "Answer: x = 6\n"),
        (
            "**Answer**\n\n```answer\nverified: true\nnotation: chemistry\npH = 2.00\n```\nDone.",
            "**Answer**\n\npH = 2.00\nDone.",
        ),
        # Under its heading the value needs no second label, and LaTeX stays maths:
        # follow-ups copied "Answer: 26.3\\,\\mathrm{N·m}" as text under **Answer**.
        (
            "**Answer**\n\n```answer\nverified: true\n26.3\\,\\mathrm{N·m}\n```\nSince …",
            "**Answer**\n\n$26.3\\,\\mathrm{N·m}$\nSince …",
        ),
        ("```answer\nverified: true\nx = \\frac{1}{2}\n```", "Answer: $x = \\frac{1}{2}$\n"),
        # Other solver and search fences are still dropped.
        ('Area is 12.\n```graph\n{"points": []}\n```', "Area is 12.\n"),
    ],
)
def test_history_keeps_the_verified_value_as_a_line(reply: str, history: str) -> None:
    assert strip_prompt_owned_fences(reply) == history


def test_history_never_carries_the_verified_marker() -> None:
    stripped = strip_prompt_owned_fences("```answer\nverified: true\nx = 6\n```")
    assert "verified" not in stripped and "```" not in stripped
