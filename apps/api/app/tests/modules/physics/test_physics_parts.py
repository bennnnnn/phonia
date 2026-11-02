"""A physics question in parts: each part worked on its own, with its own answer card."""

from __future__ import annotations

import re

import pytest

from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.fence import validate_physics_fences
from app.tests.modules.physics.test_physics_presentation import _verified


@pytest.mark.parametrize(
    ("question", "titles", "cards"),
    [
        (
            "A car accelerates from rest at 2 m/s^2 for 5 s. "
            "Find its final velocity and the distance covered.",
            ["(a) Final velocity", "(b) Distance"],
            [r"10\,\mathrm{m/s}", r"25\,\mathrm{m}"],
        ),
        (
            "A ball is launched at 20 m/s at 30 degrees above the horizontal. "
            "Find the time of flight and the range.",
            ["(a) Time of flight", "(b) Range"],
            [r"2.04\,\mathrm{s}", r"35.3\,\mathrm{m}"],
        ),
    ],
)
def test_each_part_is_worked_and_answered_on_its_own(
    question: str, titles: list[str], cards: list[str]
) -> None:
    verified = _verified(question)
    reply = maybe_direct_physics_reply(verified, question)
    assert reply is not None
    # The givens and what is asked once; then each part, a hairline between.
    assert reply.count("**Given**") == 1 and reply.count("**Required**") == 1
    assert [f"**{title}**" in reply for title in titles] == [True, True]
    assert reply.count("\n---\n") == 1
    sections = reply.split("\n---\n")
    for letter, section, card in zip("ab", sections, cards, strict=True):
        assert section.count("**Substitution**") == 1
        assert f"**Answer ({letter})**\n\n```answer\n{card}\n```" in section
    # No plain Answer, no card holding both values.
    assert "**Answer**" not in reply
    assert ";\\quad" not in reply
    # Finalized, each part keeps its own card, now marked as the server's.
    final = validate_physics_fences(reply, verified=verified, correct=False)
    found = re.findall(r"```answer\nverified: true\n(.+)\n```", final)
    assert found == cards


def test_the_solve_keeps_its_picture_in_its_own_section() -> None:
    question = "A car accelerates from rest at 2 m/s^2 for 5 s. Find its final velocity."
    verified = _verified(question)
    reply = (
        "### Car\n\n**Answer**\n\n$v = 10\\,\\text{m/s}$\n\n---\n\n"
        "### Joke Time\n\nWhy did the scarecrow win an award?"
    )
    final = validate_physics_fences(reply, verified=verified)
    if "```graph" in final or "```simulation" in final:
        picture = min(i for i in (final.find("```graph"), final.find("```simulation")) if i >= 0)
        assert picture < final.index("### Joke Time")
    assert final.rstrip().endswith("Why did the scarecrow win an award?")
