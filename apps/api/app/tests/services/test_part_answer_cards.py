"""A reply in parts the server did not verify: each part's answer in its own card
(2026-10-30, a crane's energy and power sat on the phone as plain lines)."""

import pytest

from app.services.part_answer_cards import land_part_answer_cards

_CRANE = """**Given**
$m = 450\\ \\text{kg}$

**(a) Potential energy**

**Substitution**
$E_p = 450 \\cdot 10 \\cdot 50$
$E_p = 225000\\ \\text{J}$

**Answer (a)**

$E_p = 225000\\ \\text{J}$

---

**(b) Power developed**

**Substitution**
$P = \\dfrac{225000}{5}$

**Answer (b)**

$P = 45000\\ \\text{W}$

**Check**
$45000 \\cdot 5 = 225000$"""


def test_each_part_gets_its_own_card() -> None:
    landed = land_part_answer_cards(_CRANE)
    assert landed is not None
    assert (
        "**Answer (a)**\n\n```answer\nverified: false\n$E_p = 225000\\ \\text{J}$\n```\n\n---"
        in landed
    )
    assert (
        "**Answer (b)**\n\n```answer\nverified: false\n$P = 45000\\ \\text{W}$\n```\n\n**Check**"
        in landed
    )
    # The working above each Answer and the check after it stay as written.
    assert "$E_p = 450 \\cdot 10 \\cdot 50$" in landed
    assert landed.endswith("**Check**\n$45000 \\cdot 5 = 225000$")
    assert "verified: true" not in landed


def test_landing_twice_adds_nothing() -> None:
    landed = land_part_answer_cards(_CRANE)
    assert landed is not None
    assert land_part_answer_cards(landed) is None


def test_a_part_already_carded_keeps_its_card() -> None:
    reply = (
        "**Answer (a)**\n\n```answer\nverified: true\n12.3\\,\\mathrm{N}\n```\n\n"
        "**Answer (b)**\n$N = 49.05\\ \\text{N}$"
    )
    landed = land_part_answer_cards(reply)
    assert landed is not None
    assert landed.count("```answer") == 2
    assert landed.startswith("**Answer (a)**\n\n```answer\nverified: true\n12.3")


def test_a_part_answered_in_words_stays_prose() -> None:
    reply = "**Answer (a)**\nThe acceleration doubles.\n\n**Answer (b)**\n$a = 4\\ \\text{m/s}^2$"
    landed = land_part_answer_cards(reply)
    assert landed is not None
    assert "**Answer (a)**\nThe acceleration doubles." in landed
    assert landed.count("```answer") == 1


_PARTS = "**Answer (a)**\n$t = 2\\ \\text{s}$\n\n**Answer (b)**\n$v = 19.6\\ \\text{m/s}$\n\n"


# Review (2026-10-30): a closing heading in any spelling ended no part, so the last part
# lost its card, or the closing summary was carded as that part's answer.
@pytest.mark.parametrize(
    "closing",
    [
        "**Answer**\nIt lands after 2 s at 19.6 m/s.",
        "**Answer:** It lands after 2 s at 19.6 m/s.",
        "## Answer\nIt lands after 2 s.",
        "Answer: It lands after 2 s.",
        "**Answer:** $t = 2$ s, $v = 19.6$ m/s",
        "## Answer\n$v = 15\\ \\text{m/s}$",
    ],
)
def test_a_closing_answer_after_the_parts_is_left_as_written(closing: str) -> None:
    landed = land_part_answer_cards(_PARTS + closing)
    assert landed is not None
    assert "**Answer (a)**\n\n```answer\nverified: false\n$t = 2\\ \\text{s}$\n```" in landed
    assert "**Answer (b)**\n\n```answer\nverified: false\n$v = 19.6\\ \\text{m/s}$\n```" in landed
    assert landed.endswith(closing)
    assert landed.count("```answer") == 2


@pytest.mark.parametrize(
    "label", ["**Answer:** ", "Answer: ", "## Answer\n"], ids=["bold", "plain", "atx"]
)
def test_an_answer_line_right_under_the_last_part_is_that_parts(label: str) -> None:
    reply = f"**Answer (a)**\n$t = 2\\ \\text{{s}}$\n\n**Answer (b)**\n{label}$v = 19.6\\ \\text{{m/s}}$"
    landed = land_part_answer_cards(reply)
    assert landed is not None
    assert landed.endswith(
        "**Answer (b)**\n\n```answer\nverified: false\n$v = 19.6\\ \\text{m/s}$\n```"
    )


def test_parts_answered_in_words_leave_the_closing_answer_to_the_one_card() -> None:
    # No part gains a card: the reply's closing Answer is carded as before.
    reply = (
        "**Answer (a)**\nThe acceleration doubles.\n\n**Answer (b)**\nIt halves.\n\n"
        "**Answer**\n$a = 4\\ \\text{m/s}^2$"
    )
    assert land_part_answer_cards(reply) is None


@pytest.mark.parametrize(
    "reply",
    [
        "**Answer**\n$x = 3$",
        "**Answer (a)**\n$x = 3$",
        "Answer (a) and (b) below.\n$x = 3$",
        # An example of the layout inside a code block is no part.
        "Format it like this:\n\n```markdown\n**Answer (a)**\n$x = 3$\n\n**Answer (b)**\n"
        "$y = 4$\n```\n\nThat is all.",
        "```text\n**Answer (b)**\n$y = 4$\n```\n\n**Answer (b)**\n$y = 4$",
    ],
)
def test_a_reply_not_in_parts_is_not_ours(reply: str) -> None:
    assert land_part_answer_cards(reply) is None
