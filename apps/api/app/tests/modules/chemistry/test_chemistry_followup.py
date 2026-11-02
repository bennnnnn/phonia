"""A short line after a chemistry problem replays that problem, or declines."""

import pytest

from app.modules.chat.continuation_subject import effective_presentation_subject
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.followup import chemistry_followup_problem
from app.modules.chemistry.solvers import solve_chemistry

_ACID = "What is the pH of 0.010 M HCl?"
_KA = "Ka = 1.8e-5. Find Kb."
_TWO = "What is the pH of 0.010 M HCl mixed with 0.020 M NaCl?"


def _recent(problem: str) -> list[tuple[str, str]]:
    return [("user", problem), ("assistant", "Here is the working.")]


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    return None if intent is None else solve_chemistry(intent).answer


def test_an_explanation_replays_the_previous_problem() -> None:
    for line in (
        "why is it 3.60",
        "I didn't get it",
        "help me understand it",
        "that's confusing",
    ):
        assert chemistry_followup_problem(line, _recent(_ACID)) == _ACID


def test_an_explanation_after_chemistry_keeps_the_chemistry_contract() -> None:
    prior = [("user", _ACID), ("assistant", "pH = 2.00")]
    assert effective_presentation_subject("why is it 3.60", prior) == "chemistry"


def test_another_quantity_keeps_the_givens_and_changes_the_ask() -> None:
    rewritten = chemistry_followup_problem("what about the pKa", _recent(_KA))
    assert rewritten == "Ka = 1.8e-5. Find the pKa."
    assert _answer(rewritten) is not None
    assert "pKa" in (_answer(rewritten) or "")


def test_an_ask_the_givens_cannot_answer_declines() -> None:
    assert chemistry_followup_problem("what about the pOH", _recent(_ACID)) is None
    assert chemistry_followup_problem("what about the kinetic energy", _recent(_ACID)) is None


def test_one_changed_given_is_replaced_and_resolved() -> None:
    rewritten = chemistry_followup_problem("but if it was 0.020 M", _recent(_ACID))
    assert rewritten == "What is the pH of 0.020 M HCl?"
    assert _answer(rewritten) == "pH = 1.70"


def test_a_named_replacement_uses_that_quantity() -> None:
    rewritten = chemistry_followup_problem("if the concentration is 0.020 M", _recent(_ACID))
    assert rewritten is not None and _answer(rewritten) == "pH = 1.70"


def test_two_possible_replacements_decline() -> None:
    assert chemistry_followup_problem("if the concentration is 0.020 M", _recent(_TWO)) is None


def test_a_new_problem_is_not_a_followup() -> None:
    fresh = "What is the pH of 0.020 M HCl?"
    assert chemistry_followup_problem(fresh, _recent(_ACID)) is None


def test_a_followup_after_a_non_chemistry_turn_declines() -> None:
    recent = [("user", "Solve 2x + 3 = 11"), ("assistant", "x = 4")]
    assert chemistry_followup_problem("why is it 4", recent) is None


@pytest.mark.parametrize(
    ("line", "answer"),
    [
        ("what if the concentration doubles", "pH = 1.70"),
        ("and 0.001 M?", "pH = 3.00"),
    ],
)
def test_chemistry_followup_scales_or_replaces_the_one_given(line: str, answer: str) -> None:
    rewritten = chemistry_followup_problem(line, _recent(_ACID))
    assert rewritten is not None
    assert _answer(rewritten) == answer


@pytest.mark.parametrize("line", ["show steps", "explain it", "walk me through it"])
def test_chemistry_followup_asks_for_working_replay_the_problem(line: str) -> None:
    assert chemistry_followup_problem(line, _recent(_ACID)) == _ACID


def test_chemistry_followup_two_concentrations_do_not_scale() -> None:
    assert chemistry_followup_problem("what if the concentration doubles", _recent(_TWO)) is None
