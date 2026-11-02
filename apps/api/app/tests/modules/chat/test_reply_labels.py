"""Each answer is labelled once, whatever the model copied from its history."""

from __future__ import annotations

import pytest

from app.modules.chat.reply_labels import one_answer_label


def test_a_label_under_the_heading_becomes_its_value_in_maths() -> None:
    # A torque follow-up: heading, "Answer: <raw LaTeX>", and the card drew a third label.
    reply = (
        "**Substitution**  \n$\\tau = 70 \\cdot 0.4$\n\n"
        "**Answer**\n\nAnswer: 26.3\\,\\mathrm{N·m}\n\nSince torque is proportional to force."
    )
    assert one_answer_label(reply) == (
        "**Substitution**  \n$\\tau = 70 \\cdot 0.4$\n\n"
        "**Answer**\n\n$26.3\\,\\mathrm{N·m}$\n\nSince torque is proportional to force."
    )


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        # Two headings: the earlier one goes, its value stays as working.
        (
            "**Find**\n$a$\n\n**Answer**\n$a = 3.47$\n\n**Answer**\n\n```answer\n3.47\n```",
            "**Find**\n$a$\n\n$a = 3.47$\n\n**Answer**\n\n```answer\n3.47\n```",
        ),
        # With no card, what is asked makes the reply worked, under either name (Find is
        # an older reply's Required).
        (
            "**Required**\n$a$\n\nAnswer: 3.47\n\n**Answer**\n$a = 3.47$",
            "**Required**\n$a$\n\n3.47\n\n**Answer**\n$a = 3.47$",
        ),
        (
            "**Find**\n$a$\n\nAnswer: 3.47\n\n**Answer**\n$a = 3.47$",
            "**Find**\n$a$\n\n3.47\n\n**Answer**\n$a = 3.47$",
        ),
        # An earlier "Answer: 5 m" keeps its value; the last label stays.
        (
            "**Substitution**\n$x$\n\nAnswer: 5 m\n\n**Answer**\n\n```answer\n5\n```",
            "**Substitution**\n$x$\n\n5 m\n\n**Answer**\n\n```answer\n5\n```",
        ),
    ],
)
def test_a_worked_reply_keeps_only_its_last_label(reply: str, kept: str) -> None:
    assert one_answer_label(reply) == kept


@pytest.mark.parametrize(
    "reply",
    [
        # A quiz labels each question's answer.
        "**Q1.** 2+2?\n**Answer:** 4\n\n**Q2.** 3+3?\n**Answer:** 6",
        # A question in parts keeps one label per part.
        "**Find**\n$t$, $R$\n\n**(a) Time**\n$t = 2$\n\n**Answer (a)**\n\n$t = 2$\n\n"
        "**(b) Range**\n$R = 35$\n\n**Answer (b)**\n\n$R = 35$",
        # Inside a fence nothing is a label.
        "```text\nAnswer: x\nAnswer: y\n```\n\n**Find**\n$x$\n\n**Answer**\n\n$1$",
        # One label already.
        "**Find**\n$a$\n\n**Answer**\n\n```answer\nverified: true\n3.47\n```",
    ],
)
def test_left_as_written(reply: str) -> None:
    assert one_answer_label(reply) == reply


def test_a_law_heading_after_given_reads_as_formula_for_a_checker() -> None:
    from app.services.workout import as_formula_heading

    # A follow-up that changes one given skips Find; its law still heads inputs.
    reply = (
        "**Given**  \n$F = 70$\n\n**Torque**  \n$\\tau = Fd\\sin(\\theta)$\n\n**Answer**\n\n$26.3$"
    )
    assert "**Formula**  \n$\\tau" in as_formula_heading(reply)
    # Prose with no Given or Find keeps its bold lines.
    assert as_formula_heading("**Torque**\n$x$") == "**Torque**\n$x$"
