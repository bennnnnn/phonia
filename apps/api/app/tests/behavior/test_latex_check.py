"""The STEM sweep's LaTeX check: what a reply may hold so the phone shows no source."""

from __future__ import annotations

import pytest

from app.tests.behavior.latex_check import drawn_commands, latex_problems


@pytest.mark.parametrize(
    ("reply", "problems"),
    [
        ("$v = \\frac{d}{t} = 5\\,\\mathrm{m/s}$", []),
        ("$$\\begin{aligned} a &= b \\\\ &= c \\end{aligned}$$", []),
        ("\\(\\alpha\\) and \\[\\int_0^1 x\\,dx\\]", []),
        ("```answer\n\\frac{1}{2}\n```", []),
        ("```math\n\\sqrt{2}\n```", []),
        ("`\\frac{a}{b}` is how you write it", []),
        ('```graph\n{"label": "\\u2192"}\n```', []),
        ("Then \\frac{1}{2} in prose", ["TeX outside maths: \\frac"]),
        ("The area is 25 m^{2}.", ["TeX outside maths: ^{"]),
        ("$\\nosuchcommand{x}$", ["the phone draws no \\nosuchcommand"]),
        ("```answer\n\\nosuchcommand{1}\n```", ["the phone draws no \\nosuchcommand"]),
    ],
)
def test_latex_problems_flags_what_a_reader_would_see_as_source(
    reply: str, problems: list[str]
) -> None:
    assert latex_problems(reply) == problems


def test_drawn_commands_hold_the_phones_list() -> None:
    assert {"frac", "sqrt", "mathrm", "text", "alpha", "sin", "ce", "SI"} <= drawn_commands()
