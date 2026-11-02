"""Subject registry: one owner per turn, chemistry on the shared solve block."""

from __future__ import annotations

import typing
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.modules.chemistry.block import VerifiedChemistry
from app.services.solving import VerifiedSolveBlock
from app.services.subjects.dispatch import (
    build_subject_augmentation,
    detect_subject,
    maybe_direct_subject_reply,
)
from app.services.subjects.registry import SUBJECTS, SubjectName, subject_adapter


def test_the_registry_holds_one_adapter_per_subject_name() -> None:
    names = [adapter.name for adapter in SUBJECTS]
    assert len(set(names)) == len(names)
    assert set(names) == set(typing.get_args(SubjectName))
    for name in typing.get_args(SubjectName):
        assert subject_adapter(name).name == name


def test_the_subject_literals_are_the_registrys_names() -> None:
    from app.modules.model_reader.schemas import Subject
    from app.services.subject_scan import ScannerSubject

    names = set(typing.get_args(SubjectName))
    assert set(typing.get_args(Subject)) == {*names, "none"}
    scanned = {arg for part in typing.get_args(ScannerSubject) for arg in typing.get_args(part)}
    assert scanned == {*names, "biology"}


def test_image_extract_is_math_before_any_peer() -> None:
    from app.modules.math.schemas import MathImageExtract

    extract = MathImageExtract(lhs="2x+3", rhs="11")
    assert (
        detect_subject(
            "Find Gibbs free energy when delta H=-40 kJ, delta S=-100 J and T=300 K",
            image_math_extract=extract,
        )
        == "math"
    )


def test_physics_wins_over_math() -> None:
    assert detect_subject("find the force on a 2 kg mass accelerating at 3 m/s^2") == "physics"


def test_closed_chemistry_wins_over_algebra_lookalike() -> None:
    text = "Find Gibbs free energy when delta H=-40 kJ, delta S=-100 J and T=300 K"
    assert detect_subject(text) == "chemistry"


def test_chemistry_lookup_runs_when_no_peer_claims() -> None:
    assert detect_subject("IUPAC name of SMILES CCO") == "chemistry"


def test_disabled_chemistry_does_not_claim_a_lookup() -> None:
    assert detect_subject("IUPAC name of SMILES CCO", chemistry_enabled=False) is None


@pytest.mark.asyncio
async def test_closed_chemistry_does_not_also_solve_as_math() -> None:
    text = "Find Gibbs free energy when delta H=-40 kJ, delta S=-100 J and T=300 K"
    with patch(
        "app.modules.math.subject.build_math_augmentation",
        AsyncMock(side_effect=AssertionError("math must not run")),
    ):
        result = await build_subject_augmentation(text, Settings(chemistry_enabled=True))
    assert result.subject == "chemistry"
    assert isinstance(result.verified, VerifiedChemistry)
    assert isinstance(result.verified, VerifiedSolveBlock)
    assert result.verified.canonical_answer == "ΔG = -10 kJ/mol"
    reply = maybe_direct_subject_reply(result.verified, text)
    assert reply is not None
    assert reply.count("```answer") == 1
    assert "notation: chemistry\nΔG = −10 kJ/mol" in reply
    assert "✅" not in reply
    assert result.unverified is False


@pytest.mark.asyncio
async def test_no_subject_does_not_force_the_math_solver() -> None:
    text = "What should I cook for dinner tonight"
    with patch(
        "app.modules.math.subject.build_math_augmentation",
        AsyncMock(side_effect=AssertionError("math must not run")),
    ):
        result = await build_subject_augmentation(
            text,
            Settings(math_tools_enabled=True),
            math_user_content=text,
            detected_subject=None,
        )
    assert result.subject is None
    assert result.prompt_block is None
    assert result.verified is None
    assert result.unverified is False


@pytest.mark.asyncio
async def test_uncovered_physics_keeps_the_prompt_note_and_not_a_failed_check() -> None:
    text = "binding energy of He-4, mass = 4.002603 u"
    result = await build_subject_augmentation(text, Settings(math_tools_enabled=True))
    assert result.subject == "physics"
    assert result.verified is None
    assert result.unverified is False
    assert result.prompt_block is not None
    assert result.prompt_block.startswith("Physics note:")


