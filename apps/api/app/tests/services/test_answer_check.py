"""Reading the model's own final value against the verified answer, as numbers."""

from __future__ import annotations

import pytest

from app.services.answer_check import (
    asks_without_answering,
    correction_line,
    read_verified_value,
    stated_verdict,
)

_STEPS_7 = (
    "**1. Subtract 5 from both sides**\n$2x + 5 - 5 = 17 - 5$\n$2x = 14$\n\n"
    "**2. Divide both sides by 2**\n$x = 7$\n\nEach move keeps both sides equal."
)
_PROJECTILE_WORK = (
    "**Given**  \n$v_0 = 20\\ \\text{m/s}$  \n$\\theta = 30^\\circ$\n\n**Find**  \n$R$\n\n"
    "**Formula**  \n$R = \\frac{v_0^2 \\sin 2\\theta}{g}$\n\n**Substitution**  \n"
    "$R = \\frac{20^2 \\sin 60^\\circ}{9.81}$\n\n**Answer**  \n"
)


@pytest.mark.parametrize(
    ("answer", "prose", "verdict"),
    [
        # A different final value, by number, set, or digits a substring would accept.
        ("x = 6", _STEPS_7, "conflict"),
        ("x = 6", "Subtract 5 to get 2x = 14, then divide by 2, so x = 7.", "conflict"),
        ("x = 6", "It gives $x = 6$, but no: $2x = 13$, so $x = 6.5$.", "conflict"),
        ("12.75", "**Answer**  \n$12.25$", "conflict"),
        ("12.75", "**Answer**  \n$12.755$", "conflict"),
        ("12.75", "15% of 85 is $112.75$.", "conflict"),
        ("12.75", "15% of 85 is $12.25$. Want the 10% + 5% shortcut?", "conflict"),
        ("x = 2 \\text{ or } x = 3", "so $x = 3$.", "conflict"),
        ("x = 2 \\text{ or } x = 3", "so $x = -2$ or $x = -3$.", "conflict"),
        ("x = \\frac{7}{2}", "The steps give $x = 4$.", "conflict"),
        ("35.3\\,\\mathrm{m}", _PROJECTILE_WORK + "$R = 20.4\\ \\text{m}$", "conflict"),
        ("35.3\\,\\mathrm{m}", "So $R = 35.3\\ \\text{km}$.", "conflict"),
        ("notation: chemistry\npH = 2.00", "so [H⁺] = 0.1 M, which gives pH = 1.00.", "conflict"),
        ("3.97 \\times 10^{-19}\\,\\mathrm{J}", "So E = 3.97 × 10^{-18} J.", "conflict"),
        # The same answer, however it is spelled.
        ("x = 6", "**2. Divide by 2**\n$x = 12/2 = 6$\n\nCheck: $2*6 + 5 = 17$", "same"),
        ("x = 6", "Divide by 2: $x = 6.0$.\n\nWant to try a harder one?", "same"),
        ("x = 2 \\text{ or } x = 3", "so $x = 2$ or $x = 3$.", "same"),
        ("x = 2 \\text{ or } x = 3", "So x = 2 or 3.", "same"),
        ("x = -2 \\text{ or } x = 2", "So $x = \\pm 2$.", "same"),
        ("x = \\frac{1}{2}", "Dividing both sides gives $x = 0.5$.", "same"),
        ("0.25", "The probability is $\\frac{1}{4}$.", "same"),
        ("35.3\\,\\mathrm{m}", _PROJECTILE_WORK + "$R = 35.3\\ \\text{m}$", "same"),
        ("35.31 m", "The range is about 35.31 m. Would you like the maximum height?", "same"),
        ("notation: chemistry\npH = 2.00", "pH = 2 for a strong acid.", "same"),
        ("notation: chemistry\nEa = 55 kJ/mol", "Ea = 5.5 × 10⁴ J/mol", "same"),
        ("3.97 \\times 10^{-19}\\,\\mathrm{J}", "So E = 3.97e-19 J.", "same"),
        ("9.81\\,\\mathrm{m/s^{2}}", "So $a = 9.81\\ \\text{m/s}^2$.", "same"),
        ("1500", "The answer is 1,500.", "same"),
        # A coarser rounding: the card shows, nothing is corrected.
        ("12.75", "15% of 85 is $12.8$.", "rounded"),
        ("9.81\\,\\mathrm{m/s^{2}}", "So $a = 9.8\\ \\text{m/s}^2$.", "rounded"),
        # Nothing stated, or nothing comparable.
        ("x = 6", "First $2x = 4$. Then divide.", "absent"),
        ("2", "Consider $x^2$ for this problem.", "absent"),
        (
            "35.31 m",
            "Which ball's path is at **30°** — the **2 kg** or the **1 kg** ball?",
            "absent",
        ),
        (
            "30\\,\\mathrm{W}",
            "**Given**  \n$v = 3\\,\\mathrm{m/s}$  \n$F = 10\\,\\mathrm{N}$\n\n**Answer**",
            "absent",
        ),
        ("notation: chemistry\nm(H₂O) = 36 g", "**Given**  \nM(H₂O) = 18.015 g/mol", "absent"),
        ("26.85 °C", "T = 300 K", "absent"),
        # A multiple of x in the working is not a value for x (a server lesson).
        (
            "x = 2.0",
            "**Required**  \n$x = ?$\n\n**1. Subtract**  \n$0.4 x = 0.8$\n\n**Answer**",
            "absent",
        ),
        # What is asked restates the problem under either name; it states no result.
        ("x = 7", "**Required**  \n$x = 6$\n\nWork below.", "absent"),
        ("x = 7", "**Find**  \n$x = 6$\n\nWork below.", "absent"),
        ("x = 6", "$2 x = 12$ then divide.", "absent"),
        # Not a plain value: the callers keep their string checks.
        (
            "x^{2} \\left(x \\cos{\\left(x \\right)} + 3 \\sin{\\left(x \\right)}\\right)",
            "x",
            "unknown",
        ),
        ("x = 2, y = 3", "x = 2, y = 3", "unknown"),
    ],
)
def test_stated_verdict(answer: str, prose: str, verdict: str) -> None:
    assert stated_verdict(prose, answer) == verdict


