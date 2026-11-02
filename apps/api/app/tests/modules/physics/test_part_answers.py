"""A question in parts answers each part in its own card, a hairline between parts."""

from __future__ import annotations

from app.modules.chat.finalize_parts import divide_sections
from app.modules.physics.part_answers import land_part_cards

_CARDS = [r"10\,\mathrm{m/s}", r"25\,\mathrm{m}"]


def test_each_part_answer_gets_its_own_verified_card() -> None:
    reply = (
        "**(a) Final velocity**\n\n**Answer (a)**\n\n$v = 10\\,\\text{m/s}$\n\n---\n\n"
        "**(b) Distance**\n\n**Answer (b)**\nAnswer: $s = 25\\,\\text{m}$\nIt grows as t²."
    )
    assert land_part_cards(reply, _CARDS) == (
        "**(a) Final velocity**\n\n**Answer (a)**\n\n"
        "```answer\nverified: true\n10\\,\\mathrm{m/s}\n```\n\n---\n\n"
        "**(b) Distance**\n\n**Answer (b)**\n\n"
        "```answer\nverified: true\n25\\,\\mathrm{m}\n```\n\nIt grows as t²."
    )


def test_parts_that_do_not_match_the_solve_are_left_to_the_single_card() -> None:
    # One part answered, parts out of order, or a plain Answer: not this path.
    assert land_part_cards("**Answer (a)**\n$v = 10$", _CARDS) is None
    assert land_part_cards("**Answer (b)**\n$s$\n\n**Answer (a)**\n$v$", _CARDS) is None
    assert land_part_cards("**Answer**\n$v = 10$", _CARDS) is None


def test_a_hairline_sets_each_request_section_apart() -> None:
    reply = "### Weather\nSunny.\n### Solve 2x + 3 = 7\n$x = 2$\n\n---\n\n### Joke\nHa."
    assert divide_sections(reply) == (
        "### Weather\nSunny.\n\n---\n\n### Solve 2x + 3 = 7\n$x = 2$\n\n---\n\n### Joke\nHa."
    )


def test_a_heading_inside_code_is_no_section() -> None:
    reply = "### One\nx\n```text\n### not a section\n```"
    assert divide_sections(reply) == reply