@pytest.mark.asyncio
async def test_symbolic_drag_fall_is_verified_not_a_failed_check() -> None:
    text = (
        "A particle of mass m is dropped from rest in a fluid. "
        "Drag is F = -kv. Solve v(t), the terminal velocity as t goes to infinity, "
        "and the limit as k goes to 0."
    )
    result = await build_subject_augmentation(text, Settings(math_tools_enabled=True))
    assert result.subject == "physics"
    assert result.verified is not None
    assert result.unverified is False
    assert result.prompt_block is not None
    assert r"\frac{mg}{k}" in result.prompt_block
    assert r"v_{T}" in result.prompt_block
    assert r"\lim_{k\to 0}v(t)=gt" in result.prompt_block
    assert "I couldn't automatically verify" not in result.prompt_block


@pytest.mark.asyncio
async def test_a_failed_physics_solve_is_still_unverified() -> None:
    text = "A ball is dropped from 20 m. How long until it hits the ground?"

    with patch("app.modules.physics.prompt._build_physics_block", return_value=None):
        result = await build_subject_augmentation(text, Settings(math_tools_enabled=True))
    assert result.subject == "physics"
    assert result.verified is None
    assert result.unverified is True


@pytest.mark.asyncio
async def test_chemistry_decline_is_flagged_and_element_context_is_not() -> None:
    settings = Settings(chemistry_enabled=True)
    declined = await build_subject_augmentation(
        "hydroxide substitution of SMILES CC(Cl)C",
        settings,
    )
    assert declined.verified is None
    assert declined.unverified is True
    assert declined.prompt_block is not None
    assert declined.prompt_block.startswith("Chemistry note:")

    element = await build_subject_augmentation(
        "what is the atomic mass of Fe?",
        settings,
    )
    assert element.verified is None
    assert element.unverified is False
    assert element.prompt_block is not None
    assert "Verified element data" in element.prompt_block


@pytest.mark.asyncio
async def test_fetch_returns_the_adapter_decline_flag() -> None:
    from app.modules.chat.prompt_builder import fetch_subject
    from app.services.solving import SubjectAugmentation

    settings = Settings(math_tools_enabled=True, web_search_enabled=False)
    with patch(
        "app.modules.chat.prompt_builder.build_subject_augmentation",
        AsyncMock(
            return_value=SubjectAugmentation("physics", "Physics note: declined", None, True)
        ),
    ):
        block, verified, declined, unverified_subject, _direct = await fetch_subject(
            "binding energy of He-4, mass = 4.002603 u", settings
        )
    assert block == "Physics note: declined"
    assert verified is None
    assert declined is True
    assert unverified_subject == "physics"


@pytest.mark.asyncio
async def test_chemistry_followup_solves_the_prior_problem() -> None:
    from app.modules.chat.prompt_builder import fetch_subject

    settings = Settings(chemistry_enabled=True, web_search_enabled=False, math_tools_enabled=True)
    prior = "Find the molar mass of H2O"
    _block, verified, declined, _subject, _direct = await fetch_subject(
        "how?", settings, chemistry_followup_problem=prior
    )
    assert declined is False
    assert verified is not None
    assert verified.subject == "chemistry"
    assert "18.02" in verified.text


@pytest.mark.asyncio
async def test_two_problems_joined_by_and_also_are_both_verified() -> None:
    settings = Settings(chemistry_enabled=True, math_tools_enabled=True, web_search_enabled=False)
    question = "Dilute 10 mL of 2 M HCl to 0.5 M, and also solve x^2 - 5x + 6 = 0."
    result = await build_subject_augmentation(question, settings)
    assert result.unverified is False
    assert result.direct_text is not None
    assert "40 mL" in result.direct_text
    assert "x = 2" in result.direct_text
    assert "x = 3" in result.direct_text
    assert "couldn't automatically verify" not in result.direct_text