@pytest.mark.parametrize("heading", ["Required", "Find"])
def test_a_find_placeholder_is_not_a_question(heading: str) -> None:
    reply = f"**{heading}**  \n$x = ?$\n\nWork below."
    assert asks_without_answering(reply, "x = 6") is False


@pytest.mark.parametrize(
    ("prose", "asks"),
    [
        ("Is the collision elastic or inelastic?", True),
        ("**Which ball's final path is at 30°?**", True),
        ("The range is 35.3 m. Want the max height too?", False),
        ("The range is 20.4 m. Want the max height too?", False),
        ("Let me set that up using the range equation.", False),
    ],
)
def test_asks_without_answering(prose: str, asks: bool) -> None:
    assert asks_without_answering(prose, "35.3 m") is asks


def test_asks_without_answering_defers_on_expressions() -> None:
    assert asks_without_answering("Which form do you want?", "x^{2} + 1") is None


def test_a_product_with_a_variable_is_not_a_value_with_a_unit() -> None:
    assert read_verified_value("x = 55555.5555555556 K a") is None
    value = read_verified_value("35.3 m")
    assert value is not None and value.numbers[0].unit == "m"


def test_read_verified_value_keeps_the_label_case() -> None:
    value = read_verified_value("notation: chemistry\nM(H2O) = 18.02 g/mol")
    assert value is not None and value.label == "M(H2O)"


def test_an_approximate_verified_answer_is_read_as_its_value() -> None:
    """Newton's card says x ≈ 1.41421: a wrong value still gets the correction line."""
    value = read_verified_value("x \\approx 1.41421")
    assert value is not None and value.label == "x"
    assert stated_verdict("The root is $x = 1.5$.", "x \\approx 1.41421") == "conflict"
    assert asks_without_answering("$x = 1.41421$.\nWant the steps?", "x \\approx 1.41421") is False


def test_correction_lines() -> None:
    assert correction_line("x = 6") == "The verified answer is $x = 6$."
    assert correction_line("notation: chemistry\npH = 2.00") == "The verified answer is pH = 2.00."
    assert correction_line("verified: true\nx = 6") == "The verified answer is $x = 6$."


@pytest.mark.parametrize(
    "prose",
    ["Work it through step by step. So:", "The answer is:", "**Answer:**", "So $R =$"],
)
def test_a_sentence_that_ends_before_its_value_states_nothing(prose: str) -> None:
    # An empty segment after "is:" used to raise and drop the verified card.
    assert stated_verdict(prose, "35.3\\,\\mathrm{m}") == "absent"


_RANGE = "verified: true\nR = 62.7\\,\\mathrm{m}"
_SPEED = "verified: true\nv = 19.8\\,\\mathrm{m/s}"


@pytest.mark.parametrize(
    ("answer", "prose", "verdict"),
    [
        # A result said without "=", in the verified answer's unit, is compared.
        (_RANGE, "The ball lands about 70.6 m out.", "conflict"),
        (_RANGE, "The ball lands about 62.7 m out.", "same"),
        (_RANGE, "It lands 6270 cm away.", "same"),
        (_SPEED, "The ball hits the ground at about 25 m/s.", "conflict"),
        (_SPEED, "So it hits the ground at 19.8 m/s.", "same"),
        # A given after "from" is not the result; the later statement is.
        (_RANGE, "It falls from 20 m and lands about 62.7 m away.", "same"),
        (_RANGE, "It is thrown from about 20 m high.", "absent"),
        # Another quantity's unit, or no unit, is not this answer.
        (_RANGE, "It takes 3.2 s to land.", "absent"),
        ("verified: true\nx = 6", "The answer lands on 7.", "absent"),
    ],
)
def test_stated_verdict_reads_a_result_said_without_equals(
    answer: str, prose: str, verdict: str
) -> None:
    assert stated_verdict(prose, answer) == verdict
