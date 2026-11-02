"""A wrong model number must not hide or silently contradict the verified card.

The card used to be withheld whenever the prose "already stated" the answer —
by substring (``12.75`` inside ``112.75``) — or stated a *different* ``x =``
(the conflict guard), so a reply ending ``x = 7`` beside a verified ``x = 6``
shipped with no card at all. Now the card always lands under the reply's
**Answer** heading, and a conflicting final value gets one short correction
line right above it.
"""

from __future__ import annotations

import pytest

from app.modules.math.fence import validate_math_fences
from app.services.answer_fence import VERIFIED_ANSWER_MARKER
from app.services.solving import VerifiedMathBlock


def _verified(answer: str) -> VerifiedMathBlock:
    return VerifiedMathBlock(
        text="unused",
        canonical_fence={"type": "answer", "content": answer},
        canonical_answer=answer,
    )


def _card(answer: str) -> str:
    return f"```answer\n{VERIFIED_ANSWER_MARKER}\n{answer}\n```"


_WRONG = [
    (
        "x = 6",
        "**1. Subtract 5 from both sides**\n$2x + 5 - 5 = 17 - 5$\n$2x = 14$\n\n"
        "**2. Divide both sides by 2**\n$x = 7$\n\nEach move keeps both sides equal.",
    ),
    ("x = 6", "Subtract 5 to get 2x = 14, then divide by 2, so x = 7."),
    ("x = 6", "Subtract 5, then divide by 2: $x = 7$.\n\nWant to try a harder one?"),
    ("12.75", "**Substitution**  \n$0.15 \\times 85$\n\n**Answer**  \n$12.25$"),
    ("12.75", "**Substitution**  \n$0.15 \\times 85$\n\n**Answer**  \n$12.755$"),
    ("12.75", "15% of 85 is $112.75$."),
    ("12.75", "15% of 85 is $12.25$. Want to see the shortcut with 10% + 5%?"),
    ("x = 2 \\text{ or } x = 3", "Factor: $(x-2)(x-3) = 0$, so $x = 3$."),
    ("x = 2 \\text{ or } x = 3", "Factor: $(x+2)(x+3) = 0$, so $x = -2$ or $x = -3$."),
    ("x = 0", "The correct equation is $2x + 3 = 7$.\n\n**Solution:** $x = 2$"),
]


@pytest.mark.parametrize(("answer", "prose"), _WRONG)
def test_a_wrong_final_value_gets_the_card_and_one_correction_line(answer: str, prose: str) -> None:
    out = validate_math_fences(prose, verified=_verified(answer))
    assert out.count(_card(answer)) == 1, out
    correction = f"The verified answer is ${answer}$."
    assert out.count(correction) == 1
    # The correction sits directly above the card, after the model's own text.
    assert out.index(correction) < out.index(_card(answer))
    assert out.rstrip().endswith(_card(answer))


@pytest.mark.parametrize(
    ("answer", "prose"),
    [
        ("x = 6", "Subtract 5, then divide by 2: $x = 6$."),
        ("x = 6", "Divide by 2: $x = 6.0$."),
        ("x = 2 \\text{ or } x = 3", "Factor: $(x-2)(x-3) = 0$, so $x = 2$ or $x = 3$."),
        ("12.75", "15% of 85 is $12.75$. Want to see the shortcut?"),
        ("2.02 s", "The ball lands at $t = 2.02$ s."),
    ],
)
def test_the_same_full_answer_in_prose_still_gets_the_card_once(answer: str, prose: str) -> None:
    out = validate_math_fences(prose, verified=_verified(answer))
    assert out.count(_card(answer)) == 1
    assert out.rstrip().endswith("**Answer**\n\n" + _card(answer))
    assert "The verified answer is" not in out


def test_a_coarser_rounding_gets_the_card_without_a_correction() -> None:
    out = validate_math_fences("15% of 85 is about $12.8$.", verified=_verified("12.75"))
    assert _card("12.75") in out
    assert "The verified answer is" not in out


