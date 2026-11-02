"""A named compound's structure is drawn from PubChem, never written by the model."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.gateways.pubchem_gateway import PubChemCompound, PubChemResult
from app.modules.chemistry.block import verified_structure
from app.modules.chemistry.context import build_chemistry_augmentation
from app.modules.chemistry.direct import format_direct_chemistry_reply

_CAFFEINE = PubChemCompound(
    cid=2519,
    name="caffeine",
    smiles="CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    molecular_formula="C8H10N4O2",
    molecular_weight=194.19,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "show me the structure of caffeine",
        "draw caffeine",
        "structure of caffeine",
        "can you show me caffeine's molecule",
    ],
)
async def test_a_structure_ask_is_verified_with_pubchems_smiles(message: str) -> None:
    lookup = AsyncMock(return_value=PubChemResult(compound=_CAFFEINE, error=None))
    with (
        patch("app.modules.chemistry.context.pubchem_gateway.lookup_by_name", lookup),
        patch("app.modules.chemistry.context.extract_compound_name", return_value="caffeine"),
    ):
        _text, verified, declined = await build_chemistry_augmentation(message, Settings())
    assert verified is not None and not declined
    assert verified.result.structure_smiles == _CAFFEINE.smiles


@pytest.mark.asyncio
async def test_a_question_about_a_compound_stays_context() -> None:
    lookup = AsyncMock(return_value=PubChemResult(compound=_CAFFEINE, error=None))
    with (
        patch("app.modules.chemistry.context.pubchem_gateway.lookup_by_name", lookup),
        patch("app.modules.chemistry.context.extract_compound_name", return_value="caffeine"),
    ):
        text, verified, _ = await build_chemistry_augmentation("what is caffeine", Settings())
    assert verified is None
    assert text is not None and "Canonical SMILES" in text


def test_the_structure_reply_is_one_line_and_the_drawing() -> None:
    reply = format_direct_chemistry_reply(
        verified_structure("caffeine", _CAFFEINE.smiles, "C8H10N4O2", 194.19)
    )
    assert reply.startswith("Structure of caffeine, from PubChem:\n\n```smiles\n")
    assert "**Given**" not in reply and "$" not in reply
    assert "```answer" not in reply


def test_the_model_is_told_not_to_write_the_structure() -> None:
    verified = verified_structure("caffeine", _CAFFEINE.smiles, "C8H10N4O2", 194.19)
    assert "Do not write SMILES" in verified.prompt_text
    assert verified.canonical_answer == ""
