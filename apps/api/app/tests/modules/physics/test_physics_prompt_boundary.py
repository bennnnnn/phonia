"""Physics prompt policy belongs to physics and never overclaims verification."""

from __future__ import annotations

from app.modules.chat.prompt_constants.solving import VERIFIED_SOLVE_SAFETY_HINT
from app.modules.math.reply_policy import MATH_SOLVER_HINT
from app.modules.physics.prompt import _unverified_physics_note
from app.modules.physics.reply_policy import (
    PHYSICS_INTENT_HINT,
    PHYSICS_REPLY_POLICY,
    PHYSICS_SHORT_HINT,
)
from app.services.solving import VERIFIED_MATH_BEGIN
from app.services.workout import PHYSICS_WORKOUT_PROMPT_SHORT, SELF_CHECK_PROMPT_RULE


def test_physics_prompt_names_its_subject_and_not_math() -> None:
    assert "This is a physics problem" in PHYSICS_INTENT_HINT
    assert "[BEGIN VERIFIED PHYSICS]" in PHYSICS_INTENT_HINT
    assert VERIFIED_MATH_BEGIN not in PHYSICS_INTENT_HINT


def test_math_prompt_contains_no_physics_policy() -> None:
    lower = MATH_SOLVER_HINT.lower()
    assert "physics" not in lower
    assert "projectile" not in lower
    assert "simulation" not in lower


def test_physics_prompt_cannot_claim_an_unverified_result() -> None:
    lower = PHYSICS_INTENT_HINT.lower()
    assert "if no verified block is present, do not claim verification" in lower  # safety phrase
    assert "never end on that heading" in lower
    assert "do not recompute" in lower


def test_unverified_physics_note_must_finish_the_answer() -> None:
    note = _unverified_physics_note()
    assert "finish under Answer" in note
    assert "Never end on the Answer heading" in note
    assert "solve only one fragment" not in note
    assert "Compute the result and write it under Answer." in note
    # Unverified working checks itself before its Answer.
    assert note.rstrip().endswith(SELF_CHECK_PROMPT_RULE)


def test_physics_working_contract_is_explicit_and_ordered() -> None:
    for policy in (PHYSICS_INTENT_HINT, PHYSICS_REPLY_POLICY):
        # The law's own name heads the formulas, between Required and Substitution.
        sections = ("Given", "**Required**", "Constant acceleration", "Substitution")
        positions = [policy.index(name) for name in sections]
        assert positions == sorted(positions)
        assert "Answer" in policy
    assert "governing law's name" in PHYSICS_REPLY_POLICY
    # The law's own name heads its formulas; a converted given keeps one line.
    for policy in (PHYSICS_INTENT_HINT, PHYSICS_REPLY_POLICY):
        assert PHYSICS_WORKOUT_PROMPT_SHORT in policy
        assert PHYSICS_WORKOUT_PROMPT_SHORT in policy
    assert "each value or equation on its own" in PHYSICS_REPLY_POLICY


def test_physics_prompt_forbids_model_authored_result_fences() -> None:
    for language in ("answer", "graph", "simulation", "geometry"):
        assert f"```{language}" in PHYSICS_INTENT_HINT
        assert f"```{language}" in PHYSICS_SHORT_HINT


def test_universal_verification_rule_lives_in_neutral_prompt_layer() -> None:
    lower = VERIFIED_SOLVE_SAFETY_HINT.lower()
    assert "verified" in lower
    assert "never claim" in lower
    assert "physics" not in lower
    assert "math" not in lower


def test_subject_prompt_budgets_remain_small() -> None:
    assert len(PHYSICS_INTENT_HINT) <= 1200
    assert len(PHYSICS_REPLY_POLICY) <= 900