def test_a_model_answer_fence_is_replaced_in_place_and_flagged_when_prose_disagrees() -> None:
    prose = "**2. Divide both sides by 2**\n$x = 7$\n\n```answer\nx = 7\n```\n\nThat's it."
    out = validate_math_fences(prose, verified=_verified("x = 6"))
    assert out.count("```answer") == 1
    assert _card("x = 6") in out
    assert out.index("The verified answer is $x = 6$.") < out.index(_card("x = 6"))
    assert "That's it." in out


def test_answer_fences_past_the_cap_are_demoted_not_left_as_cards() -> None:
    fences = "\n\n".join(f"```answer\nx = {n}\n```" for n in range(7, 13))
    out = validate_math_fences(fences, verified=_verified("x = 6"))
    assert VERIFIED_ANSWER_MARKER in out
    for body in out.split("```answer\n")[1:]:
        assert body.startswith(VERIFIED_ANSWER_MARKER), out
    assert "x = 12" in out


def test_a_wrong_value_in_an_untagged_fence_is_corrected_too() -> None:
    """The phone shows an untagged fence's ``x = 7`` as math, so it is a statement."""
    out = validate_math_fences(
        "Subtract 5 and divide by 2.\n\n```\nx = 7\n```", verified=_verified("x = 6")
    )
    assert out.index("The verified answer is $x = 6$.") < out.index(_card("x = 6"))


def test_a_demoted_tex_answer_reads_as_math_not_backslashes() -> None:
    out = validate_math_fences("For this one:\n\n```answer\nx = 2 \\text{ or } x = 3\n```")
    assert "$x = 2 \\text{ or } x = 3$" in out
    assert "```answer" not in out


def test_an_unverified_model_answer_fence_demotes_to_its_value_only() -> None:
    out = validate_math_fences("Weak acid.\n\n```answer\nnotation: chemistry\npH = 2.87\n```")
    assert "```answer" not in out
    assert "notation" not in out
    assert "pH = 2.87" in out


def test_a_follow_up_that_states_the_answer_lands_the_card_in_its_answer_section() -> None:
    """A follow-up ("What if the equation was 3x^2+5=4?") the model answers and the server solved.

    The card used to be withheld when the prose stated the same answer, so the
    model's own Answer section showed in a box with no check.
    """
    from app.core.config import Settings
    from app.modules.math import tools as math_tools

    intent = math_tools.extract_math_intent("solve 3x^2+5=4")
    assert intent is not None
    verified = math_tools._build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    answer = "x = \\pm \\frac{\\sqrt{3}}{3} i"
    reply = (
        "**1. Subtract 5 from both sides**\n$3x^2 = -1$\n\n"
        "**2. Divide both sides by 3**\n$x^2 = -\\frac{1}{3}$\n\n"
        "**Answer**\n$x = \\pm \\sqrt{-\\frac{1}{3}}$\n$x = \\pm \\frac{\\sqrt{3}}{3} i$\n\n"
        "The roots are imaginary because $x^2$ is negative."
    )
    out = validate_math_fences(reply, verified=verified)
    assert out.count(_card(answer)) == 1, out
    assert out.count("**Answer**") == 1
    # The model's final line is the card now, not a second copy above it.
    assert "$x = \\pm \\frac{\\sqrt{3}}{3} i$" not in out
    # Working under the heading stays, above it.
    assert out.index("$x = \\pm \\sqrt{-\\frac{1}{3}}$") < out.index("**Answer**")
    assert out.index(_card(answer)) < out.index("The roots are imaginary")
    assert "The verified answer is" not in out


def test_a_clarifying_question_still_gets_no_card() -> None:
    out = validate_math_fences(
        "Which root do you want, the positive or the negative one?",
        verified=_verified("x = 2 \\text{ or } x = -2"),
    )
    assert "```answer" not in out
